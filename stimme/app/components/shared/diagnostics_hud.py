"""Diagnostics HUD — lightweight performance overlay.

Shows CPU%, RAM (MB), and page.update() latency in the bottom-left corner.
Toggled via the 'diagnostics_hud' setting in Preferences.
"""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from app.event_bus import EventBus

_FONT = "Consolas"
_UPDATE_INTERVAL = 1.0  # seconds


class DiagnosticsHUD:
    """Self-contained diagnostics overlay widget."""

    def __init__(self, page: ft.Page, bus: "EventBus"):
        self._page = page
        self._bus = bus
        self._visible = False
        self._timer: threading.Timer | None = None
        self._last_update_ms: float = 0.0

        # Metrics
        self._cpu_pct: float = 0.0
        self._ram_mb: float = 0.0
        self._update_latency_ms: float = 0.0

        # UI controls
        self._label = ft.Text(
            value="CPU: --% | RAM: -- MB | Δ: -- ms",
            size=11,
            color="#88ffffff",
            font_family=_FONT,
        )
        self._container = ft.Container(
            content=self._label,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            bgcolor="#cc000000",
            border_radius=4,
            bottom=8,
            left=8,
            visible=False,
        )

        # Listen for setting changes
        self._bus.on("config_changed", self._on_config_changed)

        # Initialize psutil process handle (lazy)
        self._process = None

    @property
    def control(self) -> ft.Container:
        """Return the positioned container to add to a Stack."""
        return self._container

    def set_visible(self, visible: bool) -> None:
        """Show or hide the HUD and start/stop polling."""
        self._visible = visible
        self._container.visible = visible
        if visible:
            self._ensure_process()
            self._start_polling()
        else:
            self._stop_polling()

    def record_update_latency(self, ms: float) -> None:
        """Called by the EventBus after each page.update() to record latency."""
        self._last_update_ms = ms

    def cleanup(self) -> None:
        """Stop the timer thread."""
        self._stop_polling()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_config_changed(self, key: str, value, **kwargs) -> None:
        if key == "diagnostics_hud":
            self.set_visible(bool(value))
            try:
                self._page.update()
            except Exception:
                pass

    def _ensure_process(self) -> None:
        if self._process is None:
            import psutil
            self._process = psutil.Process(os.getpid())
            # Prime cpu_percent (first call always returns 0)
            self._process.cpu_percent(interval=None)

    def _start_polling(self) -> None:
        self._stop_polling()
        self._poll_tick()

    def _stop_polling(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _poll_tick(self) -> None:
        if not self._visible:
            return

        try:
            self._cpu_pct = self._process.cpu_percent(interval=None)
            mem_info = self._process.memory_info()
            self._ram_mb = mem_info.rss / (1024 * 1024)
            self._update_latency_ms = self._last_update_ms

            # Format the display
            cpu_str = f"{self._cpu_pct:4.1f}%"
            ram_str = f"{self._ram_mb:.0f} MB"
            latency_str = f"{self._update_latency_ms:.0f} ms"

            self._label.value = f"CPU: {cpu_str} | RAM: {ram_str} | Δ: {latency_str}"

            # Color the latency indicator based on severity
            if self._update_latency_ms > 500:
                self._label.color = "#ffff4444"  # red — hanging
            elif self._update_latency_ms > 100:
                self._label.color = "#ffffaa00"  # amber — sluggish
            else:
                self._label.color = "#88ffffff"  # normal

            try:
                self._page.update()
            except Exception:
                pass
        except Exception:
            pass

        # Schedule next tick
        if self._visible:
            self._timer = threading.Timer(_UPDATE_INTERVAL, self._poll_tick)
            self._timer.daemon = True
            self._timer.start()
