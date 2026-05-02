"""
Centralized event bus for Stimme.
All UI state changes go through here. This prevents:
- Competing page.update() calls from different threads
- Bidirectional reference spaghetti
- Dialog stomping
- Orphaned controls from rebuild races
"""

import threading
import traceback
from typing import Callable


def _log(msg):
    print(f"[EventBus] {msg}")


class EventBus:
    """Thread-safe event bus with a single update lock."""

    def __init__(self, page):
        self.page = page
        self._lock = threading.Lock()
        self._listeners: dict[str, list[Callable]] = {}
        self._dialog_stack: list = []

    # ------------------------------------------------------------------
    # Pub/Sub
    # ------------------------------------------------------------------

    def on(self, event: str, callback: Callable):
        """Register a listener for an event."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def emit(self, event: str, **kwargs):
        """Emit an event. All listeners are called, then page.update() once."""
        try:
            listeners = self._listeners.get(event, [])
            for cb in listeners:
                try:
                    cb(**kwargs)
                except Exception:
                    _log(f"ERROR in listener for '{event}':\n{traceback.format_exc()}")
            self.safe_update()
        except Exception:
            _log(f"ERROR emitting '{event}':\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Thread-safe page update
    # ------------------------------------------------------------------

    def safe_update(self):
        """Call page.update() exactly once, thread-safe."""
        with self._lock:
            try:
                self.page.update()
            except Exception:
                _log(f"ERROR in safe_update:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Dialog management (prevents stomping)
    # ------------------------------------------------------------------

    def show_dialog(self, dialog):
        """Show a dialog safely. Only one dialog at a time."""
        with self._lock:
            try:
                # Close any existing dialog first
                if self.page.dialog and hasattr(self.page.dialog, 'open'):
                    self.page.dialog.open = False
                self.page.dialog = dialog
                dialog.open = True
                self.page.update()
            except Exception:
                _log(f"ERROR in show_dialog:\n{traceback.format_exc()}")

    def close_dialog(self):
        """Close the current dialog."""
        with self._lock:
            try:
                if self.page.dialog:
                    self.page.dialog.open = False
                    self.page.update()
            except Exception:
                _log(f"ERROR in close_dialog:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Banner management
    # ------------------------------------------------------------------

    def show_banner(self, message: str, is_error: bool = False):
        """Show a banner message. Closes any existing banner first."""
        from app.theme import Colors, Fonts
        import flet as ft
        with self._lock:
            try:
                # Close existing banner first so the new one actually renders
                if self.page.banner:
                    self.page.banner.open = False
                    self.page.update()

                self.page.banner = ft.Banner(
                    content=ft.Text(message, color="#FFFFFF" if is_error else Colors.BACKGROUND, size=14, selectable=True),
                    actions=[ft.TextButton(
                        content=ft.Text("OK", font_family=Fonts.FRAKTUR),
                        on_click=lambda _: self.close_banner(),
                        style=ft.ButtonStyle(color=Colors.BACKGROUND if not is_error else "#2D232E"),
                    )],
                    bgcolor=Colors.DESTRUCTIVE if is_error else Colors.GOLD,
                    open=True,
                )
                self.page.update()
            except Exception:
                _log(f"ERROR in show_banner:\n{traceback.format_exc()}")

    def close_banner(self):
        """Close the current banner."""
        with self._lock:
            try:
                if self.page.banner:
                    self.page.banner.open = False
                    self.page.update()
            except Exception:
                pass
