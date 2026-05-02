import flet as ft
import traceback
from app.theme import Colors, Fonts
from app.services.history import HistoryManager
from datetime import datetime


def _log(msg):
    print(f"[HistoryView] {msg}")


def format_counter(start: int, visible: int, total: int) -> str:
    """Format the pagination counter label.

    Returns a string like "Showing 1–20 of 543".
    Extracted as a module-level function so it can be tested independently.
    """
    return f"Showing {start}\u2013{visible} of {total}"


class HistoryView:
    """History view dialog showing past translations.
    
    Design: No internal flags. Every show() call is a clean slate.
    Closing always sets page.dialog = None so nothing is left dangling.
    Pagination: renders PAGE_SIZE entries at a time, loading more on scroll.
    """

    PAGE_SIZE = 10

    def __init__(self, page: ft.Page, actions: dict = None):
        self.page = page
        self.history_manager = HistoryManager()
        self.actions = actions or {}
        # Pagination state
        self._offset = 0
        self._all_loaded = False
        self._history_controls = []
        self._list_view = None
        self._counter_text = None

    def show(self):
        """Show the history dialog with fresh content."""
        try:
            _log("show() called")

            # Always start clean — close whatever dialog is open
            self._force_close_dialog()

            # Reset pagination state so each open is a clean slate
            self._offset = 0
            self._all_loaded = False
            self._history_controls = []
            self._list_view = None
            self._counter_text = None

            # Reload from disk
            self.history_manager.load_history()

            # Build and show
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    "Translation History",
                    size=24,
                    font_family=Fonts.HEADER,
                    weight=ft.FontWeight.W_600,
                    color=Colors.FOREGROUND,
                ),
                content=ft.Container(
                    content=self._build_history_content(),
                    width=700,
                    height=500,
                    padding=ft.padding.all(20),
                ),
                actions=[
                    ft.Row(
                        controls=[
                            ft.TextButton(
                                content=ft.Text("Clear History", font_family=Fonts.FRAKTUR),
                                on_click=lambda e: self._on_clear_history(),
                                style=ft.ButtonStyle(color=Colors.DESTRUCTIVE),
                            ),
                            ft.Container(expand=True),
                            ft.TextButton(content=ft.Text("Close", font_family=Fonts.FRAKTUR), on_click=lambda e: self._force_close_dialog()),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    )
                ],
                bgcolor=Colors.SURFACE,
            )

            self.page.dialog = dialog
            dialog.open = True
            self.page.update()
        except Exception:
            _log(f"ERROR in show:\n{traceback.format_exc()}")

    def _force_close_dialog(self):
        """Unconditionally close whatever dialog is on the page."""
        try:
            if self.page.dialog:
                self.page.dialog.open = False
            self.page.dialog = None
            self.page.update()
        except Exception:
            pass

    def _build_history_content(self):
        """Build the history list content with paginated rendering."""
        entries, total = self.history_manager.get_history_slice(0, self.PAGE_SIZE)

        if total == 0:
            return ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Image(
                            src="/empty-history-icon.webp",
                            width=128,
                            height=128,
                            fit=ft.ImageFit.CONTAIN,
                            opacity=0.6,
                        ),
                        alignment=ft.alignment.center,
                        padding=ft.padding.only(bottom=24),
                    ),
                    ft.Text(
                        "No translations yet.",
                        size=14,
                        color=Colors.INK_MUTED,
                        italic=True,
                        font_family=Fonts.SERIF,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            )

        # Build first page of cards
        self._history_controls = []
        for item in entries:
            self._history_controls.append(
                self._build_card(item, len(self._history_controls), total)
            )
        self._offset = len(entries)
        self._all_loaded = self._offset >= total

        # Counter text widget
        self._counter_text = ft.Text(
            format_counter(1, self._offset, total),
            size=12,
            color=Colors.INK_MUTED,
            font_family=Fonts.MONO,
        )

        # ListView with scroll handler
        self._list_view = ft.ListView(
            controls=self._history_controls,
            expand=True,
            spacing=0,
            on_scroll=self._on_scroll,
        )

        return ft.Column(
            controls=[self._counter_text, self._list_view],
            expand=True,
            spacing=8,
        )

    def _build_card(self, item, index, total=None):
        """Build a single history card widget."""
        try:
            timestamp = datetime.fromisoformat(item.get("timestamp", ""))
            time_str = timestamp.strftime("%Y-%m-%d %H:%M")
        except Exception:
            time_str = "Unknown"

        # Use total for numbering if available, otherwise fall back to offset-based
        if total is None:
            _, total = self.history_manager.get_history_slice(0, 0)
        display_num = total - index

        source_preview = (item.get("source", "")[:100] + "...") if len(item.get("source", "")) > 100 else item.get("source", "")
        translation_preview = (item.get("translation", "")[:150] + "...") if len(item.get("translation", "")) > 150 else item.get("translation", "")

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(f"#{display_num}", size=12, color=Colors.GOLD, weight="bold", font_family=Fonts.MONO),
                            ft.Text(time_str, size=12, color=Colors.INK_MUTED, font_family=Fonts.MONO),
                            ft.Container(expand=True),
                            ft.Text(item.get("model", ""), size=11, color=Colors.INK_MUTED, font_family=Fonts.MONO),
                        ] + ([ft.Container(
                            content=ft.Text(f"⟳ {item['iteration_count']}", size=10, color=Colors.GOLD),
                            bgcolor=Colors.SURFACE_RAISED,
                            border_radius=4,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                        )] if item.get("iteration_count", 0) > 0 else []),
                        spacing=8,
                    ),
                    ft.Container(
                        content=ft.Text(source_preview, size=13, color=Colors.FOREGROUND, font_family=Fonts.SERIF, selectable=True),
                        padding=ft.padding.only(top=8),
                    ),
                    ft.Container(
                        content=ft.Text(translation_preview, size=13, color=Colors.INK_MUTED, font_family=Fonts.SERIF, italic=True, selectable=True),
                        padding=ft.padding.only(top=4),
                    ),
                    ft.Container(
                        content=ft.Text("Click to view full →", size=10, color=Colors.GOLD, italic=True),
                        padding=ft.padding.only(top=6),
                    ),
                ],
                spacing=0,
            ),
            bgcolor=Colors.SURFACE,
            border=ft.border.all(1, Colors.DIVIDER),
            border_radius=8,
            padding=ft.padding.all(16),
            margin=ft.margin.only(bottom=12),
            on_click=lambda e, itm=item: self._show_full_translation(itm),
            ink=True,
        )

    def _on_scroll(self, e: ft.OnScrollEvent):
        """Load next page when scroll reaches bottom threshold."""
        if e.pixels >= e.max_scroll_extent - 50 and not self._all_loaded:
            self._load_next_page()

    def _load_next_page(self):
        """Fetch next slice, build cards, append to list, and update counter."""
        entries, total = self.history_manager.get_history_slice(self._offset, self.PAGE_SIZE)
        if not entries:
            self._all_loaded = True
            return
        for item in entries:
            self._history_controls.append(
                self._build_card(item, len(self._history_controls), total)
            )
        self._offset += len(entries)
        if self._offset >= total:
            self._all_loaded = True
        self._update_counter(total)
        self.page.update()

    def _update_counter(self, total):
        """Update the counter text widget."""
        if self._counter_text:
            self._counter_text.value = format_counter(1, self._offset, total)

    def _show_full_translation(self, item):
        """Open a ParallelView tab for the selected history item."""
        try:
            from app.mem_debug import log_ram
            log_ram("history → open translation tab")
            _log("_show_full_translation → opening as tab")

            # Close the history dialog
            self._force_close_dialog()

            # Open as a translation tab via the shell action
            add_fn = self.actions.get("add_translation_result")
            if add_fn:
                add_fn(
                    item.get("source", ""),
                    item.get("translation", ""),
                    item.get("commentary"),
                    None,  # no metrics stored in history
                    item.get("pdf_path"),
                    history_timestamp=item.get("timestamp"),
                )
            else:
                _log("WARNING: add_translation_result action not available")

        except Exception:
            _log(f"ERROR in _show_full_translation:\n{traceback.format_exc()}")

    def _on_clear_history(self):
        """Show confirmation, then clear."""
        try:
            # Close current dialog
            self._force_close_dialog()

            def confirm_clear(e):
                try:
                    self.history_manager.clear_history()
                    # Reset pagination state
                    self._offset = 0
                    self._all_loaded = False
                    self._history_controls = []
                    self._list_view = None
                    self._counter_text = None
                    self._force_close_dialog()
                    self.show()
                except Exception:
                    _log(f"ERROR in confirm_clear:\n{traceback.format_exc()}")

            confirm_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Clear History", size=20, font_family=Fonts.HEADER, color=Colors.FOREGROUND),
                content=ft.Text("Are you sure? This cannot be undone.", size=14, color=Colors.FOREGROUND),
                actions=[
                    ft.TextButton(content=ft.Text("Cancel", font_family=Fonts.FRAKTUR), on_click=lambda e: self.show()),
                    ft.TextButton(content=ft.Text("Clear", font_family=Fonts.FRAKTUR), on_click=confirm_clear, style=ft.ButtonStyle(color=Colors.DESTRUCTIVE)),
                ],
                bgcolor=Colors.SURFACE,
            )
            self.page.dialog = confirm_dialog
            confirm_dialog.open = True
            self.page.update()
        except Exception:
            _log(f"ERROR in _on_clear_history:\n{traceback.format_exc()}")
