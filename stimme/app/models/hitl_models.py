"""Data models for the Human-in-the-Loop (HITL) workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class TranslationVersion:
    """A single version of a translated segment."""

    text: str
    instructions: str  # Thematic focus / instructions used
    timestamp: str  # ISO format
    is_manual: bool = False  # True if user-edited (not AI-generated)
    version_number: int = 1  # Sequential within segment


@dataclass
class CorrectionRecord:
    """A user correction stored in LanceDB for RAG retrieval."""

    id: str  # UUID
    german_source: str  # Original German text
    original_translation: str  # AI's original translation
    corrected_translation: str  # User's corrected version
    thematic_focus: str  # Active thematic focus at time of correction
    timestamp: str  # ISO format
    vector: List[float] = field(
        default_factory=list
    )  # Embedding of german_source (384-dim for multilingual-e5-small)


@dataclass
class DiffOp:
    """A single diff operation between two texts."""

    tag: str  # 'equal', 'insert', 'delete', 'replace'
    old_words: List[str] = field(
        default_factory=list
    )  # Words from version A (empty for 'insert')
    new_words: List[str] = field(
        default_factory=list
    )  # Words from version B (empty for 'delete')
