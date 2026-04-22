"""Markdown formatting for translated text.

Applies structural formatting (headings, subheadings) to translated output
using configurable strategies: fast regex-based detection or Haiku API-based
formatting for complex documents.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from app.models.bulk_models import Chapter


class MarkdownFormatter:
    """Applies Markdown formatting to translated text."""

    class Strategy(Enum):
        REGEX = "regex"
        HAIKU = "haiku"

    def __init__(
        self,
        strategy: "MarkdownFormatter.Strategy" = None,
        settings=None,
    ):
        if strategy is None:
            strategy = self.Strategy.REGEX
        self.strategy = strategy
        self.settings = settings  # SettingsManager, needed for Haiku strategy

    def format(self, text: str, toc: Optional[List["Chapter"]] = None) -> str:
        """Format *text* using the configured strategy.

        Parameters
        ----------
        text:
            Raw translated text to format.
        toc:
            Optional list of Chapter objects (unused by regex strategy but
            available for Haiku strategy context).

        Returns the text with Markdown heading markup applied.
        """
        if not text or not text.strip():
            return text

        if self.strategy == self.Strategy.HAIKU:
            return self._haiku_format(text)
        return self._regex_format(text)

    # ------------------------------------------------------------------
    # Regex strategy
    # ------------------------------------------------------------------

    def _regex_format(self, text: str) -> str:
        """Detect headings via regex patterns and wrap them in Markdown.

        Patterns (applied in order):
        1. "Kapitel [Number]" variants  → ``# heading``
        2. "Chapter [Number]" variants  → ``# heading``
        3. Roman numeral headings       → ``## heading``
        4. Short capitalised lines      → ``## heading`` (heuristic)
        """
        # Pattern 1: "Kapitel [Number]" (case-insensitive)
        text = re.sub(
            r"^(Kapitel\s+\w+[.:]\s*.*)",
            r"# \1",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        # Pattern 2: "Chapter [Number]" (case-insensitive)
        text = re.sub(
            r"^(Chapter\s+\d+[.:]\s*.*)",
            r"# \1",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        # Pattern 3: Roman numeral headings (I., II., III., IV., …, X.)
        text = re.sub(
            r"^((?:I{1,3}|IV|V|VI{0,3}|IX|X{0,3})\.\s+.+)",
            r"## \1",
            text,
            flags=re.MULTILINE,
        )

        # Pattern 4: Short capitalised lines – heuristic subheadings
        lines = text.split("\n")
        formatted_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if (
                len(stripped) > 10
                and len(stripped) < 60
                and stripped[0].isupper()
                and not stripped.endswith((".", ",", ";", ":"))
                and not stripped.startswith(("#", "-", "*"))
            ):
                formatted_lines.append(f"## {stripped}")
            else:
                formatted_lines.append(line)
        return "\n".join(formatted_lines)

    # ------------------------------------------------------------------
    # Haiku strategy
    # ------------------------------------------------------------------

    def _haiku_format(self, text: str) -> str:
        """Use Claude Haiku to apply Markdown formatting.

        This is a best-effort approach: if the API call fails for any
        reason the original text is returned unchanged.
        """
        try:
            import anthropic

            api_key: str | None = None
            if self.settings is not None:
                api_key = self.settings.get_api_key()

            if not api_key:
                import os
                api_key = os.getenv("CLAUDE_API_KEY", "")

            if not api_key:
                return text

            client = anthropic.Anthropic(api_key=api_key)

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=(
                    "You are a Markdown formatter. Given raw translated text, "
                    "add Markdown heading markup (# for chapters, ## for "
                    "sub-sections) where appropriate. Do NOT change the text "
                    "content itself — only add formatting. Return the "
                    "formatted text and nothing else."
                ),
                messages=[{"role": "user", "content": text}],
            )

            formatted = response.content[0].text
            return formatted if formatted else text

        except Exception:
            # Best-effort: on any failure return text unchanged
            return text
