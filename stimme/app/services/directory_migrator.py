"""DirectoryMigrator — safe directory migration for infrastructure paths.

Supports two strategies:

- ``reference_only``: update the path reference without moving files.
- ``copy_and_delete``: copy files to the new location, verify integrity
  (file count + total size match), then delete the originals.

Thread safety is enforced via a :class:`threading.Lock` and an
``_in_progress`` flag that consumers can check to block translation
operations during a migration.

All failures are handled gracefully — the original path and files are
retained, the lock is released, and an error banner is emitted via
:class:`~app.event_bus.EventBus`.
"""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class DirectoryMigrator:
    """Manages safe directory migration for infrastructure paths."""

    def __init__(self, event_bus):
        """
        Args:
            event_bus: The app's :class:`~app.event_bus.EventBus` instance
                for emitting ``migration_complete`` and error banners.
        """
        self._bus = event_bus
        self._migration_lock = threading.Lock()
        self._in_progress = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def in_progress(self) -> bool:
        """``True`` while a copy-based directory migration is running."""
        return self._in_progress

    def migrate(
        self,
        source: str | Path,
        dest: str | Path,
        strategy: str = "reference_only",
    ) -> bool:
        """Execute a directory migration.

        Args:
            source: Current directory path.
            dest: Target directory path.
            strategy: ``"reference_only"`` (just update the path, no file
                moves) or ``"copy_and_delete"`` (copy files, verify
                integrity, delete originals).

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        source = Path(source)
        dest = Path(dest)

        if strategy == "reference_only":
            return self._reference_only(source, dest)
        elif strategy == "copy_and_delete":
            return self._copy_and_delete(source, dest)
        else:
            logger.error(
                "DirectoryMigrator: unknown strategy '%s'", strategy,
            )
            return False

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _reference_only(self, source: Path, dest: Path) -> bool:
        """Update the path reference without moving files.

        Creates the destination directory if it does not exist.
        """
        try:
            dest.mkdir(parents=True, exist_ok=True)
            logger.info(
                "DirectoryMigrator: reference_only migration from %s to %s",
                source, dest,
            )
            self._emit_complete(source, dest, "reference_only")
            return True
        except OSError as exc:
            msg = f"Failed to create destination directory {dest}: {exc}"
            logger.error("DirectoryMigrator: %s", msg)
            self._emit_error(msg)
            return False

    def _copy_and_delete(self, source: Path, dest: Path) -> bool:
        """Copy files, verify integrity, then delete originals."""
        acquired = self._migration_lock.acquire(blocking=False)
        if not acquired:
            msg = "A directory migration is already in progress"
            logger.warning("DirectoryMigrator: %s", msg)
            self._emit_error(msg)
            return False

        self._in_progress = True
        try:
            return self._do_copy_and_delete(source, dest)
        finally:
            self._in_progress = False
            self._migration_lock.release()

    def _do_copy_and_delete(self, source: Path, dest: Path) -> bool:
        """Inner implementation for copy-and-delete (runs under lock)."""
        # Validate source
        if not source.exists():
            msg = f"Source directory does not exist: {source}"
            logger.error("DirectoryMigrator: %s", msg)
            self._emit_error(msg)
            return False

        if not source.is_dir():
            msg = f"Source is not a directory: {source}"
            logger.error("DirectoryMigrator: %s", msg)
            self._emit_error(msg)
            return False

        # Snapshot source metrics before copy
        source_count, source_size = self._dir_metrics(source)

        # Copy
        try:
            if dest.exists():
                # Merge into existing destination
                shutil.copytree(source, dest, dirs_exist_ok=True)
            else:
                shutil.copytree(source, dest)
            logger.info(
                "DirectoryMigrator: copied %s → %s (%d files, %d bytes)",
                source, dest, source_count, source_size,
            )
        except OSError as exc:
            msg = f"Copy failed from {source} to {dest}: {exc}"
            logger.error("DirectoryMigrator: %s", msg)
            self._emit_error(msg)
            return False

        # Verify integrity — file count and total size must match
        dest_count, dest_size = self._dir_metrics(dest)
        if dest_count < source_count or dest_size < source_size:
            msg = (
                f"Integrity check failed: source ({source_count} files, "
                f"{source_size} bytes) vs dest ({dest_count} files, "
                f"{dest_size} bytes). Retaining original files."
            )
            logger.error("DirectoryMigrator: %s", msg)
            self._emit_error(msg)
            return False

        # Delete originals
        try:
            shutil.rmtree(source)
            logger.info(
                "DirectoryMigrator: deleted original directory %s", source,
            )
        except OSError as exc:
            # Files were copied successfully — log but don't fail
            logger.warning(
                "DirectoryMigrator: could not delete original %s: %s "
                "(files were copied successfully)",
                source, exc,
            )

        self._emit_complete(source, dest, "copy_and_delete")
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dir_metrics(directory: Path) -> tuple[int, int]:
        """Return ``(file_count, total_size_bytes)`` for *directory*.

        Only counts regular files (not directories or symlinks).
        """
        count = 0
        total_size = 0
        for entry in directory.rglob("*"):
            if entry.is_file():
                count += 1
                try:
                    total_size += entry.stat().st_size
                except OSError:
                    pass
        return count, total_size

    def _emit_complete(
        self, source: Path, dest: Path, strategy: str,
    ) -> None:
        """Emit ``migration_complete`` on the EventBus."""
        try:
            self._bus.emit(
                "migration_complete",
                source=str(source),
                dest=str(dest),
                strategy=strategy,
            )
        except Exception:
            logger.warning(
                "DirectoryMigrator: failed to emit migration_complete event",
                exc_info=True,
            )

    def _emit_error(self, message: str) -> None:
        """Emit an error banner on the EventBus."""
        try:
            self._bus.emit(
                "migration_error",
                message=message,
            )
        except Exception:
            logger.warning(
                "DirectoryMigrator: failed to emit migration_error event",
                exc_info=True,
            )
