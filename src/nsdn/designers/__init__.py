"""Designer registry."""

from nsdn.designers.base import PageDesigner

DESIGNER_REGISTRY: dict[str, type[PageDesigner]] = {}


def register_designer(designer_type: str, designer_class: type[PageDesigner]) -> None:
    DESIGNER_REGISTRY[designer_type] = designer_class


def get_designer(designer_type: str) -> type[PageDesigner]:
    if designer_type not in DESIGNER_REGISTRY:
        available = ", ".join(DESIGNER_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown designer: {designer_type}. Available: {available}")
    return DESIGNER_REGISTRY[designer_type]


# Import implementations to register them
import nsdn.designers.pico  # noqa: F401
import nsdn.designers.water  # noqa: F401
