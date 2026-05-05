"""ConfigurationService — unified configuration facade.

Replaces ``SettingsManager`` and the dead ``ConfigManager`` with a single,
two-layer configuration system:

1. **Global Foundation** (``~/.stimme/config.json``) — machine-specific
   settings: hardware paths, system preferences, secrets pointers, app
   lifecycle, LLM backend, OCR preprocessing, network/proxy, hotkeys,
   datasets, billing.
2. **Scholarly Persona** (``.stimme`` files) — portable, read-only-at-runtime
   presets: prompts, model directives, hyperparameters, RAG weights, VAD
   multipliers, memory settings, glossary binding, scholar mode, thematic
   focus.

At boot the service loads ``config.json``, mounts the active persona, merges
both into an **Active Registry** (single in-memory dict), and broadcasts the
result via ``EventBus``.  All consumers read from the Active Registry through
a unified ``get(key, default)`` interface.  Backward-compatible ``get_*/set_*``
methods match the existing ``SettingsManager`` API so consumers can be migrated
incrementally.

Requirements: 1.1, 1.5, 2.1–2.5, 3.1–3.5, 4.1–4.4, 5.1–5.3, 8.5–8.7,
              10.1, 10.3
"""

from __future__ import annotations

import copy
import logging
import os
import threading
from pathlib import Path
from typing import Any

from app.services.global_loader import GlobalLoader
from app.services.persona_loader import PersonaLoader
from app.services.merge_engine import MergeEngine
from app.services.secrets_manager import SecretsManager
from app.services.directory_migrator import DirectoryMigrator

logger = logging.getLogger(__name__)


class ConfigurationService:
    """Unified configuration service — replaces SettingsManager."""

    def __init__(self, event_bus, stimme_dir: Path | None = None):
        """
        Args:
            event_bus: The app's :class:`~app.event_bus.EventBus` instance
                for broadcasting changes.
            stimme_dir: Override for the project root directory (defaults to
                ``~/.stimme`` if not provided, but normally passed by AppShell).
        """
        self._bus = event_bus
        self._stimme_dir = Path(stimme_dir) if stimme_dir else Path.home() / ".stimme"
        self._stimme_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()

        # --- Internal components ---
        config_path = self._stimme_dir / "config.json"
        self._global_loader = GlobalLoader(config_path)
        self._persona_loader = PersonaLoader()
        self._secrets = SecretsManager(env_path=self._stimme_dir.parent / ".env")
        self._migrator = DirectoryMigrator(self._bus)

        # --- State ---
        self._global: dict[str, Any] = {}
        self._persona: dict[str, Any] = {}
        self._registry: dict[str, Any] = {}
        self._mounted_persona_path: str | None = None

        # --- Boot sequence ---
        self._boot()

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def _boot(self) -> None:
        """Load global config, mount active persona if set, build registry."""
        # 1. Load Global Foundation
        self._global = self._global_loader.load()

        # 2. Mount active persona if configured
        preset_path = self._global.get("active_preset_path", "")
        if preset_path:
            p = Path(preset_path)
            if p.exists():
                self._persona = self._persona_loader.parse(p)
                self._mounted_persona_path = str(p)
            else:
                logger.warning(
                    "ConfigurationService: active_preset_path '%s' not found "
                    "— operating with Global Foundation only",
                    preset_path,
                )
                self._global["active_preset_path"] = ""
                self._global_loader.save(self._global)

        # 3. Build Active Registry
        self._rebuild_registry()

        # 4. Broadcast
        self._bus.emit("config_reloaded", registry=self.get_snapshot())

    def _rebuild_registry(self) -> None:
        """Merge global + persona and apply business rules.

        Must be called while holding ``_lock`` (or during ``__init__``).
        """
        merged = MergeEngine.merge(self._global, self._persona)
        self._registry = MergeEngine.apply_rules(merged)

    # ------------------------------------------------------------------
    # Generic API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value from the Active Registry."""
        with self._lock:
            return self._registry.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Write a value to the Global Foundation, rebuild Active Registry,
        persist to disk, and emit ``config_changed``.
        """
        with self._lock:
            self._global[key] = value
            self._rebuild_registry()
            self._global_loader.save(self._global)

        # Emit outside lock to avoid deadlock with listeners
        self._bus.emit("config_changed", key=key, value=value)

    def get_snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the entire Active Registry."""
        with self._lock:
            return copy.deepcopy(self._registry)

    # ------------------------------------------------------------------
    # Persona Management
    # ------------------------------------------------------------------

    def mount_persona(self, persona_path: str | Path) -> None:
        """Load and mount a ``.stimme`` file.

        Rebuilds Active Registry.  Emits ``persona_mounted`` and
        ``config_reloaded``.
        """
        p = Path(persona_path)
        with self._lock:
            self._persona = self._persona_loader.parse(p)
            self._mounted_persona_path = str(p)
            self._global["active_preset_path"] = str(p)
            self._rebuild_registry()
            self._global_loader.save(self._global)

        self._bus.emit("persona_mounted", path=str(p))
        self._bus.emit("config_reloaded", registry=self.get_snapshot())

    def unmount_persona(self) -> None:
        """Unmount the current persona.

        Reverts to Global Foundation only.  Emits ``persona_mounted(path=None)``
        and ``config_reloaded``.
        """
        with self._lock:
            self._persona = {}
            self._mounted_persona_path = None
            self._global["active_preset_path"] = ""
            self._rebuild_registry()
            self._global_loader.save(self._global)

        self._bus.emit("persona_mounted", path=None)
        self._bus.emit("config_reloaded", registry=self.get_snapshot())

    def get_mounted_persona_path(self) -> str | None:
        """Return the path of the currently mounted persona, or ``None``."""
        with self._lock:
            return self._mounted_persona_path

    # ------------------------------------------------------------------
    # Persona Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def serialize_persona(persona_dict: dict[str, Any]) -> str:
        """Convert a persona dictionary to a valid ``.stimme`` JSON string."""
        return PersonaLoader.serialize(persona_dict)

    @staticmethod
    def parse_persona(json_string: str) -> dict[str, Any]:
        """Convert a ``.stimme`` JSON string to a persona dictionary."""
        return PersonaLoader.deserialize(json_string)

    # ------------------------------------------------------------------
    # Directory Migration
    # ------------------------------------------------------------------

    def migrate_directory(
        self,
        key: str,
        new_path: str,
        strategy: str = "reference_only",
    ) -> None:
        """Migrate an infrastructure path.

        Args:
            key: The config key for the path (e.g. ``"export_directory"``).
            new_path: The new directory path.
            strategy: ``"reference_only"`` or ``"copy_and_delete"``.
        """
        old_path = self.get(key, "")
        success = self._migrator.migrate(old_path, new_path, strategy)
        if success:
            self.set(key, new_path)

    @property
    def migration_in_progress(self) -> bool:
        """``True`` while a copy-based directory migration is running."""
        return self._migrator.in_progress

    # ------------------------------------------------------------------
    # Secrets
    # ------------------------------------------------------------------

    def resolve_api_key(self) -> str:
        """Resolve the API key using the strict hierarchy:
        keyring → .env → RAM session cache.
        """
        return self._secrets.resolve()

    def store_api_key(self, key: str) -> bool:
        """Store the API key in the OS keyring.

        Updates ``api_key_source`` in the Global Foundation on success.
        Returns ``True`` on success.
        """
        success = self._secrets.store(key)
        if success:
            self.set("api_key_source", "os_keyring")
        return success

    def migrate_env_key_to_keyring(self) -> bool:
        """Migrate the API key from ``.env`` to OS keyring.

        Backend for the "Secure My Key" UI button.
        Returns ``True`` on success.
        """
        success = self._secrets.migrate_from_env()
        if success:
            self.set("api_key_source", "os_keyring")
        return success

    # ------------------------------------------------------------------
    # Backward-Compatible SettingsManager API
    # ------------------------------------------------------------------

    def get_model(self) -> str:
        """Get the active model name."""
        return self.get("model", "claude-sonnet-4-6")

    def set_model(self, model: str) -> None:
        """Set the active model name."""
        self.set("model", model)

    def get_api_key(self) -> str:
        """Get API key — resolves via SecretsManager hierarchy."""
        return self.resolve_api_key()

    def set_api_key(self, key: str) -> None:
        """Set API key.

        Stores the key in the OS keyring (primary) via SecretsManager and
        sets ``CLAUDE_API_KEY`` env var for the current session.  Does **not**
        persist the key value to ``config.json``.
        """
        # Store in OS keyring (best-effort)
        stored = self._secrets.store(key)
        if stored:
            self.set("api_key_source", "os_keyring")
        else:
            # Fallback: keep in RAM session cache
            self._secrets.set_session_key(key)
            self.set("api_key_source", "session")

        # Also set as environment variable for the current process
        os.environ["CLAUDE_API_KEY"] = key

    def has_api_key(self) -> bool:
        """Check if a valid API key is configured."""
        key = self.get_api_key()
        return bool(key and key.strip() and key.startswith("sk-ant-"))

    def get_ocr_language(self) -> str:
        """Get OCR language code."""
        return self.get("ocr_language", "deu")

    def set_ocr_language(self, language: str) -> None:
        """Set OCR language code."""
        self.set("ocr_language", language)

    def get_export_directory(self) -> str:
        """Get export directory path."""
        return self.get(
            "export_directory",
            str(Path.home() / "Documents" / "Stimme Exports"),
        )

    def set_export_directory(self, directory: str) -> None:
        """Set export directory.

        Attempts to create the directory (non-fatal on failure).
        """
        if not directory or not directory.strip():
            return
        self.set("export_directory", directory)
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as exc:
            logger.warning(
                "ConfigurationService: could not create export directory '%s': %s",
                directory, exc,
            )

    def get_llm_backend(self) -> str:
        """Get LLM backend selection (``'cloud'`` or ``'local'``)."""
        return self.get("llm_backend", "cloud")

    def set_llm_backend(self, backend: str) -> None:
        """Set LLM backend selection."""
        self.set("llm_backend", backend)

    def get_local_llm_endpoint(self) -> str:
        """Get local LLM server endpoint URL."""
        return self.get("local_llm_endpoint", "http://localhost:11434")

    def set_local_llm_endpoint(self, endpoint: str) -> None:
        """Set local LLM server endpoint URL."""
        self.set("local_llm_endpoint", endpoint)

    def get_local_llm_model(self) -> str:
        """Get local LLM model name."""
        return self.get("local_llm_model", "llama3")

    def set_local_llm_model(self, model: str) -> None:
        """Set local LLM model name."""
        self.set("local_llm_model", model)

    def get_local_llm_timeout(self) -> int:
        """Get local LLM request timeout in seconds."""
        return self.get("local_llm_timeout", 120)

    def set_local_llm_timeout(self, timeout: int) -> None:
        """Set local LLM request timeout in seconds."""
        self.set("local_llm_timeout", timeout)

    def get_datasets(self) -> list:
        """Get the list of active datasets."""
        return self.get("active_datasets", ["idioms", "corpus"])

    def add_dataset(self, dataset: str) -> None:
        """Add a dataset to the active list."""
        with self._lock:
            datasets = list(self._global.get("active_datasets", []))
            if dataset not in datasets:
                datasets.append(dataset)
                self._global["active_datasets"] = datasets
                self._rebuild_registry()
                self._global_loader.save(self._global)
            else:
                return  # Already present — no event needed

        self._bus.emit("config_changed", key="active_datasets", value=datasets)

    def remove_dataset(self, dataset: str) -> None:
        """Remove a dataset from the active list (safe — no error if absent)."""
        with self._lock:
            datasets = list(self._global.get("active_datasets", []))
            if dataset in datasets:
                datasets.remove(dataset)
                self._global["active_datasets"] = datasets
                self._rebuild_registry()
                self._global_loader.save(self._global)
            else:
                return  # Not present — no event needed

        self._bus.emit("config_changed", key="active_datasets", value=datasets)

    def get_scholar_mode(self) -> bool:
        """Get scholar mode flag."""
        return self.get("scholar_mode", False)

    def set_scholar_mode(self, enabled: bool) -> None:
        """Set scholar mode flag."""
        self.set("scholar_mode", enabled)

    def get_thematic_focus(self) -> str:
        """Get thematic focus string."""
        return self.get("thematic_focus", "")

    def set_thematic_focus(self, focus: str) -> None:
        """Set thematic focus string."""
        self.set("thematic_focus", focus)

    def get_remember_api_key(self) -> bool:
        """Get whether to remember API key."""
        return self.get("remember_api_key", True)

    def set_remember_api_key(self, remember: bool) -> None:
        """Set whether to remember API key."""
        self.set("remember_api_key", remember)

    # ------------------------------------------------------------------
    # Static helpers (no instance required)
    # ------------------------------------------------------------------

    @staticmethod
    def get_early_theme(stimme_dir: Path | None = None) -> str:
        """Read the persisted theme mode without instantiating the full service.

        This is used during the boot sequence to apply the correct palette
        before AppShell or any service is created.

        Args:
            stimme_dir: Path to the stimme project directory containing
                ``config.json``. If None, defaults to the grandparent of
                this file (i.e. the ``stimme/`` root).

        Returns:
            ``"dark"`` or ``"light"``. Defaults to ``"dark"`` on any error
            (missing file, corrupt JSON, unknown label).
        """
        import json

        try:
            if stimme_dir is None:
                stimme_dir = Path(__file__).resolve().parent.parent.parent
            config_path = Path(stimme_dir) / "config.json"
            if not config_path.exists():
                return "dark"
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            theme_label = cfg.get("theme", "Dunkel")
            from app.theme import _THEME_LABEL_TO_MODE
            return _THEME_LABEL_TO_MODE.get(theme_label, "dark")
        except Exception:
            return "dark"
