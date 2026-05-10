"""Child process entry point for OCR/PDF text extraction.

Runs PDF or image OCR extraction in an isolated subprocess, streaming
progress messages back to the parent via multiprocessing.Queue. When the
child exits, the OS reclaims all RAM unconditionally — including the
~35MB-per-page pixel buffers and PyMuPDF document objects.

CRITICAL: This module must NOT import app.shell, app.components, flet,
or any UI code. On Windows, the 'spawn' start method re-imports this
module in the child — any UI import would attempt to re-launch Flet.

Feature: subprocess-isolation
Requirements: 3.1, 3.2, 3.3, 3.6, 5.6, 5.8
"""

from __future__ import annotations

import os
import sys
import traceback
from multiprocessing import Queue, Event
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path setup — add stimme root so OCR/PDF imports resolve
# ---------------------------------------------------------------------------

_STIMME_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_STIMME_ROOT) not in sys.path:
    sys.path.insert(0, str(_STIMME_ROOT))

# ocr_engine.py lives in stimme/programs/
_PROGRAMS_DIR = str(_STIMME_ROOT / "programs")
if _PROGRAMS_DIR not in sys.path:
    sys.path.insert(0, _PROGRAMS_DIR)


# ---------------------------------------------------------------------------
# Path configuration — apply task_ctx settings before any OCR work
# ---------------------------------------------------------------------------

def _apply_task_context(task_ctx: dict[str, Any]) -> str:
    """Apply Tesseract/Poppler paths and OCR settings from task_ctx.

    Returns the OCR language to use.
    """
    import pytesseract

    # Set Tesseract path if provided
    tesseract_path = task_ctx.get("tesseract_path")
    if tesseract_path and os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    # Poppler path is passed to pdf2image at call time, not set globally
    # We just validate it exists if provided
    poppler_path = task_ctx.get("poppler_path")
    if poppler_path and not os.path.exists(poppler_path):
        poppler_path = None  # Fall back to system default

    # Return language setting
    return task_ctx.get("ocr_language", "deu")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_extraction(
    task_type: str,
    file_path: str,
    task_ctx: dict[str, Any],
    result_queue: Queue,
    cancel_event: Event,
) -> None:
    """Execute PDF or image text extraction, streaming progress via queue.

    This function is the target for multiprocessing.Process. It:
    1. Applies task_ctx settings (Tesseract path, Poppler path, language, DPI)
    2. Routes progress callbacks to the queue as PROGRESS messages
    3. Checks cancel_event between pages for early exit
    4. Sends a RESULT message on completion or ERROR on exception

    Args:
        task_type: Either "pdf" or "image".
        file_path: Absolute path to the file to extract text from.
        task_ctx: Serializable configuration dict from SubprocessRunner.build_task_context().
        result_queue: multiprocessing.Queue for sending messages to parent.
        cancel_event: multiprocessing.Event signalling cancellation request.
    """
    from app.services.process_worker import ExtractionMessage

    try:
        # Apply configuration from task context
        language = _apply_task_context(task_ctx)
        poppler_path = task_ctx.get("poppler_path")
        ocr_dpi = task_ctx.get("ocr_dpi", 300)

        # Validate poppler_path exists
        if poppler_path and not os.path.exists(poppler_path):
            poppler_path = None

        # Define progress callback that routes to queue
        def progress_cb(message: str, progress: float) -> None:
            result_queue.put(
                ExtractionMessage(
                    msg_type=ExtractionMessage.PROGRESS,
                    data={"message": message, "progress": progress},
                )
            )

        # Define cancel callback that checks the event
        def cancel_cb() -> bool:
            return cancel_event.is_set()

        # Route to appropriate extraction method
        if task_type == "pdf":
            text = _extract_pdf(
                file_path=file_path,
                language=language,
                poppler_path=poppler_path,
                ocr_dpi=ocr_dpi,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
        elif task_type == "image":
            text = _extract_image(
                file_path=file_path,
                language=language,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
        else:
            result_queue.put(
                ExtractionMessage(
                    msg_type=ExtractionMessage.ERROR,
                    data={
                        "error": f"Unknown task type: {task_type}",
                        "traceback": None,
                    },
                )
            )
            return

        # Send result
        result_queue.put(
            ExtractionMessage(
                msg_type=ExtractionMessage.RESULT,
                data={"text": text},
            )
        )

    except Exception as exc:
        tb_str = traceback.format_exc()
        result_queue.put(
            ExtractionMessage(
                msg_type=ExtractionMessage.ERROR,
                data={"error": str(exc), "traceback": tb_str},
            )
        )


# ---------------------------------------------------------------------------
# PDF extraction — digital text first, OCR fallback for scanned pages
# ---------------------------------------------------------------------------

def _extract_pdf(
    file_path: str,
    language: str,
    poppler_path: str | None,
    ocr_dpi: int,
    progress_cb,
    cancel_cb,
) -> str:
    """Extract text from a PDF file.

    Strategy:
    1. Try digital text extraction with PyPDF2 first (fast, no OCR needed)
    2. If digital text is insufficient (<100 chars), fall back to OCR via
       pdf2image + Tesseract
    """
    import PyPDF2

    if cancel_cb():
        raise Exception("PDF processing cancelled")

    progress_cb("Starting PDF text extraction...", 5)

    # --- Phase 1: Digital text extraction ---
    try:
        text_parts = []
        with open(file_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)

            if pdf_reader.is_encrypted:
                try:
                    pdf_reader.decrypt("")
                except Exception:
                    raise Exception(
                        "This PDF is password-protected. "
                        "Please provide an unencrypted version."
                    )

            num_pages = len(pdf_reader.pages)
            if num_pages == 0:
                raise Exception("This PDF has no pages.")

            progress_cb("Attempting digital text extraction...", 10)

            for i, page in enumerate(pdf_reader.pages):
                if cancel_cb():
                    raise Exception("PDF processing cancelled")

                text = page.extract_text()
                if text and text.strip():
                    text_parts.append(text)

                # Progress: 10% to 30% for digital extraction
                pct = 10 + (i + 1) / num_pages * 20
                progress_cb(
                    f"Processing page {i + 1} of {num_pages}...", pct
                )

        digital_text = "\n\n".join(text_parts).strip()

        # If we got substantial digital text, return it
        if len(digital_text) > 100:
            progress_cb("Digital extraction complete!", 100)
            return digital_text

    except Exception as e:
        err_str = str(e)
        # Re-raise user-facing errors
        if "password-protected" in err_str.lower() or "no pages" in err_str.lower():
            raise
        if "cancelled" in err_str.lower():
            raise
        # Otherwise fall through to OCR

    # --- Phase 2: OCR fallback ---
    if cancel_cb():
        raise Exception("PDF processing cancelled")

    progress_cb("Digital extraction insufficient, starting OCR...", 35)
    return _ocr_pdf(file_path, language, poppler_path, ocr_dpi, progress_cb, cancel_cb)


def _ocr_pdf(
    file_path: str,
    language: str,
    poppler_path: str | None,
    ocr_dpi: int,
    progress_cb,
    cancel_cb,
) -> str:
    """OCR a PDF by converting pages to images and running Tesseract."""
    import pytesseract
    from pdf2image import convert_from_path

    if cancel_cb():
        raise Exception("OCR processing cancelled")

    progress_cb("Converting PDF to images...", 40)

    # Convert PDF pages to images
    convert_kwargs = {"dpi": ocr_dpi}
    if poppler_path:
        convert_kwargs["poppler_path"] = poppler_path

    images = convert_from_path(file_path, **convert_kwargs)

    if cancel_cb():
        raise Exception("OCR processing cancelled")

    total_pages = len(images)
    text_parts = []

    for i, image in enumerate(images):
        if cancel_cb():
            raise Exception("OCR processing cancelled")

        # Progress: 45% to 95% for OCR processing
        pct = 45 + (i / total_pages) * 50
        progress_cb(f"OCR page {i + 1} of {total_pages}...", pct)

        # Use appropriate language settings
        if language == "deu":
            try:
                text = pytesseract.image_to_string(image, lang="deu_frak+deu")
            except Exception:
                text = pytesseract.image_to_string(image, lang="deu")
        else:
            text = pytesseract.image_to_string(image, lang=language)

        if text.strip():
            text_parts.append(text.strip())

    if cancel_cb():
        raise Exception("OCR processing cancelled")

    result = "\n\n".join(text_parts)
    progress_cb("OCR processing complete!", 100)
    return result


# ---------------------------------------------------------------------------
# Image extraction — direct Tesseract OCR
# ---------------------------------------------------------------------------

def _extract_image(
    file_path: str,
    language: str,
    progress_cb,
    cancel_cb,
) -> str:
    """Extract text from an image file using Tesseract OCR."""
    import pytesseract
    from PIL import Image

    if cancel_cb():
        raise Exception("Image processing cancelled")

    progress_cb("Processing image with OCR...", 20)

    image = Image.open(file_path)

    # Handle multi-frame images (e.g. multi-page TIFF) — only first frame
    if hasattr(image, "n_frames") and image.n_frames > 1:
        pass  # Process first frame only

    # Convert RGBA/P to RGB (transparency causes OCR issues)
    if image.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(
            image, mask=image.split()[-1] if "A" in image.mode else None
        )
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    if cancel_cb():
        raise Exception("Image processing cancelled")

    progress_cb("Running Tesseract OCR...", 50)

    # Use appropriate language settings
    if language == "deu":
        try:
            text = pytesseract.image_to_string(image, lang="deu_frak+deu")
        except Exception:
            text = pytesseract.image_to_string(image, lang="deu")
    else:
        text = pytesseract.image_to_string(image, lang=language)

    progress_cb("Image processing complete!", 100)
    return text.strip()
