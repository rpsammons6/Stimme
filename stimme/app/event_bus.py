"""
Centralized event bus for Stimme.
All UI state changes go through here. This prevents:
- Competing page.update() calls from different threads
- Bidirectional reference spaghetti
- Dialog stomping
- Orphaned controls from rebuild races
"""

from __future__ import annotations

import threading
import time
import traceback
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.components.shared.banner_overlay import BannerOverlay


def _log(msg):
    print(f"[EventBus] {msg}")


class EventBus:
    """Thread-safe event bus with a single update lock."""

    def __init__(self, page):
        self.page = page
        self._lock = threading.Lock()
        self._listeners: dict[str, list[Callable]] = {}
        self._dialog_stack: list = []
        self._update_latency_cb: Callable[[float], None] | None = None
        self._banner_overlay: BannerOverlay | None = None

    def set_update_latency_callback(self, cb: Callable[[float], None] | None) -> None:
        """Register a callback to receive page.update() latency in ms."""
        self._update_latency_cb = cb

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
                t0 = time.perf_counter()
                self.page.update()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                # Notify HUD if registered
                if self._update_latency_cb:
                    self._update_latency_cb(elapsed_ms)
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
    # Banner overlay registration
    # ------------------------------------------------------------------

    def register_banner_overlay(self, overlay: "BannerOverlay") -> None:
        """Called by Shell after constructing the overlay."""
        self._banner_overlay = overlay

    # ------------------------------------------------------------------
    # Banner management
    # ------------------------------------------------------------------

    def show_banner(self, message: str, is_error: bool = False, detail: str | None = None) -> None:
        """Show a banner message. Delegates to BannerOverlay if registered."""
        with self._lock:
            try:
                if self._banner_overlay is not None:
                    self._banner_overlay.show(message, is_error, detail)
                    self.page.update()
                else:
                    _log("DEPRECATED: BannerOverlay not registered, falling back to _show_banner_legacy (no-op)")
                    self._show_banner_legacy(message, is_error)
            except Exception:
                _log(f"ERROR in show_banner:\n{traceback.format_exc()}")

    def close_banner(self) -> None:
        """Close the current banner. Delegates to BannerOverlay if registered."""
        with self._lock:
            try:
                if self._banner_overlay is not None:
                    # Inline the dismiss logic to avoid deadlock (dismiss calls safe_update
                    # which would re-acquire _lock). We already hold the lock here.
                    self._banner_overlay._cancel_timer()
                    self._banner_overlay._container.visible = False
                    self.page.update()
                else:
                    _log(
                        "DEPRECATED: close_banner called but BannerOverlay not "
                        "registered. page.banner is no longer used. Ensure "
                        "BannerOverlay is registered via register_banner_overlay()."
                    )
            except Exception:
                _log(f"ERROR in close_banner:\n{traceback.format_exc()}")

    def _show_banner_legacy(self, message: str, is_error: bool = False) -> None:
        """Legacy fallback using page.banner (DEPRECATED — no-op).

        This method is deprecated. The BannerOverlay should always be
        registered before any banner calls are made. If you see the
        deprecation warning in logs, ensure Shell wires up the overlay
        during build().
        """
        _log(
            "DEPRECATED: _show_banner_legacy called but page.banner is no "
            "longer used. Ensure BannerOverlay is registered via "
            "register_banner_overlay()."
        )
