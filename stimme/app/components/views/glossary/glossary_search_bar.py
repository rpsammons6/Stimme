"""GlossarySearchBar: Enter-to-confirm search with global Search All support.

Provides a TextField that triggers filtering only on Enter key press or Search
button click (no per-keystroke filtering). Includes a "Search All" button that
spawns a background thread for cross-file global search.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Callable

import flet as ft

from app.theme import Colors, Fonts, UI

from .utils.fuzzy_search import fuzzy_filter
from .utils.global_search import run_global_search

if TYPE_CHECKING:
    from pathlib import Path

    from app.services.glossary_manager import GlossaryTerm

    from .glossary_tab_state import GlossaryTabState

logger = logging.getLogger(__name__)


def _log(msg: str) -> None:
    print(f"[GlossarySearchBar] {msg}")


class GlossarySearchBar:
    """Search bar with Enter-to-confirm local search and threaded global search.

    Local search uses RapidFuzz fuzzy matching with umlaut normalization.
    Global search scans all .glossary files in a background thread and
    displays results with provenance badges.
    """

    def __init__(
        self,
        page: ft.Page,
        state: "GlossaryTabState",
        on_results: Callable[[], None],
        actions: dict,
    ) -> None:
        self._page = page
        self._state = state
        self._on_results = on_results
        self._actions = actions
        self._search_field: ft.TextField | None = None
        self._progress_text: ft.Text | None = None
        self._progress_container: ft.Container | None = None

    def build(self) -> ft.Control:
        """Build the search bar: TextField + Search button + Search All button."""
        self._search_field = ft.TextField(
            hint_text="Search glossary terms...",
            value=self._state.search_query,
            on_submit=self._on_search_submit,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            selection_color=Colors.SECONDARY,
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, size=12, italic=True),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
            expand=True,
            height=40,
        )

        search_btn = ft.Container(
            content=UI.icon("SVGs/noun-search-5441837.svg", 20),
            tooltip="Search (Enter)",
            on_click=self._on_search_submit,
            ink=True,
        )

        search_all_btn = ft.TextButton(
            content=ft.Row(
                [
                    UI.icon("SVGs/noun-world-5441893.svg", 16),
                    ft.Text("Search All", color=Colors.GOLD, size=13),
                ],
                spacing=6,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=self._on_search_all,
            tooltip="Search across all glossary files",
        )

        self._progress_text = ft.Text(
            "",
            size=11,
            color=Colors.INK_MUTED,
            italic=True,
        )
        self._progress_container = ft.Container(
            content=ft.Row(
                [
                    ft.ProgressRing(width=14, height=14, stroke_width=2, color=Colors.GOLD),
                    self._progress_text,
                ],
                spacing=6,
            ),
            visible=False,
            padding=ft.padding.only(left=16, top=4),
        )

        return ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            self._search_field,
                            search_btn,
                            search_all_btn,
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                ),
                self._progress_container,
            ],
            spacing=0,
        )

    def _on_search_submit(self, e) -> None:
        """Triggered on Enter key or Search button click. Applies fuzzy filter."""
        query = self._search_field.value.strip() if self._search_field else ""
        start_time = time.perf_counter()

        # Clear global search state
        self._state.is_global_search = False
        self._state.global_results = []
        self._state.search_in_progress = False
        self._state.search_progress_text = ""

        if not query:
            # Clear search: reset to full term list with 100-row cap
            self._state.search_query = ""
            self._state.filtered_terms = list(self._state.glossary.terms)
            self._state.visible_count = min(100, len(self._state.filtered_terms))
        else:
            # Apply fuzzy filter
            self._state.search_query = query
            all_terms = self._state.glossary.terms
            results = fuzzy_filter(query, all_terms)
            self._state.filtered_terms = [term for term, _score in results]
            self._state.visible_count = min(100, len(self._state.filtered_terms))

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        total_records = len(self._state.glossary.terms)
        match_count = len(self._state.filtered_terms)

        logger.info(
            "[UI-DIAG] Search query %r processed in %.1fms. Returned %d matches from %d records.",
            query,
            elapsed_ms,
            match_count,
            total_records,
        )

        # Notify the tab view to rebuild the term list
        self._on_results()

    def _on_search_all(self, e) -> None:
        """Spawn a background thread for global cross-file search."""
        query = self._search_field.value.strip() if self._search_field else ""
        if not query:
            # Empty query: clear global search and reset to full term list
            self._state.is_global_search = False
            self._state.global_results = []
            self._state.search_in_progress = False
            self._state.search_progress_text = ""
            self._state.search_query = ""
            self._state.filtered_terms = list(self._state.glossary.terms)
            self._state.visible_count = min(100, len(self._state.filtered_terms))
            self._on_results()
            return

        glossary_mgr = self._actions.get("glossary_manager")
        if not glossary_mgr:
            _log("No glossary_manager in actions — cannot run global search")
            return

        glossaries_dir = glossary_mgr.glossaries_dir

        # Set search-in-progress state
        self._state.search_in_progress = True
        self._state.search_query = query
        self._state.search_progress_text = "Starting global search..."
        self._progress_container.visible = True
        self._progress_text.value = "Starting global search..."

        bus = self._actions.get("bus")
        if bus:
            bus.safe_update()
        else:
            self._page.update()

        # Spawn background thread
        thread = threading.Thread(
            target=self._run_global_search_thread,
            args=(query, glossaries_dir),
            daemon=True,
        )
        thread.start()

    def _run_global_search_thread(self, query: str, glossaries_dir: "Path") -> None:
        """Background thread: run global search and post results back to UI."""
        try:

            def progress_callback(text: str) -> None:
                self._state.search_progress_text = text
                if self._progress_text is not None:
                    self._progress_text.value = text
                bus = self._actions.get("bus")
                if bus:
                    bus.safe_update()

            results = run_global_search(
                query=query,
                glossaries_dir=glossaries_dir,
                progress_callback=progress_callback,
            )

            # Post results back to UI state
            self._state.is_global_search = True
            self._state.global_results = [(term, source) for term, source, _score in results]
            self._state.filtered_terms = [term for term, _source, _score in results]
            self._state.visible_count = min(100, len(self._state.global_results))
            self._state.search_in_progress = False
            self._state.search_progress_text = ""

            # Hide progress indicator
            if self._progress_container is not None:
                self._progress_container.visible = False

            # Notify the tab view to rebuild
            self._on_results()

            bus = self._actions.get("bus")
            if bus:
                bus.safe_update()

        except Exception as exc:
            _log(f"Global search thread error: {exc}")
            self._state.search_in_progress = False
            self._state.search_progress_text = ""
            if self._progress_container is not None:
                self._progress_container.visible = False

            bus = self._actions.get("bus")
            if bus:
                bus.show_banner(f"Global search failed: {exc}", is_error=True)
                bus.safe_update()
