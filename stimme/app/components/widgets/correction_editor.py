"""Inline editor that replaces read-only text with an editable field."""

from typing import Callable

import flet as ft

from app.theme import Colors, Fonts


class CorrectionEditor:
    """Inline editor that replaces read-only text with an editable field.

    When activated, displays a multiline TextField pre-filled with the current
    translation text, plus Save and Cancel buttons. Save calls on_save with the
    edited text (or on_cancel if text is unchanged). Cancel calls on_cancel to
    restore the original read-only display.
    """

    def __init__(
        self,
        current_text: str,
        on_save: Callable[[str], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self.current_text = current_text
        self.on_save = on_save
        self.on_cancel = on_cancel
        self._text_field = ft.TextField(
            value=current_text,
            multiline=True,
            min_lines=2,
            max_lines=8,
            bgcolor=Colors.SURFACE,
            color=Colors.FOREGROUND,
            border_color=Colors.DIVIDER,
            cursor_color=Colors.GOLD,
            selection_color=Colors.SECONDARY,
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.all(12),
            border_radius=6,
            expand=True,
        )

    def _handle_save(self, e: ft.ControlEvent) -> None:
        edited_text = self._text_field.value or ""
        if edited_text == self.current_text:
            self.on_cancel()
        else:
            self.on_save(edited_text)

    def _handle_cancel(self, e: ft.ControlEvent) -> None:
        self.on_cancel()

    def build(self) -> ft.Control:
        """Build editable text field with Save/Cancel buttons."""
        save_btn = ft.TextButton(
            text="Save",
            style=ft.ButtonStyle(color=Colors.GOLD, text_style=ft.TextStyle(font_family=Fonts.FRAKTUR)),
            on_click=self._handle_save,
        )
        cancel_btn = ft.TextButton(
            text="Cancel",
            style=ft.ButtonStyle(color=Colors.INK_MUTED, text_style=ft.TextStyle(font_family=Fonts.FRAKTUR)),
            on_click=self._handle_cancel,
        )
        return ft.Column(
            controls=[
                self._text_field,
                ft.Row(
                    controls=[save_btn, cancel_btn],
                    spacing=8,
                ),
            ],
            spacing=4,
        )
