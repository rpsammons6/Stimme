"""New Glossary dialog — prompts for a name and creates a new glossary file.

Validates that the name is non-empty and doesn't conflict with existing
glossary files in the glossaries directory. On confirm, calls
GlossaryManager.create_glossary() and opens the new glossary in a tab.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Callable

import flet as ft

from app.theme import Colors, Fonts

if TYPE_CHECKING:
    from app.event_bus import EventBus


def _log(msg: str) -> None:
    print(f"[NewGlossaryDialog] {msg}")


class NewGlossaryDialog:
    """Modal dialog for creating a new glossary.

    Prompts for a glossary name, validates it's non-empty and doesn't
    conflict with existing files, then creates the glossary and opens
    it in a new tab.
    """

    def __init__(
        self,
        page: ft.Page,
        actions: dict,
        on_created: Callable | None = None,
    ) -> None:
        self._page = page
        self._actions = actions
        self._on_created = on_created
        self._dialog: ft.AlertDialog | None = None
        self._name_field: ft.TextField | None = None
        self._error_text: ft.Text | None = None

    def show(self) -> None:
        """Build and display the new glossary dialog."""
        self._name_field = ft.TextField(
            hint_text="Enter glossary name...",
            autofocus=True,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
            on_submit=self._on_confirm,
        )

        self._error_text = ft.Text(
            "",
            size=11,
            color=Colors.DESTRUCTIVE,
            visible=False,
        )

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "New Glossary",
                size=16,
                weight="bold",
                color=Colors.GOLD,
                font_family=Fonts.HEADER,
            ),
            content=ft.Column(
                [
                    ft.Text(
                        "Enter a name for the new glossary:",
                        size=13,
                        color=Colors.FOREGROUND,
                    ),
                    self._name_field,
                    self._error_text,
                ],
                spacing=12,
                tight=True,
                width=350,
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=self._on_cancel,
                    style=ft.ButtonStyle(color=Colors.INK_MUTED),
                ),
                ft.TextButton(
                    "Create",
                    on_click=self._on_confirm,
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

    def _on_cancel(self, e) -> None:
        """Close the dialog without creating anything."""
        self._close()

    def _on_confirm(self, e) -> None:
        """Validate the name and create the glossary."""
        name = self._name_field.value.strip() if self._name_field else ""

        if not name:
            self._show_error("Glossary name cannot be empty.")
            return

        # Check for existing file conflict
        glossary_mgr = self._actions.get("glossary_manager")
        if glossary_mgr:
            file_name = f"{name.lower().replace(' ', '_')}.glossary"
            existing_files = glossary_mgr.list_glossary_files()
            for existing in existing_files:
                if existing.name.lower() == file_name.lower():
                    self._show_error(f"A glossary named '{name}' already exists.")
                    return

        # Close dialog first
        self._close()

        try:
            if not glossary_mgr:
                _log("No glossary_manager in actions — cannot create glossary")
                return

            # Create the glossary via GlossaryManager
            new_glossary = glossary_mgr.create_glossary(name)

            # Open the new glossary in a tab
            on_open_tab = self._actions.get("on_open_glossary_tab")
            if on_open_tab:
                on_open_tab(new_glossary)

            # Emit glossary_changed event
            bus = self._actions.get("bus")
            if bus:
                bus.emit("glossary_changed")
                bus.show_banner(f"Created glossary: {name}")

            # Invoke created callback
            if self._on_created:
                self._on_created(new_glossary)

        except Exception:
            _log(f"ERROR creating glossary '{name}':\n{traceback.format_exc()}")
            bus = self._actions.get("bus")
            if bus:
                bus.show_banner(f"Failed to create glossary: {name}", is_error=True)

    def _show_error(self, message: str) -> None:
        """Display a validation error in the dialog."""
        if self._error_text:
            self._error_text.value = message
            self._error_text.visible = True
        bus = self._actions.get("bus")
        if bus:
            bus.safe_update()
        else:
            self._page.update()

    def _close(self) -> None:
        """Close the dialog."""
        bus: EventBus | None = self._actions.get("bus")
        if bus:
            bus.close_dialog()
        else:
            if self._dialog:
                self._dialog.open = False
                self._page.update()
