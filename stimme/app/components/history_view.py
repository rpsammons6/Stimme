import flet as ft
from app.theme import Colors, Fonts
from app.services.history import HistoryManager
from datetime import datetime

class HistoryView:
    """History view dialog showing past translations"""
    
    def __init__(self, page: ft.Page):
        self.page = page
        self.history_manager = HistoryManager()
        
        # Create dialog
        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Translation History",
                size=24,
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_600,
                color=Colors.FOREGROUND
            ),
            content=ft.Container(
                content=self._build_history_content(),
                width=700,
                height=500,
                padding=ft.padding.all(20)
            ),
            actions=[
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Clear History",
                            on_click=self.clear_history,
                            style=ft.ButtonStyle(color=Colors.DESTRUCTIVE)
                        ),
                        ft.Container(expand=True),
                        ft.TextButton(
                            "Close",
                            on_click=self.close_dialog
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                )
            ],
            bgcolor=Colors.SURFACE,
        )
    
    def _build_history_content(self):
        """Build the history content"""
        history_items = self.history_manager.get_history()
        
        if not history_items:
            return ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Image(
                            src="/empty-history-icon.png",
                            width=128,
                            height=128,
                            fit=ft.ImageFit.CONTAIN,
                            opacity=0.6
                        ),
                        alignment=ft.alignment.center,
                        padding=ft.padding.only(bottom=24)
                    ),
                    ft.Text(
                        "No translations yet. Your translation history will appear here.",
                        size=14,
                        color=Colors.INK_MUTED,
                        italic=True,
                        font_family=Fonts.SERIF,
                        text_align=ft.TextAlign.CENTER
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True
            )
        
        # Build history items
        history_controls = []
        for i, item in enumerate(history_items):
            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(item.get("timestamp", ""))
                time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            except:
                time_str = "Unknown time"
            
            # Create history item card
            source_preview = item.get("source", "")[:100] + ("..." if len(item.get("source", "")) > 100 else "")
            translation_preview = item.get("translation", "")[:150] + ("..." if len(item.get("translation", "")) > 150 else "")
            
            history_card = ft.Container(
                content=ft.Column(
                    controls=[
                        # Header with timestamp and model
                        ft.Row(
                            controls=[
                                ft.Text(
                                    f"#{len(history_items) - i}",
                                    size=12,
                                    color=Colors.GOLD,
                                    weight="bold",
                                    font_family=Fonts.MONO
                                ),
                                ft.Text(
                                    time_str,
                                    size=12,
                                    color=Colors.INK_MUTED,
                                    font_family=Fonts.MONO
                                ),
                                ft.Container(expand=True),
                                ft.Text(
                                    item.get("model", "Unknown"),
                                    size=11,
                                    color=Colors.INK_MUTED,
                                    font_family=Fonts.MONO
                                )
                            ],
                            spacing=8
                        ),
                        
                        # Source text
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        "Source:",
                                        size=11,
                                        color=Colors.INK_MUTED,
                                        weight="bold"
                                    ),
                                    ft.Text(
                                        source_preview,
                                        size=13,
                                        color=Colors.FOREGROUND,
                                        font_family=Fonts.SERIF,
                                        selectable=True
                                    )
                                ],
                                spacing=4
                            ),
                            padding=ft.padding.only(top=8)
                        ),
                        
                        # Translation
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        "Translation:",
                                        size=11,
                                        color=Colors.INK_MUTED,
                                        weight="bold"
                                    ),
                                    ft.Text(
                                        translation_preview,
                                        size=13,
                                        color=Colors.FOREGROUND,
                                        font_family=Fonts.SERIF,
                                        selectable=True
                                    )
                                ],
                                spacing=4
                            ),
                            padding=ft.padding.only(top=8)
                        ),
                        
                        # Commentary if available
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        "Commentary:",
                                        size=11,
                                        color=Colors.INK_MUTED,
                                        weight="bold"
                                    ),
                                    ft.Text(
                                        item.get("commentary", "No commentary")[:100] + ("..." if len(item.get("commentary", "")) > 100 else ""),
                                        size=12,
                                        color=Colors.INK_MUTED,
                                        font_family=Fonts.SERIF,
                                        italic=True,
                                        selectable=True
                                    )
                                ],
                                spacing=4
                            ),
                            padding=ft.padding.only(top=8),
                            visible=bool(item.get("commentary"))
                        ),
                        
                        # Click to view full translation hint
                        ft.Container(
                            content=ft.Text(
                                "Click to view full translation",
                                size=10,
                                color=Colors.GOLD,
                                italic=True,
                                font_family=Fonts.SERIF
                            ),
                            padding=ft.padding.only(top=8),
                            alignment=ft.alignment.center
                        )
                    ],
                    spacing=0
                ),
                bgcolor=Colors.SURFACE,
                border=ft.border.all(1, Colors.DIVIDER),
                border_radius=8,
                padding=ft.padding.all(16),
                margin=ft.margin.only(bottom=12),
                on_click=lambda e, item=item: self._show_full_translation(item),
                ink=True  # Add ripple effect on click
            )
            
            history_controls.append(history_card)
        
        return ft.Column(
            controls=history_controls,
            scroll=ft.ScrollMode.HIDDEN,  # Hide scrollbar but maintain scroll functionality
            expand=True,
            spacing=0
        )
    
    def _show_full_translation(self, item):
        """Show full translation in a detailed dialog"""
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(item.get("timestamp", ""))
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = "Unknown time"
        
        # Create scrollable content for the full translation
        content = ft.Column(
            controls=[
                # Header
                ft.Row(
                    controls=[
                        ft.Text(
                            time_str,
                            size=14,
                            color=Colors.INK_MUTED,
                            font_family=Fonts.MONO
                        ),
                        ft.Container(expand=True),
                        ft.Text(
                            item.get("model", "Unknown"),
                            size=12,
                            color=Colors.INK_MUTED,
                            font_family=Fonts.MONO
                        )
                    ],
                    spacing=8
                ),
                
                ft.Divider(color=Colors.DIVIDER),
                
                # Source text
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Source Text:",
                                size=14,
                                color=Colors.INK_MUTED,
                                weight="bold",
                                font_family=Fonts.HEADER
                            ),
                            ft.Container(
                                content=ft.Text(
                                    item.get("source", ""),
                                    size=14,
                                    color=Colors.FOREGROUND,
                                    font_family=Fonts.SERIF,
                                    selectable=True
                                ),
                                bgcolor=Colors.BACKGROUND,
                                padding=ft.padding.all(12),
                                border_radius=8,
                                border=ft.border.all(1, Colors.DIVIDER)
                            )
                        ],
                        spacing=8
                    ),
                    padding=ft.padding.only(bottom=16)
                ),
                
                # Translation
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Translation:",
                                size=14,
                                color=Colors.INK_MUTED,
                                weight="bold",
                                font_family=Fonts.HEADER
                            ),
                            ft.Container(
                                content=ft.Text(
                                    item.get("translation", ""),
                                    size=14,
                                    color=Colors.FOREGROUND,
                                    font_family=Fonts.SERIF,
                                    selectable=True
                                ),
                                bgcolor=Colors.BACKGROUND,
                                padding=ft.padding.all(12),
                                border_radius=8,
                                border=ft.border.all(1, Colors.DIVIDER)
                            )
                        ],
                        spacing=8
                    ),
                    padding=ft.padding.only(bottom=16)
                ),
                
                # Commentary if available
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Commentary:",
                                size=14,
                                color=Colors.INK_MUTED,
                                weight="bold",
                                font_family=Fonts.HEADER
                            ),
                            ft.Container(
                                content=ft.Text(
                                    item.get("commentary", "No commentary provided"),
                                    size=14,
                                    color=Colors.INK_MUTED,
                                    font_family=Fonts.SERIF,
                                    italic=True,
                                    selectable=True
                                ),
                                bgcolor=Colors.BACKGROUND,
                                padding=ft.padding.all(12),
                                border_radius=8,
                                border=ft.border.all(1, Colors.DIVIDER)
                            )
                        ],
                        spacing=8
                    ),
                    visible=bool(item.get("commentary"))
                )
            ],
            scroll=ft.ScrollMode.HIDDEN,
            spacing=0
        )
        
        full_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Full Translation",
                size=24,
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_600,
                color=Colors.FOREGROUND
            ),
            content=ft.Container(
                content=content,
                width=800,
                height=600,
                padding=ft.padding.all(20)
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda e: self._close_full_dialog(full_dialog)
                )
            ],
            bgcolor=Colors.SURFACE,
        )
        
        self.page.dialog = full_dialog
        full_dialog.open = True
        self.page.update()
    
    def _close_full_dialog(self, dialog):
        """Close the full translation dialog"""
        dialog.open = False
        self.page.update()

    def clear_history(self, e):
        """Show confirmation dialog before clearing history"""
        def confirm_clear(e):
            self.history_manager.clear_history()
            # Rebuild content
            self.dialog.content.content = self._build_history_content()
            confirmation_dialog.open = False
            self.page.update()
        
        def cancel_clear(e):
            confirmation_dialog.open = False
            self.page.update()
        
        confirmation_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Clear History",
                size=20,
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_600,
                color=Colors.FOREGROUND
            ),
            content=ft.Text(
                "Are you sure you want to clear all translation history? This action cannot be undone.",
                size=14,
                color=Colors.FOREGROUND,
                font_family=Fonts.SERIF
            ),
            actions=[
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Cancel",
                            on_click=cancel_clear,
                            style=ft.ButtonStyle(color=Colors.FOREGROUND)
                        ),
                        ft.TextButton(
                            "Clear History",
                            on_click=confirm_clear,
                            style=ft.ButtonStyle(color=Colors.DESTRUCTIVE)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=8
                )
            ],
            bgcolor=Colors.SURFACE,
        )
        
        self.page.dialog = confirmation_dialog
        confirmation_dialog.open = True
        self.page.update()
    
    def close_dialog(self, e):
        """Close the dialog"""
        self.dialog.open = False
        self.page.update()
    
    def show(self):
        """Show the history dialog"""
        # Refresh history content before showing
        self.dialog.content.content = self._build_history_content()
        self.page.dialog = self.dialog
        self.dialog.open = True
        self.page.update()
