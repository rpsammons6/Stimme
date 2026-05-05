"""GlossaryTabView: Main orchestrator for a single glossary tab.

Composes GlossaryToolbar, GlossarySearchBar, and GlossaryTermList into a
unified tab view. Manages the GlossaryTabState lifecycle, wires search
results callbacks, and listens for glossary_changed events to refresh
when relevant.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

import flet as ft

from app.theme import Colors

from .glossary_search_bar import GlossarySearchBar
from .glossary_tab_state import GlossaryTabState
from .glossary_term_list import GlossaryTermList
from .glossary_toolbar import GlossaryToolbar

if TYPE_CHECKING:
    from app.event_bus import EventBus
    from app.services.glossary_manager import GlossaryFile, GlossaryTerm


def _log(msg: str) -> None:
    print(f"[GlossaryTabView] {msg}")


class GlossaryTabView:
    """Orchestrator for a single glossary tab.

    Composes the toolbar, search bar, and term list components. Manages
    the per-tab state and coordinates between sub-components via callbacks.
    Listens for glossary_changed events to refresh when the underlying
    glossary data is modified externally.
    """

    def __init__(
        self,
        page: ft.Page,
        glossary: "GlossaryFile",
        actions: dict,
    ) -> None:
        self._page = page
        self._glossary = glossary
        self._actions = actions
        self._state = GlossaryTabState(glossary=glossary)

        # Sub-component references (populated in build())
        self._toolbar: GlossaryToolbar | None = None
        self._search_bar: GlossarySearchBar | None = None
        self._term_list: GlossaryTermList | None = None
        self._container: ft.Container | None = None

        # Callback for notifying the parent (AppShell) of dirty state changes
        self._on_dirty_changed_callback = None

        # Wire up tab-level actions for sub-components
        self._tab_actions = dict(actions)
        self._tab_actions["on_dirty_changed"] = self._on_dirty_state_changed
        self._tab_actions["on_open_glossary_tab"] = actions.get("on_open_glossary_tab")
        self._tab_actions["on_term_deleted"] = self._on_term_deleted
        self._tab_actions["on_edit_term"] = self._on_edit_term
        self._tab_actions["highlight_term"] = self._highlight_term

        # Register EventBus listener for glossary_changed
        bus: EventBus | None = actions.get("bus")
        if bus:
            bus.on("glossary_changed", self._on_glossary_changed)

    @property
    def state(self) -> GlossaryTabState:
        """Access the tab's state object."""
        return self._state

    @property
    def glossary(self) -> "GlossaryFile":
        """Access the underlying glossary file."""
        return self._glossary

    def set_on_dirty_changed(self, callback) -> None:
        """Set the callback invoked when dirty state changes."""
        self._on_dirty_changed_callback = callback

    def build(self) -> ft.Control:
        """Build the full tab content: toolbar + search bar + term list.

        Returns the cached control on subsequent calls to avoid recreating
        the entire component tree on every tab switch (Requirement 12.1).
        """
        # Return cached control if already built (avoids full rebuild on tab switch)
        if self._container is not None:
            return self._container

        # Show loading indicator for large glossaries (>1000 terms)
        show_loading = len(self._glossary.terms) > 1000

        self._toolbar = GlossaryToolbar(
            page=self._page,
            state=self._state,
            actions=self._tab_actions,
        )

        self._search_bar = GlossarySearchBar(
            page=self._page,
            state=self._state,
            on_results=self._on_search_results,
            actions=self._tab_actions,
        )

        self._term_list = GlossaryTermList(
            page=self._page,
            state=self._state,
            actions=self._tab_actions,
        )

        toolbar_control = self._toolbar.build()
        search_bar_control = self._search_bar.build()

        if show_loading:
            # For large glossaries: build term list without populating rows,
            # show loading indicator, then defer row population so the user
            # sees the indicator before the heavy work begins.
            term_list_control = self._term_list.build(defer_populate=True)
            self._term_list.show_loading(True)
        else:
            term_list_control = self._term_list.build()

        self._container = ft.Container(
            content=ft.Column(
                [
                    toolbar_control,
                    search_bar_control,
                    term_list_control,
                ],
                expand=True,
                spacing=0,
            ),
            expand=True,
            bgcolor=Colors.BACKGROUND,
        )

        if show_loading:
            # Schedule deferred population: after the page renders the loading
            # indicator, populate rows and hide the indicator.
            self._schedule_deferred_populate()

        return self._container

    def _schedule_deferred_populate(self) -> None:
        """Populate rows after the initial render so the loading indicator is visible."""
        import threading

        def _deferred():
            import time
            # Small delay to allow the page to render the loading indicator
            time.sleep(0.05)
            if self._term_list:
                self._term_list.rebuild()
                self._term_list.show_loading(False)
            bus = self._actions.get("bus")
            if bus:
                bus.safe_update()
            else:
                try:
                    self._page.update()
                except Exception:
                    pass

        thread = threading.Thread(target=_deferred, daemon=True)
        thread.start()

    def mark_dirty(self) -> None:
        """Mark the tab as having unsaved modifications."""
        if not self._state.is_dirty:
            self._state.is_dirty = True
            self._notify_dirty_changed()

    def save(self) -> None:
        """Save the glossary via GlossaryManager and clear dirty state."""
        try:
            glossary_mgr = self._actions.get("glossary_manager")
            if not glossary_mgr:
                _log("No glossary_manager in actions — cannot save")
                return

            glossary_mgr.save_glossary(self._glossary)
            self._state.is_dirty = False
            self._notify_dirty_changed()

            # Emit glossary_changed event
            bus = self._actions.get("bus")
            if bus:
                bus.emit("glossary_changed")

        except (ValueError, OSError, PermissionError) as exc:
            _log(f"ERROR saving glossary: {exc}")
            bus = self._actions.get("bus")
            if bus:
                bus.show_banner(f"Failed to save glossary: {exc}", is_error=True)

    def refresh_terms(self) -> None:
        """Reload terms from the GlossaryFile and re-apply current filter."""
        try:
            # Re-read terms from the glossary object
            if self._state.search_query:
                # Re-apply the current search filter
                from .utils.fuzzy_search import fuzzy_filter

                results = fuzzy_filter(self._state.search_query, self._glossary.terms)
                self._state.filtered_terms = [term for term, _score in results]
            else:
                self._state.filtered_terms = list(self._glossary.terms)

            self._state.visible_count = min(100, len(self._state.filtered_terms))

            # Rebuild the term list display
            if self._term_list:
                self._term_list.rebuild()

            # Update toolbar term count
            if self._toolbar:
                self._toolbar.update_term_count()

            bus = self._actions.get("bus")
            if bus:
                bus.safe_update()

        except Exception:
            _log(f"ERROR in refresh_terms:\n{traceback.format_exc()}")

    def get_tab_title(self) -> str:
        """Return the glossary name, with ' *' suffix when dirty."""
        return self._state.get_tab_title()

    # ------------------------------------------------------------------
    # Private callbacks
    # ------------------------------------------------------------------
    # Private callbacks
    # ------------------------------------------------------------------

    def _highlight_term(self, german: str) -> None:
        """Trigger a temporary highlight on a term row in the list."""
        if self._term_list:
            self._term_list.highlight_term(german)

    def _on_search_results(self) -> None:
        """Called by GlossarySearchBar when search results are ready."""
        if self._term_list:
            self._term_list.rebuild()
        if self._toolbar:
            self._toolbar.update_term_count()

        bus = self._actions.get("bus")
        if bus:
            bus.safe_update()
        else:
            self._page.update()

    def _on_dirty_state_changed(self) -> None:
        """Called by sub-components when dirty state changes (e.g., after save)."""
        self._notify_dirty_changed()

    def _on_term_deleted(self, term: "GlossaryTerm") -> None:
        """Called when a term is deleted via the context menu."""
        self.mark_dirty()
        self.refresh_terms()

        # Emit glossary_changed so other components (sidebar, other tabs) refresh
        bus = self._actions.get("bus")
        if bus:
            bus.emit("glossary_changed")

    def _on_edit_term(self, term: "GlossaryTerm") -> None:
        """Called when Edit Term is selected from the context menu.

        Opens the edit term dialog pre-filled with the term's values.
        """
        from .dialogs.edit_term import EditTermDialog

        def _on_term_saved():
            self.mark_dirty()
            self.refresh_terms()

            # Emit glossary_changed so other components (sidebar, other tabs) refresh
            bus = self._actions.get("bus")
            if bus:
                bus.emit("glossary_changed")

        dialog = EditTermDialog(
            page=self._page,
            term=term,
            actions=self._tab_actions,
            on_saved=_on_term_saved,
        )
        dialog.show()

    def _on_glossary_changed(self, **kwargs) -> None:
        """Handle glossary_changed events from the EventBus.

        Refreshes the term list if the change affects this tab's glossary.
        """
        try:
            # Refresh terms to pick up any external changes
            # (e.g., another tab saved, sidebar changed active glossary)
            self._state.filtered_terms = list(self._glossary.terms)
            if self._state.search_query:
                from .utils.fuzzy_search import fuzzy_filter

                results = fuzzy_filter(
                    self._state.search_query, self._glossary.terms
                )
                self._state.filtered_terms = [term for term, _score in results]

            self._state.visible_count = min(
                self._state.visible_count, len(self._state.filtered_terms)
            )

            if self._term_list:
                self._term_list.rebuild()
            if self._toolbar:
                self._toolbar.update_term_count()

        except Exception:
            _log(f"ERROR in _on_glossary_changed:\n{traceback.format_exc()}")

    def _notify_dirty_changed(self) -> None:
        """Notify the parent about dirty state change."""
        if self._on_dirty_changed_callback:
            try:
                self._on_dirty_changed_callback(self)
            except Exception:
                _log(f"ERROR in dirty changed callback:\n{traceback.format_exc()}")
