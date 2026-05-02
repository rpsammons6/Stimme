"""CorrectionService — vectorizes, stores, retrieves, and deletes user
corrections in a dedicated LanceDB 'corrections' table.

Feature: hitl-workflow
Requirements: 5.2, 6.1, 6.2, 6.3, 6.4, 6.5, 9.3
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from app.models.hitl_models import CorrectionRecord

if TYPE_CHECKING:
    from programs.brain import TranslationBrain


class CorrectionService:
    """Manages correction vectorization, storage, and retrieval from LanceDB."""

    CORRECTIONS_TABLE = "corrections"
    MAX_CORRECTION_MATCHES = 3
    RELEVANCE_THRESHOLD = 1.0

    def __init__(self, brain: "TranslationBrain") -> None:
        self.brain = brain
        self.db = brain.db
        self.embed_model = brain.embed_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def commit_correction(
        self,
        german_source: str,
        original_translation: str,
        corrected_translation: str,
        thematic_focus: str,
    ) -> bool:
        """Vectorize and store a correction record in LanceDB.

        Creates the corrections table if it doesn't exist.
        Returns True on success, False on failure.
        """
        try:
            vector = self.embed_model.encode(german_source).tolist()
        except Exception as exc:
            print(f"⚠️  CORRECTIONS: Failed to generate embedding: {exc}")
            return False

        record = {
            "id": str(uuid.uuid4()),
            "german_source": german_source,
            "original_translation": original_translation,
            "corrected_translation": corrected_translation,
            "thematic_focus": thematic_focus,
            "timestamp": datetime.now().isoformat(),
            "vector": vector,
        }

        try:
            if self.db is None:
                print("⚠️  CORRECTIONS: No vector database connection available")
                return False

            if self.CORRECTIONS_TABLE not in self.db.table_names():
                self.db.create_table(self.CORRECTIONS_TABLE, [record])
            else:
                table = self.db.open_table(self.CORRECTIONS_TABLE)
                table.add([record])
        except Exception as exc:
            print(f"⚠️  CORRECTIONS: Failed to commit correction to memory: {exc}")
            return False

        self._register_plugin()
        return True

    def get_corrections(self) -> List[CorrectionRecord]:
        """Retrieve all correction records from the corrections table."""
        try:
            if self.db is None:
                return []
            if self.CORRECTIONS_TABLE not in self.db.table_names():
                return []
            table = self.db.open_table(self.CORRECTIONS_TABLE)
            df = table.to_pandas()
            records: List[CorrectionRecord] = []
            for _, row in df.iterrows():
                records.append(
                    CorrectionRecord(
                        id=str(row["id"]),
                        german_source=str(row["german_source"]),
                        original_translation=str(row["original_translation"]),
                        corrected_translation=str(row["corrected_translation"]),
                        thematic_focus=str(row["thematic_focus"]),
                        timestamp=str(row["timestamp"]),
                        vector=row["vector"].tolist()
                        if hasattr(row["vector"], "tolist")
                        else list(row["vector"]),
                    )
                )
            return records
        except Exception as exc:
            print(f"⚠️  CORRECTIONS: Failed to retrieve corrections: {exc}")
            return []

    def delete_correction(self, record_id: str) -> bool:
        """Delete a correction record by ID."""
        try:
            if self.db is None:
                return False
            if self.CORRECTIONS_TABLE not in self.db.table_names():
                return False
            table = self.db.open_table(self.CORRECTIONS_TABLE)
            table.delete(f'id = "{record_id}"')
            return True
        except Exception as exc:
            print(f"⚠️  CORRECTIONS: Failed to delete correction {record_id}: {exc}")
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        """Create the corrections table if it doesn't exist.

        Note: LanceDB requires at least one record to infer schema, so actual
        table creation happens inside ``commit_correction`` on the first insert.
        This method is a pre-check that logs when the DB is unavailable.
        """
        if self.db is None:
            print("⚠️  CORRECTIONS: No vector database connection available")
            return
        # Table creation with data is handled in commit_correction.
        # This method exists for explicit pre-flight checks by callers.
        if self.CORRECTIONS_TABLE in self.db.table_names():
            return  # already exists

    def _register_plugin(self) -> None:
        """Register 'corrections' in TranslationBrain.active_plugins."""
        if self.CORRECTIONS_TABLE not in self.brain.active_plugins:
            self.brain.active_plugins.insert(0, self.CORRECTIONS_TABLE)
