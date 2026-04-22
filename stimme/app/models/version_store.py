"""Version store for managing translation versions per segment per tab."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.hitl_models import TranslationVersion
from app.services.segment_aligner import SegmentPair


class VersionStore:
    """Manages translation versions for segments within translation tabs."""

    MAX_VERSIONS_PER_SEGMENT: int = 10

    def __init__(self) -> None:
        # {tab_id: {segment_index: [TranslationVersion, ...]}}
        self._versions: Dict[int, Dict[int, List[TranslationVersion]]] = {}
        # {tab_id: {segment_index: active_version_index}}
        self._active: Dict[int, Dict[int, int]] = {}

    def add_version(
        self,
        tab_id: int,
        segment_index: int,
        text: str,
        instructions: str = "",
        is_manual: bool = False,
    ) -> Optional[TranslationVersion]:
        """Add a new version for a segment. Enforces MAX_VERSIONS_PER_SEGMENT.

        Returns the new TranslationVersion, or None if the text is identical
        to the current active version (no-op).
        """
        # Ensure nested dicts exist
        if tab_id not in self._versions:
            self._versions[tab_id] = {}
            self._active[tab_id] = {}
        if segment_index not in self._versions[tab_id]:
            self._versions[tab_id][segment_index] = []
            self._active[tab_id][segment_index] = -1

        versions = self._versions[tab_id][segment_index]

        # No-op if text is identical to the current active version
        active = self.get_active_version(tab_id, segment_index)
        if active is not None and active.text == text:
            return None

        # Determine next version number
        version_number = (versions[-1].version_number + 1) if versions else 1

        version = TranslationVersion(
            text=text,
            instructions=instructions,
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_manual=is_manual,
            version_number=version_number,
        )

        versions.append(version)

        # Enforce cap — drop oldest when exceeded
        if len(versions) > self.MAX_VERSIONS_PER_SEGMENT:
            versions.pop(0)

        # Newly added version becomes active
        self._active[tab_id][segment_index] = len(versions) - 1

        return version

    def get_versions(self, tab_id: int, segment_index: int) -> List[TranslationVersion]:
        """Return all versions for a segment, ordered oldest-first."""
        return self._versions.get(tab_id, {}).get(segment_index, [])

    def get_active_version(self, tab_id: int, segment_index: int) -> Optional[TranslationVersion]:
        """Return the currently active version for a segment."""
        versions = self.get_versions(tab_id, segment_index)
        if not versions:
            return None
        idx = self._active.get(tab_id, {}).get(segment_index, -1)
        if 0 <= idx < len(versions):
            return versions[idx]
        return None

    def set_active_version(self, tab_id: int, segment_index: int, version_index: int) -> None:
        """Set which version is the active/accepted one.

        Raises IndexError if version_index is out of bounds.
        """
        versions = self.get_versions(tab_id, segment_index)
        if not versions or version_index < 0 or version_index >= len(versions):
            raise IndexError(
                f"version_index {version_index} out of range for "
                f"tab {tab_id}, segment {segment_index} "
                f"(has {len(versions)} versions)"
            )
        self._active[tab_id][segment_index] = version_index

    def get_version_count(self, tab_id: int, segment_index: int) -> int:
        """Return the number of versions stored for a segment."""
        return len(self.get_versions(tab_id, segment_index))

    def get_iteration_count(self, tab_id: int) -> int:
        """Return total versions across all segments for a tab."""
        segments = self._versions.get(tab_id, {})
        return sum(len(v) for v in segments.values())

    def initialize_from_segments(self, tab_id: int, segments: List[SegmentPair]) -> None:
        """Seed version 1 for each segment from the initial translation."""
        for seg in segments:
            self.add_version(
                tab_id=tab_id,
                segment_index=seg.index,
                text=seg.translation_text,
            )
