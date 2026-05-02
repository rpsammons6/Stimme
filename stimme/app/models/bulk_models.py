"""Data models for Bulk Mode (book-level translation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ChapterStatus(Enum):
    """Status of a chapter in the bulk translation pipeline."""

    PENDING = "pending"
    SCANNING = "scanning"
    CHUNKED = "chunked"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    ERROR = "error"


@dataclass
class Chunk:
    """A segment of chapter text produced by the sliding-window chunker."""

    index: int  # position within chapter
    text: str  # chunk text (with overlap prefix)
    word_count: int
    overlap_prefix_words: int  # words carried over from previous chunk
    is_first: bool
    is_last: bool


@dataclass
class TranslatedChunk:
    """A chunk paired with its translation and API metrics."""

    chunk: Chunk
    translation: str
    metrics: Dict[str, Any] = field(default_factory=dict)  # tokens, cost, model


@dataclass
class Chapter:
    """A structural chapter detected by the Scout service."""

    title: str  # e.g. "Kapitel 1: Die Anfänge"
    start_index: int  # character offset in full text
    end_index: int  # character offset end
    text: str  # full chapter text
    word_count: int  # pre-computed word count
    status: ChapterStatus = ChapterStatus.PENDING
    translation: Optional[str] = None
    chunks: Optional[List[Chunk]] = None


@dataclass
class BookTranslation:
    """Assembled result of a full book translation."""

    chapters: List[Chapter]
    full_translation: str  # assembled markdown
    total_metrics: Dict[str, Any] = field(default_factory=dict)  # aggregated tokens, cost
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CostEstimate:
    """Pre-translation cost estimate for selected chapters."""

    total_words: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    model_id: str
    chapter_count: int
    chunk_count: int
