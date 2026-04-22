import flet as ft
from app.theme import Colors, Fonts

class InputPanel:
    def __init__(self, workspace):
        self.workspace = workspace
        self.page = None  # Set when build() is called via parent
        
        self.text_field = ft.TextField(
            multiline=True,
            min_lines=30,
            max_lines=None,
            on_change=self.on_text_change,
            bgcolor="transparent",
            border_color="transparent",
            focused_border_color="transparent",
            color=Colors.INK,
            hint_text="Der Geist ist willig, aber das Fleisch ist schwach…",
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED,
                italic=True,
                size=16,  # Decreased from 18
                font_family=Fonts.SERIF
            ),
            text_style=ft.TextStyle(
                size=16,  # Decreased from 18
                font_family=Fonts.SERIF,
                color=Colors.INK,
                height=1.75  # line-height for readability
            ),
            border=ft.InputBorder.NONE,
            content_padding=ft.padding.all(0)
        )
        
        self.char_count = ft.Text(
            "0 words · 0 chars · ~0 tokens",
            size=11,
            color=Colors.INK_MUTED,
            font_family=Fonts.MONO
        )
        
        # Header with source label
        self.header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        "Quelle · German source",
                        size=13,
                        color=Colors.INK_MUTED,
                        italic=True,
                        font_family=Fonts.SERIF
                    ),
                    ft.Container(expand=True),
                    self.char_count
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=8),
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER))
        )
    
    def on_text_change(self, e):
        """Update character count, token estimate, and workspace state"""
        text = self.text_field.value or ""
        self.workspace.set_input_text(text)
        char_count = len(text)
        word_count = len(text.split()) if text.strip() else 0
        
        # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
        estimated_tokens = char_count // 4
        max_tokens = 150000

        if estimated_tokens > max_tokens:
            token_color = Colors.DESTRUCTIVE
            token_status = "TOO LONG"
        elif estimated_tokens > max_tokens * 0.8:
            token_color = "#F1A355"
            token_status = "NEAR LIMIT"
        else:
            token_color = Colors.INK_MUTED
            token_status = ""

        if token_status:
            self.char_count.value = f"{word_count} words · {char_count} chars · ~{estimated_tokens:,} tokens ({token_status})"
            self.char_count.color = token_color
        else:
            self.char_count.value = f"{word_count} words · {char_count} chars · ~{estimated_tokens:,} tokens"
            self.char_count.color = Colors.INK_MUTED

        # Push the update to the UI
        try:
            self.char_count.update()
        except Exception:
            # Control not yet mounted — will render correctly on next page.update()
            pass
    
    def get_text(self) -> str:
        """Get current input text"""
        return self.text_field.value or ""
    
    def set_text(self, text: str):
        """Set input text programmatically (from upload, etc.)"""
        if text is None:
            text = ""
        self.text_field.value = str(text)
        self.on_text_change(None)
    
    def build(self):
        """Build input panel"""
        return ft.Column(
            controls=[
                self.header,
                ft.Container(
                    content=self.text_field,
                    padding=ft.padding.symmetric(horizontal=24, vertical=20),
                    expand=True,
                    bgcolor=Colors.SURFACE
                )
            ],
            spacing=0,
            expand=True
        )