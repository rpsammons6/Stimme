"""Eigenstimme Badge — floating indicator when local LLM mode is active.

Shows a small gold Fraktur badge in the top-right corner reading
"Eigenstimme: ON" when the llm_backend is set to 'local'.
Hidden when using cloud mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from app.theme import Colors, Fonts

if TYPE_CHECKING:
    from app.event_bus import EventBus


class EigenstimmeBadge:
    """Floating badge indicating local LLM mode is active."""

    def __init__(self, bus: "EventBus", initial_backend: str = "cloud"):
        self._bus = bus

        is_active = (initial_backend == "local") or (initial_backend is True)

        self._label = ft.Text(
            value="Eigenstimme: ON",
            size=11,
            color=Colors.WARNING,
            font_family=Fonts.FRAKTUR,
        )
        self._container = ft.Container(
            content=self._label,
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
            bgcolor=Colors.SURFACE_RAISED,
            border=ft.border.all(1, Colors.WARNING),
            border_radius=4,
            top=34,
            right=8,
            visible=is_active,
        )

        # React to config changes
        self._bus.on("config_changed", self._on_config_changed)

    @property
    def control(self) -> ft.Container:
        """Positioned container to add to the root Stack."""
        return self._container

    def set_visible(self, visible: bool) -> None:
        """Show or hide the badge."""
        self._container.visible = visible

    def _on_config_changed(self, key: str, value, **kwargs) -> None:
        if key == "llm_backend":
            is_local = (value == "local") or (value is True)
            self._container.visible = is_local
            try:
                self._bus.page.update()
            except Exception:
                pass
