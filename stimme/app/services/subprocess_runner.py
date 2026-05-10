"""Generic subprocess runner with drain-then-join lifecycle.

Spawns memory-intensive tasks (benchmark, OCR) in short-lived child processes
using the 'spawn' start method. When the child exits, the OS reclaims all RAM
unconditionally — the only true fix for CPython's pymalloc retention.

Communication uses multiprocessing.Queue (child → parent) and
multiprocessing.Event (parent → child cancellation signal).

Feature: subprocess-isolation
Requirements: 1.1, 1.2, 1.9, 4.2, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import logging
import multiprocessing
import queue
import signal
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from app.services.process_worker import ExtractionMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Windows NTSTATUS exit codes
# ---------------------------------------------------------------------------

_WINDOWS_EXIT_CODES: dict[int, str] = {
    -1073741819: "Access Violation (0xC0000005) — possible OOM or corrupted memory",
    -1073741571: "Stack Overflow (0xC00000FD)",
    -1073741515: "DLL Not Found (0xC0000135)",
    -1073740791: "Heap Corruption (0xC0000374)",
    -1073740940: "Fast Fail / OOM (0xC0000409)",
}


# ---------------------------------------------------------------------------
# TaskSlot — tracks one active subprocess
# ---------------------------------------------------------------------------

@dataclass
class TaskSlot:
    """Tracks one active subprocess and its associated resources."""

    category: str
    process: Any  # multiprocessing.Process (from spawn context)
    result_queue: Any  # multiprocessing.Queue (from spawn context)
    cancel_event: Any  # multiprocessing.Event (from spawn context)
    poll_thread: threading.Thread
    start_time: float
    pid: int = 0
    on_output: Callable[[str], Optional[Any]] | None = None
    on_done: Callable[[dict | None], None] | None = None
    on_error: Callable[[str], None] | None = None


# ---------------------------------------------------------------------------
# SubprocessRunner
# ---------------------------------------------------------------------------

class SubprocessRunner:
    """Generic subprocess runner with drain-then-join lifecycle.

    Manages one slot per task category. Uses the 'spawn' start method to
    ensure full address-space isolation (no inherited Flet controls, ONNX
    sessions, or memory-mapped files).
    """

    # Maximum pending output lines before backpressure (discard oldest)
    MAX_BUFFER: int = 50
    # Seconds to wait for graceful shutdown after cancel signal
    CANCEL_GRACE: float = 2.0
    # Seconds to drain queue after child exits
    DRAIN_TIMEOUT: float = 5.0
    # Seconds to wait for join after drain
    JOIN_TIMEOUT: float = 5.0

    def __init__(self, event_bus, config_service=None):
        """
        Args:
            event_bus: The app's EventBus instance for broadcasting changes.
            config_service: Optional ConfigurationService for building
                Task_Context dicts passed to child processes.
        """
        self._bus = event_bus
        self._config = config_service
        self._slots: dict[str, TaskSlot] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        category: str,
        worker_target: Callable,
        worker_args: tuple = (),
        worker_kwargs: dict | None = None,
        on_output: Callable[[str], Optional[Any]] | None = None,
        on_done: Callable[[dict | None], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Spawn a child process for the given category.

        The *worker_target* callable receives ``(result_queue, cancel_event)``
        appended to *worker_args*. It should communicate results back via the
        queue using ExtractionMessage instances.

        Raises:
            RuntimeError: If a task in this category is already running.
        """
        with self._lock:
            if category in self._slots:
                raise RuntimeError(
                    f"A task in category '{category}' is already running "
                    f"(PID {self._slots[category].pid})"
                )

            # Use spawn context for full isolation
            ctx = multiprocessing.get_context("spawn")
            result_queue = ctx.Queue()
            cancel_event = ctx.Event()

            # Build full args: user args + queue + event
            full_args = worker_args + (result_queue, cancel_event)

            process = ctx.Process(
                target=worker_target,
                args=full_args,
                kwargs=worker_kwargs or {},
                daemon=True,
            )
            process.start()

            pid = process.pid
            start_time = time.monotonic()

            # Create poll thread (daemon so it dies with parent)
            slot = TaskSlot(
                category=category,
                process=process,
                result_queue=result_queue,
                cancel_event=cancel_event,
                poll_thread=threading.Thread(target=lambda: None, daemon=True),
                start_time=start_time,
                pid=pid,
                on_output=on_output,
                on_done=on_done,
                on_error=on_error,
            )

            # Create the actual poll thread with the slot reference
            poll_thread = threading.Thread(
                target=self._poll_loop,
                args=(slot,),
                daemon=True,
                name=f"subprocess-poll-{category}",
            )
            slot.poll_thread = poll_thread
            self._slots[category] = slot

            poll_thread.start()

            logger.info(
                "SubprocessRunner: spawned child PID %d for category '%s' at %.2f",
                pid, category, start_time,
            )

    def cancel(self, category: str) -> None:
        """Signal cancellation, wait grace period, then force-terminate.

        Safe to call even if no task is running for the category.
        """
        with self._lock:
            slot = self._slots.get(category)
            if slot is None:
                return

        # Signal the child to stop gracefully
        try:
            slot.cancel_event.set()
        except Exception:
            pass

        # Wait for graceful shutdown
        if slot.process.is_alive():
            slot.process.join(timeout=self.CANCEL_GRACE)

        # Force-terminate if still alive
        if slot.process.is_alive():
            logger.warning(
                "SubprocessRunner: child PID %d did not exit within %.1fs grace, terminating",
                slot.pid, self.CANCEL_GRACE,
            )
            try:
                slot.process.terminate()
                slot.process.join(timeout=1.0)
            except Exception:
                pass

        # Drain remaining messages and clean up
        self._drain_and_join(slot)
        self._cleanup_slot(category)

    def is_running(self, category: str) -> bool:
        """True if a task in this category is currently active."""
        with self._lock:
            return category in self._slots

    def shutdown_all(self, timeout: float = 3.0) -> None:
        """Terminate all active children. Called on application exit.

        Args:
            timeout: Maximum seconds to wait for all children to terminate.
        """
        with self._lock:
            categories = list(self._slots.keys())

        if not categories:
            return

        logger.info("SubprocessRunner: shutting down %d active children", len(categories))

        # Signal all children to cancel
        for cat in categories:
            with self._lock:
                slot = self._slots.get(cat)
            if slot:
                try:
                    slot.cancel_event.set()
                except Exception:
                    pass

        # Wait for termination with shared timeout
        deadline = time.monotonic() + timeout
        for cat in categories:
            with self._lock:
                slot = self._slots.get(cat)
            if slot and slot.process.is_alive():
                remaining = max(0.1, deadline - time.monotonic())
                slot.process.join(timeout=remaining)
                if slot.process.is_alive():
                    try:
                        slot.process.terminate()
                        slot.process.join(timeout=0.5)
                    except Exception:
                        pass

        # Clean up all slots
        for cat in categories:
            self._cleanup_slot(cat)

        logger.info("SubprocessRunner: shutdown complete")

    def build_task_context(self) -> dict[str, Any]:
        """Extract serializable config subset for child processes.

        Returns a plain dict with only str/int/bool/list/None values,
        suitable for pickling across the process boundary.
        """
        if self._config is None:
            # Minimal context when no config service is available
            return {
                "stimme_dir": str(Path.home() / ".stimme"),
            }

        cfg = self._config
        return {
            "tesseract_path": cfg.get("tesseract_path", None),
            "poppler_path": cfg.get("poppler_path", None),
            "ocr_language": cfg.get("ocr_language", "deu"),
            "ocr_dpi": cfg.get("ocr_dpi_scale", 300),
            "stimme_dir": str(cfg._stimme_dir) if hasattr(cfg, "_stimme_dir") else cfg.get("stimme_dir", str(Path.home() / ".stimme")),
            "export_directory": cfg.get("export_directory", str(Path.home() / "Documents" / "Stimme Exports")),
            "scholar_mode": cfg.get("scholar_mode", False),
            "thematic_focus": cfg.get("thematic_focus", ""),
            "llm_backend": cfg.get("llm_backend", "cloud"),
            "local_llm_endpoint": cfg.get("local_llm_endpoint", "http://localhost:11434"),
            "local_llm_model": cfg.get("local_llm_model", "llama3"),
            "active_datasets": cfg.get("active_datasets", ["idioms", "corpus"]),
        }

    # ------------------------------------------------------------------
    # Internal — poll loop
    # ------------------------------------------------------------------

    def _poll_loop(self, slot: TaskSlot) -> None:
        """Daemon thread: poll queue, forward output, handle lifecycle.

        Runs until the child exits and the queue is drained, or until
        a 30-second inactivity timeout is reached.
        """
        output_buffer: deque[str] = deque(maxlen=self.MAX_BUFFER)
        last_activity = time.monotonic()
        INACTIVITY_TIMEOUT = 30.0

        while True:
            try:
                msg = slot.result_queue.get(timeout=0.2)
                last_activity = time.monotonic()
                self._route_message(slot, msg, output_buffer)
            except queue.Empty:
                pass
            except (EOFError, OSError):
                # Queue broken — child likely crashed
                break

            # Check inactivity timeout
            if time.monotonic() - last_activity > INACTIVITY_TIMEOUT:
                logger.warning(
                    "SubprocessRunner: child PID %d inactive for %.0fs, timing out",
                    slot.pid, INACTIVITY_TIMEOUT,
                )
                if slot.on_error:
                    slot.on_error(
                        f"Worker timed out (no activity for {INACTIVITY_TIMEOUT:.0f}s)"
                    )
                # Force-terminate the child
                if slot.process.is_alive():
                    try:
                        slot.process.terminate()
                    except Exception:
                        pass
                break

            # Check if child has exited
            if not slot.process.is_alive():
                # Drain remaining messages then clean up
                exit_code = self._drain_and_join(slot)
                error_desc = self._interpret_exit_code(exit_code)

                # If child exited with error and no ERROR message was received
                if error_desc and slot.on_error:
                    slot.on_error(error_desc)
                elif not error_desc and exit_code == 0:
                    # Normal exit without explicit RESULT — call on_done
                    # (on_done may have already been called via RESULT message)
                    pass

                self._cleanup_slot(slot.category)
                return

        # If we broke out of the loop (timeout or broken queue)
        self._drain_and_join(slot)
        self._cleanup_slot(slot.category)

    def _route_message(
        self,
        slot: TaskSlot,
        msg: ExtractionMessage,
        output_buffer: deque[str],
    ) -> None:
        """Route a single message to the appropriate callback."""
        if msg.msg_type == ExtractionMessage.OUTPUT:
            line = msg.data.get("line", "")
            # Buffer cap: discard oldest if over limit
            if len(output_buffer) >= self.MAX_BUFFER:
                output_buffer.popleft()
            output_buffer.append(line)

            if slot.on_output:
                result = slot.on_output(line)
                # If callback returns None and LogTab is not visible,
                # discard — the callback signals visibility via return value
                if result is None:
                    # Discard is implicit — line was already in buffer
                    # but we still delivered it. The "discard" semantic
                    # means we don't accumulate unboundedly.
                    pass

        elif msg.msg_type == ExtractionMessage.PROGRESS:
            # Format progress as a string and route to on_output
            message = msg.data.get("message", "")
            progress = msg.data.get("progress")
            if progress is not None:
                formatted = f"[{progress:.0%}] {message}" if isinstance(progress, float) else f"[{progress}%] {message}"
            else:
                formatted = message

            if len(output_buffer) >= self.MAX_BUFFER:
                output_buffer.popleft()
            output_buffer.append(formatted)

            if slot.on_output:
                slot.on_output(formatted)

        elif msg.msg_type == ExtractionMessage.RESULT:
            if slot.on_done:
                slot.on_done(msg.data)

        elif msg.msg_type == ExtractionMessage.ERROR:
            error_text = msg.data.get("error", "Unknown error")
            traceback_text = msg.data.get("traceback")
            full_error = error_text
            if traceback_text:
                full_error = f"{error_text}\n{traceback_text}"
            if slot.on_error:
                slot.on_error(full_error)

    # ------------------------------------------------------------------
    # Internal — drain and join
    # ------------------------------------------------------------------

    def _drain_and_join(self, slot: TaskSlot) -> int:
        """Drain remaining queue messages, join process, return exit code.

        The drain-before-join pattern prevents Queue feeder-thread deadlocks
        that occur when a child puts data into a Queue and exits before the
        parent has consumed it.

        Returns:
            The child process exit code (0 = success, positive = Python
            exception, negative = signal/NTSTATUS).
        """
        # Phase 1: Drain queue with bounded timeout
        deadline = time.monotonic() + self.DRAIN_TIMEOUT
        while time.monotonic() < deadline:
            try:
                msg = slot.result_queue.get(timeout=0.1)
                # Route any remaining messages
                self._route_message(slot, msg, deque(maxlen=self.MAX_BUFFER))
            except queue.Empty:
                if not slot.process.is_alive():
                    break  # Child dead + queue empty = done
            except (EOFError, OSError):
                break  # Queue broken

        # Phase 2: Join with timeout
        try:
            slot.process.join(timeout=self.JOIN_TIMEOUT)
        except Exception:
            pass

        # Phase 3: Force kill if still alive (shouldn't happen normally)
        if slot.process.is_alive():
            logger.warning(
                "SubprocessRunner: child PID %d still alive after join timeout, terminating",
                slot.pid,
            )
            try:
                slot.process.terminate()
                slot.process.join(timeout=1.0)
            except Exception:
                pass

        return slot.process.exitcode if slot.process.exitcode is not None else -1

    # ------------------------------------------------------------------
    # Internal — exit code interpretation
    # ------------------------------------------------------------------

    def _interpret_exit_code(self, exitcode: int | None) -> str:
        """Map OS exit codes to human-readable error descriptions.

        Returns:
            Empty string for exit code 0 (success).
            Descriptive string for all other codes.
        """
        if exitcode is None:
            return "Process did not terminate (still running?)"
        if exitcode == 0:
            return ""
        if exitcode > 0:
            return f"Process exited with code {exitcode} (Python exception)"

        # Negative codes: signal on Unix, or Windows NTSTATUS
        if sys.platform == "win32":
            desc = _WINDOWS_EXIT_CODES.get(exitcode)
            if desc:
                return f"Hardware Exhaustion: {desc}"
            return f"OS terminated process (exit code {exitcode:#010x})"
        else:
            # Unix: negative exit code = killed by signal
            sig_num = -exitcode
            try:
                sig_name = signal.Signals(sig_num).name
            except (ValueError, AttributeError):
                sig_name = str(sig_num)
            return f"Process killed by signal {sig_name} ({sig_num})"

    # ------------------------------------------------------------------
    # Internal — cleanup
    # ------------------------------------------------------------------

    def _cleanup_slot(self, category: str) -> None:
        """Release all references for a completed task.

        Removes the slot from _slots, releasing Process, Queue, and Event
        objects so the OS can reclaim all associated resources.
        """
        with self._lock:
            slot = self._slots.pop(category, None)

        if slot is None:
            return

        end_time = time.monotonic()
        exit_code = slot.process.exitcode if slot.process.exitcode is not None else -1
        duration = end_time - slot.start_time

        logger.info(
            "SubprocessRunner: child PID %d (category='%s') finished — "
            "exit_code=%d, duration=%.1fs",
            slot.pid, category, exit_code, duration,
        )

        # Explicitly release references
        slot.process = None  # type: ignore[assignment]
        slot.result_queue = None  # type: ignore[assignment]
        slot.cancel_event = None  # type: ignore[assignment]
        slot.on_output = None
        slot.on_done = None
        slot.on_error = None
