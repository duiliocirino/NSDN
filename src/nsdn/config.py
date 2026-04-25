"""NSDN configuration model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    type: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class FilterConfig(BaseModel):
    mode: str = "sequential"  # "sequential" | "batch"
    batch_size: int = 15
    score_threshold: int = 7
    max_items_per_feed: int = 20


class SynthesizeConfig(BaseModel):
    mode: str = "llm"  # "llm" | "raw"
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


class LLMConfig(BaseModel):
    provider: str = "llama_server"
    model: str = ""
    base_url: str = "http://localhost:8181"
    temperature: float = 0.0
    max_tokens: int = 4096


class WeaviateConfig(BaseModel):
    enabled: bool = True
    url: str = "http://localhost:8080"
    embedding_model: str = "qwen3-embedding:8b"
    embedding_endpoint: str = "http://localhost:11434"
    dedup_threshold: float = 0.95
    collection_name: str = "NSDNEntries"


class AppConfig(BaseModel):
    interests: list[str] = Field(default_factory=list)
    sources: list[SourceConfig] = Field(default_factory=list)
    filter_: FilterConfig = Field(default_factory=FilterConfig, alias="filter")
    synthesize: SynthesizeConfig = Field(default_factory=SynthesizeConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    weaviate: WeaviateConfig = Field(default_factory=WeaviateConfig)
    schedule: list[str] = Field(default_factory=lambda: ["08:00", "13:00", "19:00"])

    model_config = {"populate_by_name": True}
