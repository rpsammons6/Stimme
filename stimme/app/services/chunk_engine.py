"""Sliding-window chunker for splitting long chapters into overlapping chunks.

Splits text into word-count-based chunks with configurable overlap,
snapping boundaries to sentence endings for cleaner translation units.
"""

from __future__ import annotations

from typing import List

from app.constants import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from app.models.bulk_models import Chunk, TranslatedChunk


# Punctuation sequences that mark the end of a sentence.
_SENTENCE_ENDERS = frozenset({
    ".", "!", "?",
    '."', '!"', '?"',
    ".»", "!»", "?»",
    ".'", "!'", "?'",
    ".)", "!)", "?)",
})


def snap_to_sentence_boundary(
    words: List[str], target_idx: int, max_lookahead: int = 50
) -> int:
    """Return the first word index *after* a sentence-ending word.

    Starting from *target_idx*, scan forward up to *max_lookahead* words
    looking for a word that ends with sentence-ending punctuation.  If
    found, return the index immediately after that word (i.e. the start
    of the next sentence).  If no boundary is found within the lookahead
    window, return *target_idx* unchanged.

    Args:
        words: The full list of whitespace-split words.
        target_idx: Preferred split position (word index).
        max_lookahead: Maximum number of words to scan forward.

    Returns:
        A word index suitable for slicing ``words[:result]``.
    """
    upper = min(target_idx + max_lookahead, len(words))
    for i in range(target_idx, upper):
        if any(words[i].endswith(ender) for ender in _SENTENCE_ENDERS):
            return i + 1
    return target_idx


class ChunkEngine:
    """Splits long text into overlapping chunks and stitches them back.

    Each chunk (except the first) begins with *overlap* words carried
    over from the previous chunk so the translator has surrounding
    context.  Chunk boundaries are nudged forward to the nearest
    sentence ending when possible.

    Typical usage::

        engine = ChunkEngine()
        chunks = engine.chunk(chapter_text)
        # … translate each chunk …
        full = engine.stitch(translated_chunks)
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        if chunk_size <= overlap:
            raise ValueError(
                f"chunk_size ({chunk_size}) must be greater than overlap ({overlap})"
            )
        if overlap < 0:
            raise ValueError(f"overlap must be non-negative, got {overlap}")
        if chunk_size < 1:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")

        self.chunk_size = chunk_size
        self.overlap = overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(
        self,
        text: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> List[Chunk]:
        """Split *text* into overlapping :class:`Chunk` objects.

        Args:
            text: The source text to split.
            chunk_size: Target words per chunk (default from constructor).
            overlap: Overlap words between consecutive chunks (default
                from constructor).

        Returns:
            A list of :class:`Chunk` instances covering the full text.
            A short text (≤ *chunk_size* words) yields a single chunk.

        Raises:
            ValueError: If *text* is empty or parameters are invalid.
        """
        if not text or not text.strip():
            raise ValueError("text must be non-empty")

        cs = chunk_size if chunk_size is not None else self.chunk_size
        ov = overlap if overlap is not None else self.overlap

        if cs <= ov:
            raise ValueError(
                f"chunk_size ({cs}) must be greater than overlap ({ov})"
            )

        words = text.split()
        total = len(words)

        # Short text → single chunk, no splitting needed.
        if total <= cs:
            return [
                Chunk(
                    index=0,
                    text=text,
                    word_count=total,
                    overlap_prefix_words=0,
                    is_first=True,
                    is_last=True,
                )
            ]

        chunks: List[Chunk] = []
        pos = 0  # current word-index cursor (start of non-overlap content)
        idx = 0

        while pos < total:
            is_first = pos == 0

            if is_first:
                chunk_start = 0
                raw_end = min(cs, total)
                overlap_words = 0
            else:
                chunk_start = pos - ov
                raw_end = min(pos + cs - ov, total)
                overlap_words = ov

            # Try to snap the end to a sentence boundary.
            if raw_end < total:
                chunk_end = snap_to_sentence_boundary(words, raw_end)
                # Guard: if snapping jumped past the text, clamp.
                if chunk_end > total:
                    chunk_end = total
            else:
                chunk_end = total

            is_last = chunk_end >= total
            chunk_text = " ".join(words[chunk_start:chunk_end])

            chunks.append(
                Chunk(
                    index=idx,
                    text=chunk_text,
                    word_count=chunk_end - chunk_start,
                    overlap_prefix_words=overlap_words,
                    is_first=is_first,
                    is_last=is_last,
                )
            )

            # Advance past the content we just consumed (excluding overlap).
            pos = chunk_end
            idx += 1

            if is_last:
                break

        return chunks

    def stitch(self, translated_chunks: List[TranslatedChunk]) -> str:
        """Reassemble translated chunks into a single coherent string.

        For each chunk after the first, the overlap region is estimated
        proportionally in the translated text and removed, snapping to
        the nearest sentence boundary so the join reads naturally.

        Args:
            translated_chunks: Translated chunks ordered by
                ``chunk.index`` ascending.

        Returns:
            The stitched translation as a single string.

        Raises:
            ValueError: If *translated_chunks* is empty or contains
                chunks with empty translations.
        """
        if not translated_chunks:
            raise ValueError("translated_chunks must be non-empty")

        # Sort by chunk index to guarantee correct order.
        sorted_chunks = sorted(translated_chunks, key=lambda tc: tc.chunk.index)

        if len(sorted_chunks) == 1:
            return sorted_chunks[0].translation

        parts: List[str] = []

        for i, tc in enumerate(sorted_chunks):
            if not tc.translation or not tc.translation.strip():
                raise ValueError(
                    f"Chunk {tc.chunk.index} has an empty translation"
                )

            if i == 0:
                # First chunk: use the full translation.
                parts.append(tc.translation)
            else:
                # Estimate how much of the translated text corresponds
                # to the overlap prefix carried over from the previous
                # chunk.  The ratio of overlap words to total source
                # words gives a reasonable approximation for the
                # translated word count to skip.
                if tc.chunk.word_count > 0:
                    overlap_ratio = (
                        tc.chunk.overlap_prefix_words / tc.chunk.word_count
                    )
                else:
                    overlap_ratio = 0.0

                translated_words = tc.translation.split()
                skip_words = int(len(translated_words) * overlap_ratio)

                # Snap forward to a sentence boundary so we don't cut
                # mid-sentence in the translated text.
                skip_words = snap_to_sentence_boundary(
                    translated_words, skip_words
                )

                remaining = " ".join(translated_words[skip_words:])
                if remaining:
                    parts.append(remaining)

        return "\n\n".join(parts)
