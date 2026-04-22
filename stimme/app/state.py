"""
AppState: Single source of truth for all mutable UI state in Stimme.

Components READ from this object. Only the shell (or event handlers routed
through the shell) WRITE to it. This eliminates ghost state, stale references,
and the need for bidirectional syncing between components.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from app.models.version_store import VersionStore

if TYPE_CHECKING:
    from app.models.bulk_models import BookTranslation, Chapter


class AppState:
    """Centralized mutable state for the entire application."""

    def __init__(self):
        # --- Translation tabs (shell-level) ---
        self.translation_tabs: List[Dict[str, Any]] = []
        self.active_translation_index: int = -1  # -1 = home

        # --- Input panel ---
        self.input_text: str = ""

        # --- PDF state ---
        self.pdf_file: Optional[str] = None  # filename
        self.pdf_path: Optional[str] = None  # full path

        # --- Center panel ---
        self.center_tab: int = 0  # active tab index within center panel
        self.show_logs: bool = False
        self.commentary: Optional[str] = None

        # --- Busy flags ---
        self.translating: bool = False
        self.extracting: bool = False

        # --- Book / Bulk mode ---
        self.book_chapters: Optional[List["Chapter"]] = None
        self.book_mode: bool = False
        self.book_translation: Optional["BookTranslation"] = None
        self.bulk_cancel_requested: bool = False
        self.active_chapter_index: int = -1  # -1 = no chapter selected for preview

        # --- HITL version tracking ---
        self.version_store: VersionStore = VersionStore()

    # ------------------------------------------------------------------
    # Input text (compatibility with InputPanel)
    # ------------------------------------------------------------------

    def set_input_text(self, text: str):
        """Set input text (called by InputPanel on every keystroke)."""
        self.input_text = text

    def get_input_text(self) -> str:
        """Get input text."""
        return self.input_text

    # ------------------------------------------------------------------
    # Translation tabs
    # ------------------------------------------------------------------

    def add_translation(self, source_text: str, translation: str, commentary: str = None, metrics: dict = None, pdf_path: str = None, history_timestamp: str = None) -> int:
        """Add a translation result. Returns its index."""
        data = {
            "id": len(self.translation_tabs),
            "source_preview": (source_text[:50] + "...") if len(source_text) > 50 else source_text,
            "source_full": source_text,
            "translation": translation,
            "commentary": commentary,
            "metrics": metrics,
            "timestamp": datetime.now(),
        }
        if pdf_path:
            data["pdf_path"] = pdf_path
        if history_timestamp:
            data["history_timestamp"] = history_timestamp
        self.translation_tabs.append(data)
        self.active_translation_index = len(self.translation_tabs) - 1
        return self.active_translation_index

    def get_active_translation(self) -> Optional[Dict[str, Any]]:
        """Get the currently active translation data, or None."""
        if 0 <= self.active_translation_index < len(self.translation_tabs):
            return self.translation_tabs[self.active_translation_index]
        return None

    def close_translation_tab(self, index: int):
        """Close a translation tab and adjust the active index."""
        if 0 <= index < len(self.translation_tabs):
            self.translation_tabs.pop(index)
            if self.active_translation_index >= len(self.translation_tabs):
                self.active_translation_index = len(self.translation_tabs) - 1
            elif self.active_translation_index > index:
                self.active_translation_index -= 1
        # If nothing left, go home
        if not self.translation_tabs:
            self.active_translation_index = -1

    @property
    def is_home_active(self) -> bool:
        return self.active_translation_index == -1 or not self.translation_tabs

    @property
    def has_translations(self) -> bool:
        return len(self.translation_tabs) > 0

    # ------------------------------------------------------------------
    # PDF state
    # ------------------------------------------------------------------

    def set_pdf(self, filename: str, path: str):
        """Set the active PDF."""
        self.pdf_file = filename
        self.pdf_path = path

    def clear_pdf(self):
        """Clear all PDF state."""
        self.pdf_file = None
        self.pdf_path = None

    @property
    def has_pdf(self) -> bool:
        return self.pdf_file is not None

    # ------------------------------------------------------------------
    # Center panel
    # ------------------------------------------------------------------

    def start_log_session(self):
        """Switch center panel to log view."""
        self.show_logs = True
        self.center_tab = 0

    def end_log_session(self):
        """Return center panel to normal view."""
        self.show_logs = False
        self.center_tab = 0

    def set_commentary(self, text: str):
        """Set the commentary text."""
        self.commentary = text

    # ------------------------------------------------------------------
    # Book / Bulk mode
    # ------------------------------------------------------------------

    def set_book_state(self, chapters: List["Chapter"], metadata: Optional[Dict[str, Any]] = None):
        """Activate book mode with the given chapter list."""
        self.book_chapters = chapters
        self.book_mode = True
        self.book_translation = None
        self.bulk_cancel_requested = False
        self.active_chapter_index = -1

    def clear_book_state(self):
        """Reset all book-level state (e.g. on new file load or input clear)."""
        self.book_chapters = None
        self.book_mode = False
        self.book_translation = None
        self.bulk_cancel_requested = False
        self.active_chapter_index = -1

    @property
    def is_book_mode(self) -> bool:
        """True when the current input is being handled as a book."""
        return self.book_mode

    # ------------------------------------------------------------------
    # Unsaved content check (for exit confirmation)
    # ------------------------------------------------------------------

    @property
    def has_unsaved_content(self) -> bool:
        return bool(self.input_text and self.input_text.strip()) or self.has_pdf or self.has_translations
