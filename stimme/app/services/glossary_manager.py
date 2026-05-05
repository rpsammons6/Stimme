from __future__ import annotations

import csv
import json
import logging
import shutil
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List

from app.utils.file_ops import atomic_write

if TYPE_CHECKING:
    from app.services.glossary_journal import GlossaryJournal

logger = logging.getLogger(__name__)

# Try to import pyahocorasick; fall back gracefully
try:
    import ahocorasick
    _AHOCORASICK_AVAILABLE = True
except ImportError:
    _AHOCORASICK_AVAILABLE = False
    logger.warning("pyahocorasick not installed — falling back to linear term matching")


@dataclass
class GlossaryTerm:
    german: str                    # German_Term: the base word in German
    english: str                   # English: the default equivalent
    context_target: str = "N/A"    # Context_Sensitive_Target: the equivalent in your translation
    field_tag: str = "N/A"        # Field_Tag: disciplinary lens (Philosophy, Legal, Science, etc.)
    nuance_note: str = "N/A"      # Nuance_Note: semantic shift or technical application
    created_at: str = ""
    pinned: bool = False           # Whether this term is pinned to the sidebar


SUPPORTED_SCHEMA_VERSIONS = {1}


@dataclass
class GlossaryFile:
    """Wrapper around glossary metadata + terms for .glossary file serialization."""

    schema_version: int = 1
    name: str = ""
    author: str = ""
    field_tag: str = ""
    description: str = ""
    created_at: str = ""  # ISO 8601
    terms: list[GlossaryTerm] = field(default_factory=list)
    file_path: Path | None = None  # runtime-only, not serialized

    def to_json(self) -> str:
        """Serialize to JSON string, excluding runtime-only file_path."""
        d = asdict(self)
        d.pop("file_path", None)
        return json.dumps(d, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str, file_path: Path | None = None) -> "GlossaryFile":
        """Deserialize from a JSON string. Validates schema_version."""
        d = json.loads(data)
        return cls.from_dict(d, file_path=file_path)

    @classmethod
    def from_dict(cls, d: dict, file_path: Path | None = None) -> "GlossaryFile":
        """Construct from a dict (already-parsed JSON). Validates schema_version."""
        version = d.get("schema_version")
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported schema_version: {version}. "
                f"Supported versions: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )
        terms = [
            GlossaryTerm(
                german=t.get("german", ""),
                english=t.get("english", ""),
                context_target=t.get("context_target", "N/A"),
                field_tag=t.get("field_tag", "N/A"),
                nuance_note=t.get("nuance_note", "N/A"),
                created_at=t.get("created_at", ""),
                pinned=t.get("pinned", False),
            )
            for t in d.get("terms", [])
        ]
        return cls(
            schema_version=version,
            name=d.get("name", ""),
            author=d.get("author", ""),
            field_tag=d.get("field_tag", ""),
            description=d.get("description", ""),
            created_at=d.get("created_at", ""),
            terms=terms,
            file_path=file_path,
        )


@dataclass
class ConflictEntry:
    """Represents a conflict between an existing and incoming term during import."""

    german_key: str  # normalized key (strip().lower())
    existing_term: GlossaryTerm
    incoming_term: GlossaryTerm
    source_file: str  # path of the file being imported


# ---------------------------------------------------------------------------
# CSV Import/Export Helpers
# ---------------------------------------------------------------------------

# Known header variants mapped to standard GlossaryTerm field names
_HEADER_VARIANTS: dict[str, str] = {
    "german": "german",
    "deutsch": "german",
    "de": "german",
    "english": "english",
    "en": "english",
    "translation": "english",
    "context_target": "context_target",
    "context": "context_target",
    "field_tag": "field_tag",
    "field": "field_tag",
    "domain": "field_tag",
    "nuance_note": "nuance_note",
    "notes": "nuance_note",
    "nuance": "nuance_note",
}


def build_column_mapping(headers: list[str]) -> dict[str, str]:
    """Auto-detect column mapping from CSV headers.

    Normalizes each header to lowercase and maps known variants to standard
    GlossaryTerm field names.

    Args:
        headers: List of CSV column header strings.

    Returns:
        Mapping of original_header -> glossary_field for recognized headers.
    """
    mapping: dict[str, str] = {}
    for header in headers:
        normalized = header.strip().lower()
        if normalized in _HEADER_VARIANTS:
            mapping[header] = _HEADER_VARIANTS[normalized]
    return mapping


def import_csv(
    path: Path,
    column_mapping: dict[str, str] | None = None,
) -> tuple[list[GlossaryTerm], int]:
    """Parse a CSV file into GlossaryTerm objects.

    Args:
        path: Path to the CSV file.
        column_mapping: Optional mapping of csv_header -> glossary_field.
            If None, auto-detects using build_column_mapping().

    Returns:
        Tuple of (list of parsed GlossaryTerm objects, count of skipped rows).

    Raises:
        ValueError: If required columns (german, english) are not found in the mapping.
    """
    path = Path(path)
    terms: list[GlossaryTerm] = []
    skipped = 0

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        if column_mapping is None:
            column_mapping = build_column_mapping(headers)

        # Validate required columns are present in the mapping
        mapped_fields = set(column_mapping.values())
        if "german" not in mapped_fields:
            raise ValueError(
                "Required column 'german' (or variant: deutsch, de) not found in CSV headers"
            )
        if "english" not in mapped_fields:
            raise ValueError(
                "Required column 'english' (or variant: en, translation) not found in CSV headers"
            )

        # Build reverse lookup: glossary_field -> csv_header
        field_to_header: dict[str, str] = {}
        for csv_header, field_name in column_mapping.items():
            field_to_header[field_name] = csv_header

        for row in reader:
            german_val = row.get(field_to_header.get("german", ""), "").strip()
            english_val = row.get(field_to_header.get("english", ""), "").strip()

            # Skip rows missing required fields
            if not german_val or not english_val:
                skipped += 1
                continue

            context_target = row.get(field_to_header.get("context_target", ""), "").strip() or "N/A"
            field_tag = row.get(field_to_header.get("field_tag", ""), "").strip() or "N/A"
            nuance_note = row.get(field_to_header.get("nuance_note", ""), "").strip() or "N/A"

            terms.append(
                GlossaryTerm(
                    german=german_val,
                    english=english_val,
                    context_target=context_target,
                    field_tag=field_tag,
                    nuance_note=nuance_note,
                )
            )

    return terms, skipped


def export_csv(terms: list[GlossaryTerm], path: Path) -> None:
    """Write glossary terms as a CSV file with standard headers.

    Args:
        terms: List of GlossaryTerm objects to export.
        path: Destination path for the CSV file.
    """
    path = Path(path)
    fieldnames = ["german", "english", "context_target", "field_tag", "nuance_note"]

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for term in terms:
            writer.writerow(
                {
                    "german": term.german,
                    "english": term.english,
                    "context_target": term.context_target,
                    "field_tag": term.field_tag,
                    "nuance_note": term.nuance_note,
                }
            )


# ---------------------------------------------------------------------------
# Aho-Corasick Term Matcher
# ---------------------------------------------------------------------------


class AhoCorasickMatcher:
    """Wraps pyahocorasick for term matching with graceful fallback."""

    def __init__(self):
        self._automaton = None  # ahocorasick.Automaton or None
        self._dirty: bool = True
        self._terms: dict[str, GlossaryTerm] = {}  # german_lower -> term

    def set_terms(self, terms: list[GlossaryTerm]) -> None:
        """Replace all terms and mark automaton as dirty."""
        self._terms = {}
        for term in terms:
            key = term.german.strip().lower()
            if key:
                self._terms[key] = term
        self._dirty = True

    def invalidate(self) -> None:
        """Mark automaton for rebuild on next search."""
        self._dirty = True

    def search(self, text: str) -> list[GlossaryTerm]:
        """Scan text in a single pass, return matched terms."""
        if not text or not self._terms:
            return []

        if not _AHOCORASICK_AVAILABLE:
            return self._linear_fallback(text)

        if self._dirty:
            self._rebuild()

        matched: dict[str, GlossaryTerm] = {}
        for end_idx, (key, term) in self._automaton.iter(text.lower()):
            if key not in matched:
                matched[key] = term
        return list(matched.values())

    def _rebuild(self) -> None:
        """Build the Aho-Corasick automaton from current terms."""
        self._automaton = ahocorasick.Automaton()
        for key, term in self._terms.items():
            self._automaton.add_word(key, (key, term))
        self._automaton.make_automaton()
        self._dirty = False

    def _linear_fallback(self, text: str) -> list[GlossaryTerm]:
        """Fallback when pyahocorasick is unavailable."""
        text_lower = text.lower()
        matched: list[GlossaryTerm] = []
        for key, term in self._terms.items():
            if key in text_lower:
                matched.append(term)
        return matched


class GlossaryManager:
    """Service for managing pinned glossary terms that enforce translation consistency."""

    def __init__(
        self,
        journal: GlossaryJournal | None = None,
        config_service=None,
        event_bus=None,
    ):
        # Project root: stimme/ directory (where main.py lives)
        project_root = Path(__file__).resolve().parent.parent.parent

        self.glossary_dir = project_root
        self.glossary_file = self.glossary_dir / "glossary.json"
        self.glossary_dir.mkdir(exist_ok=True)

        # Compute glossaries directory (portable mode vs standard)
        if getattr(sys, 'frozen', False):
            # Portable mode: use ./glossaries/ relative to executable
            self._glossaries_dir = Path(sys.executable).parent / "glossaries"
        else:
            # Standard mode: use ./glossaries/ in the project root
            self._glossaries_dir = project_root / "glossaries"
        self._glossaries_dir.mkdir(parents=True, exist_ok=True)

        self.terms: List[GlossaryTerm] = []
        self.is_dirty: bool = False
        self._journal = journal
        self._config_service = config_service
        self._event_bus = event_bus
        self._active_paths: list[Path] = []
        self._loaded_glossaries: dict[Path, GlossaryFile] = {}
        self._matcher = AhoCorasickMatcher()
        self._migrate_legacy()
        self.load()

        # Load active glossaries from config (if available)
        if self._config_service is not None:
            active_paths_str = self._config_service.get("active_glossaries", [])
            for path_str in active_paths_str:
                p = Path(path_str)
                if p.exists():
                    try:
                        self.load_glossary(p)
                        if p not in self._active_paths:
                            self._active_paths.append(p)
                    except (ValueError, json.JSONDecodeError) as e:
                        logger.warning("Could not load active glossary %s: %s", p, e)

    @property
    def glossaries_dir(self) -> Path:
        """Return the glossaries directory path (portable or standard)."""
        return self._glossaries_dir

    def list_glossary_files(self) -> list[Path]:
        """Enumerate all .glossary files in the glossaries directory, sorted alphabetically."""
        return sorted(self._glossaries_dir.glob("*.glossary"))

    @property
    def active_glossaries(self) -> list[GlossaryFile]:
        """Return list of active GlossaryFile objects."""
        return [self._loaded_glossaries[p] for p in self._active_paths if p in self._loaded_glossaries]

    @property
    def primary_glossary(self) -> GlossaryFile | None:
        """Return the first active glossary or None."""
        active = self.active_glossaries
        return active[0] if active else None

    def load_glossary(self, path: Path) -> GlossaryFile:
        """Read and parse a .glossary file, store in loaded glossaries cache.

        Args:
            path: Path to the .glossary file to load.

        Returns:
            The parsed GlossaryFile object.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file contains invalid JSON or unsupported schema.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Glossary file not found: {path}")
        data = path.read_text(encoding="utf-8")
        glossary = GlossaryFile.from_json(data, file_path=path)
        self._loaded_glossaries[path] = glossary
        return glossary

    def save_glossary(self, glossary: GlossaryFile | None = None) -> None:
        """Write a glossary to disk using atomic_write.

        Args:
            glossary: The GlossaryFile to save. If None, saves the primary active glossary.

        Raises:
            ValueError: If no glossary is provided and no primary glossary is active.
        """
        if glossary is None:
            glossary = self.primary_glossary
        if glossary is None:
            raise ValueError("No glossary to save: no glossary provided and no primary glossary active")
        if glossary.file_path is None:
            raise ValueError("Cannot save glossary without a file_path")
        atomic_write(glossary.file_path, glossary.to_json())

    def create_glossary(self, name: str, **metadata) -> GlossaryFile:
        """Create a new empty glossary file in the glossaries directory.

        Args:
            name: Display name for the glossary.
            **metadata: Additional metadata fields (author, field_tag, description).

        Returns:
            The newly created GlossaryFile object.
        """
        file_name = f"{name.lower().replace(' ', '_')}.glossary"
        file_path = self._glossaries_dir / file_name
        glossary = GlossaryFile(
            schema_version=1,
            name=name,
            author=metadata.get("author", ""),
            field_tag=metadata.get("field_tag", ""),
            description=metadata.get("description", ""),
            created_at=datetime.now().isoformat(),
            terms=[],
            file_path=file_path,
        )
        atomic_write(file_path, glossary.to_json())
        self._loaded_glossaries[file_path] = glossary
        return glossary

    def set_active(self, path: Path, slot: str = "primary") -> None:
        """Activate a glossary in the given slot (primary or secondary).

        Args:
            path: Path to the .glossary file to activate.
            slot: Either "primary" (default) or "secondary".

        Raises:
            ValueError: If attempting to activate more than 2 glossaries.
        """
        path = Path(path)

        # Load the glossary if not already loaded
        if path not in self._loaded_glossaries:
            self.load_glossary(path)

        if slot == "primary":
            if len(self._active_paths) == 0:
                self._active_paths.append(path)
            else:
                self._active_paths[0] = path
        elif slot == "secondary":
            if len(self._active_paths) == 0:
                # Need a primary first; set path as primary
                self._active_paths.append(path)
            elif len(self._active_paths) == 1:
                self._active_paths.append(path)
            else:
                self._active_paths[1] = path
        else:
            raise ValueError(f"Invalid slot: {slot}. Must be 'primary' or 'secondary'.")

        # Enforce max 2 active glossaries
        if len(self._active_paths) > 2:
            raise ValueError("Maximum of 2 active glossaries allowed")

        # Persist active glossary paths
        if self._config_service is not None:
            self._config_service.set("active_glossaries", [str(p) for p in self._active_paths])

        # Emit glossary_changed event
        if self._event_bus is not None:
            self._event_bus.emit("glossary_changed")

    def swap_glossary(self, path: Path) -> None:
        """Replace the current primary glossary with a new one.

        Auto-saves the current primary glossary before loading the new one.

        Args:
            path: Path to the new glossary file to load as primary.
        """
        path = Path(path)

        # Auto-save current primary if it exists and has a file_path
        current_primary = self.primary_glossary
        if current_primary is not None and current_primary.file_path is not None:
            self.save_glossary(current_primary)

        # Load the new glossary
        if path not in self._loaded_glossaries:
            self.load_glossary(path)

        # Set as primary (replace first element or add)
        if len(self._active_paths) == 0:
            self._active_paths.append(path)
        else:
            self._active_paths[0] = path

        # Persist active glossary paths
        if self._config_service is not None:
            self._config_service.set("active_glossaries", [str(p) for p in self._active_paths])

        # Emit glossary_changed event
        if self._event_bus is not None:
            self._event_bus.emit("glossary_changed")

    def get_active_terms(self) -> list[GlossaryTerm]:
        """Merge terms from all active glossaries into a single list.

        Returns:
            Combined list of GlossaryTerm objects from all active glossaries.
        """
        merged: list[GlossaryTerm] = []
        for p in self._active_paths:
            if p in self._loaded_glossaries:
                merged.extend(self._loaded_glossaries[p].terms)
        return merged

    def import_glossary(
        self, path: Path, column_mapping: dict | None = None
    ) -> tuple[GlossaryFile, list[ConflictEntry]]:
        """Import a glossary file (.glossary or .csv) into the glossaries directory.

        Args:
            path: Path to the file to import.
            column_mapping: Optional column mapping for CSV files.

        Returns:
            Tuple of (imported GlossaryFile, list of ConflictEntry for conflicts).

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file has an unsupported schema or format.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Import file not found: {path}")

        suffix = path.suffix.lower()

        if suffix == ".glossary":
            # Parse and validate the .glossary file
            data = path.read_text(encoding="utf-8")
            glossary = GlossaryFile.from_json(data, file_path=path)

            # Copy file to glossaries directory
            dest = self._glossaries_dir / path.name
            shutil.copy2(path, dest)

            # Update file_path to the new location
            glossary.file_path = dest

            # Store in loaded glossaries
            self._loaded_glossaries[dest] = glossary

        elif suffix == ".csv":
            terms, skipped = import_csv(path, column_mapping=column_mapping)
            if skipped > 0:
                logger.info("CSV import: skipped %d malformed rows", skipped)
            # Create a GlossaryFile from the imported terms
            file_name = path.stem + ".glossary"
            dest = self._glossaries_dir / file_name
            glossary = GlossaryFile(
                schema_version=1,
                name=path.stem,
                created_at=datetime.now().isoformat(),
                terms=terms,
                file_path=dest,
            )
            atomic_write(dest, glossary.to_json())
            self._loaded_glossaries[dest] = glossary
        else:
            raise ValueError(
                f"Unsupported file format: '{suffix}'. Expected '.glossary' or '.csv'."
            )

        # Detect conflicts with existing active terms
        existing_terms = self.get_active_terms()
        existing_by_key: dict[str, GlossaryTerm] = {}
        for term in existing_terms:
            key = term.german.strip().lower()
            existing_by_key[key] = term

        conflicts: list[ConflictEntry] = []
        for incoming_term in glossary.terms:
            key = incoming_term.german.strip().lower()
            if key in existing_by_key:
                conflicts.append(
                    ConflictEntry(
                        german_key=key,
                        existing_term=existing_by_key[key],
                        incoming_term=incoming_term,
                        source_file=str(path),
                    )
                )

        return glossary, conflicts

    def export_glossary(self, path: Path, filter_fn=None) -> None:
        """Export the active glossary (or filtered subset) to a .glossary file.

        Args:
            path: Destination path for the exported file.
            filter_fn: Optional callable that takes a GlossaryTerm and returns bool.
                       Only terms where filter_fn(term) is True are included.

        Raises:
            ValueError: If no active glossary exists.
        """
        primary = self.primary_glossary
        if primary is None:
            raise ValueError("No active glossary to export")

        if filter_fn is not None:
            terms = [t for t in primary.terms if filter_fn(t)]
        else:
            terms = list(primary.terms)

        exported = GlossaryFile(
            schema_version=primary.schema_version,
            name=primary.name,
            author=primary.author,
            field_tag=primary.field_tag,
            description=primary.description,
            created_at=primary.created_at,
            terms=terms,
        )
        atomic_write(Path(path), exported.to_json())

    def export_csv(self, path: Path, filter_fn=None) -> None:
        """Export the active glossary terms as CSV.

        Args:
            path: Destination path for the CSV file.
            filter_fn: Optional callable that takes a GlossaryTerm and returns bool.
                       Only terms where filter_fn(term) is True are included.

        Raises:
            ValueError: If no active glossary exists.
        """
        primary = self.primary_glossary
        if primary is None:
            raise ValueError("No active glossary to export")

        if filter_fn is not None:
            terms = [t for t in primary.terms if filter_fn(t)]
        else:
            terms = list(primary.terms)

        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["german", "english", "context_target", "field_tag", "nuance_note"]
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for term in terms:
            writer.writerow(
                {
                    "german": term.german,
                    "english": term.english,
                    "context_target": term.context_target,
                    "field_tag": term.field_tag,
                    "nuance_note": term.nuance_note,
                }
            )
        atomic_write(dest, buf.getvalue())

    def load(self) -> None:
        """Load glossary from file, recovering gracefully from corruption."""
        if self.glossary_file.exists():
            try:
                with open(self.glossary_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.terms = [
                        GlossaryTerm(
                            german=entry.get("german", ""),
                            english=entry.get("english", ""),
                            context_target=entry.get("context_target", "N/A"),
                            field_tag=entry.get("field_tag", "N/A"),
                            nuance_note=entry.get("nuance_note", entry.get("notes", "N/A")),
                            created_at=entry.get("created_at", ""),
                            pinned=entry.get("pinned", False),
                        )
                        for entry in data
                    ]
                else:
                    print("⚠️  GLOSSARY: File contained non-list data, resetting")
                    self.terms = []
                    self._backup_and_reset()
            except json.JSONDecodeError as e:
                print(f"⚠️  GLOSSARY: Corrupted JSON, backing up and resetting: {e}")
                self.terms = []
                self._backup_and_reset()
            except Exception as e:
                print(f"⚠️  GLOSSARY: Error loading glossary, starting fresh: {e}")
                self.terms = []
        else:
            self.terms = []

    def save(self) -> None:
        """Save glossary to file using atomic write."""
        try:
            self.glossary_dir.mkdir(exist_ok=True)
            content = json.dumps([asdict(t) for t in self.terms], indent=2, ensure_ascii=False)
            atomic_write(self.glossary_file, content)
            self.is_dirty = False
            if self._journal is not None:
                self._journal.reset()
        except Exception as e:
            print(f"⚠️  GLOSSARY: Error saving: {e}")

    def _backup_and_reset(self) -> None:
        """Backup corrupted file and start fresh."""
        try:
            backup_path = self.glossary_file.with_suffix(".json.bak")
            if self.glossary_file.exists():
                shutil.copy2(self.glossary_file, backup_path)
                print(f"  GLOSSARY: Corrupted file backed up to {backup_path}")
            self.save()
        except Exception as e:
            print(f"  GLOSSARY: Could not backup: {e}")

    def _migrate_legacy(self) -> None:
        """Migrate legacy flat-array glossary.json to .glossary format.

        This method is idempotent: if the target file already exists, it skips.
        On corrupted JSON or permission errors, it logs a warning and starts empty.
        """
        target_path = self._glossaries_dir / "legacy_imported.glossary"

        # Idempotent: skip if already migrated
        if target_path.exists():
            return

        # Skip if legacy file doesn't exist
        if not self.glossary_file.exists():
            return

        try:
            raw = self.glossary_file.read_text(encoding="utf-8")
            data = json.loads(raw)

            if not isinstance(data, list):
                logger.warning(
                    "Legacy glossary.json is not a flat JSON array, skipping migration"
                )
                return

            # Parse legacy terms into GlossaryTerm objects
            terms = [
                GlossaryTerm(
                    german=entry.get("german", ""),
                    english=entry.get("english", ""),
                    context_target=entry.get("context_target", "N/A"),
                    field_tag=entry.get("field_tag", "N/A"),
                    nuance_note=entry.get("nuance_note", entry.get("notes", "N/A")),
                    created_at=entry.get("created_at", ""),
                    pinned=entry.get("pinned", False),
                )
                for entry in data
                if isinstance(entry, dict)
            ]

            # Wrap in a GlossaryFile with metadata
            glossary_file = GlossaryFile(
                schema_version=1,
                name="Legacy Imported",
                created_at=datetime.now().isoformat(),
                terms=terms,
            )

            # Write to glossaries/legacy_imported.glossary using atomic_write
            atomic_write(target_path, glossary_file.to_json())

            # Create backup of the original legacy file
            backup_path = self.glossary_file.with_name("glossary.json.migrated_backup")
            shutil.copy2(self.glossary_file, backup_path)

            # Set as Primary Active Glossary
            self._active_paths = [target_path]

            logger.info(
                "Legacy glossary migrated to %s (%d terms)",
                target_path,
                len(terms),
            )

        except json.JSONDecodeError as e:
            logger.warning(
                "Legacy glossary.json contains corrupted JSON, skipping migration: %s",
                e,
            )
        except PermissionError as e:
            logger.warning(
                "Permission error during legacy migration, skipping: %s",
                e,
            )

    def add_term(
        self,
        german: str,
        english: str,
        context_target: str = "",
        field_tag: str = "",
        nuance_note: str = "",
    ) -> None:
        """Add or overwrite a glossary term. German and English are required."""
        if not german.strip() or not english.strip():
            raise ValueError("German and English fields must not be empty")

        german = german.strip()
        english = english.strip()
        context_target = context_target.strip() or "N/A"
        field_tag = field_tag.strip() or "N/A"
        nuance_note = nuance_note.strip() or "N/A"

        # Overwrite if exists (case-insensitive duplicate detection)
        self.terms = [t for t in self.terms if t.german.strip().lower() != german.strip().lower()]
        new_term = GlossaryTerm(
            german=german,
            english=english,
            context_target=context_target,
            field_tag=field_tag,
            nuance_note=nuance_note,
            created_at=datetime.now().isoformat(),
        )
        self.terms.append(new_term)
        self.is_dirty = True
        if self._journal is not None:
            from app.services.glossary_journal import JournalEntry

            self._journal.append(
                JournalEntry(
                    operation="add",
                    term_data=asdict(new_term),
                    glossary_path=str(self.glossary_file),
                    timestamp=datetime.now().isoformat(),
                )
            )
        self._matcher.invalidate()
        self.save()

    def remove_term(self, german: str) -> None:
        """Remove a term by case-insensitive German match."""
        normalized = german.strip().lower()
        removed = [t for t in self.terms if t.german.strip().lower() == normalized]
        self.terms = [t for t in self.terms if t.german.strip().lower() != normalized]
        if removed:
            self.is_dirty = True
            self._matcher.invalidate()
            if self._journal is not None:
                from app.services.glossary_journal import JournalEntry

                self._journal.append(
                    JournalEntry(
                        operation="remove",
                        term_data=asdict(removed[0]),
                        glossary_path=str(self.glossary_file),
                        timestamp=datetime.now().isoformat(),
                    )
                )
        self.save()

    def get_terms(self) -> List[GlossaryTerm]:
        """Return all terms sorted alphabetically by German."""
        return sorted(self.terms, key=lambda t: t.german.lower())

    def get_pinned_terms(self) -> List[GlossaryTerm]:
        """Return only pinned terms sorted alphabetically by German."""
        return sorted([t for t in self.terms if t.pinned], key=lambda t: t.german.lower())

    def pin_term(self, german: str) -> None:
        """Pin a term to the sidebar by German key (case-insensitive)."""
        normalized = german.strip().lower()
        for t in self.terms:
            if t.german.strip().lower() == normalized:
                t.pinned = True
                self.is_dirty = True
                if self._journal is not None:
                    from app.services.glossary_journal import JournalEntry

                    self._journal.append(
                        JournalEntry(
                            operation="pin",
                            term_data=asdict(t),
                            glossary_path=str(self.glossary_file),
                            timestamp=datetime.now().isoformat(),
                        )
                    )
                break
        self.save()

    def unpin_term(self, german: str) -> None:
        """Unpin a term from the sidebar by German key (case-insensitive)."""
        normalized = german.strip().lower()
        for t in self.terms:
            if t.german.strip().lower() == normalized:
                t.pinned = False
                self.is_dirty = True
                if self._journal is not None:
                    from app.services.glossary_journal import JournalEntry

                    self._journal.append(
                        JournalEntry(
                            operation="unpin",
                            term_data=asdict(t),
                            glossary_path=str(self.glossary_file),
                            timestamp=datetime.now().isoformat(),
                        )
                    )
                break
        self.save()

    def get_prompt_block(self, source_text: str = "") -> str:
        """Return the formatted MANDATORY TERMS block for prompt injection.

        Uses Aho-Corasick matching to find relevant terms in source_text.
        Always includes pinned terms. Caps at max_injected_terms.
        Returns empty string when no terms match and no terms are pinned.
        """
        # Get all active terms (from active glossaries, or fall back to self.terms)
        all_terms = self.get_active_terms() if self._active_paths else self.terms

        if not all_terms:
            return ""

        # Get max_injected_terms from config or default
        max_injected = 50
        if self._config_service is not None:
            max_injected = self._config_service.get("max_injected_terms", 50)

        # Update matcher with current terms
        self._matcher.set_terms(all_terms)

        # Get pinned terms (always included)
        pinned_terms = [t for t in all_terms if t.pinned]

        # Get matched terms from source_text
        matched_terms = []
        if source_text:
            matched_terms = self._matcher.search(source_text)

        # Build priority-ordered list:
        # 1. Matched terms (from source_text)
        # 2. Pinned terms (not already in matched)
        # 3. Remaining terms by creation date (newest first)

        included: list[GlossaryTerm] = []
        seen_keys: set[str] = set()

        # Add matched terms first
        for term in matched_terms:
            key = term.german.strip().lower()
            if key not in seen_keys:
                included.append(term)
                seen_keys.add(key)

        # Add pinned terms (not already included)
        for term in pinned_terms:
            key = term.german.strip().lower()
            if key not in seen_keys:
                included.append(term)
                seen_keys.add(key)

        # If source_text is empty/None, only return pinned terms
        if not source_text:
            included = [t for t in included if t.pinned]
            if not included:
                return ""
        else:
            # Add remaining terms by creation date (newest first) if we have room
            remaining = [t for t in all_terms if t.german.strip().lower() not in seen_keys]
            remaining.sort(key=lambda t: t.created_at, reverse=True)
            for term in remaining:
                if len(included) >= max_injected:
                    break
                included.append(term)

        # Cap at max_injected_terms
        included = included[:max_injected]

        if not included:
            return ""

        # Log injection statistics
        logger.info(
            "Prompt block: %d matched, %d pinned, %d total active terms",
            len(matched_terms),
            len(pinned_terms),
            len(all_terms),
        )

        # Format the prompt block
        lines = ["--- MANDATORY TERMS (ALWAYS USE THESE EXACT TRANSLATIONS) ---"]
        for term in included:
            entry = f'"{term.german}" → "{term.context_target}"'
            if term.field_tag and term.field_tag != "N/A":
                entry += f" [{term.field_tag}]"
            if term.nuance_note and term.nuance_note != "N/A":
                entry += f" — {term.nuance_note}"
            lines.append(entry)
        lines.append("--- END MANDATORY TERMS ---")
        return "\n".join(lines)

    def apply_journal_recovery(self, entries: list) -> None:
        """Replay journal entries to recover unsaved glossary edits.

        Args:
            entries: List of JournalEntry objects from the journal file.

        Skips entries referencing non-existent glossary paths and reports
        errors via the EventBus. After processing, saves the glossary
        and resets the journal.
        """
        from app.services.glossary_journal import JournalEntry

        glossary_paths_checked: dict[str, bool] = {}

        for entry in entries:
            glossary_path = entry.glossary_path

            # Cache path existence checks to avoid repeated filesystem calls
            if glossary_path not in glossary_paths_checked:
                glossary_paths_checked[glossary_path] = Path(glossary_path).exists()

            if not glossary_paths_checked[glossary_path]:
                if self._event_bus:
                    self._event_bus.show_banner(
                        f"Recovery: Glossary not found at {glossary_path}",
                        is_error=True,
                    )
                continue

            if entry.operation == "add":
                german = entry.term_data.get("german", "")
                english = entry.term_data.get("english", "")
                if german.strip() and english.strip():
                    # Directly manipulate terms to avoid re-journaling and repeated saves
                    normalized = german.strip().lower()
                    self.terms = [
                        t for t in self.terms
                        if t.german.strip().lower() != normalized
                    ]
                    new_term = GlossaryTerm(
                        german=german.strip(),
                        english=english.strip(),
                        context_target=entry.term_data.get("context_target", "").strip() or "N/A",
                        field_tag=entry.term_data.get("field_tag", "").strip() or "N/A",
                        nuance_note=entry.term_data.get("nuance_note", "").strip() or "N/A",
                        created_at=entry.term_data.get("created_at", datetime.now().isoformat()),
                    )
                    self.terms.append(new_term)
                    self.is_dirty = True
            elif entry.operation == "remove":
                german = entry.term_data.get("german", "")
                if german.strip():
                    normalized = german.strip().lower()
                    original_len = len(self.terms)
                    self.terms = [
                        t for t in self.terms
                        if t.german.strip().lower() != normalized
                    ]
                    if len(self.terms) < original_len:
                        self.is_dirty = True

        # Invalidate matcher since terms may have changed
        self._matcher.invalidate()

        # Save once after all entries are processed
        self.save()

        # Reset the journal (save() already resets, but be explicit for clarity)
        if self._journal:
            self._journal.reset()
