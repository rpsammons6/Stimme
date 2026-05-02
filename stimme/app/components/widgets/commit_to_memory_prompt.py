"""Non-blocking prompt asking user to commit correction to memory."""

from typing import Callable

import flet as ft

from app.theme import Colors, Fonts


class CommitToMemoryPrompt:
    """Non-blocking prompt asking user to commit correction to memory.

    Displays a non-modal AlertDialog with Yes/No options after a manual
    correction is saved. The dialog is dismissible and does not block
    user interaction.
    """

    def __init__(
        self,
        page: ft.Page,
        on_yes: Callable[[], None],
        on_no: Callable[[], None],
    ) -> None:
        self.page = page
        self.on_yes = on_yes
        self.on_no = on_no
        self._dialog: ft.AlertDialog | None = None

    def _close(self) -> None:
        """Close the dialog."""
        if self._dialog is not None:
            self._dialog.open = False
            self.page.update()

    def _handle_yes(self, e: ft.ControlEvent) -> None:
        self._close()
        self.on_yes()

    def _handle_no(self, e: ft.ControlEvent) -> None:
        self._close()
        self.on_no()

    def show(self) -> None:
        """Display the prompt as a non-modal dialog."""
        self._dialog = ft.AlertDialog(
            modal=False,
            title=ft.Text(
                "Commit to Memory",
                font_family=Fonts.HEADER,
                color=Colors.GOLD,
                size=18,
            ),
            content=ft.Text(
                "Commit this correction to memory? "
                "Stimme will use it to improve future translations.",
                color=Colors.FOREGROUND,
                font_family=Fonts.SERIF,
                size=13,
            ),
            actions=[
                ft.TextButton(
                    text="Yes",
                    style=ft.ButtonStyle(color=Colors.GOLD, text_style=ft.TextStyle(font_family=Fonts.FRAKTUR)),
                    on_click=self._handle_yes,
                ),
                ft.TextButton(
                    text="No",
                    style=ft.ButtonStyle(color=Colors.INK_MUTED, text_style=ft.TextStyle(font_family=Fonts.FRAKTUR)),
                    on_click=self._handle_no,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=Colors.SURFACE,
            shape=ft.RoundedRectangleBorder(radius=8),
        )
        self.page.dialog = self._dialog
        self._dialog.open = True
        self.page.update()
