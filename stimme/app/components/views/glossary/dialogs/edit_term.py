"""Edit Term dialog — modal for editing an existing glossary term.

Displays a pre-filled form with the German field read-only and all other
fields editable. Validates that the English field is non-empty before saving.
On save, calls GlossaryManager.add_term() with updated values and sets the
tab's dirty state.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Callable

import flet as ft

from app.theme import Colors, Fonts

if TYPE_CHECKING:
    from app.event_bus import EventBus
    from app.services.glossary_manager import GlossaryTerm


def _log(msg: str) -> None:
    print(f"[EditTermDialog] {msg}")


class EditTermDialog:
    """Modal dialog for editing a glossary term.

    The German field is displayed read-only (it's the key). English is
    required; context_target, field_tag, and nuance_note are optional.
    """

    def __init__(
        self,
        page: ft.Page,
        term: "GlossaryTerm",
        actions: dict,
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        self._page = page
        self._term = term
        self._actions = actions
        self._on_saved = on_saved
        self._dialog: ft.AlertDialog | None = None

        # Form fields
        self._english_field: ft.TextField | None = None
        self._context_field: ft.TextField | None = None
        self._field_tag_field: ft.TextField | None = None
        self._nuance_field: ft.TextField | None = None
        self._error_text: ft.Text | None = None

    def show(self) -> None:
        """Build and display the edit term dialog."""
        self._english_field = ft.TextField(
            value=self._term.english if self._term.english != "N/A" else "",
            hint_text="English translation (required)",
            autofocus=True,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
            on_submit=self._on_save,
        )

        self._context_field = ft.TextField(
            value=self._term.context_target if self._term.context_target != "N/A" else "",
            hint_text="Context-sensitive target",
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )

        self._field_tag_field = ft.TextField(
            value=self._term.field_tag if self._term.field_tag != "N/A" else "",
            hint_text="Field tag (e.g., Philosophy, Legal)",
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )

        self._nuance_field = ft.TextField(
            value=self._term.nuance_note if self._term.nuance_note != "N/A" else "",
            hint_text="Nuance note",
            multiline=True,
            min_lines=2,
            max_lines=3,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )

        self._error_text = ft.Text(
            "",
            size=11,
            color=Colors.DESTRUCTIVE,
            visible=False,
        )

        german_display = ft.TextField(
            value=self._term.german,
            read_only=True,
            bgcolor=Colors.MUTED,
            border_color=Colors.DIVIDER,
            color=Colors.INK_MUTED,
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"Edit: {self._term.german}",
                size=16,
                weight="bold",
                color=Colors.GOLD,
                font_family=Fonts.HEADER,
            ),
            content=ft.Column(
                [
                    ft.Text("German (read-only)", size=11, color=Colors.INK_MUTED),
                    german_display,
                    ft.Text("English *", size=11, color=Colors.INK_MUTED),
                    self._english_field,
                    ft.Text("Context Target", size=11, color=Colors.INK_MUTED),
                    self._context_field,
                    ft.Text("Field Tag", size=11, color=Colors.INK_MUTED),
                    self._field_tag_field,
                    ft.Text("Nuance Note", size=11, color=Colors.INK_MUTED),
                    self._nuance_field,
                    self._error_text,
                ],
                spacing=6,
                tight=True,
                width=400,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=self._on_cancel,
                    style=ft.ButtonStyle(color=Colors.INK_MUTED),
                ),
                ft.TextButton(
                    "Save",
                    on_click=self._on_save,
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
        """Close the dialog without saving."""
        self._close()

    def _on_save(self, e) -> None:
        """Validate and save the edited term."""
        english = self._english_field.value.strip() if self._english_field else ""

        if not english:
            if self._error_text:
                self._error_text.value = "English translation is required."
                self._error_text.visible = True
            bus = self._actions.get("bus")
            if bus:
                bus.safe_update()
            else:
                self._page.update()
            return

        # Clear error
        if self._error_text:
            self._error_text.visible = False

        # Gather values
        context_target = self._context_field.value.strip() if self._context_field else ""
        field_tag = self._field_tag_field.value.strip() if self._field_tag_field else ""
        nuance_note = self._nuance_field.value.strip() if self._nuance_field else ""

        # Close dialog first
        self._close()

        try:
            glossary_mgr = self._actions.get("glossary_manager")
            if not glossary_mgr:
                _log("No glossary_manager in actions — cannot save term")
                return

            # add_term overwrites existing term with same German key
            glossary_mgr.add_term(
                german=self._term.german,
                english=english,
                context_target=context_target,
                field_tag=field_tag,
                nuance_note=nuance_note,
            )

            # Notify dirty state change
            on_dirty_changed = self._actions.get("on_dirty_changed")
            if on_dirty_changed:
                on_dirty_changed()

            # Emit glossary_changed event
            bus = self._actions.get("bus")
            if bus:
                bus.emit("glossary_changed")

            # Invoke saved callback
            if self._on_saved:
                self._on_saved()

        except Exception:
            _log(f"ERROR saving term:\n{traceback.format_exc()}")
            bus = self._actions.get("bus")
            if bus:
                bus.show_banner(f"Failed to save term: {self._term.german}", is_error=True)

    def _close(self) -> None:
        """Close the dialog."""
        bus: EventBus | None = self._actions.get("bus")
        if bus:
            bus.close_dialog()
        else:
            if self._dialog:
                self._dialog.open = False
                self._page.update()
