"""GlossaryToolbar: New/Open/Save/Save As buttons with term count display.

Provides the toolbar row for glossary tab operations including creating new
glossaries, opening existing files, saving changes, and Save As to a new
location. Displays the current term count alongside the action buttons.
"""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, Callable

import flet as ft

from app.theme import Colors, Fonts

if TYPE_CHECKING:
    from .glossary_tab_state import GlossaryTabState

logger = logging.getLogger(__name__)


def _log(msg: str) -> None:
    print(f"[GlossaryToolbar] {msg}")


class GlossaryToolbar:
    """Toolbar with New/Open/Save/Save As buttons and term count indicator.

    Integrates with GlossaryManager for file operations and emits
    glossary_changed events via the EventBus on successful saves.
    """

    def __init__(
        self,
        page: ft.Page,
        state: "GlossaryTabState",
        actions: dict,
    ) -> None:
        self._page = page
        self._state = state
        self._actions = actions
        self._term_count_text: ft.Text | None = None
        self._open_picker: ft.FilePicker | None = None
        self._save_as_picker: ft.FilePicker | None = None
        self._new_glossary_dialog: ft.AlertDialog | None = None
        self._name_field: ft.TextField | None = None

    def build(self) -> ft.Control:
        """Build the toolbar row: New | Open | Save | Save As + term count."""
        # Set up file pickers
        self._open_picker = ft.FilePicker(on_result=self._on_open_result)
        self._save_as_picker = ft.FilePicker(on_result=self._on_save_as_result)

        # Add pickers to page overlay so they can function
        self._page.overlay.append(self._open_picker)
        self._page.overlay.append(self._save_as_picker)

        add_term_btn = ft.TextButton(
            text="Add Term",
            icon=ft.Icons.BOOKMARK_ADD,
            on_click=self._on_add_term,
            tooltip="Add a new term to this glossary",
            style=ft.ButtonStyle(color=Colors.GOLD),
        )

        new_btn = ft.TextButton(
            text="New",
            icon=ft.Icons.NOTE_ADD_OUTLINED,
            on_click=self._on_new_glossary,
            tooltip="Create a new glossary",
            style=ft.ButtonStyle(color=Colors.FOREGROUND),
        )

        open_btn = ft.TextButton(
            text="Open",
            icon=ft.Icons.FOLDER_OPEN_OUTLINED,
            on_click=self._on_open_glossary,
            tooltip="Open a glossary file (.glossary or .csv)",
            style=ft.ButtonStyle(color=Colors.FOREGROUND),
        )

        save_btn = ft.TextButton(
            text="Save",
            icon=ft.Icons.SAVE_OUTLINED,
            on_click=self._on_save,
            tooltip="Save current glossary",
            style=ft.ButtonStyle(color=Colors.FOREGROUND),
        )

        save_as_btn = ft.TextButton(
            text="Save As",
            icon=ft.Icons.SAVE_AS_OUTLINED,
            on_click=self._on_save_as,
            tooltip="Save glossary to a new location",
            style=ft.ButtonStyle(color=Colors.FOREGROUND),
        )

        self._term_count_text = ft.Text(
            self._format_term_count(),
            size=11,
            color=Colors.INK_MUTED,
            italic=True,
        )

        return ft.Container(
            content=ft.Row(
                [
                    add_term_btn,
                    ft.VerticalDivider(width=1, color=Colors.DIVIDER),
                    new_btn,
                    ft.VerticalDivider(width=1, color=Colors.DIVIDER),
                    open_btn,
                    ft.VerticalDivider(width=1, color=Colors.DIVIDER),
                    save_btn,
                    save_as_btn,
                    ft.Container(expand=True),
                    self._term_count_text,
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=6),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

    def update_term_count(self) -> None:
        """Refresh the term count display from current state."""
        if self._term_count_text is not None:
            self._term_count_text.value = self._format_term_count()

    # ------------------------------------------------------------------
    # New Glossary
    # ------------------------------------------------------------------

    def _on_new_glossary(self, e) -> None:
        """Show a dialog prompting for the new glossary name."""
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
            on_submit=self._on_new_glossary_confirm,
        )

        self._new_glossary_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("New Glossary", size=16, weight="bold", color=Colors.GOLD),
            content=ft.Column(
                [
                    ft.Text(
                        "Enter a name for the new glossary:",
                        size=13,
                        color=Colors.FOREGROUND,
                    ),
                    self._name_field,
                ],
                spacing=12,
                tight=True,
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=self._on_new_glossary_cancel,
                    style=ft.ButtonStyle(color=Colors.INK_MUTED),
                ),
                ft.TextButton(
                    "Create",
                    on_click=self._on_new_glossary_confirm,
                    style=ft.ButtonStyle(color=Colors.GOLD),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=Colors.BACKGROUND,
        )

        bus = self._actions.get("bus")
        if bus:
            bus.show_dialog(self._new_glossary_dialog)
        else:
            self._page.dialog = self._new_glossary_dialog
            self._new_glossary_dialog.open = True
            self._page.update()

    def _on_new_glossary_cancel(self, e) -> None:
        """Close the new glossary dialog without action."""
        bus = self._actions.get("bus")
        if bus:
            bus.close_dialog()
        else:
            if self._new_glossary_dialog:
                self._new_glossary_dialog.open = False
                self._page.update()

    def _on_new_glossary_confirm(self, e) -> None:
        """Create the new glossary and open it in a new tab."""
        name = self._name_field.value.strip() if self._name_field else ""
        if not name:
            return

        # Close dialog first
        bus = self._actions.get("bus")
        if bus:
            bus.close_dialog()
        else:
            if self._new_glossary_dialog:
                self._new_glossary_dialog.open = False
                self._page.update()

        try:
            glossary_mgr = self._actions.get("glossary_manager")
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
            if bus:
                bus.emit("glossary_changed")
                bus.show_banner(f"Created glossary: {name}")

        except Exception:
            _log(f"ERROR creating glossary '{name}':\n{traceback.format_exc()}")
            if bus:
                bus.show_banner(f"Failed to create glossary: {name}", is_error=True)

    # ------------------------------------------------------------------
    # Add Term
    # ------------------------------------------------------------------

    def _on_add_term(self, e) -> None:
        """Open a dialog to add a new term to the current glossary."""
        german_field = ft.TextField(
            hint_text="e.g. Geist",
            autofocus=True,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )
        english_field = ft.TextField(
            hint_text="e.g. Spirit",
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )
        context_target_field = ft.TextField(
            hint_text="e.g. deconstruct",
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )
        field_tag_field = ft.TextField(
            hint_text="e.g. Philosophy, Legal, Science…",
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )
        nuance_note_field = ft.TextField(
            hint_text="Briefly explain the semantic shift…",
            multiline=True,
            min_lines=2,
            max_lines=4,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
        )

        error_text = ft.Text("", size=11, color=Colors.DESTRUCTIVE, visible=False)

        bus = self._actions.get("bus")

        def on_save(dialog_e):
            try:
                german = german_field.value.strip() if german_field.value else ""
                english = english_field.value.strip() if english_field.value else ""
                context_target = context_target_field.value.strip() if context_target_field.value else ""
                field_tag = field_tag_field.value.strip() if field_tag_field.value else ""
                nuance_note = nuance_note_field.value.strip() if nuance_note_field.value else ""

                _log(f"ADD TERM: german='{german}', english='{english}'")

                if not german or not english:
                    error_text.value = "German and English fields are required."
                    error_text.visible = True
                    self._page.update()
                    _log("ADD TERM: Validation failed — german or english empty")
                    return

                # Add term directly to this tab's glossary file
                from datetime import datetime
                from app.services.glossary_manager import GlossaryTerm

                glossary = self._state.glossary
                _log(f"ADD TERM: Target glossary='{glossary.name}', file_path={glossary.file_path}, current_terms={len(glossary.terms)}")

                new_term = GlossaryTerm(
                    german=german,
                    english=english,
                    context_target=context_target or "N/A",
                    field_tag=field_tag or "N/A",
                    nuance_note=nuance_note or "N/A",
                    created_at=datetime.now().isoformat(),
                )

                # Remove existing term with same german key (case-insensitive)
                before_count = len(glossary.terms)
                glossary.terms = [
                    t for t in glossary.terms
                    if t.german.strip().lower() != german.lower()
                ]
                after_dedup = len(glossary.terms)
                glossary.terms.append(new_term)
                _log(f"ADD TERM: before={before_count}, after_dedup={after_dedup}, after_add={len(glossary.terms)}")

                # Mark dirty and refresh the term list display
                self._state.is_dirty = True
                # Update filtered_terms so the ListView shows the new term immediately
                self._state.filtered_terms = list(glossary.terms)
                self._state.visible_count = min(100, len(self._state.filtered_terms))
                _log(f"ADD TERM: Marked dirty. is_dirty={self._state.is_dirty}, filtered_terms={len(self._state.filtered_terms)}")

                on_dirty_changed = self._actions.get("on_dirty_changed")
                if on_dirty_changed:
                    on_dirty_changed()
                    _log("ADD TERM: on_dirty_changed callback invoked")
                else:
                    _log("ADD TERM: WARNING — no on_dirty_changed callback in actions")

                # Close dialog
                if bus:
                    bus.close_dialog()
                    bus.emit("glossary_changed")
                    _log("ADD TERM: glossary_changed emitted")
                    # Trigger row highlight
                    highlight = self._actions.get("highlight_term")
                    if highlight:
                        highlight(german)
                else:
                    add_dialog.open = False
                    self._page.update()

            except Exception:
                _log(f"ERROR in add term on_save:\n{traceback.format_exc()}")

        def on_cancel(dialog_e):
            if bus:
                bus.close_dialog()
            else:
                add_dialog.open = False
                self._page.update()

        add_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Add Glossary Term", size=16, weight="bold", color=Colors.GOLD),
            content=ft.Column(
                [
                    ft.Text("German Term *", size=12, color=Colors.INK_MUTED),
                    german_field,
                    ft.Text("English (default equivalent) *", size=12, color=Colors.INK_MUTED),
                    english_field,
                    ft.Text("Context-Sensitive Target", size=12, color=Colors.INK_MUTED),
                    context_target_field,
                    ft.Text("Field Tag", size=12, color=Colors.INK_MUTED),
                    field_tag_field,
                    ft.Text("Nuance Note", size=12, color=Colors.INK_MUTED),
                    nuance_note_field,
                    error_text,
                ],
                spacing=8,
                tight=True,
                width=340,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=on_cancel,
                    style=ft.ButtonStyle(color=Colors.INK_MUTED),
                ),
                ft.ElevatedButton(
                    content=ft.Text("Save", weight="bold"),
                    on_click=on_save,
                    bgcolor=Colors.GOLD,
                    color=Colors.BACKGROUND,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=Colors.BACKGROUND,
        )

        if bus:
            bus.show_dialog(add_dialog)
        else:
            self._page.dialog = add_dialog
            add_dialog.open = True
            self._page.update()

    # ------------------------------------------------------------------
    # Open Glossary
    # ------------------------------------------------------------------

    def _on_open_glossary(self, e) -> None:
        """Open a file picker for .glossary and .csv files."""
        if self._open_picker:
            self._open_picker.pick_files(
                dialog_title="Open Glossary",
                allowed_extensions=["glossary", "csv"],
                allow_multiple=False,
            )

    def _on_open_result(self, e: ft.FilePickerResultEvent) -> None:
        """Handle the file picker result for opening a glossary."""
        if not e.files:
            return  # User cancelled

        file_path = e.files[0].path
        if not file_path:
            return

        from pathlib import Path

        path = Path(file_path)
        suffix = path.suffix.lower()

        bus = self._actions.get("bus")
        glossary_mgr = self._actions.get("glossary_manager")

        if not glossary_mgr:
            _log("No glossary_manager in actions — cannot open file")
            return

        try:
            if suffix == ".glossary":
                glossary = glossary_mgr.load_glossary(path)
            elif suffix == ".csv":
                # Import CSV as a new glossary
                glossary, conflicts = glossary_mgr.import_glossary(path)
                # If there are conflicts, let the conflict resolution handler deal with them
                on_conflicts = self._actions.get("on_import_conflicts")
                if conflicts and on_conflicts:
                    on_conflicts(conflicts)
            else:
                if bus:
                    bus.show_banner(
                        "Only .glossary and .csv files are supported",
                        is_error=True,
                    )
                return

            # Open the glossary in a new tab
            on_open_tab = self._actions.get("on_open_glossary_tab")
            if on_open_tab:
                on_open_tab(glossary)

        except FileNotFoundError:
            if bus:
                bus.show_banner(f"Glossary file not found: {path}", is_error=True)
        except ValueError as exc:
            error_msg = str(exc)
            if "csv" in suffix:
                error_msg = (
                    "Error: Failed to import .csv to Glossaries. "
                    "Please compare the format of your CSV to the documentation and try again."
                )
            if bus:
                bus.show_banner(error_msg, is_error=True)
        except Exception as exc:
            _log(f"ERROR opening file '{path}':\n{traceback.format_exc()}")
            if bus:
                bus.show_banner(f"Failed to open file: {exc}", is_error=True)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self, e) -> None:
        """Save the current glossary and clear dirty state."""
        glossary_mgr = self._actions.get("glossary_manager")
        bus = self._actions.get("bus")

        if not glossary_mgr:
            _log("SAVE: No glossary_manager in actions — cannot save")
            return

        glossary = self._state.glossary
        _log(f"SAVE: glossary='{glossary.name}', file_path={glossary.file_path}, terms={len(glossary.terms)}, is_dirty={self._state.is_dirty}")

        try:
            glossary_mgr.save_glossary(self._state.glossary)
            self._state.is_dirty = False
            _log(f"SAVE: Success. Written to {glossary.file_path}")

            # Notify the tab view to update the tab title
            on_dirty_changed = self._actions.get("on_dirty_changed")
            if on_dirty_changed:
                on_dirty_changed()

            # Emit glossary_changed event
            if bus:
                bus.emit("glossary_changed")

        except ValueError as exc:
            _log(f"SAVE ERROR (ValueError): {exc}")
            if bus:
                bus.show_banner(f"Failed to save glossary: {exc}", is_error=True)
        except (OSError, PermissionError) as exc:
            _log(f"SAVE ERROR (disk): {exc}")
            if bus:
                bus.show_banner(f"Failed to save glossary: {exc}", is_error=True)

    # ------------------------------------------------------------------
    # Save As
    # ------------------------------------------------------------------

    def _on_save_as(self, e) -> None:
        """Open a file picker for save location."""
        if self._save_as_picker:
            self._save_as_picker.save_file(
                dialog_title="Save Glossary As",
                allowed_extensions=["glossary"],
                file_name=f"{self._state.glossary.name or 'untitled'}.glossary",
            )

    def _on_save_as_result(self, e: ft.FilePickerResultEvent) -> None:
        """Handle the file picker result for Save As."""
        if not e.path:
            return  # User cancelled

        from pathlib import Path

        save_path = Path(e.path)
        bus = self._actions.get("bus")
        glossary_mgr = self._actions.get("glossary_manager")

        if not glossary_mgr:
            _log("No glossary_manager in actions — cannot save as")
            return

        try:
            # Ensure .glossary extension
            if save_path.suffix.lower() != ".glossary":
                save_path = save_path.with_suffix(".glossary")

            # Update the glossary's file_path and save
            self._state.glossary.file_path = save_path
            glossary_mgr.save_glossary(self._state.glossary)
            self._state.is_dirty = False

            # Notify the tab view to update the tab title
            on_dirty_changed = self._actions.get("on_dirty_changed")
            if on_dirty_changed:
                on_dirty_changed()

            # Emit glossary_changed event
            if bus:
                bus.emit("glossary_changed")
                bus.show_banner(f"Saved as: {save_path.name}")

        except (OSError, PermissionError) as exc:
            _log(f"ERROR in Save As: {exc}")
            if bus:
                bus.show_banner(f"Failed to save glossary: {exc}", is_error=True)
        except Exception as exc:
            _log(f"ERROR in Save As:\n{traceback.format_exc()}")
            if bus:
                bus.show_banner(f"Failed to save glossary: {exc}", is_error=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_term_count(self) -> str:
        """Format the total term count for display."""
        total = len(self._state.glossary.terms)
        return f"{total:,} terms"
