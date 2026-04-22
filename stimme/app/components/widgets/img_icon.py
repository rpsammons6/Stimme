import flet as ft

class ImgIcon:
    """Renders an image asset as an icon (supports SVG, PNG, WebP)"""
    
    def __init__(self, asset_name: str, width: int = 28, height: int = 28):
        # Use asset path directly - Flet will resolve from assets_dir
        self.asset_name = asset_name
        self.width = width
        self.height = height
    
    def build(self):
        """Build the image icon"""
        return ft.Image(
            src=f"/{self.asset_name}",
            width=self.width,
            height=self.height,
            fit=ft.ImageFit.CONTAIN
        )