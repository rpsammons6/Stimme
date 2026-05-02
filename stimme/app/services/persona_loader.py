"""PersonaLoader — parses, validates, and self-heals Scholarly Persona (``.stimme``) files.

The loader enforces:
- File size limit (1 MB)
- Valid JSON structure
- Secret-pattern key rejection (entire file rejected)
- Unrecognized key stripping
- Type validation with fallback to schema defaults
- Numeric range clamping

All self-healing actions are logged with structured messages so operators
can trace exactly what was changed and why.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.services.config_schema import PERSONA_SCHEMA, defaults, validate_value

logger = logging.getLogger(__name__)


class PersonaLoader:
    """Parses and validates Scholarly Persona (``.stimme``) files."""

    MAX_FILE_SIZE: int = 1_048_576  # 1 MB

    SECRET_PATTERNS: list[str] = [
        "api_key",
        "secret",
        "token",
        "password",
        "credential",
    ]

    KNOWN_KEYS: set[str] = set(PERSONA_SCHEMA.keys())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, path: Path) -> dict[str, Any]:
        """Parse a ``.stimme`` file with full validation.

        Steps:
        1. Check file size ≤ ``MAX_FILE_SIZE``
        2. Parse JSON
        3. Reject if any key matches ``SECRET_PATTERNS``
        4. Warn and strip unrecognized keys
        5. Type-validate and range-clamp each known key

        Returns the validated persona dict.  May be empty if the file is
        rejected or all values fail validation.
        """
        path = Path(path)

        # --- 1. File size check ---
        try:
            file_size = path.stat().st_size
        except OSError as exc:
            logger.error(
                "Persona load failed: path=%s error=%s", path, exc,
            )
            return {}

        if file_size > self.MAX_FILE_SIZE:
            logger.error(
                "Persona rejected: path=%s size=%d exceeds limit=%d",
                path, file_size, self.MAX_FILE_SIZE,
            )
            return {}

        # --- 2. Parse JSON ---
        try:
            raw_text = path.read_text(encoding="utf-8")
            raw_data = json.loads(raw_text)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(
                "Persona rejected: path=%s invalid JSON: %s", path, exc,
            )
            return {}

        if not isinstance(raw_data, dict):
            logger.error(
                "Persona rejected: path=%s root is %s, expected dict",
                path, type(raw_data).__name__,
            )
            return {}

        # --- 3. Reject secret-pattern keys ---
        # Only check keys that are NOT in KNOWN_KEYS — legitimate schema keys
        # like "max_tokens" contain the substring "token" but are safe.
        for key in raw_data:
            if key not in self.KNOWN_KEYS and self._matches_secret_pattern(key):
                logger.error(
                    "Persona rejected: path=%s contains secret-pattern key '%s'",
                    path, key,
                )
                return {}

        # --- 4. Strip unrecognized keys ---
        unrecognized = set(raw_data.keys()) - self.KNOWN_KEYS
        if unrecognized:
            logger.warning(
                "Persona strip: path=%s unrecognized keys=%s",
                path, sorted(unrecognized),
            )

        # --- 5. Type-validate and range-clamp known keys ---
        persona_defaults = defaults(PERSONA_SCHEMA)
        result: dict[str, Any] = {}
        heal_count = 0

        for key in self.KNOWN_KEYS:
            if key not in raw_data:
                continue

            value = raw_data[key]
            validated, was_healed = validate_value(key, value, PERSONA_SCHEMA)

            if was_healed:
                heal_count += 1

            result[key] = validated

        # If every single provided value was healed, the file is essentially
        # garbage — log an error but still return whatever we could salvage.
        provided_keys = set(raw_data.keys()) & self.KNOWN_KEYS
        if provided_keys and heal_count == len(provided_keys):
            logger.error(
                "Persona degraded: path=%s all %d values required healing",
                path, heal_count,
            )

        return result

    @staticmethod
    def serialize(persona_dict: dict[str, Any]) -> str:
        """Serialize a persona dict to a JSON string (sorted keys, 2-space indent)."""
        return json.dumps(persona_dict, sort_keys=True, indent=2, ensure_ascii=False)

    @staticmethod
    def deserialize(json_string: str) -> dict[str, Any]:
        """Parse a JSON string into a persona dict."""
        return json.loads(json_string)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _matches_secret_pattern(cls, key: str) -> bool:
        """Return ``True`` if *key* contains any secret pattern (case-insensitive)."""
        lower = key.lower()
        return any(pattern in lower for pattern in cls.SECRET_PATTERNS)
