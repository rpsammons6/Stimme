"""Per-tab state dataclass for glossary tab views."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.glossary_manager import GlossaryFile, GlossaryTerm


@dataclass
class GlossaryTabState:
    """Holds the complete UI state for a single glossary tab.

    Each open glossary tab maintains its own independent instance so that
    search queries, filtered results, and dirty flags are isolated.
    """

    glossary: GlossaryFile
    search_query: str = ""
    filtered_terms: list[GlossaryTerm] = field(default_factory=list)
    visible_count: int = 100
    is_dirty: bool = False
    is_global_search: bool = False
    global_results: list[tuple[GlossaryTerm, str]] = field(default_factory=list)
    search_in_progress: bool = False
    search_progress_text: str = ""

    def __post_init__(self) -> None:
        """Cap visible_count to actual term count on initialization."""
        if not self.filtered_terms:
            self.filtered_terms = list(self.glossary.terms)
        self.visible_count = min(self.visible_count, len(self.filtered_terms))

    def get_tab_title(self) -> str:
        """Return the glossary name, appending ' *' when dirty."""
        name = self.glossary.name or "Untitled"
        if self.is_dirty:
            return f"{name} *"
        return name
