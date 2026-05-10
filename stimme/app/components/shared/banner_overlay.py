"""BannerOverlay — floating notification banner rendered inside the root Stack.

Replaces Flet's built-in page.banner with a positioned overlay that floats
below the menu bar (top=28) and spans full width. Eliminates layout shift
caused by the native banner pushing content down.

Two banner types:
- Confirmation (is_error=False): Gold background, auto-dismisses after 3s.
- Error (is_error=True): Destructive background, persists until dismissed.
"""

from __future__ import annotations

import threading
import traceback
from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from app.event_bus import EventBus

MAX_DETAIL_LENGTH = 120


def _log(msg):
    print(f"[BannerOverlay] {msg}")


class BannerOverlay:
    """Floating banner notification rendered inside the root Stack."""

    def __init__(self, bus: "EventBus"):
        self._bus = bus
        self._timer: threading.Timer | None = None

        # UI controls
        self._message_text = ft.Text(
            value="",
            size=14,
            selectable=True,
        )
        self._detail_text = ft.Text(
            value="",
            size=12,
            visible=False,
        )
        self._dismiss_btn = ft.TextButton(
            content=ft.Text("OK"),
            on_click=lambda _: self.dismiss(),
        )

        # Positioned container — overlay at top=28, full width
        self._container = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[self._message_text, self._detail_text],
                        spacing=2,
                        expand=True,
                    ),
                    self._dismiss_btn,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            top=28,
            left=0,
            right=0,
            visible=False,
        )

    @property
    def control(self) -> ft.Container:
        """Positioned container to add to the root Stack."""
        return self._container

    def show(self, message: str, is_error: bool = False, detail: str | None = None) -> None:
        """Display a banner. Dismisses any existing banner first."""
        from app.theme import Colors, Fonts

        try:
            # Cancel any existing timer before displaying
            self._cancel_timer()

            # Update message
            self._message_text.value = message
            self._message_text.color = (
                Colors.DESTRUCTIVE_FOREGROUND if is_error else Colors.BACKGROUND
            )

            # Update background color
            self._container.bgcolor = Colors.DESTRUCTIVE if is_error else Colors.GOLD

            # Update dismiss button color
            self._dismiss_btn.style = ft.ButtonStyle(
                color=Colors.PRIMARY_FOREGROUND if is_error else Colors.BACKGROUND
            )
            # Set dismiss button font
            self._dismiss_btn.content = ft.Text("OK", font_family=Fonts.FRAKTUR)

            # Handle detail text
            formatted_detail = self._format_detail(detail)
            if formatted_detail:
                self._detail_text.value = formatted_detail
                self._detail_text.color = Colors.MUTED_FOREGROUND
                self._detail_text.visible = True
            else:
                self._detail_text.value = ""
                self._detail_text.visible = False

            # Show the banner
            self._container.visible = True

            # Start auto-dismiss timer only for confirmation banners
            if not is_error:
                timer = threading.Timer(3.0, self._on_auto_dismiss)
                timer.daemon = True
                self._timer = timer
                timer.start()

        except Exception:
            _log(f"ERROR in show:\n{traceback.format_exc()}")
            self._container.visible = False

    def dismiss(self) -> None:
        """Hide the current banner and cancel any pending timer."""
        try:
            # Idempotent — no-op if already hidden
            if not self._container.visible:
                return

            self._cancel_timer()
            self._container.visible = False
            self._bus.safe_update()
        except Exception:
            _log(f"ERROR in dismiss:\n{traceback.format_exc()}")

    def _format_detail(self, detail: str | None) -> str:
        """Truncate detail text to MAX_DETAIL_LENGTH chars + ellipsis if needed."""
        if not detail:
            return ""
        if len(detail) > MAX_DETAIL_LENGTH:
            return detail[:MAX_DETAIL_LENGTH] + "\u2026"
        return detail

    def _on_auto_dismiss(self) -> None:
        """Timer callback — only dismiss if this timer is still the active one."""
        # Check stale reference: if _timer has been replaced, this is a no-op
        current_timer = threading.current_thread()
        if self._timer is not current_timer:
            return
        self.dismiss()

    def _cancel_timer(self) -> None:
        """Cancel any pending auto-dismiss timer."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
