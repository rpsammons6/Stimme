"""
StateService — orchestrates session snapshot persistence and recovery.

Periodically serializes AppState to ``~/.stimme/session_recovery.json`` using
:func:`atomic_write` and restores it on startup when a snapshot is found.
Also monitors worker processes for unexpected termination.
"""

import json
import logging
import threading
import time
from pathlib import Path

from app.state import AppState
from app.utils.file_ops import atomic_write

logger = logging.getLogger(__name__)


class StateService:
    """Manages session snapshot persistence and recovery detection.

    Parameters
    ----------
    state:
        The live :class:`AppState` instance to serialize.
    bus:
        The :class:`EventBus` used for UI notifications (banners, etc.).
    stimme_dir:
        Path to the ``~/.stimme/`` directory where recovery files are stored.
    """

    SAVE_INTERVAL: int = 60  # seconds
    SNAPSHOT_FILE: str = "session_recovery.json"

    def __init__(self, state: AppState, bus, stimme_dir: Path) -> None:
        self._state = state
        self._bus = bus
        self._stimme_dir = Path(stimme_dir)
        self._snapshot_path = self._stimme_dir / self.SNAPSHOT_FILE
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Periodic auto-save
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic auto-save timer.

        Creates a repeating :class:`threading.Timer` that calls
        :meth:`save_now` every :attr:`SAVE_INTERVAL` seconds.  The timer
        re-schedules itself after each tick.
        """
        with self._lock:
            self._schedule_timer()

    def stop(self, clean_exit: bool = True) -> None:
        """Stop the periodic auto-save timer.

        Parameters
        ----------
        clean_exit:
            If ``True`` (the default), the snapshot file is deleted to
            indicate a clean shutdown.  Pass ``False`` to preserve the
            snapshot (e.g. for crash-recovery testing).
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

        if clean_exit:
            try:
                if self._snapshot_path.exists():
                    self._snapshot_path.unlink()
            except OSError:
                pass

    def _schedule_timer(self) -> None:
        """Create and start a single-shot timer that will call :meth:`_tick`."""
        self._timer = threading.Timer(self.SAVE_INTERVAL, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        """Timer callback: save and re-schedule."""
        try:
            self.save_now()
        finally:
            with self._lock:
                # Re-schedule regardless of whether save_now succeeded.
                if self._timer is not None:
                    self._schedule_timer()

    # ------------------------------------------------------------------
    # Snapshot persistence
    # ------------------------------------------------------------------

    def save_now(self) -> None:
        """Serialize the current AppState and write it atomically to disk.

        On failure the exception is caught and logged as
        ``[SYSTEM]: Auto-save failed: {error}``.  The error is **not**
        re-raised so the periodic timer can continue on the next cycle.
        """
        try:
            data = self._state.to_json()
            payload = json.dumps(data, ensure_ascii=False, indent=2)
            atomic_write(self._snapshot_path, payload)
        except Exception as exc:  # noqa: BLE001
            logger.error("[SYSTEM]: Auto-save failed: %s", exc)
            print(f"[SYSTEM]: Auto-save failed: {exc}")

    # ------------------------------------------------------------------
    # Recovery detection
    # ------------------------------------------------------------------

    def check_recovery(self) -> dict | None:
        """Check for an existing snapshot file and return its contents.

        Returns
        -------
        dict or None
            Parsed snapshot data if the file exists and is valid JSON,
            otherwise ``None``.

        If the file contains invalid JSON it is deleted and a log message
        is emitted: ``[SYSTEM]: Recovery file corrupted, starting fresh``.
        """
        if not self._snapshot_path.exists():
            return None

        try:
            text = self._snapshot_path.read_text(encoding="utf-8")
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error("[SYSTEM]: Recovery file corrupted, starting fresh")
            print("[SYSTEM]: Recovery file corrupted, starting fresh")
            try:
                self._snapshot_path.unlink()
            except OSError:
                pass
            return None

    # ------------------------------------------------------------------
    # Recovery application
    # ------------------------------------------------------------------

    def apply_recovery(self, data: dict) -> AppState:
        """Restore an :class:`AppState` from previously saved recovery data.

        If the snapshot references a ``pdf_path`` that no longer exists on
        disk, the PDF fields are cleared and a warning is logged.

        Parameters
        ----------
        data:
            The dict returned by :meth:`check_recovery`.

        Returns
        -------
        AppState
            A new AppState instance with recovered field values.
        """
        state = AppState.from_json(data)

        if state.pdf_path and not Path(state.pdf_path).exists():
            logger.warning(
                "[SYSTEM]: PDF not found at %s, skipping PDF recovery",
                state.pdf_path,
            )
            print(f"[SYSTEM]: PDF not found at {state.pdf_path}, skipping PDF recovery")
            state.pdf_file = None
            state.pdf_path = None

        return state

    # ------------------------------------------------------------------
    # Recovery discard
    # ------------------------------------------------------------------

    def discard_recovery(self) -> None:
        """Delete the snapshot file if it exists."""
        try:
            if self._snapshot_path.exists():
                self._snapshot_path.unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Worker crash detection
    # ------------------------------------------------------------------

    def monitor_worker(self, process) -> None:
        """Start a daemon thread that polls a child process for unexpected termination.

        The thread checks ``process.exitcode`` every 2 seconds.  When the
        process terminates with a non-zero exit code, :meth:`_on_worker_crash`
        is called.  A normal exit (code 0) is silently ignored.

        The worker is **not** restarted automatically — the user must do
        this manually.

        Parameters
        ----------
        process:
            A :class:`multiprocessing.Process` (or compatible object) with
            ``pid``, ``exitcode``, and ``is_alive()`` attributes.
        """
        def _poll() -> None:
            while True:
                if not process.is_alive():
                    exit_code = process.exitcode
                    if exit_code is not None and exit_code != 0:
                        stderr = ""
                        if hasattr(process, "stderr") and process.stderr:
                            try:
                                stderr = process.stderr.read()
                            except Exception:
                                stderr = ""
                        self._on_worker_crash(process.pid, exit_code, stderr)
                    return
                time.sleep(2)

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()

    def _on_worker_crash(self, pid: int, exit_code: int, stderr: str) -> None:
        """Handle a detected worker crash.

        1. Log the PID and exit code.
        2. Log captured stderr (if any).
        3. Show a red error banner via the EventBus.
        4. Trigger an immediate snapshot via :meth:`save_now`.

        Parameters
        ----------
        pid:
            The OS process ID of the crashed worker.
        exit_code:
            The non-zero exit code returned by the worker.
        stderr:
            Any captured stderr output from the worker (may be empty).
        """
        logger.error(
            "[SYSTEM]: Child Process %s terminated with exit code %s",
            pid,
            exit_code,
        )
        print(f"[SYSTEM]: Child Process {pid} terminated with exit code {exit_code}")

        if stderr:
            logger.error("[SYSTEM]: Worker stderr: %s", stderr)
            print(f"[SYSTEM]: Worker stderr: {stderr}")

        try:
            self._bus.show_banner(
                "Inference Worker crashed. Data preserved. Check console for details.",
                is_error=True,
            )
        except Exception:
            pass

        self.save_now()
