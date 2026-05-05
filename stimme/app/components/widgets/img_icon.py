import flet as ft
from app.theme import Colors

class ImgIcon:
    """Renders an image asset as an icon (supports SVG, PNG, WebP)"""
    
    def __init__(self, asset_name: str, width: int = 28, height: int = 28, color=None):
        # Use asset path directly - Flet will resolve from assets_dir
        self.asset_name = asset_name
        self.width = width
        self.height = height
        self.color = color
    
    def build(self):
        """Build the image icon"""
        # SVGs use a semantic color tint; PNGs/WebPs render as-is.
        is_svg = self.asset_name.lower().endswith(".svg")
        tint = self.color if self.color is not None else (Colors.GOLD if is_svg else None)
        return ft.Image(
            src=f"/{self.asset_name}",
            width=self.width,
            height=self.height,
            fit=ft.ImageFit.CONTAIN,
            color=tint,
        )