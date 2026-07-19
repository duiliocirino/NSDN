# Delivery System Design

## Overview

Automated delivery of generated editions to external channels (Telegram, email). Enables "set and forget" — editions reach the user without manual intervention.

## Architecture

```
Synthesize (design mode)
       │
       ▼
  Edition output dir
  ├── edition.pdf
  ├── edition-mobile.pdf
  └── topics/
       │
       ▼
  DeliveryBuilder.build_payload()
       │
       ├──► TelegramDelivery.deliver()  ──► Telegram Bot API
       ├──► EmailDelivery.deliver()     ──► SMTP / SendGrid / Mailgun
       └──► (future targets via registry)
```

## Registry Pattern

Consistent with existing extension points (`EntrySource`, `PageDesigner`, `ClusterStrategy`, etc.).

**`delivery/__init__.py`** — registry + auto-registration:

```python
DELIVERY_REGISTRY: dict[str, type[DeliveryTarget]] = {}

def register_delivery(name: str, cls: type[DeliveryTarget]) -> None: ...
def get_delivery(name: str) -> type[DeliveryTarget]: ...

# Auto-register by importing implementations
import nsdn.delivery.telegram  # noqa: F401  (registers "telegram")
import nsdn.delivery.email     # noqa: F401  (registers "email")
```

## Configuration

### YAML format — follows existing `SourceConfig` pattern

Targets use `type` + `config` dict, matching how sources are configured:

```yaml
delivery:
  enabled: true
  content:
    include_pdf: true                # Desktop edition PDF
    include_mobile_pdf: true         # Mobile edition PDF
    include_caption: true            # Text summary (topic names + entry count)
    caption_template: |              # Simple string with {placeholder} substitution
      NSDN Edition — {date} ({slot})
      Topics: {topics}
      Entries: {entry_count}
  targets:
    - type: telegram
      label: "my-telegram"
      enabled: true
      config:
        bot_token: "${TELEGRAM_BOT_TOKEN}"
        chat_id: "${TELEGRAM_CHAT_ID}"
        send_as_document: true
        caption_prefix: ""

    - type: email
      label: "my-email"
      enabled: false
      config:
        method: "smtp"               # "smtp" | "sendgrid" | "mailgun"
        smtp_host: "smtp.example.com"
        smtp_port: 587
        smtp_user: "${EMAIL_USER}"
        smtp_password: "${EMAIL_PASSWORD}"
        from: "nsdn@example.com"
        to: ["user@example.com"]
        subject_template: "NSDN — {date} ({slot})"
```

### Pydantic models — added to `config.py`

```python
class DeliveryContentConfig(BaseModel):
    """What to include in the delivery payload."""
    include_pdf: bool = True
    include_mobile_pdf: bool = True
    include_caption: bool = True
    caption_template: str = (
        "NSDN Edition — {date} ({slot})\n"
        "Topics: {topics}\n"
        "Entries: {entry_count}"
    )


class DeliveryTargetConfig(BaseModel):
    """Per-target configuration — matches SourceConfig pattern."""
    type: str
    label: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class DeliveryResult(BaseModel):
    """Result of a single delivery attempt."""
    target_type: str
    target_label: str
    success: bool
    message: str = ""


class DeliveryConfig(BaseModel):
    """Top-level delivery configuration."""
    enabled: bool = False
    content: DeliveryContentConfig = Field(default_factory=DeliveryContentConfig)
    targets: list[DeliveryTargetConfig] = Field(default_factory=list)
```

Added to `AppConfig`:
```python
delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
```

### `ContentInfo` model — passed to each target

```python
class ContentInfo(BaseModel):
    """Assembled content ready for delivery."""
    date: str
    slot: str
    topics: list[str]
    entry_count: int
    pdf_path: Path | None
    mobile_pdf_path: Path | None
    caption: str
```

### Design decisions

- **Target config uses `type` + `config` dict** — matches `SourceConfig` exactly. Target-specific fields (`bot_token`, `chat_id`, `smtp_host`) live inside `config`, not at the top level.
- **Sensitive fields** support `${ENV_VAR}` substitution — resolved in `loader.py` at config load time, not in individual delivery targets. This benefits all config sections uniformly.
- **Per-target `enabled`** — individual targets can be toggled without disabling all delivery.
- **Error handling** — delivery failures log and continue; never fail `nsdn run`.
- **Caption template** — simple string with `{placeholder}` substitution (not Jinja2).

## File Structure

```
src/nsdn/delivery/
├── __init__.py          # DELIVERY_REGISTRY + register/get + auto-imports
├── base.py              # DeliveryTarget ABC + ContentInfo model
├── builder.py           # build_content_info() — assembles PDFs + caption from edition dir
├── telegram.py          # TelegramDelivery — Bot API sendDocument
└── email.py             # EmailDelivery — SMTP / SendGrid / Mailgun
```

## Components

### `DeliveryTarget` ABC

Matches `EntrySource` instantiation pattern (`label` + `config`):

```python
class DeliveryTarget(ABC):
    target_type: str

    def __init__(self, label: str, config: dict[str, Any]):
        self.label = label
        self.config = config

    @abstractmethod
    def deliver(self, content_info: ContentInfo) -> DeliveryResult: ...
```

### `build_content_info()`

In `builder.py` — reads the edition output directory and assembles delivery payload:

- Accepts `edition_dir: Path` + `content: DeliveryContentConfig`
- Collects PDFs based on `content.include_pdf` / `content.include_mobile_pdf`
- Generates caption from `content.caption_template` using:
  - `{date}` — extracted from edition directory name (e.g., `2026-07-11-morning/` → `2026-07-11`)
  - `{slot}` — extracted from directory name (`morning`)
  - `{topics}` — comma-separated topic names from subdirectories in `topics/`
  - `{entry_count}` — count of topic subdirectories × average entries, or read from a manifest file if one exists
- Returns `ContentInfo` passed to each target's `deliver()`

### Topic and entry count discovery

The edition directory structure is:
```
output/journal/2026-07-11-morning/
├── edition.pdf
├── edition-mobile.pdf
└── topics/
    ├── topic-a.pdf
    ├── topic-b.pdf
    └── topic-c.pdf
```

Topics are discovered by listing `topics/` subdirectories. Entry count is the number of topic PDFs (each topic = one page). A more accurate count would require a manifest file written by synthesize — future enhancement.

### `TelegramDelivery`

- Uses `requests.post` to `https://api.telegram.org/bot{token}/sendDocument`
- Reads `bot_token` and `chat_id` from `self.config`
- Sends desktop PDF first (with caption), then mobile PDF (without caption) as separate documents
- `send_as_document: true` — sends as downloadable file, not inline photo
- `caption_prefix` — optional string prepended to the caption

### `EmailDelivery`

- Reads all fields from `self.config`
- **SMTP mode**: `smtplib.SMTP` with `starttls()`, attaches PDFs, sets subject from `subject_template`
- **SendGrid mode**: `requests.post` to `https://api.sendgrid.com/v3/mail/send`
- **Mailgun mode**: `requests.post` to `https://api.mailgun.net/v3/{domain}/messages`
- Attachments named `edition-{date}-{slot}.pdf` and `edition-{date}-{slot}-mobile.pdf`

## CLI Integration

### `nsdn run --deliver`

In `cli.py`, after synthesize completes:

```python
@cli.command()
@click.option("--deliver", is_flag=True, help="Deliver edition after synthesis.")
@click.pass_context
def run(ctx, deliver):
    # ... existing pipeline ...
    synth_result = run_synthesize(config, db, synth_llm)

    if deliver and config.delivery.enabled:
        click.echo("\n=== Deliver ===")
        edition_dir = synth_result.get("edition_dir")
        if edition_dir:
            run_delivery(config, Path(edition_dir))
        else:
            click.echo("  No edition to deliver")
```

The synthesize result dict must include `edition_dir` (the output directory path). This requires a small change to `synthesize.py` / `component.py` to return the edition directory path.

### `nsdn deliver --edition <path>`

Standalone delivery of a specific edition directory:

```python
@cli.command()
@click.option("--edition", type=click.Path(exists=True), required=True,
              help="Path to edition directory to deliver.")
@click.pass_context
def deliver(ctx, edition):
    config = ctx.obj["config"]
    run_delivery(config, Path(edition))
```

If `--edition` is omitted, auto-detect the latest edition by finding the newest directory under `config.output.directory`.

### `run_delivery()` helper

In `delivery/__init__.py`:

```python
def run_delivery(config: AppConfig, edition_dir: Path) -> list[DeliveryResult]:
    """Execute delivery for all enabled targets."""
    content_info = build_content_info(edition_dir, config.delivery.content)
    results: list[DeliveryResult] = []

    for target_cfg in config.delivery.targets:
        if not target_cfg.enabled:
            continue
        target_cls = get_delivery(target_cfg.type)
        target = target_cls(target_cfg.label, target_cfg.config)
        try:
            result = target.deliver(content_info)
            results.append(result)
        except Exception as e:
            logger.error("Delivery failed for %s: %s", target_cfg.label, e)
            results.append(DeliveryResult(
                target_type=target_cfg.type,
                target_label=target_cfg.label,
                success=False,
                message=str(e),
            ))
    return results
```

## Env Var Resolution

In `loader.py`, applied to all config values before Pydantic parsing:

```python
import re

def _resolve_env_vars(obj):
    """Recursively replace ${VAR_NAME} with os.environ values."""
    if isinstance(obj, str):
        def _replace(match):
            var = match.group(1)
            return os.environ.get(var, match.group(0))
        return re.sub(r'\$\{([^}]+)\}', _replace, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(v) for v in obj]
    return obj

def load_config(path: Path | str | None = None) -> AppConfig:
    # ... existing code ...
    data = yaml.safe_load(f) or {}
    data = _resolve_env_vars(data)
    return AppConfig(**data)
```

This benefits all config sections — not just delivery.

## Changes to Existing Code

| File | Change |
|------|--------|
| `config.py` | Add `DeliveryContentConfig`, `DeliveryTargetConfig`, `DeliveryResult`, `DeliveryConfig` models; add `delivery` to `AppConfig` |
| `loader.py` | Add `_resolve_env_vars()` recursive substitution before Pydantic parsing |
| `synthesize.py` or `component.py` | Return `edition_dir` in synthesize result dict (design mode) |
| `cli.py` | Add `--deliver` flag to `run`, add `deliver` command |
| `delivery/` (new) | All delivery module files |

## Implementation Plan

### Phase 1: Core Infrastructure
- `config.py` — add `DeliveryConfig` + related models to `AppConfig`
- `loader.py` — add `_resolve_env_vars()` for `${VAR}` substitution
- `delivery/__init__.py` — registry + `run_delivery()` helper
- `delivery/base.py` — `DeliveryTarget` ABC + `ContentInfo` model
- `delivery/builder.py` — `build_content_info()` from edition directory

### Phase 2: Telegram Target
- `delivery/telegram.py` — `TelegramDelivery` with Bot API `sendDocument`
- Auto-registers as `"telegram"` in `__init__.py`

### Phase 3: CLI Wiring
- `cli.py` — `nsdn deliver` command + `--deliver` flag on `nsdn run`
- `synthesize.py` / `component.py` — return `edition_dir` in result

### Phase 4: Email Target
- `delivery/email.py` — `EmailDelivery` with SMTP (SendGrid/Mailgun as future)
- Auto-registers as `"email"` in `__init__.py`

### Phase 5: Documentation
- `FUTURE_STEPS.md` — move delivery to "In Progress"
- `docs/DESIGN.md` — add delivery to pluggable abstractions list

## Dependencies

No new dependencies. Uses:
- `requests` (already in pyproject.toml)
- `smtplib` (stdlib)
- `re` (stdlib)
- `os.environ` (stdlib)

## Future Extensions

- **WhatsApp** — via WhatsApp Business API
- **Matrix/Element** — via Matrix client SDK
- **Webhook** — generic HTTP POST with configurable payload
- **Push notifications** — Firebase Cloud Messaging
- **Archive** — deliver to cloud storage (S3, rclone)
- **Manifest file** — synthesize writes `manifest.json` with accurate entry counts per topic for precise caption data
