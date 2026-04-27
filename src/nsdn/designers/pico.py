"""Pico.css designer."""

from nsdn.designers.base import PageDesigner
from nsdn.designers import register_designer


class PicoDesigner(PageDesigner):
    designer_type = "pico"

    def get_template_path(self) -> str:
        return "templates/pico.html"

    def get_css(self) -> str:
        # Return empty for linked CSS by default
        return ""

    def get_css_url(self) -> str:
        return "https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css"


register_designer("pico", PicoDesigner)
