"""Save Changes dialog — prompts user before closing a dirty glossary tab.

Presents three options:
- Save: saves the glossary via GlossaryManager, then closes the tab.
- Don't Save: closes the tab without saving.
- Cancel: keeps the tab open (no action).
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Callable

import flet as ft

from app.theme import Colors, Fonts

if TYPE_CHECKING:
    from app.event_bus import EventBus
    from app.services.glossary_manager import GlossaryFile


def _log(msg: str) -> None:
    print(f"[SaveChangesDialog] {msg}")


class SaveChangesDialog:
    """Modal dialog for unsaved changes confirmation on tab close.

    Provides Save, Don't Save, and Cancel options. The caller provides
    callbacks for each action so the dialog remains decoupled from
    tab management logic.
    """

    def __init__(
        self,
        page: ft.Page,
        glossary_name: str,
        actions: dict,
        on_save: Callable[[], None] | None = None,
        on_dont_save: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self._page = page
        self._glossary_name = glossary_name
        self._actions = actions
        self._on_save = on_save
        self._on_dont_save = on_dont_save
        self._on_cancel = on_cancel
        self._dialog: ft.AlertDialog | None = None

    def show(self) -> None:
        """Build and display the save changes dialog."""
        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Save Changes?",
                size=16,
                weight="bold",
                color=Colors.GOLD,
                font_family=Fonts.HEADER,
            ),
            content=ft.Text(
                f'Do you want to save changes to "{self._glossary_name}"?',
                size=13,
                color=Colors.FOREGROUND,
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=self._handle_cancel,
                    style=ft.ButtonStyle(color=Colors.INK_MUTED),
                ),
                ft.TextButton(
                    "Don't Save",
                    on_click=self._handle_dont_save,
                    style=ft.ButtonStyle(color=Colors.DESTRUCTIVE),
                ),
                ft.TextButton(
                    "Save",
                    on_click=self._handle_save,
                    style=ft.ButtonStyle(color=Colors.GOLD),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=Colors.BACKGROUND,
        )

        bus: EventBus | None = self._actions.get("bus")
        if bus:
            bus.show_dialog(self._dialog)
        else:
            self._page.dialog = self._dialog
            self._dialog.open = True
            self._page.update()

    def _handle_save(self, e) -> None:
        """Save the glossary, then close the tab."""
        self._close()
        try:
            if self._on_save:
                self._on_save()
        except Exception:
            _log(f"ERROR in save callback:\n{traceback.format_exc()}")

    def _handle_dont_save(self, e) -> None:
        """Close the tab without saving."""
        self._close()
        try:
            if self._on_dont_save:
                self._on_dont_save()
        except Exception:
            _log(f"ERROR in don't save callback:\n{traceback.format_exc()}")

    def _handle_cancel(self, e) -> None:
        """Keep the tab open — no action."""
        self._close()
        try:
            if self._on_cancel:
                self._on_cancel()
        except Exception:
            _log(f"ERROR in cancel callback:\n{traceback.format_exc()}")

    def _close(self) -> None:
        """Close the dialog."""
        bus: EventBus | None = self._actions.get("bus")
        if bus:
            bus.close_dialog()
        else:
            if self._dialog:
                self._dialog.open = False
                self._page.update()
