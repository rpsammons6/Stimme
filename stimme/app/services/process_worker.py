"""Process worker and pool for isolated PDF/OCR extraction.

Spawns CPU-heavy extraction work in a separate OS process so the Flet UI
thread stays responsive.  Communication uses multiprocessing.Queue (results,
progress) and multiprocessing.Event (cancellation).
"""

from __future__ import annotations

from multiprocessing import Process, Queue, Event
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# ExtractionMessage — typed IPC envelope
# ---------------------------------------------------------------------------

@dataclass
class ExtractionMessage:
    """Message sent from a worker process back to the main process."""

    PROGRESS: str = field(default="progress", init=False, repr=False)
    RESULT: str = field(default="result", init=False, repr=False)
    ERROR: str = field(default="error", init=False, repr=False)

    msg_type: str
    data: dict


# Class-level constants so callers can reference without an instance.
ExtractionMessage.PROGRESS = "progress"
ExtractionMessage.RESULT = "result"
ExtractionMessage.ERROR = "error"


# ---------------------------------------------------------------------------
# _worker_target — top-level (picklable) function for the child process
# ---------------------------------------------------------------------------

def _worker_target(
    task_type: str,
    file_path: str,
    kwargs: dict,
    result_queue: Queue,
    cancel_event: Event,
) -> None:
    """Entry point executed inside the child process.

    Must remain a **top-level function** so it is picklable by the *spawn*
    start-method used on macOS / Windows.
    """
    try:
        if task_type == "pdf":
            from app.services.pdf_import import PDFImportService

            def progress_cb(msg, pct):
                result_queue.put(
                    ExtractionMessage(msg_type=ExtractionMessage.PROGRESS, data={"message": msg, "progress": pct})
                )

            def cancel_cb():
                return cancel_event.is_set()

            text = PDFImportService.extract_pdf_text(
                file_path,
                use_ocr=kwargs.get("use_ocr", True),
                progress_callback=progress_cb,
                cancel_callback=cancel_cb,
            )
            result_queue.put(
                ExtractionMessage(msg_type=ExtractionMessage.RESULT, data={"text": text})
            )

        elif task_type == "image":
            from app.services.pdf_import import PDFImportService

            def progress_cb(msg, pct):
                result_queue.put(
                    ExtractionMessage(msg_type=ExtractionMessage.PROGRESS, data={"message": msg, "progress": pct})
                )

            def cancel_cb():
                return cancel_event.is_set()

            text = PDFImportService.extract_image_text(
                file_path,
                progress_callback=progress_cb,
                cancel_callback=cancel_cb,
            )
            result_queue.put(
                ExtractionMessage(msg_type=ExtractionMessage.RESULT, data={"text": text})
            )

        else:
            result_queue.put(
                ExtractionMessage(msg_type=ExtractionMessage.ERROR, data={"error": f"Unknown task type: {task_type}"})
            )

    except Exception as e:
        result_queue.put(
            ExtractionMessage(msg_type=ExtractionMessage.ERROR, data={"error": str(e)})
        )


# ---------------------------------------------------------------------------
# WorkerPool — manages a single child process at a time
# ---------------------------------------------------------------------------

class WorkerPool:
    """Manages at most one extraction worker process at a time."""

    def __init__(self) -> None:
        self._active_process: Optional[Process] = None
        self._result_queue: Optional[Queue] = None
        self._cancel_event: Optional[Event] = None

    # -- public API ---------------------------------------------------------

    @property
    def is_busy(self) -> bool:
        """True when a worker process is alive."""
        return self._active_process is not None and self._active_process.is_alive()

    def submit(self, task_type: str, file_path: str, **kwargs) -> Queue:
        """Spawn a worker for *task_type* and return the result queue.

        Raises ``RuntimeError`` if a job is already running.
        """
        if self.is_busy:
            raise RuntimeError("An extraction job is already running")

        self._result_queue = Queue()
        self._cancel_event = Event()
        self._active_process = Process(
            target=_worker_target,
            args=(task_type, file_path, kwargs, self._result_queue, self._cancel_event),
            daemon=True,
        )
        self._active_process.start()
        return self._result_queue

    def cancel(self) -> None:
        """Request graceful cancellation, wait 2 s, then force-terminate."""
        if self._cancel_event:
            self._cancel_event.set()

        if self._active_process and self._active_process.is_alive():
            self._active_process.join(timeout=2.0)
            if self._active_process.is_alive():
                self._active_process.terminate()

        self._cleanup()

    # -- internal -----------------------------------------------------------

    def _cleanup(self) -> None:
        self._active_process = None
        self._result_queue = None
        self._cancel_event = None
