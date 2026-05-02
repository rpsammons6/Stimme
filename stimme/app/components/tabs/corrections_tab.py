"""CorrectionsTab — displays and manages committed correction records from LanceDB.

Feature: hitl-workflow
Requirements: 9.1, 9.2, 9.3, 9.4
"""

import traceback
from datetime import datetime

import flet as ft

from app.event_bus import EventBus
from app.services.correction_service import CorrectionService
from app.theme import Colors, Fonts


def _log(msg):
    print(f"[CorrectionsTab] {msg}")


class CorrectionsTab:
    """Displays and manages correction records from LanceDB."""

    def __init__(
        self,
        page: ft.Page,
        correction_service: CorrectionService,
        bus: EventBus,
    ) -> None:
        self._page = page
        self._correction_service = correction_service
        self._bus = bus
        self._container = ft.Column(expand=True, spacing=0)

    def build(self) -> ft.Control:
        """Build the corrections list view with delete buttons.
        Shows placeholder when empty.
        """
        self._rebuild_content()
        return self._container

    def refresh(self) -> None:
        """Rebuild the content and update the page."""
        self._rebuild_content()
        try:
            self._page.update()
        except Exception:
            _log(f"ERROR in refresh update:\n{traceback.format_exc()}")

    def _rebuild_content(self) -> None:
        """Fetch corrections and rebuild the list."""
        self._container.controls.clear()

        records = self._correction_service.get_corrections()

        if not records:
            self._container.controls.append(self._build_empty_state())
            return

        # Header
        self._container.controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(
                            "Corrections",
                            size=24,
                            font_family=Fonts.HEADER,
                            color=Colors.GOLD,
                        ),
                        ft.Container(expand=True),
                        ft.Text(
                            f"{len(records)} correction{'s' if len(records) != 1 else ''}",
                            size=11,
                            color=Colors.INK_MUTED,
                            italic=True,
                        ),
                    ],
                    spacing=10,
                ),
                padding=ft.padding.symmetric(horizontal=16, vertical=12),
            )
        )

        # Scrollable list of correction cards
        cards = []
        for record in records:
            cards.append(self._build_card(record))

        self._container.controls.append(
            ft.ListView(controls=cards, expand=True, spacing=8, padding=ft.padding.symmetric(horizontal=16))
        )

    def _build_empty_state(self) -> ft.Control:
        """Build the empty state placeholder."""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=48, color=Colors.INK_MUTED),
                    ft.Text(
                        "No corrections committed yet.",
                        size=14,
                        color=Colors.INK_MUTED,
                        italic=True,
                        font_family=Fonts.SERIF,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "Edit a translation and choose 'Commit to Memory'\nto teach Stimme your style.",
                        size=12,
                        color=Colors.INK_MUTED,
                        font_family=Fonts.SERIF,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
            ),
            alignment=ft.alignment.center,
            expand=True,
        )

    def _build_card(self, record) -> ft.Control:
        """Build a single correction record card."""
        # Format timestamp
        try:
            ts = datetime.fromisoformat(record.timestamp)
            time_str = ts.strftime("%Y-%m-%d %H:%M")
        except Exception:
            time_str = record.timestamp

        return ft.Container(
            content=ft.Column(
                [
                    # Row: DE source + delete button
                    ft.Row(
                        [
                            ft.Text("DE:", size=11, color=Colors.GOLD, weight="bold"),
                            ft.Text(
                                record.german_source,
                                size=13,
                                color=Colors.GOLD,
                                font_family=Fonts.SERIF,
                                expand=True,
                                no_wrap=False,
                                selectable=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=Colors.DESTRUCTIVE,
                                icon_size=18,
                                tooltip="Delete correction",
                                on_click=lambda e, rid=record.id: self._on_delete(rid),
                            ),
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    # Original translation
                    ft.Row(
                        [
                            ft.Text("Original:", size=11, color=Colors.INK_MUTED, weight="bold"),
                            ft.Text(
                                record.original_translation,
                                size=13,
                                color=Colors.INK_MUTED,
                                font_family=Fonts.SERIF,
                                expand=True,
                                no_wrap=False,
                                selectable=True,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    # Corrected translation
                    ft.Row(
                        [
                            ft.Text("Corrected:", size=11, color=Colors.FOREGROUND, weight="bold"),
                            ft.Text(
                                record.corrected_translation,
                                size=13,
                                color=Colors.FOREGROUND,
                                font_family=Fonts.SERIF,
                                expand=True,
                                no_wrap=False,
                                selectable=True,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    # Timestamp
                    ft.Text(
                        time_str,
                        size=10,
                        color=Colors.INK_MUTED,
                        font_family=Fonts.MONO,
                    ),
                ],
                spacing=6,
            ),
            bgcolor=Colors.SURFACE,
            border=ft.border.all(1, Colors.DIVIDER),
            border_radius=8,
            padding=ft.padding.all(14),
        )

    def _on_delete(self, record_id: str) -> None:
        """Delete a correction record and refresh the view."""
        try:
            success = self._correction_service.delete_correction(record_id)
            if success:
                self._bus.show_banner("Correction deleted.")
            else:
                self._bus.show_banner("Failed to delete correction.", is_error=True)
        except Exception:
            _log(f"ERROR deleting correction {record_id}:\n{traceback.format_exc()}")
            self._bus.show_banner("Failed to delete correction.", is_error=True)
        self.refresh()
