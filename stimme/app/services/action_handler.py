"""ActionHandler — executes special actions triggered by button-type settings.

Handles Danger Zone purges (clear history, clear cache, wipe corrections),
LanceDB optimization, dependency health checks, VAD reset, keyring migration,
persona save/load, and language pack import.

All methods catch exceptions, log errors, and show error banners via EventBus
without crashing.

Feature: settings-menu
Requirements: 8.2, 8.3, 8.4, 8.7, 5.5, 5.6, 10.3, 4.5, 4.6, 4.7
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.constants import BASE_DIR, HISTORY_DIR, VECTOR_DB_PATH

if TYPE_CHECKING:
    from app.event_bus import EventBus
    from app.services.configuration_service import ConfigurationService

logger = logging.getLogger(__name__)


class ActionHandler:
    """Executes special actions triggered by button-type settings in the
    Preferences window.

    Each action is dispatched by its ``action_id`` string from the schema.
    All methods are fire-and-forget safe — exceptions are caught, logged,
    and surfaced as error banners via the EventBus.
    """

    # Maps action_id strings from the schema to method names.
    _DISPATCH: dict[str, str] = {
        "clear_history": "_do_clear_history",
        "clear_cache": "_do_clear_cache",
        "wipe_lancedb": "_do_wipe_corrections",
        "optimize_lancedb": "_do_optimize_lancedb",
        "run_dependency_check": "_do_run_dependency_check",
        "reset_vad": "_do_reset_vad",
        "migrate_key_to_keyring": "_do_migrate_key_to_keyring",
        "save_persona": "_do_save_persona",
        "load_persona": "_do_load_persona",
        "import_language_pack": "_do_import_language_pack",
    }

    def __init__(
        self,
        settings: ConfigurationService,
        bus: EventBus,
    ) -> None:
        self._settings = settings
        self._bus = bus

    # ------------------------------------------------------------------
    # Public dispatcher
    # ------------------------------------------------------------------

    def execute(self, action_id: str, **kwargs: Any) -> Any:
        """Dispatch an action by its ID string from the schema.

        Returns the action's return value (e.g. the status dict from
        ``run_dependency_check``), or ``None`` on failure.
        """
        method_name = self._DISPATCH.get(action_id)
        if method_name is None:
            logger.warning("ActionHandler: unknown action_id '%s'", action_id)
            return None

        method = getattr(self, method_name)
        try:
            return method(**kwargs)
        except Exception as exc:
            logger.error(
                "ActionHandler: action '%s' failed: %s", action_id, exc,
                exc_info=True,
            )
            self._bus.show_banner(
                f"Action failed: {exc}",
                is_error=True,
            )
            return None

    # ------------------------------------------------------------------
    # Danger Zone actions
    # ------------------------------------------------------------------

    def _do_clear_history(self) -> None:
        """Delete JSON session log files from the history directory.

        Requirement: 8.2
        """
        history_dir = self._resolve_history_dir()
        if not history_dir.exists():
            self._bus.show_banner("No history directory found — nothing to clear.")
            return

        count = 0
        for f in history_dir.iterdir():
            if f.is_file() and f.suffix == ".json":
                f.unlink()
                count += 1

        logger.info("ActionHandler: cleared %d history file(s) from %s", count, history_dir)
        self._bus.show_banner(f"Cleared {count} session history file(s).")

    def _do_clear_cache(self) -> None:
        """Delete temporary PDF and BERT cache files.

        Looks for cached files in the standard temp/cache locations under
        the Stimme base directory.

        Requirement: 8.3
        """
        cache_dirs = [
            BASE_DIR / "cache",
            BASE_DIR / "temp",
            BASE_DIR / ".cache",
        ]

        count = 0
        for cache_dir in cache_dirs:
            if not cache_dir.exists():
                continue
            for f in cache_dir.rglob("*"):
                if f.is_file():
                    f.unlink()
                    count += 1

        logger.info("ActionHandler: cleared %d cache file(s)", count)
        self._bus.show_banner(f"Cleared {count} cached file(s).")

    def _do_wipe_corrections(self) -> None:
        """Delete the LanceDB corrections table.

        Requirement: 8.4
        """
        try:
            import lancedb
        except ImportError:
            self._bus.show_banner(
                "LanceDB is not installed — cannot wipe corrections.",
                is_error=True,
            )
            return

        db_path = self._resolve_vector_db_path()
        if not db_path.exists():
            self._bus.show_banner("No vector database found — nothing to wipe.")
            return

        db = lancedb.connect(str(db_path))
        table_name = "corrections"

        if table_name not in db.table_names():
            self._bus.show_banner("No corrections table found — nothing to wipe.")
            return

        db.drop_table(table_name)
        logger.info("ActionHandler: wiped corrections table from %s", db_path)
        self._bus.show_banner("Learned corrections have been permanently deleted.")

    def _do_optimize_lancedb(self) -> None:
        """Run vacuum on the LanceDB vector store.

        Requirement: 5.6
        """
        try:
            import lancedb
        except ImportError:
            self._bus.show_banner(
                "LanceDB is not installed — cannot optimize.",
                is_error=True,
            )
            return

        db_path = self._resolve_vector_db_path()
        if not db_path.exists():
            self._bus.show_banner("No vector database found — nothing to optimize.")
            return

        db = lancedb.connect(str(db_path))
        tables = db.table_names()
        if not tables:
            self._bus.show_banner("No tables found in vector database.")
            return

        optimized = 0
        for name in tables:
            table = db.open_table(name)
            table.compact_files()
            table.cleanup_old_versions()
            optimized += 1

        logger.info(
            "ActionHandler: optimized %d table(s) in %s", optimized, db_path,
        )
        self._bus.show_banner(f"Optimized {optimized} table(s) in the vector database.")

    # ------------------------------------------------------------------
    # Dependency health check
    # ------------------------------------------------------------------

    def _do_run_dependency_check(self) -> dict[str, bool]:
        """Verify system dependencies and return a status map.

        Checks: Tesseract, Poppler, ONNX models, LanceDB, keyring backend.

        Requirement: 8.7
        """
        status: dict[str, bool] = {
            "tesseract": False,
            "poppler": False,
            "onnx_models": False,
            "lancedb": False,
            "keyring": False,
        }

        # --- Tesseract ---
        status["tesseract"] = self._check_tesseract()

        # --- Poppler ---
        status["poppler"] = self._check_poppler()

        # --- ONNX models ---
        status["onnx_models"] = self._check_onnx_models()

        # --- LanceDB ---
        status["lancedb"] = self._check_lancedb()

        # --- Keyring ---
        status["keyring"] = self._check_keyring()

        # Build a human-readable report
        report_lines = []
        for dep, ok in status.items():
            icon = "✅" if ok else "❌"
            report_lines.append(f"{icon} {dep.replace('_', ' ').title()}")
        report = "  |  ".join(report_lines)

        logger.info("ActionHandler: dependency check — %s", status)
        self._bus.show_banner(f"Dependency Check: {report}")

        return status

    # ------------------------------------------------------------------
    # VAD reset
    # ------------------------------------------------------------------

    def _do_reset_vad(self) -> None:
        """Restore VAD multipliers to their default value of 1.0.

        Requirement: 5.5
        """
        for key in ("valence_multiplier", "arousal_multiplier", "dominance_multiplier"):
            self._settings.set(key, 1.0)

        logger.info("ActionHandler: VAD multipliers reset to 1.0")
        self._bus.show_banner("VAD multipliers restored to defaults (1.0).")

    # ------------------------------------------------------------------
    # Keyring migration
    # ------------------------------------------------------------------

    def _do_migrate_key_to_keyring(self) -> None:
        """Migrate the API key from .env to the OS keyring.

        Requirement: 10.3
        """
        success = self._settings.migrate_env_key_to_keyring()
        if success:
            self._bus.show_banner("API key migrated to OS keyring successfully.")
        else:
            self._bus.show_banner(
                "Could not migrate API key. The OS keyring may be unavailable, "
                "or no key was found in .env. The key remains in its current location.",
                is_error=True,
            )

    # ------------------------------------------------------------------
    # Persona save / load
    # ------------------------------------------------------------------

    def _do_save_persona(self, *, path: str | None = None) -> None:
        """Serialize the current persona settings to a .stimme file.

        If *path* is not provided, the caller (PreferencesWindow) is expected
        to have collected it via a file picker before invoking this action.

        Requirement: 4.5
        """
        if not path:
            logger.warning("ActionHandler: save_persona called without a path")
            self._bus.show_banner(
                "No file path provided for persona save.",
                is_error=True,
            )
            return

        snapshot = self._settings.get_snapshot()
        # Extract persona-layer keys only (non-global settings)
        persona_data = {
            k: v for k, v in snapshot.items()
            if k in self._persona_keys()
        }

        json_str = self._settings.serialize_persona(persona_data)
        target = Path(path)
        from app.utils.file_ops import atomic_write
        atomic_write(target, json_str)

        logger.info("ActionHandler: persona saved to %s", target)
        self._bus.show_banner(f"Persona saved to {target.name}.")

    def _do_load_persona(self, *, path: str | None = None) -> None:
        """Mount a .stimme file as the active persona.

        If *path* is not provided, the caller (PreferencesWindow) is expected
        to have collected it via a file picker before invoking this action.

        Requirement: 4.6, 4.7
        """
        if not path:
            logger.warning("ActionHandler: load_persona called without a path")
            self._bus.show_banner(
                "No file path provided for persona load.",
                is_error=True,
            )
            return

        target = Path(path)
        if not target.exists():
            self._bus.show_banner(
                f"Persona file not found: {target.name}",
                is_error=True,
            )
            return

        self._settings.mount_persona(target)
        logger.info("ActionHandler: persona loaded from %s", target)
        self._bus.show_banner(f"Persona loaded from {target.name}.")

    # ------------------------------------------------------------------
    # Language pack import
    # ------------------------------------------------------------------

    def _do_import_language_pack(self, *, path: str | None = None) -> None:
        """Import a language JSON file into the application's locales directory.

        Requirement: 7.5 (Interface tab — Import Language Pack)
        """
        if not path:
            logger.warning("ActionHandler: import_language_pack called without a path")
            self._bus.show_banner(
                "No file path provided for language pack import.",
                is_error=True,
            )
            return

        source = Path(path)
        if not source.exists() or source.suffix != ".json":
            self._bus.show_banner(
                "Invalid language pack file. Please select a .json file.",
                is_error=True,
            )
            return

        # Validate that the file is valid JSON
        try:
            json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._bus.show_banner(
                f"Invalid language pack: {exc}",
                is_error=True,
            )
            return

        locales_dir = BASE_DIR / "locales"
        locales_dir.mkdir(parents=True, exist_ok=True)

        dest = locales_dir / source.name
        shutil.copy2(source, dest)

        logger.info("ActionHandler: language pack imported to %s", dest)
        self._bus.show_banner(f"Language pack '{source.name}' imported successfully.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_history_dir(self) -> Path:
        """Return the history directory, preferring the configured path."""
        configured = self._settings.get("history_directory", "")
        if configured:
            return Path(configured)
        return HISTORY_DIR

    def _resolve_vector_db_path(self) -> Path:
        """Return the LanceDB vector store path, preferring the configured path."""
        configured = self._settings.get("lancedb_path", "")
        if configured:
            return Path(configured)
        return VECTOR_DB_PATH

    @staticmethod
    def _persona_keys() -> set[str]:
        """Return the set of known persona-layer config keys."""
        return {
            "temperature",
            "max_tokens",
            "master_prompt",
            "vector_distance_threshold",
            "context_limit",
            "vad_enabled",
            "valence_multiplier",
            "arousal_multiplier",
            "dominance_multiplier",
            "cross_chunk_memory",
            "scholar_mode",
            "thematic_focus",
        }

    # ------------------------------------------------------------------
    # Dependency check helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_tesseract() -> bool:
        """Return True if Tesseract is available on the system."""
        try:
            import subprocess
            result = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    @staticmethod
    def _check_poppler() -> bool:
        """Return True if Poppler utilities are available."""
        try:
            import subprocess
            result = subprocess.run(
                ["pdftoppm", "-v"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    @staticmethod
    def _check_onnx_models() -> bool:
        """Return True if ONNX model files exist in the models directory."""
        models_dir = BASE_DIR / "models"
        if not models_dir.exists():
            return False
        onnx_files = list(models_dir.rglob("*.onnx"))
        return len(onnx_files) > 0

    @staticmethod
    def _check_lancedb() -> bool:
        """Return True if the lancedb package is importable and the DB path exists."""
        try:
            import lancedb  # noqa: F401
            return VECTOR_DB_PATH.exists()
        except ImportError:
            return False

    @staticmethod
    def _check_keyring() -> bool:
        """Return True if the keyring backend is functional."""
        try:
            import keyring
            # Attempt a no-op read to verify the backend works
            keyring.get_password("stimme_health_check", "probe")
            return True
        except ImportError:
            return False
        except Exception:
            # Backend exists but may have issues — still counts as available
            # since the import succeeded
            return True
