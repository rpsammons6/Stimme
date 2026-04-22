"""Word-level diff computation using Python's difflib."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List

from app.models.hitl_models import DiffOp


class DiffComputer:
    """Computes word-level diffs between two translation texts."""

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Split text into word tokens, keeping punctuation as separate tokens."""
        return re.findall(r"\w+|[^\w\s]", text)

    @staticmethod
    def compute_diff(text_a: str, text_b: str) -> List[DiffOp]:
        """Compute word-level diff between two texts.

        Algorithm:
        1. Split both texts into word tokens (preserving punctuation as separate tokens)
        2. Run difflib.SequenceMatcher on the word lists
        3. Convert opcodes to DiffOp list

        Returns list of DiffOp with tag in {'equal', 'insert', 'delete', 'replace'}.
        """
        words_a = DiffComputer.tokenize(text_a)
        words_b = DiffComputer.tokenize(text_b)

        matcher = SequenceMatcher(a=words_a, b=words_b)
        ops: List[DiffOp] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            ops.append(
                DiffOp(
                    tag=tag,
                    old_words=words_a[i1:i2],
                    new_words=words_b[j1:j2],
                )
            )

        return ops
