"""Native bitmap-paging PDF viewer using ft.Image + ScholarlyPDFEngine.

Replaces the broken WebView_PDF_Viewer with a single ft.Image viewport,
a 3-page sliding window cache, background thread rendering, and a
minimalist [<] Page X of Y [>] navigation overlay.
"""

import gc
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import flet as ft

from app.theme import Colors
from programs.pdf_engine import ScholarlyPDFEngine


def _log(msg: str) -> None:
    print(f"[PDFViewer] {msg}")


class PDFViewer:
    """Native bitmap-paging PDF viewer using ft.Image + ScholarlyPDFEngine.

    Public interface matches the old WebView_PDF_Viewer for drop-in
    replacement in CenterPanel, ParallelView, and AppShell.
    """

    def __init__(self, page: ft.Page):
        self._page: ft.Page = page
        self._engine: Optional[ScholarlyPDFEngine] = None
        self._pdf_name: Optional[str] = None
        self._cache: dict[int, str] = {}  # page_num -> base64 JPEG
        self._current_page: int = 0
        self._total_pages: int = 0
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

        # UI controls — initialised in build()
        self._image: Optional[ft.Image] = None
        self._page_label: Optional[ft.Text] = None
        self._prev_btn: Optional[ft.IconButton] = None
        self._next_btn: Optional[ft.IconButton] = None
        self._error_container: Optional[ft.Container] = None
        self._nav_row: Optional[ft.Row] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def pdf_name(self) -> Optional[str]:
        """The display name of the currently loaded PDF."""
        return self._pdf_name

    @property
    def is_loaded(self) -> bool:
        """True if a PDF is currently loaded and the engine is active."""
        return self._engine is not None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_pdf(self, pdf_path: str, pdf_name: str) -> None:
        """Open a PDF, render the first page, and populate the cache.

        If the file does not exist an error container is shown instead
        of crashing.

        Args:
            pdf_path: Filesystem path to the PDF file.
            pdf_name: Display name for the PDF.
        """
        self._pdf_name = pdf_name

        if not os.path.isfile(pdf_path):
            _log(f"File not found: {pdf_path}")
            self._engine = None
            self._show_error(
                "PDF file not found",
                f"Could not find: {pdf_path}",
            )
            return

        try:
            # Close any previously loaded document first
            if self._engine is not None:
                self._engine.close()
                self._engine = None

            self._engine = ScholarlyPDFEngine(pdf_path)
            self._total_pages = self._engine.total_pages
            self._current_page = 0
            self._cache.clear()

            # Render first page synchronously so the user sees it immediately
            first_b64 = self._engine.render_page_jpeg(0)
            self._cache[0] = first_b64

            # Pre-render page 1 if it exists
            if self._total_pages > 1:
                second_b64 = self._engine.render_page_jpeg(1)
                self._cache[1] = second_b64

            # Update viewport
            if self._image is not None:
                self._image.src_base64 = first_b64
                self._image.visible = True
            if self._error_container is not None:
                self._error_container.visible = False
            if self._nav_row is not None:
                self._nav_row.visible = True

            self._update_nav_state()
            _log(f"Loaded: {pdf_name} ({self._total_pages} pages)")

        except Exception as exc:
            _log(f"Error loading PDF: {exc}")
            self._engine = None
            self._show_error(
                "Failed to open PDF",
                str(exc),
            )

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> ft.Control:
        """Return an ft.Stack with the viewport image and navigation overlay.

        The viewport is a single ft.Image that fills the container.
        Scrollbars are hidden — only the navigation overlay provides
        page control.
        """
        self._image = ft.Image(
            src_base64="",
            fit=ft.ImageFit.CONTAIN,
            expand=True,
            visible=False,
        )

        self._error_container = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.ERROR, size=48, color=Colors.DESTRUCTIVE),
                    ft.Text(
                        "No PDF loaded",
                        size=16,
                        color=Colors.DESTRUCTIVE,
                        weight="bold",
                    ),
                    ft.Text(
                        "Open a PDF to view it here.",
                        size=14,
                        color=Colors.INK_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.alignment.center,
            expand=True,
            visible=True,
        )

        self._prev_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            icon_color=Colors.FOREGROUND,
            icon_size=24,
            disabled=True,
            on_click=lambda _: self._navigate(self._current_page - 1),
        )

        self._next_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            icon_color=Colors.FOREGROUND,
            icon_size=24,
            disabled=True,
            on_click=lambda _: self._navigate(self._current_page + 1),
        )

        self._page_label = ft.Text(
            "Page 0 of 0",
            size=13,
            color=Colors.FOREGROUND,
        )

        self._nav_row = ft.Row(
            controls=[self._prev_btn, self._page_label, self._next_btn],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
            visible=False,
        )

        nav_overlay = ft.Container(
            content=self._nav_row,
            alignment=ft.alignment.bottom_center,
            padding=ft.padding.only(bottom=8),
        )

        stack = ft.Stack(
            controls=[
                ft.Container(
                    content=self._image,
                    expand=True,
                    # Hide scrollbars — navigation overlay is the only control
                ),
                self._error_container,
                nav_overlay,
            ],
            expand=True,
        )

        # If a PDF is already loaded (e.g. rebuild_tabs re-called build()),
        # restore the viewport so the user doesn't see "No PDF loaded".
        if self._engine is not None and self._cache.get(self._current_page):
            self._image.src_base64 = self._cache[self._current_page]
            self._image.visible = True
            self._error_container.visible = False
            self._nav_row.visible = True
            self._update_nav_state()

        return stack

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, page_num: int) -> None:
        """Navigate to *page_num*, serving from cache when possible.

        Updates the viewport image, evicts stale cache entries, and
        pre-renders adjacent pages in the background.
        """
        if self._engine is None:
            return

        # Clamp to valid range
        page_num = max(0, min(page_num, self._total_pages - 1))

        # Serve from cache or render on miss
        if page_num in self._cache:
            b64 = self._cache[page_num]
        else:
            b64 = self._render_and_cache(page_num)

        self._current_page = page_num

        # Update viewport
        if self._image is not None:
            self._image.src_base64 = b64
            try:
                self._page.update()
            except Exception:
                pass

        # Evict stale entries and pre-render neighbours
        self._evict_cache(page_num)
        gc.collect()
        self._pre_render_adjacent(page_num)
        self._update_nav_state()

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _render_and_cache(self, page_num: int) -> str:
        """Render a page via the engine and store the result in the cache.

        Returns:
            Base64-encoded JPEG string for the rendered page.
        """
        try:
            b64 = self._engine.render_page_jpeg(page_num)
            self._cache[page_num] = b64
            return b64
        except Exception as exc:
            _log(f"Render error for page {page_num}: {exc}")
            return ""

    def _evict_cache(self, current: int) -> None:
        """Remove cache entries outside the 3-page window around *current*.

        Evicted values are set to ``None`` before deletion to help the
        garbage collector reclaim the base64 strings promptly.
        """
        keep = {current - 1, current, current + 1} & set(
            range(self._total_pages)
        )
        for key in list(self._cache.keys()):
            if key not in keep:
                self._cache[key] = None  # release the string
                del self._cache[key]

    def _pre_render_adjacent(self, current: int) -> None:
        """Submit background tasks to render pages adjacent to *current*.

        Only pages that are within bounds and not already cached are
        submitted.
        """
        for adj in (current - 1, current + 1):
            if 0 <= adj < self._total_pages and adj not in self._cache:
                try:
                    self._executor.submit(self._render_and_cache, adj)
                except RuntimeError:
                    # Executor shut down — ignore
                    pass

    # ------------------------------------------------------------------
    # UI state helpers
    # ------------------------------------------------------------------

    def _update_nav_state(self) -> None:
        """Synchronise the navigation overlay with the current page."""
        if self._page_label is not None:
            self._page_label.value = (
                f"Page {self._current_page + 1} of {self._total_pages}"
            )
        if self._prev_btn is not None:
            self._prev_btn.disabled = self._current_page == 0
        if self._next_btn is not None:
            self._next_btn.disabled = (
                self._current_page >= self._total_pages - 1
            )

    def _show_error(self, title: str, detail: str) -> None:
        """Display an error message in the error container."""
        if self._error_container is not None:
            self._error_container.content = ft.Column(
                controls=[
                    ft.Icon(ft.Icons.ERROR, size=48, color=Colors.DESTRUCTIVE),
                    ft.Text(
                        title,
                        size=16,
                        color=Colors.DESTRUCTIVE,
                        weight="bold",
                    ),
                    ft.Text(
                        detail,
                        size=14,
                        color=Colors.INK_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            )
            self._error_container.visible = True
        if self._image is not None:
            self._image.visible = False
        if self._nav_row is not None:
            self._nav_row.visible = False

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Close the engine, clear the cache, null all references.

        Calls ``gc.collect()`` to reclaim unreferenced objects.
        """
        _log("cleanup called")
        if self._engine is not None:
            try:
                self._engine.close()
            except Exception:
                pass
            self._engine = None

        # Release all cached base64 strings
        for key in list(self._cache.keys()):
            self._cache[key] = None
        self._cache.clear()

        # Shut down the background executor so worker threads release
        # indirect references (submitted callables) to this PDFViewer.
        if self._executor is not None:
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                pass
            self._executor = None

        self._pdf_name = None
        self._current_page = 0
        self._total_pages = 0
        self._image = None
        self._page_label = None
        self._prev_btn = None
        self._next_btn = None
        self._error_container = None
        self._nav_row = None
        self._page = None

        gc.collect()

# Backward-compatible alias — other modules still import the old name.
WebView_PDF_Viewer = PDFViewer
