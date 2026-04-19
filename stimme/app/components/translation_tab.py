import flet as ft

class TranslationTab:
    def __init__(self, result: dict):
        self.result = result
    
    def build(self):
        """Build translation tab content"""
        return ft.Column(
            controls=[
                ft.Text(f"Translation Result", size=14, weight="bold"),
                ft.Divider(height=1),
                ft.Text(self.result.get("translation", ""), selectable=True),
            ],
            expand=True,
            spacing=10
        )
