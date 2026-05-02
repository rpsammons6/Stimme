"""SecretsManager — OS-level credential virtualization for API key management.

Manages the Anthropic API key using a strict resolution hierarchy:

1. **OS Keyring** — Windows Credential Manager / macOS Keychain / Linux Secret
   Service via the ``keyring`` library (primary, encrypted at rest).
2. **``.env`` file / ``CLAUDE_API_KEY`` environment variable** — plaintext
   fallback for environments where the keyring is unavailable.
3. **RAM session cache** — volatile, never persisted; used when the user
   enters a key via the UI prompt.

The manager never persists API key *values* to ``config.json`` or ``.stimme``
files.  Only the ``api_key_source`` status field is written to the Global
Foundation so the UI can display where the key is currently stored.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SecretsManager:
    """OS-level credential virtualization for API key management.

    Hierarchy: 1. OS Keyring → 2. .env file → 3. RAM session cache.
    """

    SERVICE_NAME: str = "stimme"
    ACCOUNT_NAME: str = "api_key"

    def __init__(self, env_path: Path | None = None):
        self._env_path = Path(env_path) if env_path is not None else None
        self._session_key: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self) -> str:
        """Resolve the API key using the strict hierarchy.

        Returns the key string, or an empty string if all sources fail.
        """
        # 1. OS keyring
        key = self._read_keyring()
        if key:
            return key

        # 2. .env file / CLAUDE_API_KEY env var
        key = self._read_env()
        if key:
            return key

        # 3. RAM session cache
        if self._session_key:
            return self._session_key

        return ""

    def store(self, api_key: str) -> bool:
        """Save *api_key* to the OS keyring.

        Returns ``True`` on success.  Logs a warning on keyring failure
        without crashing.
        """
        try:
            import keyring
            keyring.set_password(self.SERVICE_NAME, self.ACCOUNT_NAME, api_key)
            logger.info("SecretsManager: API key stored in OS keyring")
            return True
        except Exception as exc:
            logger.warning(
                "SecretsManager: failed to store key in OS keyring: %s", exc,
            )
            return False

    def delete(self) -> None:
        """Remove the API key from the OS keyring and clear the RAM cache."""
        try:
            import keyring
            keyring.delete_password(self.SERVICE_NAME, self.ACCOUNT_NAME)
            logger.info("SecretsManager: API key deleted from OS keyring")
        except Exception as exc:
            logger.warning(
                "SecretsManager: failed to delete key from OS keyring: %s", exc,
            )
        self._session_key = ""

    def migrate_from_env(self) -> bool:
        """Migrate the API key from ``.env`` / env var into the OS keyring.

        1. Read the key via :meth:`_read_env`.
        2. Store it into the OS keyring via :meth:`store`.
        3. Remove the ``CLAUDE_API_KEY`` line from the ``.env`` file.

        Returns ``True`` on success, ``False`` if no key exists or migration
        fails.  This is the backend for the "Secure My Key" UI button.
        """
        key = self._read_env()
        if not key:
            logger.info(
                "SecretsManager: migrate_from_env — no .env key found, nothing to migrate",
            )
            return False

        if not self.store(key):
            logger.error(
                "SecretsManager: migrate_from_env — failed to store key in keyring",
            )
            return False

        # Remove the CLAUDE_API_KEY line from the .env file.
        self._remove_env_key()
        logger.info(
            "SecretsManager: migrate_from_env — key migrated from .env to OS keyring",
        )
        return True

    def set_session_key(self, api_key: str) -> None:
        """Hold *api_key* in RAM only for the current session (never persisted).

        Used when the user enters a key via the UI prompt.
        """
        self._session_key = api_key

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_keyring(self) -> str | None:
        """Attempt ``keyring.get_password()``.

        Returns ``None`` on any failure (e.g. headless Linux with no secret
        service backend).
        """
        try:
            import keyring
            value = keyring.get_password(self.SERVICE_NAME, self.ACCOUNT_NAME)
            if value:
                return value
            return None
        except Exception as exc:
            logger.warning(
                "SecretsManager: keyring backend unavailable: %s", exc,
            )
            return None

    def _read_env(self) -> str | None:
        """Read the API key from the ``.env`` file or the ``CLAUDE_API_KEY``
        environment variable.

        Returns ``None`` if not found.
        """
        # Try .env file first
        key = self._read_env_file()
        if key:
            return key

        # Fall back to environment variable
        env_val = os.environ.get("CLAUDE_API_KEY", "")
        if env_val and env_val.strip():
            return env_val.strip()

        return None

    def _read_env_file(self) -> str | None:
        """Parse the ``.env`` file for a ``CLAUDE_API_KEY=...`` line.

        Returns the value or ``None`` if the file doesn't exist or the key
        isn't present.
        """
        env_path = self._resolve_env_path()
        if env_path is None or not env_path.exists():
            return None

        try:
            text = env_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("SecretsManager: could not read .env file: %s", exc)
            return None

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            if name.strip() == "CLAUDE_API_KEY":
                val = value.strip().strip("'\"")
                if val:
                    return val

        return None

    def _remove_env_key(self) -> None:
        """Remove the ``CLAUDE_API_KEY`` line from the ``.env`` file.

        Preserves all other lines.  No-op if the file doesn't exist.
        """
        env_path = self._resolve_env_path()
        if env_path is None or not env_path.exists():
            return

        try:
            text = env_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "SecretsManager: could not read .env for cleanup: %s", exc,
            )
            return

        # Keep every line that is NOT a CLAUDE_API_KEY assignment.
        kept: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if "=" in stripped:
                name, _, _ = stripped.partition("=")
                if name.strip() == "CLAUDE_API_KEY":
                    continue
            kept.append(line)

        new_text = "\n".join(kept)
        # Preserve trailing newline if the original had one.
        if text.endswith("\n"):
            new_text += "\n"

        try:
            env_path.write_text(new_text, encoding="utf-8")
            logger.info("SecretsManager: removed CLAUDE_API_KEY from .env")
        except OSError as exc:
            logger.warning(
                "SecretsManager: could not write cleaned .env: %s", exc,
            )

    def _resolve_env_path(self) -> Path | None:
        """Return the path to the ``.env`` file, or ``None``."""
        if self._env_path is not None:
            return self._env_path
        # Default: look for .env in the working directory
        candidate = Path.cwd() / ".env"
        if candidate.exists():
            return candidate
        return None
