"""
Append-only journal for unsaved glossary edits.

Records each glossary operation (add, modify, remove) as a JSON-lines entry
so that unsaved edits can be recovered after a crash. The journal is truncated
when the glossary is successfully saved to disk.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from app.utils.file_ops import atomic_write


@dataclass
class JournalEntry:
    """A single journaled glossary operation."""

    operation: str       # "add", "modify", or "remove"
    term_data: dict      # serialized GlossaryTerm fields
    glossary_path: str   # absolute path to the source glossary file
    timestamp: str       # ISO 8601


class GlossaryJournal:
    """Append-only log of unsaved glossary edits for crash recovery.

    Each call to :meth:`append` writes one JSON line to the journal file.
    Calling :meth:`reset` atomically truncates the file (safe against crashes
    during the truncation itself).
    """

    JOURNAL_FILE: str = "glossary_journal.log"

    def __init__(self, stimme_dir: Path) -> None:
        self._stimme_dir = Path(stimme_dir)
        self._journal_path = self._stimme_dir / self.JOURNAL_FILE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, entry: JournalEntry) -> None:
        """Serialize *entry* to JSON and append it as a new line."""
        self._stimme_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(entry), ensure_ascii=False)
        with open(self._journal_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def reset(self) -> None:
        """Truncate the journal using :func:`atomic_write`."""
        atomic_write(self._journal_path, "")

    def read_entries(self) -> list[JournalEntry]:
        """Parse every line in the journal and return a list of entries.

        Malformed lines are silently skipped so that a partially-written
        trailing line (from a crash mid-append) does not prevent recovery
        of earlier entries.
        """
        if not self._journal_path.exists():
            return []

        entries: list[JournalEntry] = []
        with open(self._journal_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(
                        JournalEntry(
                            operation=data.get("operation", ""),
                            term_data=data.get("term_data", {}),
                            glossary_path=data.get("glossary_path", ""),
                            timestamp=data.get("timestamp", ""),
                        )
                    )
                except (json.JSONDecodeError, TypeError, KeyError):
                    # Skip malformed lines gracefully
                    continue
        return entries

    def has_entries(self) -> bool:
        """Return ``True`` if the journal file exists and is non-empty."""
        if not self._journal_path.exists():
            return False
        return self._journal_path.stat().st_size > 0
