"""Fuzzy search utility with umlaut normalization for glossary term filtering.

Uses RapidFuzz for typo-tolerant matching. Falls back to simple substring
matching if RapidFuzz is not available.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.glossary_manager import GlossaryTerm

logger = logging.getLogger(__name__)

# Try to import RapidFuzz; fall back gracefully
try:
    from rapidfuzz import fuzz as _fuzz

    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False
    logger.warning(
        "rapidfuzz not installed — falling back to substring matching for glossary search"
    )

# ---------------------------------------------------------------------------
# Umlaut normalization
# ---------------------------------------------------------------------------

_UMLAUT_TO_DOUBLE: dict[str, str] = {
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "ß": "ss",
    "Ä": "Ae",
    "Ö": "Oe",
    "Ü": "Ue",
}

_DOUBLE_TO_UMLAUT: dict[str, str] = {
    "ae": "ä",
    "oe": "ö",
    "ue": "ü",
    "ss": "ß",
    "Ae": "Ä",
    "Oe": "Ö",
    "Ue": "Ü",
}


def normalize_umlauts(text: str) -> str:
    """Normalize umlauts to their double-vowel equivalents for comparison.

    Converts ä→ae, ö→oe, ü→ue, ß→ss (and uppercase variants).
    This produces a canonical ASCII-friendly form suitable for fuzzy matching.
    """
    result = text
    for umlaut, double in _UMLAUT_TO_DOUBLE.items():
        result = result.replace(umlaut, double)
    return result


# ---------------------------------------------------------------------------
# Fuzzy filter
# ---------------------------------------------------------------------------


def fuzzy_filter(
    query: str,
    terms: list["GlossaryTerm"],
    threshold: int = 70,
    fields: tuple[str, ...] = ("german", "english", "context_target"),
) -> list[tuple["GlossaryTerm", int]]:
    """Filter terms by fuzzy matching against the query.

    Args:
        query: The search string entered by the user.
        terms: List of GlossaryTerm objects to search through.
        threshold: Minimum similarity score (0–100) to include a result.
        fields: Tuple of GlossaryTerm field names to match against.

    Returns:
        List of (term, best_score) tuples sorted by score descending.
        Only terms with best_score >= threshold are included.
    """
    if not query or not terms:
        return []

    # Normalize the query for umlaut-insensitive matching
    normalized_query = normalize_umlauts(query).lower()

    if _RAPIDFUZZ_AVAILABLE:
        return _fuzzy_filter_rapidfuzz(normalized_query, terms, threshold, fields)
    else:
        return _fuzzy_filter_fallback(normalized_query, terms, fields)


def _fuzzy_filter_rapidfuzz(
    normalized_query: str,
    terms: list["GlossaryTerm"],
    threshold: int,
    fields: tuple[str, ...],
) -> list[tuple["GlossaryTerm", int]]:
    """RapidFuzz-based fuzzy matching."""
    results: list[tuple["GlossaryTerm", int]] = []

    for term in terms:
        best_score = 0
        for field_name in fields:
            value = getattr(term, field_name, "") or ""
            normalized_value = normalize_umlauts(value).lower()
            # Use partial_ratio for substring-aware matching
            score = int(_fuzz.partial_ratio(normalized_query, normalized_value))
            if score > best_score:
                best_score = score
        if best_score >= threshold:
            results.append((term, best_score))

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def _fuzzy_filter_fallback(
    normalized_query: str,
    terms: list["GlossaryTerm"],
    fields: tuple[str, ...],
) -> list[tuple["GlossaryTerm", int]]:
    """Fallback substring matching when RapidFuzz is unavailable.

    Returns matches with a synthetic score of 100 (exact substring match).
    """
    results: list[tuple["GlossaryTerm", int]] = []

    for term in terms:
        for field_name in fields:
            value = getattr(term, field_name, "") or ""
            normalized_value = normalize_umlauts(value).lower()
            if normalized_query in normalized_value:
                results.append((term, 100))
                break

    return results
