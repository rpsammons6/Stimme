import flet as ft
from app.theme import Colors, Fonts

class TranslationResultTab:
    """Component for displaying a translation result using clean layout"""
    
    def __init__(self, translation_data: dict):
        self.translation_data = translation_data
        
        # Get translation and commentary
        translation = translation_data.get("translation", "")
        commentary = translation_data.get("commentary")
        
        # Create main translation markdown component with better styling
        self.translation_markdown = ft.Markdown(
            value=translation,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme="monokai",
            code_style=ft.TextStyle(
                font_family=Fonts.MONO,
                size=14,
                color=Colors.GOLD
            )
        )
        
        # Create commentary markdown component if available
        self.commentary_markdown = None
        if commentary:
            self.commentary_markdown = ft.Markdown(
                value=commentary,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="monokai",
                code_style=ft.TextStyle(
                    font_family=Fonts.MONO,
                    size=14,
                    color=Colors.GOLD
                )
            )
        
        # Create metrics footer if available
        self.metrics_footer = None
        if translation_data.get("metrics"):
            self.metrics_footer = self._create_metrics_footer(translation_data["metrics"])
    
    def _create_metrics_footer(self, metrics: dict):
        """Create metrics footer display"""
        cost = metrics.get("estimated_cost", 0)
        input_tokens = metrics.get("input_tokens", 0)
        output_tokens = metrics.get("output_tokens", 0)
        total_tokens = input_tokens + output_tokens
        model_used = metrics.get("model_used", "Unknown")
        
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        f"💰 ${cost}",
                        size=12,
                        color=Colors.INK_MUTED,
                        font_family=Fonts.MONO
                    ),
                    ft.Text("•", size=12, color=Colors.INK_MUTED),
                    ft.Text(
                        f"🎯 {total_tokens} tokens ({input_tokens}→{output_tokens})",
                        size=12,
                        color=Colors.INK_MUTED,
                        font_family=Fonts.MONO
                    ),
                    ft.Text("•", size=12, color=Colors.INK_MUTED),
                    ft.Text(
                        f"🤖 {model_used}",
                        size=12,
                        color=Colors.INK_MUTED,
                        font_family=Fonts.MONO
                    ),
                    ft.Container(expand=True),
                    ft.Text(
                        f"📅 {self.translation_data.get('timestamp', '').strftime('%H:%M:%S') if self.translation_data.get('timestamp') else ''}",
                        size=12,
                        color=Colors.INK_MUTED,
                        font_family=Fonts.MONO
                    )
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.START
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=12),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(top=ft.BorderSide(1, Colors.DIVIDER))
        )
    
    def build(self):
        """Build the translation result tab with clean, non-overlapping layout"""
        
        # Create a scrollable column with all content
        content_controls = []
        
        # Translation section
        translation_section = ft.Container(
            content=ft.Column(
                controls=[
                    # Translation header
                    ft.Container(
                        content=ft.Text(
                            "Translation",
                            size=24,
                            color=Colors.GOLD,
                            font_family=Fonts.HEADER,
                            weight=ft.FontWeight.W_600
                        ),
                        padding=ft.padding.only(bottom=16)
                    ),
                    # Translation content in a contained area
                    ft.Container(
                        content=self.translation_markdown,
                        bgcolor=Colors.SURFACE,
                        border_radius=8,
                        padding=ft.padding.all(20),
                        border=ft.border.all(1, Colors.DIVIDER)
                    )
                ],
                spacing=0
            ),
            padding=ft.padding.all(24)
        )
        content_controls.append(translation_section)
        
        # Commentary section if available
        if self.commentary_markdown:
            # Ornamental divider
            divider = ft.Container(
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
                            size=16,
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
                padding=ft.padding.symmetric(horizontal=24, vertical=20)
            )
            content_controls.append(divider)
            
            # Commentary content
            commentary_section = ft.Container(
                content=ft.Column(
                    controls=[
                        # Commentary header
                        ft.Container(
                            content=ft.Text(
                                "Commentary",
                                size=20,
                                color=Colors.GOLD,
                                font_family=Fonts.HEADER,
                                weight=ft.FontWeight.W_500
                            ),
                            padding=ft.padding.only(bottom=16)
                        ),
                        # Commentary content in a contained area
                        ft.Container(
                            content=self.commentary_markdown,
                            bgcolor=Colors.SURFACE,
                            border_radius=8,
                            padding=ft.padding.all(20),
                            border=ft.border.all(1, Colors.DIVIDER)
                        )
                    ],
                    spacing=0
                ),
                padding=ft.padding.symmetric(horizontal=24, vertical=0)
            )
            content_controls.append(commentary_section)
        
        # Add metrics footer if available
        if self.metrics_footer:
            content_controls.append(self.metrics_footer)
        
        # Return the complete layout
        return ft.Container(
            content=ft.Column(
                controls=content_controls,
                spacing=0,
                scroll=ft.ScrollMode.HIDDEN
            ),
            expand=True,
            bgcolor=Colors.BACKGROUND
        )
    
    def get_tab_title(self) -> str:
        """Get the title for this tab"""
        source_preview = self.translation_data.get("source_preview", "Translation")
        return source_preview
    
    def get_source_text(self) -> str:
        """Get the full source text"""
        return self.translation_data.get("source_full", "")