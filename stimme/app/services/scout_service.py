"""ScoutService — extracts structural TOC from documents.

Primary strategy: read PDF bookmarks / detect headings via font-size analysis
using pdfplumber.  Fallback: send page samples to Claude Haiku and ask it to
identify chapter headings.  Last resort: single chapter covering entire text.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from typing import Callable, List, Optional

import anthropic

from app.constants import SCOUT_MODEL
from app.contexts.settings import SettingsManager
from app.models.bulk_models import Chapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAGE_SIZE = 3000          # chars per virtual page
_SAMPLE_CHARS = 500        # chars taken from start/end of each page


class ScoutService:
    """Extracts a Table of Contents from raw text using Claude Haiku."""

    SCOUT_MODEL = SCOUT_MODEL

    def __init__(self, settings: SettingsManager):
        self.settings = settings
        self.client: Optional[anthropic.Anthropic] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_toc(
        self,
        text: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        pdf_path: Optional[str] = None,
    ) -> List[Chapter]:
        """Return an ordered list of Chapter objects covering *text*.

        Strategy order:
        1. If *pdf_path* is provided, try extracting structure from the PDF
           (bookmarks first, then font-size heading detection).
        2. Fall back to Haiku-based page-sample analysis.
        3. Last resort: single Chapter containing entire text.

        Postconditions
        --------------
        - len(result) >= 1
        - result[0].start_index == 0
        - result[-1].end_index == len(text)
        - Adjacent chapters: result[i].end_index == result[i+1].start_index
        - On any failure → single Chapter containing entire text
        """
        if not text or not text.strip():
            return [self._fallback_chapter(text or "")]

        # --- Strategy 1: PDF structural extraction ---
        if pdf_path:
            try:
                if progress_callback:
                    progress_callback("Reading PDF structure…", 10)
                chapters = _extract_toc_from_pdf(pdf_path, text)
                if chapters and len(chapters) > 1:
                    if progress_callback:
                        progress_callback("PDF structure extracted.", 100)
                    logger.info("TOC extracted from PDF structure: %d chapters", len(chapters))
                    return chapters
                logger.info("PDF structure yielded ≤1 chapter, falling back to Haiku")
            except Exception as exc:
                logger.warning("PDF structure extraction failed: %s", exc)

        # --- Strategy 2: Haiku-based extraction ---
        try:
            if progress_callback:
                progress_callback("Building page samples…", 10)

            sample = self._build_scout_prompt(text)

            if progress_callback:
                progress_callback("Sending to Scout model…", 30)

            raw_json = self._call_haiku(sample)

            if progress_callback:
                progress_callback("Parsing TOC response…", 70)

            chapters = self._parse_toc_response(raw_json, text)

            if progress_callback:
                progress_callback("TOC extraction complete.", 100)

            return chapters

        except Exception as exc:
            logger.warning("Scout extraction failed, using fallback: %s", exc)
            return [self._fallback_chapter(text)]

    # ------------------------------------------------------------------
    # Prompt construction  (Task 3.2)
    # ------------------------------------------------------------------

    def _build_scout_prompt(self, text: str) -> str:
        """Build the page-sampling prompt sent to Haiku.

        Splits *text* into virtual pages of ~3000 chars, takes the first
        and last 500 chars of each page, and joins them with page-break
        markers.
        """
        pages = _split_into_pages(text, page_size=_PAGE_SIZE)
        samples: list[str] = []
        for i, page in enumerate(pages, 1):
            first = page[:_SAMPLE_CHARS]
            last = page[-_SAMPLE_CHARS:] if len(page) > _SAMPLE_CHARS else ""
            if last and last != first:
                samples.append(f"[Page {i}]\n{first}\n...\n{last}")
            else:
                samples.append(f"[Page {i}]\n{first}")

        return "\n---PAGE BREAK---\n".join(samples)

    # ------------------------------------------------------------------
    # Response parsing  (Task 3.3)
    # ------------------------------------------------------------------

    def _parse_toc_response(
        self, raw_json: str, full_text: str
    ) -> List[Chapter]:
        """Parse Haiku's JSON into Chapter objects with position mapping.

        Applies JSON repair (strip markdown fences, fix trailing commas)
        and fuzzy text-position matching when exact ``find()`` fails.
        """
        cleaned = _repair_json(raw_json)

        try:
            entries = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("JSON decode failed after repair, using fallback")
            return [self._fallback_chapter(full_text)]

        if not isinstance(entries, list) or len(entries) == 0:
            return [self._fallback_chapter(full_text)]

        chapters: list[Chapter] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", f"Chapter {i + 1}"))
            start_hint = str(entry.get("start", ""))

            # --- position mapping ---
            start_pos = _find_position(full_text, start_hint)
            if start_pos == -1:
                # If we can't locate this chapter, skip it
                continue

            chapters.append(
                _ChapterStub(title=title, start_index=start_pos)
            )

        if not chapters:
            return [self._fallback_chapter(full_text)]

        # Sort by start_index
        chapters.sort(key=lambda c: c.start_index)

        # Ensure first chapter starts at 0
        if chapters[0].start_index != 0:
            chapters.insert(
                0, _ChapterStub(title="Preamble", start_index=0)
            )

        # Build final Chapter objects with contiguous boundaries
        result: list[Chapter] = []
        for i, stub in enumerate(chapters):
            start = stub.start_index
            end = chapters[i + 1].start_index if i + 1 < len(chapters) else len(full_text)
            chapter_text = full_text[start:end]
            result.append(
                Chapter(
                    title=stub.title,
                    start_index=start,
                    end_index=end,
                    text=chapter_text,
                    word_count=len(chapter_text.split()),
                )
            )

        return result

    # ------------------------------------------------------------------
    # Haiku API call
    # ------------------------------------------------------------------

    def _call_haiku(self, text_sample: str) -> str:
        """Send the page-sample prompt to Haiku and return the raw response."""
        # Always get a fresh API key — the user may have entered/changed it
        # in the sidebar since the last call.
        api_key = self.settings.get_api_key()
        if not api_key:
            raise RuntimeError("No API key configured")

        # Recreate client if key changed or not yet initialized
        if self.client is None or getattr(self, '_last_api_key', None) != api_key:
            self.client = anthropic.Anthropic(api_key=api_key)
            self._last_api_key = api_key

        system_prompt = (
            "You are a document structure analyst. Given page samples from a "
            "book or long document, identify the chapter or section headings "
            "and the first few words of each chapter/section.\n\n"
            "Return ONLY a JSON array. Each element must have:\n"
            '  - "title": the chapter/section heading\n'
            '  - "start": the first 5-10 words of that chapter/section '
            "(copied verbatim from the text)\n\n"
            "Example:\n"
            '[{"title": "Chapter 1: The Beginning", '
            '"start": "It was a dark and stormy night"}]\n\n'
            "If you cannot identify chapters, return a single entry covering "
            "the whole document."
        )

        response = self.client.messages.create(
            model=self.SCOUT_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": text_sample}],
        )

        return response.content[0].text

    # ------------------------------------------------------------------
    # Fallback  (Task 3.4)
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_chapter(text: str) -> Chapter:
        """Return a single Chapter spanning the entire text."""
        return Chapter(
            title="Full Document",
            start_index=0,
            end_index=len(text),
            text=text,
            word_count=len(text.split()),
        )


# ======================================================================
# PDF structural extraction
# ======================================================================

def _extract_toc_from_pdf(pdf_path: str, full_text: str) -> List[Chapter]:
    """Try to extract chapter structure directly from the PDF.

    Strategy:
    1. Read PDF bookmarks/outlines (most reliable — the PDF's own TOC).
    2. If no bookmarks, detect headings by font-size analysis with pdfplumber.
    3. Map detected headings back to positions in *full_text*.

    Returns a list of Chapter objects, or an empty list if nothing useful
    was found.
    """
    import pdfplumber

    chapters: list[Chapter] = []

    with pdfplumber.open(pdf_path) as pdf:
        # --- Attempt 1: PDF bookmarks / outlines ---
        outlines = _get_pdf_outlines(pdf)
        if outlines:
            logger.info("Found %d PDF bookmarks", len(outlines))
            chapters = _outlines_to_chapters(outlines, full_text)
            if chapters and len(chapters) > 1:
                return chapters

        # --- Attempt 2: Font-size heading detection ---
        logger.info("No usable bookmarks, trying font-size heading detection")
        headings = _detect_headings_by_font_size(pdf)
        if headings:
            logger.info("Detected %d headings by font size", len(headings))
            chapters = _headings_to_chapters(headings, full_text)
            if chapters and len(chapters) > 1:
                return chapters

    return chapters


def _get_pdf_outlines(pdf) -> List[dict]:
    """Extract bookmark/outline entries from a pdfplumber PDF object.

    Returns a list of dicts with 'title' and 'page_num' keys.
    """
    outlines: list[dict] = []
    try:
        # pdfplumber doesn't expose outlines directly, but the underlying
        # pdfminer resolver does.  We access it via the PDF's catalog.
        from pdfminer.pdftypes import resolve1
        from pdfminer.pdfparser import PDFParser
        from pdfminer.pdfdocument import PDFDocument

        catalog = pdf.pdf.catalog
        if "Outlines" not in catalog:
            return []

        outlines_ref = resolve1(catalog["Outlines"])
        if not outlines_ref or "First" not in outlines_ref:
            return []

        # Walk the outline tree (first/next linked list)
        node = resolve1(outlines_ref["First"])
        while node:
            title = node.get("Title", b"")
            if isinstance(title, bytes):
                title = title.decode("utf-8", errors="replace")
            title = str(title).strip()

            # Resolve the destination page number
            page_num = _resolve_outline_page(node, pdf)

            if title and page_num is not None:
                outlines.append({"title": title, "page_num": page_num})

            # Move to next sibling
            if "Next" in node:
                node = resolve1(node["Next"])
            else:
                break

    except Exception as exc:
        logger.debug("Could not read PDF outlines: %s", exc)

    return outlines


def _resolve_outline_page(node: dict, pdf) -> Optional[int]:
    """Resolve a bookmark node to a 0-based page number."""
    try:
        from pdfminer.pdftypes import resolve1

        dest = node.get("Dest") or node.get("A", {}).get("D")
        if dest is None:
            return None

        dest = resolve1(dest)
        if isinstance(dest, list) and len(dest) > 0:
            page_ref = dest[0]
            page_ref = resolve1(page_ref)
            # Match against pdfplumber's page list
            for i, page in enumerate(pdf.pages):
                if page.page_obj.pageid == page_ref.objid:
                    return i
    except Exception:
        pass
    return None


def _outlines_to_chapters(
    outlines: List[dict], full_text: str
) -> List[Chapter]:
    """Convert PDF bookmark entries into Chapter objects.

    Each bookmark has a title and page number.  We find the title text
    in *full_text* to get character offsets.
    """
    stubs: list[_ChapterStub] = []

    for outline in outlines:
        title = outline["title"]
        pos = _find_position(full_text, title)
        if pos >= 0:
            stubs.append(_ChapterStub(title=title, start_index=pos))

    if not stubs:
        return []

    stubs.sort(key=lambda s: s.start_index)

    # Ensure first chapter starts at 0
    if stubs[0].start_index > 0:
        stubs.insert(0, _ChapterStub(title="Preamble", start_index=0))

    # Build contiguous chapters
    result: list[Chapter] = []
    for i, stub in enumerate(stubs):
        start = stub.start_index
        end = stubs[i + 1].start_index if i + 1 < len(stubs) else len(full_text)
        chapter_text = full_text[start:end]
        result.append(
            Chapter(
                title=stub.title,
                start_index=start,
                end_index=end,
                text=chapter_text,
                word_count=len(chapter_text.split()),
            )
        )

    return result


def _detect_headings_by_font_size(pdf) -> List[dict]:
    """Detect headings using multi-tier font-size clustering.

    Strategy:
    1. Collect font sizes from all pages *except* the first (title pages
       are outliers with oversized fonts that skew detection).
    2. Identify the dominant body size (most common).
    3. Find distinct size tiers above the body size — these are heading
       levels (chapter titles, section headings, etc.).
    4. Use the *lowest* tier above body as the chapter heading size.
       This catches "Kapitel I" even when the title page had a 36pt font
       and chapter headings are 16pt on a 12pt body.
    5. Short text runs at that tier = chapter headings.

    Returns a list of dicts with 'title' and 'page_num'.
    """
    from collections import Counter

    # --- Pass 1: collect font sizes, skipping page 1 (title page) ---
    body_sizes: list[float] = []       # pages 2+ (for body size calc)
    all_page_sizes: list[float] = []   # all pages (for reference)

    for page_idx, page in enumerate(pdf.pages):
        try:
            chars = page.chars or []
            for ch in chars:
                size = ch.get("size", 0)
                if size > 0:
                    rounded = round(size, 1)
                    all_page_sizes.append(rounded)
                    if page_idx > 0:  # skip first page
                        body_sizes.append(rounded)
        except Exception:
            continue

    # If the PDF is only 1 page, use all sizes
    if not body_sizes:
        body_sizes = all_page_sizes
    if not body_sizes:
        return []

    # --- Pass 2: find dominant body size and heading tiers ---
    size_counts = Counter(body_sizes)
    dominant_size = size_counts.most_common(1)[0][0]

    # Collect distinct sizes that are meaningfully larger than body text.
    # "Meaningfully" = at least 1.15× body size (catches 14pt on 12pt body).
    min_heading_size = dominant_size * 1.15
    heading_sizes = sorted(set(
        s for s in size_counts if s >= min_heading_size
    ))

    if not heading_sizes:
        # No sizes above body — try a looser threshold with all pages
        all_counts = Counter(all_page_sizes)
        dominant_all = all_counts.most_common(1)[0][0]
        min_heading_all = dominant_all * 1.15
        heading_sizes = sorted(set(
            s for s in all_counts if s >= min_heading_all
        ))
        if not heading_sizes:
            return []
        dominant_size = dominant_all

    # The chapter heading tier is the *smallest* size above body.
    # Larger sizes are likely title-page or part-level headings.
    chapter_heading_size = heading_sizes[0]

    # Allow a tolerance band: anything within ±0.5pt of the chapter tier
    # counts as a chapter heading.
    size_lo = chapter_heading_size - 0.5
    size_hi = chapter_heading_size + 0.5

    # --- Pass 3: extract text runs at the chapter heading size ---
    headings: list[dict] = []
    for page_idx, page in enumerate(pdf.pages):
        try:
            chars = page.chars or []
            if not chars:
                continue

            current_run: list[str] = []
            current_size = 0.0

            for ch in chars:
                size = round(ch.get("size", 0), 1)
                char_text = ch.get("text", "")

                if size_lo <= size <= size_hi and char_text.strip():
                    if not current_run or abs(size - current_size) < 1.0:
                        current_run.append(char_text)
                        current_size = size
                    else:
                        _flush_heading_run(current_run, page_idx, headings)
                        current_run = [char_text]
                        current_size = size
                else:
                    if current_run:
                        _flush_heading_run(current_run, page_idx, headings)
                        current_run = []
                        current_size = 0.0

            if current_run:
                _flush_heading_run(current_run, page_idx, headings)

        except Exception:
            continue

    # --- Pass 4: if we only found 1 heading (likely the title), try the
    # next tier up or include page-1 headings at a secondary size ---
    if len(headings) <= 1 and len(heading_sizes) > 1:
        # Try the next size tier
        next_tier = heading_sizes[1]
        tier_lo = next_tier - 0.5
        tier_hi = next_tier + 0.5
        alt_headings: list[dict] = []
        for page_idx, page in enumerate(pdf.pages):
            try:
                chars = page.chars or []
                if not chars:
                    continue
                current_run = []
                current_size = 0.0
                for ch in chars:
                    size = round(ch.get("size", 0), 1)
                    char_text = ch.get("text", "")
                    if tier_lo <= size <= tier_hi and char_text.strip():
                        if not current_run or abs(size - current_size) < 1.0:
                            current_run.append(char_text)
                            current_size = size
                        else:
                            _flush_heading_run(current_run, page_idx, alt_headings)
                            current_run = [char_text]
                            current_size = size
                    else:
                        if current_run:
                            _flush_heading_run(current_run, page_idx, alt_headings)
                            current_run = []
                            current_size = 0.0
                if current_run:
                    _flush_heading_run(current_run, page_idx, alt_headings)
            except Exception:
                continue
        if len(alt_headings) > 1:
            headings = alt_headings

    return headings


def _flush_heading_run(
    chars: list[str],
    page_idx: int,
    headings: list[dict],
) -> None:
    """Flush a character run into headings if it looks like a heading."""
    text = "".join(chars).strip()
    # Headings: non-empty, short-ish, not just page numbers
    if 2 < len(text) < 150 and not text.isdigit():
        headings.append({"title": text, "page_num": page_idx})


def _headings_to_chapters(
    headings: List[dict], full_text: str
) -> List[Chapter]:
    """Convert font-size-detected headings into Chapter objects."""
    stubs: list[_ChapterStub] = []

    for heading in headings:
        title = heading["title"]
        pos = _find_position(full_text, title)
        if pos >= 0:
            # Avoid duplicate positions (same heading found twice)
            if not stubs or abs(stubs[-1].start_index - pos) > 50:
                stubs.append(_ChapterStub(title=title, start_index=pos))

    if not stubs:
        return []

    stubs.sort(key=lambda s: s.start_index)

    # Ensure first chapter starts at 0
    if stubs[0].start_index > 0:
        stubs.insert(0, _ChapterStub(title="Preamble", start_index=0))

    # Build contiguous chapters
    result: list[Chapter] = []
    for i, stub in enumerate(stubs):
        start = stub.start_index
        end = stubs[i + 1].start_index if i + 1 < len(stubs) else len(full_text)
        chapter_text = full_text[start:end]
        result.append(
            Chapter(
                title=stub.title,
                start_index=start,
                end_index=end,
                text=chapter_text,
                word_count=len(chapter_text.split()),
            )
        )

    return result


# ======================================================================
# Module-level helpers
# ======================================================================

class _ChapterStub:
    """Lightweight intermediate used during TOC parsing."""

    __slots__ = ("title", "start_index")

    def __init__(self, title: str, start_index: int):
        self.title = title
        self.start_index = start_index


def _split_into_pages(text: str, page_size: int = _PAGE_SIZE) -> List[str]:
    """Split *text* into pages of approximately *page_size* characters."""
    if not text:
        return []
    pages: list[str] = []
    for i in range(0, len(text), page_size):
        pages.append(text[i : i + page_size])
    return pages


def _repair_json(raw: str) -> str:
    """Best-effort JSON repair.

    - Strip markdown fences (```json ... ```)
    - Remove trailing commas before ] or }
    - Strip leading/trailing whitespace
    """
    text = raw.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)

    # Remove trailing commas  (e.g.  {"a":1,} or [1,2,])
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text.strip()


def _find_position(text: str, hint: str) -> int:
    """Locate *hint* in *text*.  Tries exact match first, then fuzzy."""
    if not hint or not hint.strip():
        return -1

    hint_clean = hint.strip()

    # 1. Exact match
    pos = text.find(hint_clean)
    if pos != -1:
        return pos

    # 2. Try first 40 chars of hint (in case Haiku added extra words)
    short_hint = hint_clean[:40]
    pos = text.find(short_hint)
    if pos != -1:
        return pos

    # 3. Fuzzy match using difflib
    return _fuzzy_find(text, hint_clean)


def _fuzzy_find(text: str, query: str, window: int = 200) -> int:
    """Slide a window over *text* and return the position of the best match.

    Uses ``difflib.SequenceMatcher`` for scoring.  Returns -1 if no
    reasonable match is found (ratio < 0.5).
    """
    query_len = len(query)
    if query_len == 0 or len(text) == 0:
        return -1

    best_pos = -1
    best_ratio = 0.5  # minimum acceptable ratio

    step = max(1, query_len // 4)
    for i in range(0, len(text) - query_len + 1, step):
        candidate = text[i : i + query_len]
        ratio = difflib.SequenceMatcher(None, query, candidate).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_pos = i

    return best_pos
