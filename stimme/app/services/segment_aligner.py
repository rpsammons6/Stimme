import re
from dataclasses import dataclass
from typing import List


@dataclass
class SegmentPair:
    index: int
    source_text: str
    translation_text: str


class SegmentAligner:
    """Aligns source and translation texts into paired segments.

    Strategy:
    1. Split both texts into paragraphs (double newline).
    2. If paragraph counts match, align 1:1.
    3. If not, split all paragraphs into sentences and align sentences.
    4. If sentence counts still differ, use proportional mapping.
    """

    def align(self, source: str, translation: str) -> List[SegmentPair]:
        """Split source and translation into aligned segment pairs."""
        if not source and not translation:
            return []

        # If only one side has text, return a single pair
        if not source or not translation:
            return [SegmentPair(index=0, source_text=source.strip(), translation_text=translation.strip())]

        src_paras = self._split_paragraphs(source)
        tgt_paras = self._split_paragraphs(translation)

        # Paragraph counts match — align 1:1
        if len(src_paras) == len(tgt_paras):
            return [
                SegmentPair(index=i, source_text=s, translation_text=t)
                for i, (s, t) in enumerate(zip(src_paras, tgt_paras))
            ]

        # Paragraph counts differ — fall back to sentence-level alignment
        src_sents = self._split_sentences(source)
        tgt_sents = self._split_sentences(translation)

        if len(src_sents) == len(tgt_sents):
            return [
                SegmentPair(index=i, source_text=s, translation_text=t)
                for i, (s, t) in enumerate(zip(src_sents, tgt_sents))
            ]

        # Sentence counts differ — proportional mapping
        return self._proportional_map(src_sents, tgt_sents)

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text on double newlines, stripping whitespace and dropping empties."""
        parts = re.split(r"\n\s*\n", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_sentences(self, text: str) -> List[str]:
        """Split text on sentence-ending punctuation followed by whitespace.

        Handles German quotation marks (» « „ ") and avoids splitting on
        common abbreviations (z.B., d.h., u.a., etc.).
        """
        # Collapse newlines into spaces for sentence splitting
        normalized = re.sub(r"\n+", " ", text).strip()
        if not normalized:
            return []

        # Split on sentence-ending punctuation (.!?) that is optionally followed
        # by a closing quote and then whitespace + an uppercase letter or quote.
        # Negative lookbehind avoids splitting on common German abbreviations.
        pattern = r'(?<!\b[zZdDuUeEiIoO]\.[A-Za-z])([.!?][»""\'\)]?)\s+(?=[A-ZÄÖÜ»„\"])'
        parts = re.split(pattern, normalized)

        # re.split with a capturing group interleaves text and delimiters.
        # Rejoin each text chunk with its trailing punctuation.
        sentences: List[str] = []
        i = 0
        while i < len(parts):
            chunk = parts[i]
            # If the next part is a captured delimiter, append it to this chunk
            if i + 1 < len(parts) and re.fullmatch(r'[.!?][»""\'\)]*', parts[i + 1]):
                chunk += parts[i + 1]
                i += 2
            else:
                i += 1
            stripped = chunk.strip()
            if stripped:
                sentences.append(stripped)

        return sentences

    def _proportional_map(
        self, src_segments: List[str], tgt_segments: List[str]
    ) -> List[SegmentPair]:
        """Map segments proportionally when counts don't match.

        The shorter list drives the pair count. Extra segments from the longer
        list are distributed evenly across pairs (joined with spaces).
        """
        if not src_segments and not tgt_segments:
            return []

        # Determine which side is shorter
        if len(src_segments) <= len(tgt_segments):
            short, long = src_segments, tgt_segments
            src_is_short = True
        else:
            short, long = tgt_segments, src_segments
            src_is_short = False

        n = len(short) if short else 1
        pairs: List[SegmentPair] = []

        for i in range(n):
            # Calculate the slice of the longer list that maps to this index
            start = (i * len(long)) // n
            end = ((i + 1) * len(long)) // n
            merged = " ".join(long[start:end])

            if src_is_short:
                pairs.append(SegmentPair(index=i, source_text=short[i], translation_text=merged))
            else:
                pairs.append(SegmentPair(index=i, source_text=merged, translation_text=short[i]))

        return pairs
