"""Water.css designer."""

import importlib.resources

from nsdn.designers.base import PageDesigner
from nsdn.designers import register_designer


class WaterDesigner(PageDesigner):
    designer_type = "water"

    def get_template_path(self) -> str:
        return "templates/water.html"

    def get_css(self) -> str:
        try:
            return importlib.resources.read_text("nsdn.assets", "water.min.css")
        except FileNotFoundError:
            return ""

    def get_css_url(self) -> str:
        return ""


register_designer("water", WaterDesigner)
