"""GlossaryTermList: Lazy-rendered term list with Load More and context menu.

Renders glossary terms using ft.ListView for performance with large glossaries.
Displays only `state.visible_count` rows at a time with a Load More button to
append the next batch of 100 rows.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

import flet as ft

from app.theme import Colors, Fonts

if TYPE_CHECKING:
    from app.services.glossary_manager import GlossaryTerm

    from .glossary_tab_state import GlossaryTabState


def _log(msg: str) -> None:
    print(f"[GlossaryTermList] {msg}")


class GlossaryTermList:
    """Renders the glossary term list with lazy loading and context menu support.

    Uses ft.ListView for lazy rendering so only visible rows are instantiated.
    Shows a Load More button when visible_count < total filtered terms.
    Provides right-click context menu with Edit, Pin, and Delete options.
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
        self._list_view: ft.ListView | None = None
        self._load_more_btn: ft.Container | None = None
        self._term_count_text: ft.Text | None = None
        self._loading_indicator: ft.Container | None = None
        self._container: ft.Column | None = None
        self._highlighted_term: str | None = None  # German key of recently added term

    def build(self, defer_populate: bool = False) -> ft.Control:
        """Build the full term list control: header + ListView + Load More + count.

        Args:
            defer_populate: If True, skip initial row population (caller will
                call rebuild() later). Used for large glossaries so the loading
                indicator is visible before the heavy row-building work begins.
        """
        header = self._build_header()
        self._list_view = ft.ListView(expand=True, spacing=0, auto_scroll=False)
        self._term_count_text = ft.Text(
            self._format_count(),
            size=11,
            color=Colors.INK_MUTED,
            italic=True,
        )
        self._load_more_btn = ft.Container(
            content=ft.TextButton(
                text="Load More",
                icon=ft.Icons.EXPAND_MORE,
                on_click=self._on_load_more,
                style=ft.ButtonStyle(color=Colors.GOLD),
            ),
            alignment=ft.alignment.center,
            visible=self._should_show_load_more(),
        )

        # Loading indicator for large glossaries (>1000 terms)
        self._loading_indicator = ft.Container(
            content=ft.Row(
                [
                    ft.ProgressRing(width=20, height=20, stroke_width=2, color=Colors.GOLD),
                    ft.Text("Loading glossary...", size=12, color=Colors.INK_MUTED),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.alignment.center,
            visible=False,
        )

        # Populate initial rows (unless deferred for large glossaries)
        if not defer_populate:
            self._populate_rows()

        self._container = ft.Column(
            [
                header,
                self._loading_indicator,
                self._list_view,
                self._load_more_btn,
                ft.Container(
                    content=self._term_count_text,
                    padding=ft.padding.symmetric(horizontal=16, vertical=6),
                ),
            ],
            expand=True,
            spacing=0,
        )
        return self._container

    def rebuild(self) -> None:
        """Rebuild the ListView controls from current state (incremental update)."""
        if self._list_view is None:
            return
        self._populate_rows()
        self._update_count()
        self._load_more_btn.visible = self._should_show_load_more()

    def highlight_term(self, german: str) -> None:
        """Temporarily highlight a term row, then fade after 1.5 seconds.
        
        Sets the highlight flag and schedules a clear. The actual highlight
        rendering happens in the next rebuild() call triggered by glossary_changed.
        """
        self._highlighted_term = german

        # Schedule highlight clear after delay
        import threading

        def _clear():
            import time
            time.sleep(1.5)
            self._highlighted_term = None
            try:
                if self._list_view is not None:
                    self._populate_rows()
                    self._update_count()
                    self._load_more_btn.visible = self._should_show_load_more()
                    bus = self._actions.get("bus")
                    if bus:
                        bus.safe_update()
                    else:
                        self._page.update()
            except (AssertionError, Exception):
                pass  # Control tree may have changed; ignore stale update

        threading.Thread(target=_clear, daemon=True).start()
        self._populate_rows()
        self._update_count()
        self._load_more_btn.visible = self._should_show_load_more()

        # Push the highlighted rows to the UI — the bus.emit() safe_update()
        # already fired before highlight_term was called, so we need our own.
        bus = self._actions.get("bus")
        if bus:
            bus.safe_update()
        else:
            self._page.update()

    def show_loading(self, visible: bool = True) -> None:
        """Show or hide the loading indicator for large glossaries."""
        if self._loading_indicator is not None:
            self._loading_indicator.visible = visible

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_header(self) -> ft.Container:
        """Build the styled header row with column labels."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text("German", size=12, weight="bold", color=Colors.GOLD, width=160),
                    ft.Text("English", size=12, weight="bold", color=Colors.GOLD, width=160),
                    ft.Text("Context Target", size=12, weight="bold", color=Colors.GOLD, width=140),
                    ft.Text("Field Tag", size=12, weight="bold", color=Colors.GOLD, width=100),
                    ft.Text("Nuance Note", size=12, weight="bold", color=Colors.GOLD, expand=True),
                ],
                spacing=12,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

    def _populate_rows(self) -> None:
        """Populate the ListView with rows up to visible_count."""
        if self._list_view is None:
            return

        self._list_view.controls.clear()

        terms = self._state.filtered_terms[: self._state.visible_count]

        # Show global search results with provenance badges if in global mode
        if self._state.is_global_search and self._state.global_results:
            visible_results = self._state.global_results[: self._state.visible_count]
            for term, source_name in visible_results:
                row = self._build_global_result_row(term, source_name)
                self._list_view.controls.append(row)
        else:
            for term in terms:
                row = self._build_term_row(term)
                self._list_view.controls.append(row)

    def _build_term_row(self, term: "GlossaryTerm") -> ft.GestureDetector:
        """Build a single term row with right-click context menu support."""
        context_target = term.context_target if term.context_target != "N/A" else "—"
        field_tag = term.field_tag if term.field_tag != "N/A" else "—"
        nuance = (
            term.nuance_note
            if hasattr(term, "nuance_note") and term.nuance_note and term.nuance_note != "N/A"
            else "—"
        )

        # Highlight recently added term with a subtle gold tint
        is_highlighted = (
            self._highlighted_term is not None
            and term.german.strip().lower() == self._highlighted_term.strip().lower()
        )
        row_bgcolor = "#2B2A1A" if is_highlighted else None  # subtle warm highlight

        row_container = ft.Container(
            content=ft.Row(
                [
                    ft.Text(term.german, size=13, color=Colors.INK, weight="bold", width=160),
                    ft.Text(term.english, size=13, color=Colors.FOREGROUND, width=160),
                    ft.Text(context_target, size=12, color=Colors.INK_MUTED, width=140),
                    ft.Text(field_tag, size=12, color=Colors.INK_MUTED, italic=True, width=100),
                    ft.Text(nuance, size=12, color=Colors.INK_MUTED, expand=True, no_wrap=False),
                ],
                spacing=12,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            bgcolor=row_bgcolor,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

        return ft.GestureDetector(
            content=row_container,
            on_secondary_tap_down=lambda e, t=term: self._on_right_click(e, t),
        )

    def _build_global_result_row(self, term: "GlossaryTerm", source_name: str) -> ft.Container:
        """Build a row for global search results with a provenance badge."""
        context_target = term.context_target if term.context_target != "N/A" else "—"
        field_tag = term.field_tag if term.field_tag != "N/A" else "—"

        provenance_badge = ft.Chip(
            label=ft.Text(source_name, size=10),
            bgcolor=Colors.SECONDARY,
            label_style=ft.TextStyle(color=Colors.FOREGROUND, size=10),
        )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(term.german, size=13, color=Colors.INK, weight="bold", width=140),
                    ft.Text(term.english, size=13, color=Colors.FOREGROUND, width=140),
                    ft.Text(context_target, size=12, color=Colors.INK_MUTED, width=120),
                    ft.Text(field_tag, size=12, color=Colors.INK_MUTED, italic=True, width=80),
                    provenance_badge,
                ],
                spacing=8,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

    def _on_load_more(self, e) -> None:
        """Increment visible_count by 100 and append new rows."""
        total = self._get_total_count()
        old_visible = self._state.visible_count
        self._state.visible_count = min(old_visible + 100, total)

        # Append only the new rows (incremental update)
        if self._state.is_global_search and self._state.global_results:
            new_results = self._state.global_results[old_visible : self._state.visible_count]
            for term, source_name in new_results:
                row = self._build_global_result_row(term, source_name)
                self._list_view.controls.append(row)
        else:
            new_terms = self._state.filtered_terms[old_visible : self._state.visible_count]
            for term in new_terms:
                row = self._build_term_row(term)
                self._list_view.controls.append(row)

        self._update_count()
        self._load_more_btn.visible = self._should_show_load_more()

        bus = self._actions.get("bus")
        if bus:
            bus.safe_update()
        else:
            self._page.update()

    def _on_right_click(self, e, term: "GlossaryTerm") -> None:
        """Show context menu: Edit Term, Pin to Sidebar, Delete Term."""
        is_pinned = getattr(term, "pinned", False)
        pin_text = "Unpin from Sidebar" if is_pinned else "Pin to Sidebar"
        pin_icon = ft.Icons.PUSH_PIN if is_pinned else ft.Icons.PUSH_PIN_OUTLINED

        def on_edit(menu_e):
            self._close_menu()
            on_edit_cb = self._actions.get("on_edit_term")
            if on_edit_cb:
                on_edit_cb(term)

        def on_pin(menu_e):
            self._close_menu()
            try:
                glossary_mgr = self._actions.get("glossary_manager")
                if glossary_mgr:
                    if is_pinned:
                        glossary_mgr.unpin_term(term.german)
                    else:
                        glossary_mgr.pin_term(term.german)
                    refresh = self._actions.get("refresh_glossary_sidebar")
                    if refresh:
                        refresh()
                    bus = self._actions.get("bus")
                    if bus:
                        action_text = "Unpinned from" if is_pinned else "📌 Pinned to"
                        bus.show_banner(f"{action_text} sidebar: {term.german}")
            except Exception:
                _log(f"ERROR pin/unpin term '{term.german}':\n{traceback.format_exc()}")

        def on_delete(menu_e):
            self._close_menu()
            try:
                glossary_mgr = self._actions.get("glossary_manager")
                if glossary_mgr:
                    glossary_mgr.remove_term(term.german)
                    refresh = self._actions.get("refresh_glossary_sidebar")
                    if refresh:
                        refresh()
                    bus = self._actions.get("bus")
                    if bus:
                        bus.show_banner(f"Deleted: {term.german}")
                    # Notify the tab view to mark dirty and refresh
                    on_term_deleted = self._actions.get("on_term_deleted")
                    if on_term_deleted:
                        on_term_deleted(term)
            except Exception:
                _log(f"ERROR deleting term '{term.german}':\n{traceback.format_exc()}")

        # Get cursor position from the event
        x = getattr(e, "global_x", None) or getattr(e, "local_x", 200)
        y = getattr(e, "global_y", None) or getattr(e, "local_y", 200)

        menu = ft.Container(
            content=ft.Column(
                [
                    ft.TextButton(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.EDIT_OUTLINED, size=16, color=Colors.GOLD),
                                ft.Text("Edit Term", size=13, color=Colors.INK),
                            ],
                            spacing=8,
                        ),
                        on_click=on_edit,
                    ),
                    ft.Divider(height=1, color=Colors.DIVIDER),
                    ft.TextButton(
                        content=ft.Row(
                            [
                                ft.Icon(pin_icon, size=16, color=Colors.GOLD),
                                ft.Text(pin_text, size=13, color=Colors.INK),
                            ],
                            spacing=8,
                        ),
                        on_click=on_pin,
                    ),
                    ft.Divider(height=1, color=Colors.DIVIDER),
                    ft.TextButton(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.DELETE_OUTLINE, size=16, color=Colors.DESTRUCTIVE),
                                ft.Text("Delete Term", size=13, color=Colors.DESTRUCTIVE),
                            ],
                            spacing=8,
                        ),
                        on_click=on_delete,
                    ),
                ],
                spacing=0,
                tight=True,
            ),
            bgcolor=Colors.SURFACE,
            border=ft.border.all(1, Colors.DIVIDER),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=4, vertical=4),
            shadow=ft.BoxShadow(blur_radius=8, color="#33000000"),
            left=x,
            top=y,
        )

        # Full-screen transparent backdrop that dismisses the menu on any click
        backdrop = ft.GestureDetector(
            content=ft.Container(expand=True, bgcolor=ft.Colors.TRANSPARENT),
            on_tap=lambda _: self._close_menu(),
            on_secondary_tap=lambda _: self._close_menu(),
        )

        self._page.overlay.clear()
        self._page.overlay.append(backdrop)
        self._page.overlay.append(menu)
        self._page.update()

    def _close_menu(self) -> None:
        """Remove the context menu overlay."""
        self._page.overlay.clear()
        self._page.update()

    def _should_show_load_more(self) -> bool:
        """Return True if there are more rows to load."""
        return self._state.visible_count < self._get_total_count()

    def _get_total_count(self) -> int:
        """Get the total number of items (filtered terms or global results)."""
        if self._state.is_global_search and self._state.global_results:
            return len(self._state.global_results)
        return len(self._state.filtered_terms)

    def _format_count(self) -> str:
        """Format the term count indicator string."""
        visible = self._state.visible_count
        total = self._get_total_count()
        return f"{visible:,} / {total:,} terms"

    def _update_count(self) -> None:
        """Update the term count text control."""
        if self._term_count_text is not None:
            self._term_count_text.value = self._format_count()
