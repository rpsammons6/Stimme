"""Child process entry point for benchmark execution.

Runs the full Stimme benchmark suite in an isolated subprocess, streaming
all print() output back to the parent via multiprocessing.Queue as OUTPUT
messages.  When the child exits, the OS reclaims all RAM unconditionally.

CRITICAL: This module must NOT import app.shell, app.components, flet,
or any UI code. On Windows, the 'spawn' start method re-imports this
module in the child — any UI import would attempt to re-launch Flet.

Feature: subprocess-isolation
Requirements: 2.1, 2.2, 2.6, 5.8
"""

from __future__ import annotations

import io
import os
import sys
import traceback
from multiprocessing import Queue, Event
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path setup — add stimme root so benchmark imports resolve
# ---------------------------------------------------------------------------

_STIMME_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_STIMME_ROOT) not in sys.path:
    sys.path.insert(0, str(_STIMME_ROOT))

# benchmark.py lives in stimme/programs/tests/
_PROGRAMS_TESTS_DIR = str(_STIMME_ROOT / "programs" / "tests")
if _PROGRAMS_TESTS_DIR not in sys.path:
    sys.path.insert(0, _PROGRAMS_TESTS_DIR)


# ---------------------------------------------------------------------------
# Stdout capture — routes print() to the IPC queue as OUTPUT messages
# ---------------------------------------------------------------------------

class _QueueWriter(io.TextIOBase):
    """A text stream that routes each complete line to the result queue."""

    def __init__(self, result_queue: Queue):
        self._queue = result_queue
        self._buffer = ""

    def write(self, text: str) -> int:
        from app.services.process_worker import ExtractionMessage

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._queue.put(
                ExtractionMessage(
                    msg_type=ExtractionMessage.OUTPUT,
                    data={"line": line},
                )
            )
        return len(text)

    def flush(self) -> None:
        from app.services.process_worker import ExtractionMessage

        if self._buffer:
            self._queue.put(
                ExtractionMessage(
                    msg_type=ExtractionMessage.OUTPUT,
                    data={"line": self._buffer},
                )
            )
            self._buffer = ""

    @property
    def encoding(self):
        return "utf-8"

    def isatty(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Cancel check helper
# ---------------------------------------------------------------------------

def _check_cancel(cancel_event: Event) -> bool:
    """Return True if cancellation has been requested."""
    return cancel_event.is_set()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_benchmark(
    task_ctx: dict[str, Any],
    result_queue: Queue,
    cancel_event: Event,
) -> None:
    """Execute the full benchmark suite, streaming output via queue.

    This function is the target for multiprocessing.Process. It:
    1. Redirects stdout/stderr to capture all print() output
    2. Runs each benchmark stage, checking for cancellation between stages
    3. Sends a RESULT message on completion or ERROR on exception

    Args:
        task_ctx: Serializable configuration dict from SubprocessRunner.build_task_context().
        result_queue: multiprocessing.Queue for sending messages to parent.
        cancel_event: multiprocessing.Event signalling cancellation request.
    """
    from app.services.process_worker import ExtractionMessage

    # Redirect stdout and stderr to capture all print() output
    writer = _QueueWriter(result_queue)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = writer
    sys.stderr = writer

    try:
        import benchmark

        # Header
        print("╔══════════════════════════════════════════════════════════╗")
        print("║          STIMME — Benchmark Performance Report           ║")
        print("╚══════════════════════════════════════════════════════════╝")
        print(f"  PID: {os.getpid()} | RAM at start: {benchmark.ram_mb():.1f}MB")

        reports = []

        # --- Stage 1: Cold boot ---
        if _check_cancel(cancel_event):
            print("\n  ⚠️  Benchmark cancelled.")
            return
        r_boot, brain = benchmark.bench_cold_boot()
        r_boot.print()
        reports.append(r_boot)

        # --- Stage 2: ONNX model sizes ---
        if _check_cancel(cancel_event):
            print("\n  ⚠️  Benchmark cancelled.")
            return
        r = benchmark.bench_model_sizes()
        r.print()
        reports.append(r)

        # --- Stage 3: Import times ---
        if _check_cancel(cancel_event):
            print("\n  ⚠️  Benchmark cancelled.")
            return
        r = benchmark.bench_import_times()
        r.print()
        reports.append(r)

        # --- Stage 4: RAG retrieval ---
        if _check_cancel(cancel_event):
            print("\n  ⚠️  Benchmark cancelled.")
            return
        r = benchmark.bench_rag_retrieval(brain)
        r.print()
        reports.append(r)

        # --- Stage 5: Sentiment ---
        if _check_cancel(cancel_event):
            print("\n  ⚠️  Benchmark cancelled.")
            return
        r = benchmark.bench_sentiment(brain)
        r.print()
        reports.append(r)

        # --- Stage 6: Embedding ---
        if _check_cancel(cancel_event):
            print("\n  ⚠️  Benchmark cancelled.")
            return
        r = benchmark.bench_embedding(brain)
        r.print()
        reports.append(r)

        # --- Stage 7: Warm start / leak detection ---
        if _check_cancel(cancel_event):
            print("\n  ⚠️  Benchmark cancelled.")
            return
        r = benchmark.bench_warm_start(brain, iterations=5)
        r.print()
        reports.append(r)

        # --- Summary ---
        if _check_cancel(cancel_event):
            print("\n  ⚠️  Benchmark cancelled.")
            return
        benchmark.print_summary(reports)

        # Flush any remaining buffered output
        writer.flush()

        # Send RESULT message to signal completion
        result_queue.put(
            ExtractionMessage(
                msg_type=ExtractionMessage.RESULT,
                data={"text": "Benchmark complete"},
            )
        )

    except Exception as exc:
        # Flush any partial output before sending error
        writer.flush()

        tb_str = traceback.format_exc()
        result_queue.put(
            ExtractionMessage(
                msg_type=ExtractionMessage.ERROR,
                data={"error": str(exc), "traceback": tb_str},
            )
        )

    finally:
        # Restore original stdout/stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr
