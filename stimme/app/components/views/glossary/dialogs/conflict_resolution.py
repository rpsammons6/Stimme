"""Conflict Resolution dialog — handles merge conflicts during glossary import.

Displays conflicts in batches of 10 with navigation. For each conflict,
shows the German term, existing English translation, and incoming English
translation with source file. Resolution options: Keep Mine, Use Theirs,
Keep Both. An "Apply to All" checkbox applies the chosen strategy to all
remaining conflicts.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Callable

import flet as ft

from app.theme import Colors, Fonts

if TYPE_CHECKING:
    from app.event_bus import EventBus
    from app.services.glossary_manager import ConflictEntry


def _log(msg: str) -> None:
    print(f"[ConflictResolutionDialog] {msg}")


# Resolution strategies
KEEP_MINE = "keep_mine"
USE_THEIRS = "use_theirs"
KEEP_BOTH = "keep_both"


class ConflictResolutionDialog:
    """Modal dialog for resolving import conflicts in batches of 10.

    Each conflict shows the German term, existing and incoming English
    translations, and provides Keep Mine / Use Theirs / Keep Both options.
    An "Apply to All" checkbox applies the selected strategy to all
    remaining unresolved conflicts.
    """

    BATCH_SIZE = 10

    def __init__(
        self,
        page: ft.Page,
        conflicts: list["ConflictEntry"],
        actions: dict,
        on_resolved: Callable[[list[tuple["ConflictEntry", str]]], None] | None = None,
    ) -> None:
        """Initialize the conflict resolution dialog.

        Args:
            page: The Flet page instance.
            conflicts: List of ConflictEntry objects to resolve.
            actions: Actions dict with bus, glossary_manager, etc.
            on_resolved: Callback with list of (conflict, resolution) tuples
                         when all conflicts are resolved.
        """
        self._page = page
        self._conflicts = list(conflicts)
        self._actions = actions
        self._on_resolved = on_resolved
        self._dialog: ft.AlertDialog | None = None

        # Resolution tracking
        self._resolutions: dict[int, str] = {}  # index -> resolution strategy
        self._current_offset = 0
        self._apply_to_all = False
        self._apply_to_all_checkbox: ft.Checkbox | None = None

        # Per-conflict resolution dropdowns for the current batch
        self._batch_controls: list[ft.Dropdown] = []

    @property
    def total_conflicts(self) -> int:
        """Total number of conflicts."""
        return len(self._conflicts)

    @property
    def resolved_count(self) -> int:
        """Number of conflicts already resolved."""
        return len(self._resolutions)

    def show(self) -> None:
        """Build and display the conflict resolution dialog."""
        self._current_offset = 0
        self._build_and_show()

    def _build_and_show(self) -> None:
        """Build the dialog content for the current batch and show it."""
        batch_end = min(
            self._current_offset + self.BATCH_SIZE, self.total_conflicts
        )
        batch = self._conflicts[self._current_offset:batch_end]
        batch_size = len(batch)

        # Header info
        header_text = ft.Text(
            f"Conflicts: {self._current_offset + 1}–{batch_end} of {self.total_conflicts}",
            size=12,
            color=Colors.INK_MUTED,
            italic=True,
        )

        # Build conflict rows
        conflict_rows = []
        self._batch_controls = []

        for i, conflict in enumerate(batch):
            global_idx = self._current_offset + i
            row = self._build_conflict_row(conflict, global_idx)
            conflict_rows.append(row)

        # Apply to All checkbox
        self._apply_to_all_checkbox = ft.Checkbox(
            label="Apply to all remaining conflicts",
            value=self._apply_to_all,
            on_change=self._on_apply_to_all_changed,
            check_color=Colors.GOLD,
            label_style=ft.TextStyle(size=12, color=Colors.FOREGROUND),
        )

        content = ft.Column(
            [
                header_text,
                ft.Divider(height=1, color=Colors.DIVIDER),
                *conflict_rows,
                ft.Divider(height=1, color=Colors.DIVIDER),
                self._apply_to_all_checkbox,
            ],
            spacing=8,
            tight=True,
            width=550,
            height=450,
            scroll=ft.ScrollMode.AUTO,
        )

        # Actions
        actions = []

        # Cancel button
        actions.append(
            ft.TextButton(
                "Cancel Import",
                on_click=self._on_cancel,
                style=ft.ButtonStyle(color=Colors.INK_MUTED),
            )
        )

        # Next 10 button (only if more conflicts remain after this batch)
        has_next = batch_end < self.total_conflicts
        if has_next:
            actions.append(
                ft.TextButton(
                    "Next 10",
                    on_click=self._on_next_batch,
                    style=ft.ButtonStyle(color=Colors.FOREGROUND),
                )
            )

        # Resolve button
        actions.append(
            ft.TextButton(
                "Resolve" if not has_next else "Resolve Batch",
                on_click=self._on_resolve_batch,
                style=ft.ButtonStyle(color=Colors.GOLD),
            )
        )

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Resolve Import Conflicts",
                size=16,
                weight="bold",
                color=Colors.GOLD,
                font_family=Fonts.HEADER,
            ),
            content=content,
            actions=actions,
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

    def _build_conflict_row(self, conflict: "ConflictEntry", global_idx: int) -> ft.Control:
        """Build a single conflict display row with resolution dropdown."""
        from pathlib import Path

        source_name = Path(conflict.source_file).stem if conflict.source_file else "unknown"

        # Resolution dropdown
        current_resolution = self._resolutions.get(global_idx, "")
        dropdown = ft.Dropdown(
            options=[
                ft.dropdown.Option(KEEP_MINE, "Keep Mine"),
                ft.dropdown.Option(USE_THEIRS, "Use Theirs"),
                ft.dropdown.Option(KEEP_BOTH, "Keep Both"),
            ],
            value=current_resolution or None,
            hint_text="Choose...",
            width=140,
            height=40,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            text_style=ft.TextStyle(size=11),
            border_radius=4,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=4),
            on_change=lambda e, idx=global_idx: self._on_resolution_changed(e, idx),
        )
        self._batch_controls.append(dropdown)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                conflict.german_key,
                                size=13,
                                weight="bold",
                                color=Colors.FOREGROUND,
                                font_family=Fonts.SERIF,
                            ),
                            ft.Container(expand=True),
                            dropdown,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            ft.Text("Existing:", size=11, color=Colors.INK_MUTED),
                            ft.Text(
                                conflict.existing_term.english,
                                size=11,
                                color=Colors.FOREGROUND,
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.Row(
                        [
                            ft.Text("Incoming:", size=11, color=Colors.INK_MUTED),
                            ft.Text(
                                conflict.incoming_term.english,
                                size=11,
                                color=Colors.FOREGROUND,
                            ),
                            ft.Chip(
                                label=ft.Text(source_name, size=9),
                                bgcolor=Colors.SECONDARY,
                                label_style=ft.TextStyle(
                                    color=Colors.SECONDARY_FOREGROUND, size=9
                                ),
                            ),
                        ],
                        spacing=6,
                    ),
                ],
                spacing=4,
                tight=True,
            ),
            padding=ft.padding.symmetric(vertical=6, horizontal=4),
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

    def _on_resolution_changed(self, e, idx: int) -> None:
        """Record the resolution choice for a specific conflict."""
        if e.control.value:
            self._resolutions[idx] = e.control.value

    def _on_apply_to_all_changed(self, e) -> None:
        """Toggle the Apply to All flag."""
        self._apply_to_all = e.control.value

    def _on_next_batch(self, e) -> None:
        """Resolve current batch and advance to the next 10 conflicts."""
        # First resolve the current batch
        self._resolve_current_batch()

        # Advance offset
        self._current_offset += self.BATCH_SIZE

        # If all resolved (via Apply to All), finish
        if self.resolved_count >= self.total_conflicts:
            self._finish_resolution()
            return

        # Show next batch
        self._close()
        self._build_and_show()

    def _on_resolve_batch(self, e) -> None:
        """Resolve the current batch. If all done, close and invoke callback."""
        self._resolve_current_batch()

        # Check if all conflicts are resolved
        batch_end = min(
            self._current_offset + self.BATCH_SIZE, self.total_conflicts
        )
        has_next = batch_end < self.total_conflicts

        if has_next and not self._apply_to_all:
            # Advance to next batch
            self._current_offset += self.BATCH_SIZE
            self._close()
            self._build_and_show()
        else:
            # All resolved (either last batch or Apply to All)
            self._finish_resolution()

    def _resolve_current_batch(self) -> None:
        """Record resolutions for the current batch."""
        batch_end = min(
            self._current_offset + self.BATCH_SIZE, self.total_conflicts
        )

        # Get the dominant resolution from this batch for Apply to All
        dominant_resolution = None
        for i in range(self._current_offset, batch_end):
            if i in self._resolutions:
                dominant_resolution = self._resolutions[i]
                break

        # Default unresolved conflicts in this batch to KEEP_MINE
        for i in range(self._current_offset, batch_end):
            if i not in self._resolutions:
                self._resolutions[i] = dominant_resolution or KEEP_MINE

        # If Apply to All is checked, apply the dominant resolution to all remaining
        if self._apply_to_all and dominant_resolution:
            for i in range(batch_end, self.total_conflicts):
                if i not in self._resolutions:
                    self._resolutions[i] = dominant_resolution

    def _finish_resolution(self) -> None:
        """Close dialog and invoke the on_resolved callback."""
        self._close()

        try:
            # Build the resolution list
            resolved_pairs: list[tuple["ConflictEntry", str]] = []
            for i, conflict in enumerate(self._conflicts):
                resolution = self._resolutions.get(i, KEEP_MINE)
                resolved_pairs.append((conflict, resolution))

            # Apply resolutions via GlossaryManager
            self._apply_resolutions(resolved_pairs)

            # Invoke callback
            if self._on_resolved:
                self._on_resolved(resolved_pairs)

            # Emit glossary_changed
            bus = self._actions.get("bus")
            if bus:
                bus.emit("glossary_changed")
                bus.show_banner(
                    f"Resolved {self.total_conflicts} conflict(s)."
                )

        except Exception:
            _log(f"ERROR in finish_resolution:\n{traceback.format_exc()}")
            bus = self._actions.get("bus")
            if bus:
                bus.show_banner("Failed to apply conflict resolutions.", is_error=True)

    def _apply_resolutions(
        self, resolved_pairs: list[tuple["ConflictEntry", str]]
    ) -> None:
        """Apply the resolved conflicts to the glossary via GlossaryManager."""
        glossary_mgr = self._actions.get("glossary_manager")
        if not glossary_mgr:
            _log("No glossary_manager in actions — cannot apply resolutions")
            return

        for conflict, resolution in resolved_pairs:
            try:
                if resolution == KEEP_MINE:
                    # Keep existing term — no action needed
                    pass
                elif resolution == USE_THEIRS:
                    # Overwrite with incoming term
                    glossary_mgr.add_term(
                        german=conflict.incoming_term.german,
                        english=conflict.incoming_term.english,
                        context_target=conflict.incoming_term.context_target,
                        field_tag=conflict.incoming_term.field_tag,
                        nuance_note=conflict.incoming_term.nuance_note,
                    )
                elif resolution == KEEP_BOTH:
                    # Keep existing (already there) and add incoming with
                    # disambiguated field_tag suffix
                    existing_tag = conflict.existing_term.field_tag or "N/A"
                    incoming_tag = conflict.incoming_term.field_tag or "N/A"

                    # If tags are the same, disambiguate with source info
                    if existing_tag == incoming_tag:
                        from pathlib import Path

                        source_name = (
                            Path(conflict.source_file).stem
                            if conflict.source_file
                            else "imported"
                        )
                        incoming_tag = f"{incoming_tag} [{source_name}]"

                    # Add the incoming term with a modified german key to
                    # avoid overwriting the existing one
                    glossary_mgr.add_term(
                        german=f"{conflict.incoming_term.german} [{incoming_tag}]",
                        english=conflict.incoming_term.english,
                        context_target=conflict.incoming_term.context_target,
                        field_tag=incoming_tag,
                        nuance_note=conflict.incoming_term.nuance_note,
                    )
            except Exception:
                _log(
                    f"ERROR applying resolution for '{conflict.german_key}':\n"
                    f"{traceback.format_exc()}"
                )

    def _on_cancel(self, e) -> None:
        """Cancel the import — close dialog without applying resolutions."""
        self._close()
        bus = self._actions.get("bus")
        if bus:
            bus.show_banner("Import cancelled — no conflicts resolved.")

    def _close(self) -> None:
        """Close the dialog."""
        bus: EventBus | None = self._actions.get("bus")
        if bus:
            bus.close_dialog()
        else:
            if self._dialog:
                self._dialog.open = False
                self._page.update()
