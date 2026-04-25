"""Source registry."""

from nsdn.sources.base import EntrySource

SOURCE_REGISTRY: dict[str, type[EntrySource]] = {}


def register_source(source_type: str, source_class: type[EntrySource]) -> None:
    SOURCE_REGISTRY[source_type] = source_class


def get_source(source_type: str) -> type[EntrySource]:
    if source_type not in SOURCE_REGISTRY:
        available = ", ".join(SOURCE_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown source type: {source_type}. Available: {available}")
    return SOURCE_REGISTRY[source_type]


# Import implementations to register them
import nsdn.sources.reddit  # noqa: F401
