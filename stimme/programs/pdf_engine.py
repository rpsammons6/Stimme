"""Unified PDF engine built on PyMuPDF.

Handles page rendering (JPEG for display, PNG for OCR), digital text
extraction, bookmark/TOC retrieval, and deterministic memory release.
"""

import base64

import fitz  # PyMuPDF


class ScholarlyPDFEngine:
    """Unified PDF engine built on PyMuPDF.

    Handles page rendering (JPEG/PNG), digital text extraction,
    and OCR fallback via Tesseract.
    """

    def __init__(self, path: str):
        """Open a PDF document.

        Args:
            path: Filesystem path to the PDF file.
        """
        self.doc: fitz.Document = fitz.open(path)
        self.total_pages: int = len(self.doc)
        self.current_page: int = 0

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    def extract_text(self, page_num: int) -> str:
        """Extract embedded digital text from a page.

        Args:
            page_num: 0-based page index.

        Returns:
            Extracted text string (empty if page is scanned).
        """
        page = self.doc.load_page(page_num)
        return page.get_text()

    def extract_text_dict(self, page_num: int) -> dict:
        """Extract structured text with font metadata from a page.

        Uses ``page.get_text("dict")`` for font-size heading detection.

        Args:
            page_num: 0-based page index.

        Returns:
            PyMuPDF text dict with blocks/lines/spans.
        """
        page = self.doc.load_page(page_num)
        return page.get_text("dict")

    # ------------------------------------------------------------------
    # TOC / bookmarks
    # ------------------------------------------------------------------

    def get_toc(self) -> list[list]:
        """Return the PDF table of contents (bookmarks).

        Returns:
            List of ``[level, title, page_num]`` entries from
            ``doc.get_toc()``.
        """
        return self.doc.get_toc()

    # ------------------------------------------------------------------
    # Page rendering
    # ------------------------------------------------------------------

    def render_page_jpeg(self, page_num: int, zoom: float = 2.0) -> str:
        """Render a page as a JPEG-encoded base64 string for display.

        Args:
            page_num: 0-based page index.
            zoom: Zoom factor (2.0 = 144 DPI on a 72-DPI base).

        Returns:
            Base64-encoded JPEG string.
        """
        page = self.doc.load_page(page_num)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        jpeg_bytes = pix.tobytes("jpeg")
        pix = None  # deterministic release
        return base64.b64encode(jpeg_bytes).decode("ascii")

    def render_page_png(self, page_num: int, dpi: int | None = None) -> bytes:
        """Render a page as PNG bytes for OCR.

        If *dpi* is ``None`` the engine selects a value in [150, 200]
        dynamically based on page dimensions.

        Args:
            page_num: 0-based page index.
            dpi: Target DPI (150–200 range).  ``None`` for auto-select.

        Returns:
            Raw PNG bytes.
        """
        page = self.doc.load_page(page_num)

        if dpi is None:
            dpi = self._select_ocr_dpi(page)

        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        pix = None  # deterministic release
        return png_bytes

    # ------------------------------------------------------------------
    # DPI selection
    # ------------------------------------------------------------------

    @staticmethod
    def _select_ocr_dpi(page: fitz.Page) -> int:
        """Choose an OCR DPI in [150, 200] based on page dimensions.

        Larger pages get a lower DPI to keep the resulting pixmap
        manageable; smaller pages get a higher DPI for better OCR
        accuracy.

        Args:
            page: A loaded ``fitz.Page``.

        Returns:
            An integer DPI in the range [150, 200].
        """
        rect = page.rect
        # Use the longer edge as the size metric
        max_dim = max(rect.width, rect.height)

        # Typical A4 long edge at 72 DPI ≈ 842 points.
        # Pages larger than ~1200 pts get the minimum DPI; pages
        # smaller than ~600 pts get the maximum.
        if max_dim >= 1200:
            return 150
        if max_dim <= 600:
            return 200

        # Linear interpolation between 200 and 150 over [600, 1200]
        ratio = (max_dim - 600) / 600.0
        return int(round(200 - ratio * 50))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the document and release the file handle."""
        if self.doc:
            self.doc.close()
