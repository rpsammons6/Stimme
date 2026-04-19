import flet as ft
from app.theme import Colors, Fonts
from app.components.img_icon import ImgIcon

class LoadingScreen:
    """Loading screen overlay with progress bar and cancellation support"""
    
    def __init__(self, page: ft.Page):
        self.page = page
        self.dialog = None
        self.progress_bar = None
        self.status_text = None
        self.cancel_callback = None
        
        # Create stimme logo icon
        self.logo_icon = ImgIcon("stimme-logo.png", 120, 120)
        
    def show(self, title: str = "Processing...", cancel_callback=None):
        """
        Show loading screen
        
        Args:
            title: Title text to display
            cancel_callback: Optional callback function to call when cancel is clicked
        """
        self.cancel_callback = cancel_callback
        
        # Progress bar
        self.progress_bar = ft.ProgressBar(
            width=300,
            height=8,
            bgcolor=Colors.SURFACE,
            color=Colors.GOLD,
            value=0
        )
        
        # Status text
        self.status_text = ft.Text(
            "Initializing...",
            font_family=Fonts.SERIF,
            size=14,
            color=Colors.INK_MUTED,
            text_align=ft.TextAlign.CENTER
        )
        
        # Cancel button (only show if callback provided)
        cancel_button = None
        if cancel_callback:
            cancel_button = ft.TextButton(
                "Cancel",
                on_click=self._on_cancel,
                style=ft.ButtonStyle(
                    color=Colors.DESTRUCTIVE
                )
            )
        
        # Create dialog content
        content_controls = [
            ft.Container(
                content=self.logo_icon.build(),
                alignment=ft.alignment.center,
                margin=ft.margin.only(bottom=20)
            ),
            ft.Text(
                title,
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_500,
                size=18,
                color=Colors.FOREGROUND,
                text_align=ft.TextAlign.CENTER
            ),
            ft.Container(height=10),
            self.status_text,
            ft.Container(height=15),
            self.progress_bar
        ]
        
        if cancel_button:
            content_controls.extend([
                ft.Container(height=20),
                ft.Container(
                    content=cancel_button,
                    alignment=ft.alignment.center
                )
            ])
        
        # Create modal dialog
        self.dialog = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=ft.Column(
                    controls=content_controls,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0
                ),
                width=400,
                height=300 if cancel_callback else 250,
                padding=ft.padding.all(20)
            ),
            bgcolor=Colors.BACKGROUND,
            shape=ft.RoundedRectangleBorder(radius=12)
        )
        
        # Show dialog
        self.page.dialog = self.dialog
        self.dialog.open = True
        self.page.update()
    
    def update_progress(self, message: str, progress: float):
        """
        Update progress bar and status message
        
        Args:
            message: Status message to display
            progress: Progress value (0-100)
        """
        if self.status_text:
            self.status_text.value = message
        
        if self.progress_bar:
            self.progress_bar.value = progress / 100.0  # Convert to 0-1 range
        
        if self.page:
            self.page.update()
    
    def hide(self):
        """Hide loading screen"""
        if self.dialog:
            self.dialog.open = False
            self.page.dialog = None
            self.page.update()
            self.dialog = None
            self.progress_bar = None
            self.status_text = None
            self.cancel_callback = None
    
    def _on_cancel(self, e):
        """Handle cancel button click"""
        if self.cancel_callback:
            self.cancel_callback()
        self.hide()