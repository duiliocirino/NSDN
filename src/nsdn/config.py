"""NSDN configuration model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    type: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class SummarizeConfig(BaseModel):
    enabled: bool = True
    strategy: str = "llm"
    batch_size: int = 10
    max_content_chars: int = 8000
    max_summary_chars: int = 500
    min_length: int = 500  # only summarize content longer than this


class FilterConfig(BaseModel):
    mode: str = "sequential"  # "sequential" | "batch"
    batch_size: int = 15
    score_threshold: int = 7
    max_items_per_feed: int = 20


class SynthesizeConfig(BaseModel):
    mode: str = "llm"  # "llm" | "raw" | "design"
    cluster_strategy: str = "llm"
    raw_content: str = "summary"  # "summary" | "truncated" | "full"
    raw_max_chars: int = 2000
    max_sections: int = 5
    style: str = "technical_minimal"


class OutputConfig(BaseModel):
    directory: str = "./output/journal"
    designer: str = "pico"
    inline_css: bool = True
    cache_images: bool = False


class RetentionConfig(BaseModel):
    keep_days: int = 30
    action: str = "archive"  # "archive" | "delete"


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""
    provider: str = "llama_server"
    model: str = ""
    base_url: str = "http://localhost:8181"
    temperature: float = 0.0
    max_tokens: int = 4096


class LLMConfig(BaseModel):
    """LLM configuration with per-stage model selection.

    Each pipeline stage references a model by name via `models` dict.
    Falls back to `default` if the stage is not specified.
    """
    default: ProviderConfig = Field(default_factory=ProviderConfig)
    models: dict[str, ProviderConfig] = Field(default_factory=dict)

    def get(self, stage: str = "") -> ProviderConfig:
        """Get provider config for a stage, falling back to default."""
        if stage and stage in self.models:
            stage_cfg = self.models[stage]
            defaults = self.default.model_dump()
            merged = {**defaults, **stage_cfg.model_dump(exclude_unset=True)}
            return ProviderConfig(**merged)
        return self.default

    @property
    def temperature(self) -> float:
        """Backward compat — returns default temperature."""
        return self.default.temperature


class WeaviateConfig(BaseModel):
    enabled: bool = True
    url: str = "http://localhost:8080"
    embedding_model: str = "qwen3-embedding:8b"
    embedding_endpoint: str = "http://localhost:11434"
    dedup_threshold: float = 0.95
    collection_name: str = "NSDNEntries"


class NewspaperConfig(BaseModel):
    """Newspaper agent configuration (used when synthesize.mode = 'design')."""
    enabled: bool = True
    strategy: str = "component"  # "component" | "template" | "scratch"
    max_iterations: int = 4
    quality_threshold: int = 7
    viewport: dict[str, int] = Field(default_factory=lambda: {"width": 794, "height": 1123})  # A4 at 96dpi
    screenshot: dict[str, int] = Field(default_factory=lambda: {"dpi": 300})
    pdf: dict[str, str] = Field(default_factory=lambda: {"format": "A4", "margin": "20mm"})
    evaluation: dict[str, float] = Field(default_factory=lambda: {"text_weight": 0.3, "vlm_weight": 0.7})
    cover: dict[str, str] = Field(default_factory=lambda: {"style": "minimal"})
    layouts: list[str] = Field(default_factory=lambda: ["hero", "grid", "sidebar"])
    font_preset: str = "classic"  # classic, editorial, modern, newspaper
    fonts: dict[str, str] = Field(
        default_factory=lambda: {
            "serif": "Georgia, 'Times New Roman', serif",
            "sans": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "google_fonts": "",  # @import URL for Google Fonts (optional)
        }
    )
    colors: dict[str, str] = Field(
        default_factory=lambda: {
            "text": "#333",
            "text-muted": "#555",
            "border": "#333",
            "border-light": "#eee",
            "accent": "#0066cc",
        }
    )


class AppConfig(BaseModel):
    debug: bool = False
    interests: list[str] = Field(default_factory=list)
    sources: list[SourceConfig] = Field(default_factory=list)
    summarize: SummarizeConfig = Field(default_factory=SummarizeConfig)
    filter_: FilterConfig = Field(default_factory=FilterConfig, alias="filter")
    synthesize: SynthesizeConfig = Field(default_factory=SynthesizeConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    weaviate: WeaviateConfig = Field(default_factory=WeaviateConfig)
    newspaper: NewspaperConfig = Field(default_factory=NewspaperConfig)
    schedule: list[str] = Field(default_factory=lambda: ["08:00", "13:00", "19:00"])

    model_config = {"populate_by_name": True}
