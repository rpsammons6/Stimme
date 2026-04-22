import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List


@dataclass
class GlossaryTerm:
    german: str                    # German_Term: the base word in German
    english: str                   # English: the default equivalent
    context_target: str = "N/A"    # Context_Sensitive_Target: the equivalent in your translation
    field_tag: str = "N/A"        # Field_Tag: disciplinary lens (Philosophy, Legal, Science, etc.)
    nuance_note: str = "N/A"      # Nuance_Note: semantic shift or technical application
    created_at: str = ""
    pinned: bool = False           # Whether this term is pinned to the sidebar


class GlossaryManager:
    """Service for managing pinned glossary terms that enforce translation consistency."""

    def __init__(self):
        self.glossary_dir = Path.home() / ".stimme"
        self.glossary_file = self.glossary_dir / "glossary.json"
        self.glossary_dir.mkdir(exist_ok=True)
        self.terms: List[GlossaryTerm] = []
        self.load()

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
        """Save glossary to file."""
        try:
            self.glossary_dir.mkdir(exist_ok=True)
            with open(self.glossary_file, "w", encoding="utf-8") as f:
                json.dump([asdict(t) for t in self.terms], f, indent=2)
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

        # Overwrite if exists
        self.terms = [t for t in self.terms if t.german != german]
        self.terms.append(
            GlossaryTerm(
                german=german,
                english=english,
                context_target=context_target,
                field_tag=field_tag,
                nuance_note=nuance_note,
                created_at=datetime.now().isoformat(),
            )
        )
        self.save()

    def remove_term(self, german: str) -> None:
        """Remove a term by exact German match."""
        self.terms = [t for t in self.terms if t.german != german]
        self.save()

    def get_terms(self) -> List[GlossaryTerm]:
        """Return all terms sorted alphabetically by German."""
        return sorted(self.terms, key=lambda t: t.german.lower())

    def get_pinned_terms(self) -> List[GlossaryTerm]:
        """Return only pinned terms sorted alphabetically by German."""
        return sorted([t for t in self.terms if t.pinned], key=lambda t: t.german.lower())

    def pin_term(self, german: str) -> None:
        """Pin a term to the sidebar by German key."""
        for t in self.terms:
            if t.german == german:
                t.pinned = True
                break
        self.save()

    def unpin_term(self, german: str) -> None:
        """Unpin a term from the sidebar by German key."""
        for t in self.terms:
            if t.german == german:
                t.pinned = False
                break
        self.save()

    def get_prompt_block(self) -> str:
        """Return the formatted MANDATORY TERMS block for prompt injection, or empty string."""
        if not self.terms:
            return ""

        lines = ["--- MANDATORY TERMS (ALWAYS USE THESE EXACT TRANSLATIONS) ---"]
        for term in sorted(self.terms, key=lambda t: t.german.lower()):
            entry = f'"{term.german}" → "{term.context_target}"'
            if term.field_tag and term.field_tag != "N/A":
                entry += f" [{term.field_tag}]"
            if term.nuance_note and term.nuance_note != "N/A":
                entry += f" — {term.nuance_note}"
            lines.append(entry)
        lines.append("--- END MANDATORY TERMS ---")
        return "\n".join(lines)
