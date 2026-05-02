"""Version navigation control for a segment in ParallelView."""

from typing import Callable

import flet as ft

from app.models.version_store import VersionStore
from app.theme import Colors, Fonts


class VersionNav:
    """Version navigation control for a segment in ParallelView.

    Renders: ``< v2/5 > [Compare] [Accept]``

    Only visible when the segment has more than one version.
    """

    def __init__(
        self,
        tab_id: int,
        segment_index: int,
        version_store: VersionStore,
        on_compare: Callable,
        on_accept: Callable,
    ) -> None:
        self.tab_id = tab_id
        self.segment_index = segment_index
        self.version_store = version_store
        self.on_compare = on_compare
        self.on_accept = on_accept

    @property
    def visible(self) -> bool:
        """Return False when the segment has 1 or fewer versions."""
        return self.version_store.get_version_count(self.tab_id, self.segment_index) > 1

    def _active_index(self) -> int:
        versions = self.version_store.get_versions(self.tab_id, self.segment_index)
        if not versions:
            return 0
        idx = self.version_store._active.get(self.tab_id, {}).get(self.segment_index, 0)
        return max(0, min(idx, len(versions) - 1))

    def _go_prev(self, e: ft.ControlEvent) -> None:
        idx = self._active_index()
        if idx > 0:
            self.version_store.set_active_version(
                self.tab_id, self.segment_index, idx - 1
            )

    def _go_next(self, e: ft.ControlEvent) -> None:
        idx = self._active_index()
        total = self.version_store.get_version_count(self.tab_id, self.segment_index)
        if idx < total - 1:
            self.version_store.set_active_version(
                self.tab_id, self.segment_index, idx + 1
            )

    def _handle_compare(self, e: ft.ControlEvent) -> None:
        self.on_compare(self.tab_id, self.segment_index)

    def _handle_accept(self, e: ft.ControlEvent) -> None:
        self.on_accept(self.tab_id, self.segment_index)

    def build(self) -> ft.Control:
        """Build the version nav: ``< v2/5 > [Compare] [Accept]``."""
        idx = self._active_index()
        total = self.version_store.get_version_count(self.tab_id, self.segment_index)

        prev_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            icon_size=16,
            icon_color=Colors.INK_MUTED,
            on_click=self._go_prev,
            style=ft.ButtonStyle(padding=ft.padding.all(0)),
            width=24,
            height=24,
        )

        version_label = ft.Text(
            f"v{idx + 1}/{total}",
            size=11,
            color=Colors.GOLD,
            font_family=Fonts.MONO,
        )

        next_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            icon_size=16,
            icon_color=Colors.INK_MUTED,
            on_click=self._go_next,
            style=ft.ButtonStyle(padding=ft.padding.all(0)),
            width=24,
            height=24,
        )

        compare_btn = ft.TextButton(
            text="Compare",
            style=ft.ButtonStyle(
                color=Colors.INK_MUTED,
                padding=ft.padding.symmetric(horizontal=4),
                text_style=ft.TextStyle(size=11, font_family=Fonts.FRAKTUR),
            ),
            on_click=self._handle_compare,
        )

        accept_btn = ft.TextButton(
            text="Accept",
            style=ft.ButtonStyle(
                color=Colors.GOLD,
                padding=ft.padding.symmetric(horizontal=4),
                text_style=ft.TextStyle(size=11, font_family=Fonts.FRAKTUR),
            ),
            on_click=self._handle_accept,
        )

        return ft.Row(
            controls=[prev_btn, version_label, next_btn, compare_btn, accept_btn],
            spacing=2,
            visible=self.visible,
        )
