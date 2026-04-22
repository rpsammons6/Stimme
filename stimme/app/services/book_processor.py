"""BookProcessor — top-level orchestrator for bulk (book-level) translation.

Coordinates the full pipeline: detect → scout → chunk → translate → stitch →
assemble, with cancellation support and per-chapter error handling.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.constants import BOOK_THRESHOLD, MODEL_PRICING
from app.contexts.settings import SettingsManager
from app.event_bus import EventBus
from app.models.bulk_models import (
    BookTranslation,
    Chapter,
    ChapterStatus,
    CostEstimate,
    TranslatedChunk,
)
from app.services.chunk_engine import ChunkEngine
from app.services.markdown_formatter import MarkdownFormatter
from app.services.scout_service import ScoutService
from app.services.translation_service import TranslationService

logger = logging.getLogger(__name__)


class BookProcessor:
    """Orchestrates bulk translation of book-length documents.

    Responsibilities:
    - Detect whether input qualifies as a "book" (> BOOK_THRESHOLD words)
    - Coordinate Scout → Chunk → Translate → Stitch → Assemble pipeline
    - Emit progress events via EventBus
    - Support cancellation at chunk boundaries
    - Provide cost estimates before translation begins
    """

    def __init__(
        self,
        settings: SettingsManager,
        translation_service: TranslationService,
        bus: EventBus,
    ) -> None:
        self.settings = settings
        self.translation_service = translation_service
        self.bus = bus
        self.scout = ScoutService(settings)
        self.chunker = ChunkEngine()
        self.formatter = MarkdownFormatter()
        self._cancel_requested: bool = False

    # ------------------------------------------------------------------
    # Book detection  (Task 5.2)
    # ------------------------------------------------------------------

    def detect_book(self, text: str) -> bool:
        """Return True if *text* has more than BOOK_THRESHOLD words."""
        if not text:
            return False
        return len(text.split()) > BOOK_THRESHOLD

    # ------------------------------------------------------------------
    # Structural scanning  (Task 5.3)
    # ------------------------------------------------------------------

    def scan_structure(
        self,
        text: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        pdf_path: Optional[str] = None,
    ) -> List[Chapter]:
        """Extract a Table of Contents from *text* via the Scout service."""
        return self.scout.extract_toc(text, progress_callback, pdf_path=pdf_path)

    # ------------------------------------------------------------------
    # Chapter translation  (Task 5.4 + 5.6 + 5.7)
    # ------------------------------------------------------------------

    def translate_chapters(
        self,
        chapters: List[Chapter],
        selected_indices: List[int],
        progress_callback: Optional[Callable[[str, float], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
        glossary_block: str = "",
    ) -> BookTranslation:
        """Translate selected chapters through the chunk pipeline.

        For each selected chapter:
        1. Chunk the chapter text
        2. Translate each chunk via TranslationService.translate_sync()
        3. Emit "chunk_translated" after each chunk
        4. Stitch translated chunks
        5. Emit "chapter_translated"
        6. Check cancellation at each chunk boundary

        On error: mark chapter as ERROR, continue with next chapter.
        On cancel: return partial results (completed chapters only).
        """
        # Reset cancellation flag at the start of each run
        self._cancel_requested = False

        total_metrics: Dict[str, Any] = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "model": self.settings.get_model(),
            "chapters_translated": 0,
            "chapters_errored": 0,
        }

        # Pre-compute total chunks for progress reporting
        total_chunks = 0
        for idx in selected_indices:
            ch = chapters[idx]
            chunk_count = max(1, math.ceil(ch.word_count / self.chunker.chunk_size))
            total_chunks += chunk_count
        completed_chunks = 0

        translated_chapters: List[Chapter] = []

        for chapter_idx in selected_indices:
            # --- Cancellation check (Task 5.6) ---
            if self._cancel_requested:
                logger.info("Cancellation requested, stopping before chapter %d", chapter_idx)
                break

            chapter = chapters[chapter_idx]
            chapter.status = ChapterStatus.TRANSLATING

            try:
                # Step 1: Chunk
                chunks = self.chunker.chunk(chapter.text)
                chapter.chunks = chunks
                chapter.status = ChapterStatus.CHUNKED

                translated_chunks: List[TranslatedChunk] = []
                chapter_errored = False

                for chunk in chunks:
                    # --- Cancellation check at chunk boundary (Task 5.6) ---
                    if self._cancel_requested:
                        logger.info(
                            "Cancellation requested at chunk %d of chapter %d",
                            chunk.index, chapter_idx,
                        )
                        break

                    try:
                        # Step 2: Translate
                        success, translation_text, commentary, metrics = (
                            self.translation_service.translate_sync(
                                chunk.text, cache_control=True, glossary_block=glossary_block
                            )
                        )

                        if not success:
                            raise RuntimeError(translation_text)

                        tc = TranslatedChunk(
                            chunk=chunk,
                            translation=translation_text,
                            metrics=metrics or {},
                        )
                        translated_chunks.append(tc)

                        # Aggregate metrics
                        if metrics:
                            total_metrics["total_input_tokens"] += metrics.get("input_tokens", 0)
                            total_metrics["total_output_tokens"] += metrics.get("output_tokens", 0)
                            total_metrics["total_cost_usd"] += metrics.get("cost_usd", 0.0)

                        completed_chunks += 1

                        # Step 3: Emit chunk progress
                        progress = completed_chunks / total_chunks if total_chunks > 0 else 1.0
                        self.bus.emit(
                            "chunk_translated",
                            chapter_idx=chapter_idx,
                            chunk_idx=chunk.index,
                            total_chunks=len(chunks),
                            progress=progress,
                        )

                        if progress_callback:
                            progress_callback(
                                f"Chapter {chapter_idx + 1}, chunk {chunk.index + 1}/{len(chunks)}",
                                progress * 100,
                            )

                    except Exception as chunk_err:
                        # --- Error handling (Task 5.7): failed chunk → ERROR chapter ---
                        logger.error(
                            "Chunk %d of chapter '%s' failed: %s",
                            chunk.index, chapter.title, chunk_err,
                        )
                        chapter.status = ChapterStatus.ERROR
                        total_metrics["chapters_errored"] += 1
                        chapter_errored = True
                        break  # Stop processing this chapter's remaining chunks

                if chapter_errored:
                    # Preserve partial chapter info but move on
                    continue

                # If cancelled mid-chapter (not all chunks translated),
                # don't stitch partial chunks — just stop.
                if self._cancel_requested and len(translated_chunks) < len(chunks):
                    break

                # Step 4: Stitch translated chunks
                if translated_chunks:
                    stitched = self.chunker.stitch(translated_chunks)
                    chapter.translation = stitched
                    chapter.status = ChapterStatus.TRANSLATED
                    total_metrics["chapters_translated"] += 1
                    translated_chapters.append(chapter)

                    # Step 5: Emit chapter completion
                    self.bus.emit("chapter_translated", chapter_idx=chapter_idx)

            except Exception as chapter_err:
                # Catch-all for unexpected errors (e.g. chunking failure)
                logger.error(
                    "Chapter '%s' failed: %s", chapter.title, chapter_err,
                )
                chapter.status = ChapterStatus.ERROR
                total_metrics["chapters_errored"] += 1
                continue

        # Assemble full translation from completed chapters
        full_parts: List[str] = []
        for ch in translated_chapters:
            if ch.translation:
                full_parts.append(f"# {ch.title}\n\n{ch.translation}")

        full_translation = "\n\n---\n\n".join(full_parts)

        # Emit completion event with metrics so the handler can show the right banner
        self.bus.emit(
            "book_translation_complete",
            chapters_translated=total_metrics["chapters_translated"],
            chapters_errored=total_metrics["chapters_errored"],
        )

        return BookTranslation(
            chapters=chapters,
            full_translation=full_translation,
            total_metrics=total_metrics,
            timestamp=datetime.now(),
        )

    # ------------------------------------------------------------------
    # Cancellation  (Task 5.6)
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """Request cancellation of the current translation run.

        Takes effect at the next chunk boundary — the current chunk
        completes before processing stops.
        """
        self._cancel_requested = True
        logger.info("BookProcessor: cancellation requested")

    # ------------------------------------------------------------------
    # Cost estimation  (Task 5.5)
    # ------------------------------------------------------------------

    def estimate_cost(
        self,
        chapters: List[Chapter],
        selected_indices: List[int],
    ) -> CostEstimate:
        """Estimate translation cost for the selected chapters.

        Uses model-specific pricing from MODEL_PRICING, with token
        estimates of ~1.3 tokens/word (German input) and ~1.1 tokens/word
        (English output), plus 500 tokens per chunk for system prompt overhead.
        """
        model_id = self.settings.get_model()
        selected = [chapters[i] for i in selected_indices]
        total_words = sum(ch.word_count for ch in selected)

        # Estimate chunk count
        chunk_count = sum(
            max(1, math.ceil(ch.word_count / self.chunker.chunk_size))
            for ch in selected
        )

        # Token estimation
        est_input_tokens = int(total_words * 1.3) + (chunk_count * 500)
        est_output_tokens = int(total_words * 1.1)

        # Pricing lookup (default to Sonnet pricing if model unknown)
        input_price, output_price = MODEL_PRICING.get(model_id, (3.0, 15.0))
        cost = (
            (est_input_tokens * input_price / 1_000_000)
            + (est_output_tokens * output_price / 1_000_000)
        )

        return CostEstimate(
            total_words=total_words,
            estimated_input_tokens=est_input_tokens,
            estimated_output_tokens=est_output_tokens,
            estimated_cost_usd=round(cost, 4),
            model_id=model_id,
            chapter_count=len(selected),
            chunk_count=chunk_count,
        )
