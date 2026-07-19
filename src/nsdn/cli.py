"""NSDN CLI entry point."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from nsdn.db import Database
from nsdn.delivery import run_delivery
from nsdn.extract import run_extract
from nsdn.filter import run_filter
from nsdn.llm import create_provider
from nsdn.loader import load_config
from nsdn.render import render_directory, render_markdown
from nsdn.serve import run_serve
from nsdn.summarizers import run_summarize
from nsdn.synthesize import run_synthesize
from nsdn.vector import VectorStore

logger = logging.getLogger(__name__)


@click.group()
@click.option("-c", "--config", type=click.Path(), default=None, help="Path to config file.")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx, config, verbose):
    """NSDN — No Social Detox News."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config)


@cli.command()
@click.pass_context
def extract(ctx):
    """Extract entries from all configured sources."""
    config = ctx.obj["config"]
    db = Database()
    vector = VectorStore(config.weaviate) if config.weaviate.enabled else None

    try:
        stats = run_extract(config, db, vector)
        for name, count in stats.items():
            click.echo(f"  {name}: {count} new entries")
        click.echo(f"Total: {sum(stats.values())} entries extracted")
    finally:
        db.close()
        if vector:
            vector.close()


@cli.command()
@click.pass_context
def filter(ctx):
    """Score and filter entries."""
    config = ctx.obj["config"]
    db = Database()
    llm = create_provider(config.llm, model_name="filter")

    try:
        result = run_filter(config, db, llm)
        click.echo(f"Scored: {result['scored']}, Kept: {result['kept']}")
    finally:
        db.close()


@cli.command()
@click.pass_context
def summarize(ctx):
    """Generate summaries for entries with long content."""
    config = ctx.obj["config"]
    db = Database()
    llm = create_provider(config.llm, model_name="summarize")

    try:
        result = run_summarize(config, db, llm)
        click.echo(f"Summarized: {result['summarized']}, Skipped: {result['skipped']}")
    finally:
        db.close()


@cli.command()
@click.pass_context
def synthesize(ctx):
    """Cluster and write journal edition."""
    config = ctx.obj["config"]
    db = Database()
    llm = create_provider(config.llm, model_name="synthesize")

    try:
        result = run_synthesize(config, db, llm)
        if result.get("entries", 0) == 0:
            click.echo("No entries to synthesize")
        elif result.get("md_file"):
            click.echo(f"Markdown: {result['md_file']}")
            click.echo(f"HTML:     {result['html_file']}")
            click.echo(f"Entries:  {result['entries']}, Sections: {result['sections']}")
        elif result.get("files"):
            click.echo(f"Entries:  {result['entries']}, Topics: {result.get('topics', 0)}, Files: {len(result['files'])}")
            for f in result["files"]:
                click.echo(f"  {f}")
    finally:
        db.close()


@cli.command()
@click.option("-f", "--file", type=click.Path(exists=True), required=True, help="Markdown file to render.")
@click.pass_context
def render(ctx, file):
    """Render a Markdown file to HTML."""
    config = ctx.obj["config"]
    md_path = Path(file)
    html_path = render_markdown(config, md_path)
    click.echo(f"Rendered: {html_path}")


@cli.command()
@click.pass_context
def render_all(ctx):
    """Render all Markdown files in the output directory."""
    config = ctx.obj["config"]
    rendered = render_directory(config)
    click.echo(f"Rendered {len(rendered)} files")


@cli.command()
@click.option("-p", "--port", default=8080, help="Port to serve on.")
@click.option("-d", "--directory", default=None, help="Directory to serve (defaults to config output dir).")
@click.pass_context
def serve(ctx, port, directory):
    """Serve the output directory as a static site."""
    config = ctx.obj["config"]
    dir_path = directory or config.output.directory
    run_serve(dir_path, port=port)


@cli.command()
@click.option("--deliver", is_flag=True, help="Deliver edition after synthesis.")
@click.pass_context
def run(ctx, deliver):
    """Run the full pipeline: extract → summarize → filter → synthesize."""
    config = ctx.obj["config"]
    db = Database()
    vector = VectorStore(config.weaviate) if config.weaviate.enabled else None

    try:
        click.echo("=== Extract ===")
        stats = run_extract(config, db, vector)
        for name, count in stats.items():
            click.echo(f"  {name}: {count} new entries")

        click.echo("\n=== Summarize ===")
        sum_llm = create_provider(config.llm, model_name="summarize")
        sum_result = run_summarize(config, db, sum_llm)
        click.echo(f"  Summarized: {sum_result['summarized']}, Skipped: {sum_result['skipped']}")

        click.echo("\n=== Filter ===")
        filter_llm = create_provider(config.llm, model_name="filter")
        filter_result = run_filter(config, db, filter_llm)
        click.echo(f"  Scored: {filter_result['scored']}, Kept: {filter_result['kept']}")

        click.echo(f"\n=== Synthesize (mode={config.synthesize.mode}) ===")
        synth_llm = create_provider(config.llm, model_name="synthesize")
        synth_result = run_synthesize(config, db, synth_llm)
        if config.synthesize.mode == "design":
            if synth_result.get("files"):
                for f in synth_result["files"]:
                    click.echo(f"  Output: {f}")
            else:
                click.echo("  No entries to design")
        elif synth_result.get("md_file"):
            click.echo(f"  Markdown: {synth_result['md_file']}")
            click.echo(f"  HTML:     {synth_result['html_file']}")
        else:
            click.echo("  No entries to synthesize")

        # Delivery
        if deliver and config.delivery.enabled:
            click.echo("\n=== Deliver ===")
            edition_dir = synth_result.get("edition_dir")
            if edition_dir:
                results = run_delivery(config, Path(edition_dir))
                for r in results:
                    status = "OK" if r.success else "FAIL"
                    click.echo(f"  [{status}] {r.target_label}: {r.message}")
            else:
                click.echo("  No edition to deliver")
    finally:
        db.close()
        if vector:
            vector.close()


@cli.command()
@click.option("--edition", type=click.Path(exists=True), default=None,
              help="Path to edition directory to deliver. Defaults to latest edition.")
@click.pass_context
def deliver(ctx, edition):
    """Deliver a previously generated edition."""
    config = ctx.obj["config"]

    if not config.delivery.enabled:
        click.echo("Delivery is not enabled in config")
        return

    # Resolve edition directory
    edition_path = Path(edition) if edition else _latest_edition_dir(config)
    if not edition_path or not edition_path.is_dir():
        click.echo(f"No edition found at: {edition_path}")
        return

    click.echo(f"Delivering: {edition_path.name}")
    results = run_delivery(config, edition_path)
    for r in results:
        status = "OK" if r.success else "FAIL"
        click.echo(f"  [{status}] {r.target_label}: {r.message}")


def _latest_edition_dir(config) -> Path | None:
    """Find the most recent edition directory."""
    output_dir = Path(config.output.directory)
    if not output_dir.is_dir():
        return None
    editions = sorted(
        (d for d in output_dir.iterdir() if d.is_dir() and d.name[0:4].isdigit()),
        key=lambda d: d.name,
    )
    return editions[-1] if editions else None


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate all configured sources."""
    config = ctx.obj["config"]
    from nsdn.sources import get_source

    for src_cfg in config.sources:
        source_class = get_source(src_cfg.type)
        source = source_class(src_cfg.name, src_cfg.config)
        ok = source.validate()
        status = "OK" if ok else "FAILED"
        click.echo(f"  [{status}] {src_cfg.name} ({src_cfg.type})")


if __name__ == "__main__":
    cli()
