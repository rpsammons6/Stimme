import flet as ft
from app.theme import Colors, Fonts

LOADING_BG = "#231E24"


class LoadingScreen:
    """Loading screen with two modes:
    - Full-page (startup): replaces page content with the loading image
    - Dialog (upload/processing): shows a modal dialog over the existing UI
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self.cancel_callback = None
        self._cancelled = False
        self._overlay = None
        self._dialog = None
        self._mode = None  # "fullpage" or "dialog"
        self.progress_bar = None
        self.status_text = None

    def show(self, title: str = "Processing...", cancel_callback=None, fullpage=False):
        """Show loading screen.
        
        Args:
            title: Status text
            cancel_callback: Optional cancel handler
            fullpage: If True, takes over the entire page (for startup). 
                      If False, shows as a modal dialog (for uploads).
        """
        self.cancel_callback = cancel_callback
        self._cancelled = False
        self._mode = "fullpage" if fullpage else "dialog"

        # Build shared controls
        self.progress_bar = ft.ProgressBar(
            width=360, height=6, bgcolor="#3A3040", color=Colors.GOLD,
            value=0, border_radius=3,
        )
        self.status_text = ft.Text(
            title, font_family=Fonts.SERIF, size=14,
            color=Colors.INK_MUTED, text_align=ft.TextAlign.CENTER, italic=True,
        )

        cancel_btn = None
        if cancel_callback:
            cancel_btn = ft.TextButton(
                "Cancel", on_click=self._on_cancel,
                style=ft.ButtonStyle(color=Colors.DESTRUCTIVE, text_style=ft.TextStyle(font_family=Fonts.FRAKTUR)),
            )

        bottom_controls = [self.status_text, ft.Container(height=12), self.progress_bar]
        if cancel_btn:
            bottom_controls.extend([ft.Container(height=12), cancel_btn])

        if self._mode == "fullpage":
            self._show_fullpage(title, bottom_controls)
        else:
            self._show_dialog(title, bottom_controls)

    def _show_fullpage(self, title, bottom_controls):
        """Full-page mode for startup."""
        bottom_section = ft.Container(
            content=ft.Column(controls=bottom_controls, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            alignment=ft.alignment.center, padding=ft.padding.only(bottom=60),
        )
        self._overlay = ft.Container(
            content=ft.Column(controls=[
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Image(src="/loadingscreen.png", width=400, height=400, fit=ft.ImageFit.CONTAIN),
                    alignment=ft.alignment.center,
                ),
                ft.Container(expand=True),
                bottom_section,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, spacing=0),
            bgcolor=LOADING_BG, expand=True,
        )
        self.page.controls.clear()
        self.page.controls.append(self._overlay)
        self.page.bgcolor = LOADING_BG
        self.page.update()

    def _show_dialog(self, title, bottom_controls):
        """Dialog mode for uploads/processing — doesn't touch page controls."""
        # Close any existing dialog first
        try:
            if self.page.dialog and hasattr(self.page.dialog, 'open') and self.page.dialog.open:
                self.page.dialog.open = False
                self.page.update()
        except Exception:
            pass

        from app.components.widgets.img_icon import ImgIcon
        logo = ImgIcon("stimme-logo.png", 100, 100)

        self._dialog = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Container(content=logo.build(), alignment=ft.alignment.center, margin=ft.margin.only(bottom=16)),
                        ft.Text(title, font_family=Fonts.HEADER, weight=ft.FontWeight.W_500, size=18,
                                color=Colors.FOREGROUND, text_align=ft.TextAlign.CENTER),
                        ft.Container(height=8),
                    ] + bottom_controls,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0,
                ),
                width=400, height=280 if self.cancel_callback else 240, padding=ft.padding.all(20),
            ),
            bgcolor=Colors.BACKGROUND,
            shape=ft.RoundedRectangleBorder(radius=12),
        )
        self.page.dialog = self._dialog
        self._dialog.open = True
        self.page.update()

    def update_progress(self, message: str, progress: float):
        """Update progress bar and status message (thread-safe)."""
        try:
            if self.status_text:
                self.status_text.value = message
            if self.progress_bar:
                self.progress_bar.value = max(0.0, min(1.0, progress / 100.0))
            if self.page:
                self.page.update()
        except Exception:
            pass

    def hide(self):
        """Hide the loading screen (thread-safe)."""
        try:
            if self._mode == "fullpage":
                if self._overlay and self._overlay in self.page.controls:
                    self.page.controls.remove(self._overlay)
                self._overlay = None
                self.page.bgcolor = Colors.BACKGROUND
                self.page.update()
            elif self._mode == "dialog":
                if self._dialog:
                    self._dialog.open = False
                    if self.page.dialog is self._dialog:
                        self.page.dialog = None
                    self._dialog = None
                    self.page.update()
            self.progress_bar = None
            self.status_text = None
            self.cancel_callback = None
            self._mode = None
        except Exception:
            pass

    def _on_cancel(self, e):
        if self._cancelled:
            return
        self._cancelled = True
        if self.cancel_callback:
            self.cancel_callback()
        self.hide()
