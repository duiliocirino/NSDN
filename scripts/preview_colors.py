#!/usr/bin/env python3
"""Preview current newspaper color configuration."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nsdn.loader import load_config


def main():
    config_path = Path("config/nsdn.yaml")
    if not config_path.exists():
        print(f"Error: Config not found at {config_path}")
        sys.exit(1)

    config = load_config(config_path)
    colors = config.newspaper.colors

    # Generate preview HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>NSDN Color Preview</title>
    <style>
        :root {{
            --color-text: {colors["text"]};
            --color-text-muted: {colors["text-muted"]};
            --color-border: {colors["border"]};
            --color-border-light: {colors["border-light"]};
            --color-accent: {colors["accent"]};
        }}
        body {{ font-family: system-ui, sans-serif; padding: 2rem; background: #f5f5f5; color: var(--color-text); }}
        h1 {{ margin-bottom: 1rem; }}
        p {{ color: var(--color-text-muted); margin-bottom: 2rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1.5rem; }}
        .swatch {{
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .color-box {{
            height: 100px;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 1.1rem;
            text-shadow: 0 1px 2px rgba(0,0,0,0.2);
        }}
        .info {{ padding: 1rem; }}
        .info h3 {{ margin: 0 0 0.5rem; font-size: 1rem; color: var(--color-text); }}
        .info code {{ display: block; background: #eee; padding: 0.4rem; border-radius: 4px; font-family: monospace; font-size: 0.9rem; word-break: break-all; }}
        .preview {{ margin-top: 2rem; background: white; padding: 1.5rem; border-radius: 8px; border-top: 4px solid var(--color-accent); }}
        .preview h2 {{ color: var(--color-text); border-bottom: 1px solid var(--color-border-light); padding-bottom: 0.5rem; }}
        .preview a {{ color: var(--color-accent); text-decoration: none; }}
        .preview a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1>NSDN Color Preview</h1>
    <p>Current palette from <code>config/nsdn.yaml</code>. Edit the config and re-run this script to update.</p>
    
    <div class="grid">
        <div class="swatch">
            <div class="color-box" style="background: var(--color-text); color: white;">Text</div>
            <div class="info"><h3>text</h3><code>{colors['text']}</code></div>
        </div>
        <div class="swatch">
            <div class="color-box" style="background: var(--color-text-muted); color: white;">Muted</div>
            <div class="info"><h3>text-muted</h3><code>{colors['text-muted']}</code></div>
        </div>
        <div class="swatch">
            <div class="color-box" style="background: var(--color-border); color: white;">Border</div>
            <div class="info"><h3>border</h3><code>{colors['border']}</code></div>
        </div>
        <div class="swatch">
            <div class="color-box" style="background: var(--color-border-light); color: black;">Light</div>
            <div class="info"><h3>border-light</h3><code>{colors['border-light']}</code></div>
        </div>
        <div class="swatch">
            <div class="color-box" style="background: var(--color-accent); color: white;">Accent</div>
            <div class="info"><h3>accent</h3><code>{colors['accent']}</code></div>
        </div>
    </div>

    <div class="preview">
        <h2>Live Preview</h2>
        <p style="color: var(--color-text);">This is how your text will look. <a href="#">This is a sample link using the accent color.</a></p>
        <hr style="border: 0; border-top: 1px solid var(--color-border-light);">
        <p style="color: var(--color-text-muted);">This is muted text, typically used for secondary information like dates or summaries.</p>
    </div>
</body>
</html>
"""

    output_path = Path("output/journal/color_preview.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(f"✓ Generated {output_path}")
    print(f"  Open in browser: file://{output_path.resolve()}")


if __name__ == "__main__":
    main()
