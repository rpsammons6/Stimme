"""GlobalLoader — loads, validates, and persists the Global Foundation (``config.json``).

Responsibilities:
- Load ``config.json`` from disk, creating it with built-in defaults if missing.
- Back up corrupted files (``config.json.bak``) and recreate with defaults.
- Persist changes via :func:`~app.utils.file_ops.atomic_write` for crash safety.
- Provide the canonical set of default values via :meth:`defaults`.

All disk errors are logged and handled gracefully — the loader never crashes
the application.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from app.services.config_schema import GLOBAL_SCHEMA, defaults as schema_defaults
from app.utils.file_ops import atomic_write

logger = logging.getLogger(__name__)


class GlobalLoader:
    """Loads and persists the Global Foundation (``config.json``)."""

    def __init__(self, config_path: Path):
        self._path = Path(config_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """Load ``config.json``.

        - If the file does not exist, create it with built-in defaults.
        - If the file contains invalid JSON, back it up with a ``.bak``
          extension and recreate with defaults.
        - Returns the loaded (or default) configuration dictionary.
        """
        if not self._path.exists():
            logger.info(
                "GlobalLoader: config not found at %s — creating with defaults",
                self._path,
            )
            default_data = self.defaults()
            self.save(default_data)
            return default_data

        # File exists — try to parse it.
        try:
            raw_text = self._path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "GlobalLoader: corrupted config at %s (%s) — backing up and recreating",
                self._path, exc,
            )
            self._backup()
            default_data = self.defaults()
            self.save(default_data)
            return default_data

        if not isinstance(data, dict):
            logger.warning(
                "GlobalLoader: config root is %s (expected dict) — backing up and recreating",
                type(data).__name__,
            )
            self._backup()
            default_data = self.defaults()
            self.save(default_data)
            return default_data

        return data

    def save(self, data: dict[str, Any]) -> None:
        """Persist *data* to ``config.json`` via :func:`atomic_write`.

        Logs the error on failure without crashing.
        """
        try:
            content = json.dumps(data, indent=2, ensure_ascii=False)
            atomic_write(self._path, content)
        except OSError as exc:
            logger.error(
                "GlobalLoader: failed to save config to %s: %s",
                self._path, exc,
            )

    @staticmethod
    def defaults() -> dict[str, Any]:
        """Return the full default Global Foundation dictionary."""
        return schema_defaults(GLOBAL_SCHEMA)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _backup(self) -> None:
        """Copy the current config file to ``config.json.bak``.

        Silently ignores errors — the backup is best-effort.
        """
        backup_path = self._path.with_suffix(".bak")
        try:
            shutil.copy2(self._path, backup_path)
            logger.info(
                "GlobalLoader: corrupted config backed up to %s", backup_path,
            )
        except OSError as exc:
            logger.warning(
                "GlobalLoader: could not create backup at %s: %s",
                backup_path, exc,
            )
