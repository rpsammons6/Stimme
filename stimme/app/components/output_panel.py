import flet as ft
from app.theme import Colors, Fonts

class OutputPanel:
    def __init__(self):
        self.translation_text = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme="monokai",
            code_style=ft.TextStyle(
                font_family=Fonts.MONO,
                size=14,
                color=Colors.GOLD
            ),
            on_tap_link=lambda e: print(f"Link tapped: {e.data}")
        )
        
        self.commentary_text = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme="monokai"
        )
        
        # Create the welcome state with the large S logo
        self.welcome_state = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Image(
                            src="/stimme-s.png",
                            width=192,
                            height=192,
                            fit=ft.ImageFit.CONTAIN,
                            opacity=0.9
                        ),
                        alignment=ft.alignment.center,
                        padding=ft.padding.only(bottom=16)
                    ),
                    ft.Container(
                        content=ft.Text(
                            "A scholarly workbench for the careful rendering of German into English.\nEnter or upload a passage to begin.",
                            size=15,
                            color=Colors.INK_MUTED,
                            text_align=ft.TextAlign.CENTER,
                            italic=True,
                            font_family=Fonts.SERIF
                        ),
                        width=420,
                        padding=ft.padding.symmetric(horizontal=32)
                    ),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Container(
                                    content=ft.Container(
                                        bgcolor=Colors.GOLD,
                                        height=1,
                                        opacity=0.4
                                    ),
                                    expand=True
                                ),
                                ft.Text(
                                    "✦",
                                    size=16,
                                    color=Colors.GOLD,
                                    opacity=0.7
                                ),
                                ft.Container(
                                    content=ft.Container(
                                        bgcolor=Colors.GOLD,
                                        height=1,
                                        opacity=0.4
                                    ),
                                    expand=True
                                )
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=16
                        ),
                        width=128,
                        margin=ft.margin.only(top=32, bottom=16)
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0
            ),
            alignment=ft.alignment.center,
            expand=True
        )
        
        self.content_container = ft.Column(
            controls=[self.welcome_state],
            spacing=0,
            expand=True,
            scroll=ft.ScrollMode.AUTO
        )
        
        self.current_translation = ""
        self.current_commentary = ""
    
    def get_translation(self) -> str:
        """Get current translation"""
        return self.current_translation
    
    def set_translation(self, translation: str, model: str = "", commentary: str = "", metrics: dict = None):
        """Set translation output"""
        self.current_translation = translation
        self.current_commentary = commentary
        
        # Build content with scholarly prose styling
        controls = []
        
        if translation:
            # Translation section with scholarly prose
            translation_container = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=self.translation_text,
                            padding=ft.padding.symmetric(vertical=8)
                        )
                    ],
                    spacing=0
                ),
                padding=ft.padding.symmetric(horizontal=32, vertical=24)
            )
            self.translation_text.value = translation
            controls.append(translation_container)
            
            # Metrics footer if available
            if metrics:
                cost = metrics.get("estimated_cost", 0)
                tokens = metrics.get("input_tokens", 0) + metrics.get("output_tokens", 0)
                model_used = metrics.get("model_used", model)
                
                metrics_footer = ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                f"Cost: ${cost}",
                                size=11,
                                color=Colors.INK_MUTED,
                                font_family=Fonts.MONO
                            ),
                            ft.Text("•", size=11, color=Colors.INK_MUTED),
                            ft.Text(
                                f"Tokens: {tokens}",
                                size=11,
                                color=Colors.INK_MUTED,
                                font_family=Fonts.MONO
                            ),
                            ft.Text("•", size=11, color=Colors.INK_MUTED),
                            ft.Text(
                                f"Model: {model_used}",
                                size=11,
                                color=Colors.INK_MUTED,
                                font_family=Fonts.MONO
                            )
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    padding=ft.padding.symmetric(horizontal=32, vertical=16),
                    border=ft.border.only(top=ft.BorderSide(1, Colors.DIVIDER))
                )
                controls.append(metrics_footer)
            
            # Commentary section if available
            if commentary:
                # Create ornamental divider
                ornament_divider = ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Container(
                                    bgcolor=Colors.GOLD,
                                    height=1,
                                    opacity=0.4
                                ),
                                expand=True
                            ),
                            ft.Text(
                                "❦ Philological Commentary ❦",
                                size=14,
                                color=Colors.GOLD,
                                font_family=Fonts.SERIF,
                                opacity=0.9
                            ),
                            ft.Container(
                                content=ft.Container(
                                    bgcolor=Colors.GOLD,
                                    height=1,
                                    opacity=0.4
                                ),
                                expand=True
                            )
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=16
                    ),
                    margin=ft.margin.symmetric(vertical=32, horizontal=32)
                )
                
                commentary_container = ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Container(
                                content=self.commentary_text,
                                padding=ft.padding.symmetric(vertical=8)
                            )
                        ],
                        spacing=0
                    ),
                    padding=ft.padding.symmetric(horizontal=32, vertical=0)
                )
                self.commentary_text.value = commentary
                
                controls.extend([
                    ornament_divider,
                    commentary_container
                ])
        
        self.content_container.controls = controls if controls else [self.welcome_state]
    
    def clear(self):
        """Clear output"""
        self.current_translation = ""
        self.current_commentary = ""
        self.translation_text.value = ""
        self.commentary_text.value = ""
        self.content_container.controls = [self.welcome_state]
    
    def build(self):
        """Build output panel"""
        return ft.Container(
            content=self.content_container,
            expand=True,
            bgcolor="#3A3238"  # Slightly different from input (bg-surface/30 in original)
        )