"""Global search utility — scans all .glossary files for fuzzy matches.

This module is designed to run in the caller's thread. The caller (typically
GlossarySearchBar) is responsible for spawning a background thread.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from app.services.glossary_manager import GlossaryFile, GlossaryTerm

from .fuzzy_search import fuzzy_filter

logger = logging.getLogger(__name__)


def run_global_search(
    query: str,
    glossaries_dir: Path,
    progress_callback: Callable[[str], None],
    threshold: int = 70,
) -> list[tuple[GlossaryTerm, str, int]]:
    """Scan all .glossary files for fuzzy matches against the query.

    Args:
        query: The search string to match against terms.
        glossaries_dir: Directory containing .glossary files.
        progress_callback: Called with status text during the scan
            (e.g., "Searching 3/15 glossaries...").
        threshold: Minimum fuzzy score to include a result.

    Returns:
        List of (term, source_glossary_name, score) tuples sorted by
        score descending.
    """
    if not query:
        return []

    glossary_files = sorted(glossaries_dir.glob("*.glossary"))
    total_files = len(glossary_files)

    if total_files == 0:
        return []

    all_results: list[tuple[GlossaryTerm, str, int]] = []
    total_terms_indexed = 0

    for idx, file_path in enumerate(glossary_files, start=1):
        progress_callback(f"Searching {idx}/{total_files} glossaries...")

        try:
            data = file_path.read_text(encoding="utf-8")
            glossary = GlossaryFile.from_json(data, file_path=file_path)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.warning("Skipping %s during global search: %s", file_path.name, exc)
            continue

        total_terms_indexed += len(glossary.terms)
        matches = fuzzy_filter(query, glossary.terms, threshold=threshold)

        for term, score in matches:
            all_results.append((term, glossary.name or file_path.stem, score))

    # Log diagnostic
    logger.info(
        "[SEARCH-DIAG]: Global scan initiated. %d terms indexed across %d files.",
        total_terms_indexed,
        total_files,
    )

    # Sort all results by score descending
    all_results.sort(key=lambda x: x[2], reverse=True)
    return all_results
