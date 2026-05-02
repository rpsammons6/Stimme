"""LibraryView — Chapter Tree UI for bulk (book-level) translation.

Renders between Navigation and Input Panel when a book is detected.
Shows chapter list with checkboxes, word counts, status indicators,
per-chapter progress bars, cost estimate, and translate/cancel controls.
"""

from __future__ import annotations

import traceback
from typing import Callable, Dict, List

import flet as ft

from app.event_bus import EventBus
from app.models.bulk_models import Chapter, ChapterStatus, CostEstimate
from app.state import AppState
from app.theme import Colors, Fonts


def _log(msg):
    print(f"[LibraryView] {msg}")


# Status indicator colors
_STATUS_COLORS = {
    ChapterStatus.PENDING: Colors.INK_MUTED,
    ChapterStatus.SCANNING: Colors.WARNING,
    ChapterStatus.CHUNKED: Colors.INK_MUTED,
    ChapterStatus.TRANSLATING: Colors.GOLD,
    ChapterStatus.TRANSLATED: Colors.GOLD,
    ChapterStatus.ERROR: Colors.DESTRUCTIVE,
}

_STATUS_ICONS = {
    ChapterStatus.PENDING: ft.Icons.CIRCLE_OUTLINED,
    ChapterStatus.SCANNING: ft.Icons.HOURGLASS_TOP,
    ChapterStatus.CHUNKED: ft.Icons.CIRCLE_OUTLINED,
    ChapterStatus.TRANSLATING: ft.Icons.AUTORENEW,
    ChapterStatus.TRANSLATED: ft.Icons.CHECK_CIRCLE,
    ChapterStatus.ERROR: ft.Icons.ERROR_OUTLINE,
}


class LibraryView:
    """Chapter Tree UI component for bulk mode.

    Responsibilities (Tasks 7.1–7.6):
    - Render chapter list with checkboxes, word counts, status indicators
    - "Translate All" button with dynamic cost estimate
    - Chapter click → populate InputPanel for preview
    - Per-chapter progress bars updated via EventBus
    - Cancel button during translation
    - "Book Detected" banner with "Scan Structure" option
    """

    def __init__(
        self,
        page: ft.Page,
        bus: EventBus,
        state: AppState,
        actions: dict,
    ) -> None:
        self.page = page
        self.bus = bus
        self.state = state
        self.actions = actions

        # UI state
        self.chapter_checkboxes: List[ft.Checkbox] = []
        self.progress_bars: Dict[int, ft.ProgressBar] = {}
        self._translating = False

        # --- Top-level controls ---

        # Cost label (Task 7.2)
        self.cost_label = ft.Text(
            "",
            size=11,
            color=Colors.INK_MUTED,
            font_family=Fonts.MONO,
        )

        # Translate All button (Task 7.2)
        self.translate_all_btn = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.TRANSLATE, size=16),
                    ft.Text("Translate All", font_family=Fonts.FRAKTUR, size=14, weight="bold"),
                ],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=self.on_translate_all,
            bgcolor=Colors.GOLD,
            color=Colors.BACKGROUND,
            height=34,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
        )

        # Cancel button (Task 7.5)
        self.cancel_btn = ft.OutlinedButton(
            text="Cancel",
            icon=ft.Icons.CANCEL,
            on_click=self._on_cancel,
            height=34,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
                color=Colors.DESTRUCTIVE,
                side=ft.BorderSide(1, Colors.DESTRUCTIVE),
            ),
            visible=False,
        )

        # Chapter list container — ListView for virtualization
        self._chapter_list = ft.ListView(spacing=2, expand=True)

        # "Book Detected" banner (Task 7.6)
        self._book_detected_banner = self._build_book_detected_banner()

        # --- Register EventBus listeners ---
        self.bus.on("chunk_translated", self._on_chunk_translated)
        self.bus.on("chapter_translated", self._on_chapter_translated)
        self.bus.on("book_translation_complete", self._on_book_complete)


    # ------------------------------------------------------------------
    # Build (Task 7.1)
    # ------------------------------------------------------------------

    def build(self) -> ft.Container:
        """Build the LibraryView column."""
        # Select-all checkbox
        self._select_all_cb = ft.Checkbox(
            label="Select all",
            value=True,
            on_change=self._on_select_all,
            check_color=Colors.BACKGROUND,
            active_color=Colors.GOLD,
            label_style=ft.TextStyle(size=11, color=Colors.INK_MUTED),
        )

        header = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Library",
                        size=16,
                        font_family=Fonts.HEADER,
                        color=Colors.GOLD,
                        weight=ft.FontWeight.W_700,
                    ),
                    ft.Container(height=4),
                    self._select_all_cb,
                ],
                spacing=0,
            ),
            padding=ft.padding.only(left=16, right=16, top=14, bottom=6),
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

        # Action bar: translate + cancel + cost
        action_bar = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [self.translate_all_btn, self.cancel_btn],
                        spacing=8,
                    ),
                    self.cost_label,
                ],
                spacing=4,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            border=ft.border.only(top=ft.BorderSide(1, Colors.DIVIDER)),
        )

        return ft.Container(
            content=ft.Column(
                [
                    self._book_detected_banner,
                    header,
                    ft.Container(
                        content=self._chapter_list,
                        expand=True,
                        padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    ),
                    action_bar,
                ],
                spacing=0,
                expand=True,
            ),
            width=260,
            bgcolor=Colors.SURFACE,
            border=ft.border.only(right=ft.BorderSide(1, Colors.DIVIDER)),
        )

    # ------------------------------------------------------------------
    # Book Detected banner (Task 7.6)
    # ------------------------------------------------------------------

    def _build_book_detected_banner(self) -> ft.Container:
        """Build the 'Book Detected' overlay banner."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.AUTO_STORIES, size=18, color=Colors.BACKGROUND),
                    ft.Text(
                        "Book Detected",
                        size=13,
                        font_family=Fonts.SERIF,
                        weight=ft.FontWeight.W_700,
                        color=Colors.BACKGROUND,
                    ),
                    ft.Container(expand=True),
                    ft.TextButton(
                        "Scan Structure",
                        on_click=self._on_scan_structure,
                        style=ft.ButtonStyle(
                            color=Colors.BACKGROUND,
                            text_style=ft.TextStyle(font_family=Fonts.FRAKTUR),
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=Colors.GOLD,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            visible=False,  # shown via show_book_detected_banner()
        )

    def show_book_detected_banner(self, visible: bool = True) -> None:
        """Show or hide the 'Book Detected' banner."""
        self._book_detected_banner.visible = visible

    def _on_scan_structure(self, e) -> None:
        """Trigger structural scan via actions callback."""
        try:
            scan_fn = self.actions.get("scan_structure")
            if scan_fn:
                # Hide banner once scan is triggered
                self._book_detected_banner.visible = False
                self.bus.safe_update()
                scan_fn()
            else:
                _log("WARNING: 'scan_structure' action not available")
        except Exception:
            _log(f"ERROR in _on_scan_structure:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Chapter list rendering (Task 7.1)
    # ------------------------------------------------------------------

    def update_chapters(self, chapters: List[Chapter]) -> None:
        """Rebuild the chapter list from the given chapters."""
        self._chapter_list.controls.clear()
        self.chapter_checkboxes.clear()
        self.progress_bars.clear()

        for idx, chapter in enumerate(chapters):
            cb = ft.Checkbox(
                value=True,
                on_change=lambda e, i=idx: self._on_chapter_selection_change(e, i),
                check_color=Colors.BACKGROUND,
                active_color=Colors.GOLD,
            )
            self.chapter_checkboxes.append(cb)

            # Progress bar (Task 7.4)
            progress_bar = ft.ProgressBar(
                value=0,
                bgcolor=Colors.SURFACE_RAISED,
                color=Colors.GOLD,
                height=3,
                visible=False,
            )
            self.progress_bars[idx] = progress_bar

            # Status indicator
            status_color = _STATUS_COLORS.get(chapter.status, Colors.INK_MUTED)
            status_icon = _STATUS_ICONS.get(chapter.status, ft.Icons.CIRCLE_OUTLINED)

            # Word count display
            wc = chapter.word_count
            wc_str = f"{wc:,}" if wc >= 1000 else str(wc)

            # Chapter row
            chapter_row = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                cb,
                                ft.Icon(status_icon, size=12, color=status_color),
                                ft.GestureDetector(
                                    on_tap=lambda e, i=idx: self.on_chapter_click(i),
                                    mouse_cursor=ft.MouseCursor.CLICK,
                                    content=ft.Text(
                                        chapter.title,
                                        size=13,
                                        font_family=Fonts.SERIF,
                                        color=Colors.FOREGROUND,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        expand=True,
                                    ),
                                ),
                                ft.Text(
                                    f"{wc_str} w",
                                    size=10,
                                    color=Colors.INK_MUTED,
                                    font_family=Fonts.MONO,
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        progress_bar,
                    ],
                    spacing=2,
                ),
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=4,
                on_hover=lambda e, i=idx: self._on_chapter_hover(e, i),
            )
            self._chapter_list.controls.append(chapter_row)

        # Trigger initial cost estimate
        self._update_cost_estimate()


    # ------------------------------------------------------------------
    # Chapter click → preview in InputPanel (Task 7.3)
    # ------------------------------------------------------------------

    def on_chapter_click(self, chapter_idx: int) -> None:
        """Populate InputPanel with the selected chapter's text."""
        try:
            chapters = self.state.book_chapters
            if not chapters or chapter_idx < 0 or chapter_idx >= len(chapters):
                return

            chapter = chapters[chapter_idx]
            self.state.active_chapter_index = chapter_idx

            set_input = self.actions.get("set_input_text")
            if set_input:
                set_input(chapter.text)

            # Highlight the active chapter row
            for i, container in enumerate(self._chapter_list.controls):
                if isinstance(container, ft.Container):
                    container.bgcolor = (
                        Colors.SURFACE_RAISED if i == chapter_idx else None
                    )

            self.bus.safe_update()
        except Exception:
            _log(f"ERROR in on_chapter_click:\n{traceback.format_exc()}")

    def _on_chapter_hover(self, e, idx: int) -> None:
        """Subtle hover effect on chapter rows."""
        try:
            container = self._chapter_list.controls[idx]
            if isinstance(container, ft.Container):
                if idx != self.state.active_chapter_index:
                    container.bgcolor = (
                        Colors.SURFACE_RAISED if e.data == "true" else None
                    )
                    container.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Selection handling (Task 7.2 / 7.6)
    # ------------------------------------------------------------------

    def _on_select_all(self, e) -> None:
        """Toggle all chapter checkboxes."""
        try:
            val = e.control.value
            for cb in self.chapter_checkboxes:
                cb.value = val
            self._update_cost_estimate()
            # Granular update: only refresh the chapter list and cost label
            self._chapter_list.update()
            self.cost_label.update()
        except Exception:
            _log(f"ERROR in _on_select_all:\n{traceback.format_exc()}")

    def _on_chapter_selection_change(self, e, chapter_idx: int) -> None:
        """Update cost estimate when a chapter checkbox changes."""
        try:
            self._update_cost_estimate()
            self.cost_label.update()
        except Exception:
            _log(f"ERROR in _on_chapter_selection_change:\n{traceback.format_exc()}")

    def _get_selected_indices(self) -> List[int]:
        """Return indices of checked chapters."""
        return [i for i, cb in enumerate(self.chapter_checkboxes) if cb.value]

    # ------------------------------------------------------------------
    # Cost estimate (Task 7.2)
    # ------------------------------------------------------------------

    def _update_cost_estimate(self) -> None:
        """Recalculate and display cost estimate for selected chapters."""
        try:
            chapters = self.state.book_chapters
            selected = self._get_selected_indices()

            if not chapters or not selected:
                self.cost_label.value = "No chapters selected"
                self.translate_all_btn.disabled = True
                return

            book_processor = self.actions.get("book_processor")
            if not book_processor:
                self.cost_label.value = f"{len(selected)} chapter(s) selected"
                self.translate_all_btn.disabled = False
                return

            estimate = book_processor.estimate_cost(chapters, selected)
            self.show_cost_estimate(estimate)
            self.translate_all_btn.disabled = False
        except Exception:
            _log(f"ERROR in _update_cost_estimate:\n{traceback.format_exc()}")
            self.cost_label.value = "Cost estimate unavailable"

    def show_cost_estimate(self, estimate: CostEstimate) -> None:
        """Display a cost estimate in the cost label."""
        words = f"{estimate.total_words:,}"
        cost = f"${estimate.estimated_cost_usd:.4f}"
        self.cost_label.value = (
            f"~{words} words · {estimate.chunk_count} chunks · {cost}"
        )

    # ------------------------------------------------------------------
    # Translate All (Task 7.2)
    # ------------------------------------------------------------------

    def on_translate_all(self, e) -> None:
        """Start bulk translation of selected chapters."""
        try:
            selected = self._get_selected_indices()
            if not selected:
                return

            self._set_translating(True)

            # Show progress bars for selected chapters
            for idx in selected:
                if idx in self.progress_bars:
                    self.progress_bars[idx].value = 0
                    self.progress_bars[idx].visible = True

            self.bus.safe_update()

            start_fn = self.actions.get("start_bulk_translate")
            if start_fn:
                start_fn(selected)
            else:
                _log("WARNING: 'start_bulk_translate' action not available")
                self._set_translating(False)
        except Exception:
            _log(f"ERROR in on_translate_all:\n{traceback.format_exc()}")
            self._set_translating(False)

    # ------------------------------------------------------------------
    # Cancel (Task 7.5)
    # ------------------------------------------------------------------

    def _on_cancel(self, e) -> None:
        """Cancel the in-progress bulk translation."""
        try:
            # Immediate UI feedback — disable cancel button and show status
            self.cancel_btn.disabled = True
            self.cancel_btn.text = "Cancelling…"
            self.cost_label.value = "Cancelling after current chunk…"
            self.bus.safe_update()

            book_processor = self.actions.get("book_processor")
            if book_processor:
                book_processor.cancel()
                self.state.bulk_cancel_requested = True
            cancel_fn = self.actions.get("cancel_bulk_translate")
            if cancel_fn:
                cancel_fn()
        except Exception:
            _log(f"ERROR in _on_cancel:\n{traceback.format_exc()}")

    def _set_translating(self, translating: bool) -> None:
        """Toggle between translate and cancel button visibility, sync toolbar."""
        self._translating = translating
        self.translate_all_btn.visible = not translating
        self.cancel_btn.visible = translating
        # Reset cancel button state for next use
        self.cancel_btn.disabled = False
        self.cancel_btn.text = "Cancel"
        # Disable checkboxes during translation
        for cb in self.chapter_checkboxes:
            cb.disabled = translating
        # Sync the toolbar translate button so both stay in lockstep
        # (guard against re-entrant calls from HomeTab._set_translate_busy)
        if not getattr(self, '_syncing', False):
            self._syncing = True
            try:
                set_toolbar_busy = self.actions.get("set_translate_busy")
                if set_toolbar_busy:
                    set_toolbar_busy(translating)
            finally:
                self._syncing = False

    # ------------------------------------------------------------------
    # Progress updates via EventBus (Task 7.4)
    # ------------------------------------------------------------------

    def update_progress(self, chapter_idx: int, progress: float) -> None:
        """Update a chapter's progress bar (0.0 – 1.0)."""
        try:
            bar = self.progress_bars.get(chapter_idx)
            if bar:
                bar.value = min(1.0, max(0.0, progress))
                bar.visible = True
        except Exception:
            _log(f"ERROR in update_progress:\n{traceback.format_exc()}")

    def _on_chunk_translated(self, **kwargs) -> None:
        """Handle 'chunk_translated' EventBus event."""
        try:
            chapter_idx = kwargs.get("chapter_idx", -1)
            chunk_idx = kwargs.get("chunk_idx", 0)
            total_chunks = kwargs.get("total_chunks", 1)

            if chapter_idx < 0:
                return

            # Per-chapter progress = completed chunks / total chunks in chapter
            chapter_progress = (chunk_idx + 1) / total_chunks if total_chunks > 0 else 1.0
            self.update_progress(chapter_idx, chapter_progress)

            # Update status indicator
            self._update_chapter_status(chapter_idx, ChapterStatus.TRANSLATING)
        except Exception:
            _log(f"ERROR in _on_chunk_translated:\n{traceback.format_exc()}")

    def _on_chapter_translated(self, **kwargs) -> None:
        """Handle 'chapter_translated' EventBus event."""
        try:
            chapter_idx = kwargs.get("chapter_idx", -1)
            if chapter_idx < 0:
                return

            # Mark progress as complete
            self.update_progress(chapter_idx, 1.0)
            self._update_chapter_status(chapter_idx, ChapterStatus.TRANSLATED)
        except Exception:
            _log(f"ERROR in _on_chapter_translated:\n{traceback.format_exc()}")

    def _on_book_complete(self, **kwargs) -> None:
        """Handle 'book_translation_complete' EventBus event."""
        try:
            self._set_translating(False)
            self.bus.safe_update()
        except Exception:
            _log(f"ERROR in _on_book_complete:\n{traceback.format_exc()}")

    def _update_chapter_status(self, chapter_idx: int, status: ChapterStatus) -> None:
        """Update the status icon/color for a chapter row."""
        try:
            chapters = self.state.book_chapters
            if not chapters or chapter_idx >= len(chapters):
                return

            chapters[chapter_idx].status = status

            # Find the status icon in the chapter row and update it
            if chapter_idx < len(self._chapter_list.controls):
                container = self._chapter_list.controls[chapter_idx]
                if isinstance(container, ft.Container) and isinstance(container.content, ft.Column):
                    row = container.content.controls[0]  # the ft.Row
                    if isinstance(row, ft.Row) and len(row.controls) > 1:
                        icon_ctrl = row.controls[1]  # status icon
                        if isinstance(icon_ctrl, ft.Icon):
                            icon_ctrl.name = _STATUS_ICONS.get(status, ft.Icons.CIRCLE_OUTLINED)
                            icon_ctrl.color = _STATUS_COLORS.get(status, Colors.INK_MUTED)
        except Exception:
            _log(f"ERROR in _update_chapter_status:\n{traceback.format_exc()}")
