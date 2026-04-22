import flet as ft
import traceback
from app.components.layout.input_panel import InputPanel
from app.components.layout.center_panel import CenterPanel
from app.components.shared.loading_screen import LoadingScreen
from app.components.layout.drag_divider import DragDivider
from app.components.views.library_view import LibraryView
from app.state import AppState
from app.contexts.settings import SettingsManager
from app.services.translation_service import TranslationService
from app.theme import Colors, Fonts, UI
from app.services.pdf_import import PDFImportService


def _log(msg):
    print(f"[HomeTab] {msg}")


class HomeTab:
    def __init__(self, page: ft.Page, state: AppState, settings: SettingsManager, bus=None, actions=None):
        self.page = page
        self.state = state
        self.settings = settings
        self.bus = bus          # EventBus (for banners and safe_update)
        self.actions = actions or {}  # Shell callbacks (no direct shell ref)

        # 1. Services
        self.translation_service = TranslationService(settings)

        # 2. Panels
        self.input_panel = InputPanel(state)
        self.center_panel = CenterPanel(page, settings, sidebar=None, state=state, actions=actions)
        self.loading_screen = LoadingScreen(page)
        self.library_view = LibraryView(page, bus, state, actions)

        # 3. Local UI state (not shared)
        self.current_pdf_file = None
        self.left_width = 0.5

        # 4. Buttons
        self.translate_btn = ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.TRANSLATE, size=20),
                ft.Text("Translate", font_family=Fonts.FRAKTUR, size=16, weight="bold"),
            ], spacing=8, alignment="center"),
            on_click=self.on_translate,
            bgcolor=Colors.GOLD, color=Colors.BACKGROUND,
            height=36, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
        )
        self.upload_btn = ft.OutlinedButton(
            content=ft.Row([ft.Icon(ft.Icons.UPLOAD_FILE, size=20), ft.Text("Upload", font_family=Fonts.FRAKTUR, size=14)], spacing=8),
            on_click=self.on_upload,
            height=36, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
        )
        self.export_btn = ft.OutlinedButton(
            content=ft.Row([UI.icon("icon-export.svg", 20), ft.Text("Export", font_family=Fonts.FRAKTUR, size=14)], spacing=8),
            on_click=self.on_export,
            height=36, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
        )
        self.history_btn = ft.TextButton(
            content=ft.Row([UI.icon("icon-scroll.svg", 24), ft.Text("History", font_family=Fonts.FRAKTUR, size=14)], spacing=8),
            on_click=self.on_history, height=36,
        )

        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)
        self.page.overlay.append(self.file_picker)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call(self, action_name, *args, **kwargs):
        """Call a shell action by name. Safe if action doesn't exist."""
        fn = self.actions.get(action_name)
        if fn:
            fn(*args, **kwargs)
        else:
            _log(f"WARNING: action '{action_name}' not available")

    def _show_banner(self, msg, is_error=False):
        """Show a banner via the EventBus, with fallback."""
        try:
            if self.bus:
                self.bus.show_banner(msg, is_error=is_error)
            else:
                # Fallback: direct page banner
                if self.page.banner:
                    self.page.banner.open = False
                    self.page.update()
                color = "#FFFFFF" if is_error else Colors.BACKGROUND
                bg = Colors.DESTRUCTIVE if is_error else Colors.GOLD
                self.page.banner = ft.Banner(
                    content=ft.Text(msg, color=color, size=14, selectable=True),
                    actions=[ft.TextButton(
                        content=ft.Text("OK", font_family=Fonts.FRAKTUR),
                        on_click=lambda _: self._close_banner(),
                    )],
                    bgcolor=bg, open=True,
                )
                self.page.update()
        except Exception:
            _log(f"ERROR in _show_banner:\n{traceback.format_exc()}")

    def _close_banner(self):
        try:
            if self.bus:
                self.bus.close_banner()
            else:
                self.page.banner.open = False
                self.page.update()
        except Exception:
            pass

    def _safe_update(self):
        """Thread-safe page update."""
        if self.bus:
            self.bus.safe_update()
        else:
            try:
                self.page.update()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Core actions
    # ------------------------------------------------------------------

    def on_translate(self, e):
        try:
            if self.translate_btn.disabled:
                _log("on_translate skipped — already in progress")
                return
            text = self.input_panel.get_text()
            if not text.strip():
                return self._show_banner("No German text detected.", is_error=True)
            if not self.settings.has_api_key():
                return self._show_banner("Please add API key in sidebar.", is_error=True)

            # In book mode, delegate to the LibraryView's bulk translate
            if self.state.book_mode and self.state.book_chapters:
                _log("Book mode active — delegating to bulk translate")
                self.library_view.on_translate_all(e)
                return

            _log("Starting translation...")
            self.center_panel.start_log_session()
            self._set_translate_busy(True)
            self.page.update()

            # Get glossary block before spawning thread (safe to read from main thread)
            glossary_mgr = self.actions.get("glossary_manager")
            glossary_block = glossary_mgr.get_prompt_block() if glossary_mgr else ""

            def run_background():
                try:
                    success, translation, commentary, metrics = self.translation_service.translate_sync(
                        text, log_callback=self.center_panel.log_tab.append,
                        pdf_path=self.state.pdf_path,
                        glossary_block=glossary_block,
                    )
                    if success:
                        _log("Translation succeeded")
                        self._call("add_translation_result", text, translation, commentary, metrics, self.state.pdf_path)
                        if commentary:
                            self.center_panel.set_commentary(commentary)
                        self._show_banner("Translation Complete")
                    else:
                        _log(f"Translation failed: {translation}")
                        self._show_banner(translation, is_error=True)
                except Exception as ex:
                    _log(f"ERROR in background translation:\n{traceback.format_exc()}")
                    self._show_banner(f"System Error: {str(ex)}", is_error=True)
                finally:
                    self.center_panel.log_tab.mark_done()
                    self._set_translate_busy(False)
                    self._safe_update()

            import threading
            threading.Thread(target=run_background, daemon=True).start()
        except Exception:
            _log(f"ERROR in on_translate:\n{traceback.format_exc()}")

    def _set_translate_busy(self, busy: bool):
        """Set the toolbar translate button busy state and sync with LibraryView."""
        self.translate_btn.disabled = busy
        row = self.translate_btn.content
        if isinstance(row, ft.Row):
            for ctrl in row.controls:
                if isinstance(ctrl, ft.Icon):
                    row.controls[row.controls.index(ctrl)] = UI.icon("icon-hourglass.svg", 20) if busy else ft.Icon(ft.Icons.TRANSLATE, size=20)
                    break
            for ctrl in row.controls:
                if isinstance(ctrl, ft.Text):
                    ctrl.value = "Processing..." if busy else "Translate"
                    break
        # Sync LibraryView — but guard against re-entrant calls
        if hasattr(self, 'library_view') and not getattr(self, '_syncing_busy', False):
            self._syncing_busy = True
            try:
                self.library_view._set_translating(busy)
            finally:
                self._syncing_busy = False

    def on_history(self, e):
        try:
            _log("on_history clicked")
            self._call("open_history")
        except Exception:
            _log(f"ERROR in on_history:\n{traceback.format_exc()}")

    def on_export(self, e):
        try:
            _log("on_export clicked")
            self._call("show_export_dialog")
        except Exception:
            _log(f"ERROR in on_export:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------

    def on_upload(self, e):
        self.file_picker.pick_files(allowed_extensions=["pdf", "txt", "md", "png", "jpg", "jpeg", "tiff", "bmp"])

    def on_file_picked(self, e: ft.FilePickerResultEvent):
        try:
            if not e.files:
                return
            file = e.files[0]
            name = file.name
            path = file.path
            ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""

            # If there's existing content (PDF loaded or text in input), confirm before overwriting
            has_existing = self.state.has_pdf or bool(self.state.input_text and self.state.input_text.strip())
            suppress_confirm = getattr(self.settings, '_suppress_pdf_overwrite', False)

            if has_existing and not suppress_confirm:
                self._show_overwrite_confirmation(name, path, ext)
            else:
                self._process_picked_file(name, path, ext)
        except Exception:
            _log(f"ERROR in on_file_picked:\n{traceback.format_exc()}")
            self._show_banner("Upload failed. Check terminal for details.", is_error=True)

    def _show_overwrite_confirmation(self, name: str, path: str, ext: str):
        """Show a confirmation dialog before overwriting existing content with a new file."""
        dont_show_again = ft.Checkbox(
            label="Don't show this again",
            value=False,
            label_style=ft.TextStyle(size=12, color=Colors.INK_MUTED),
        )

        def on_confirm(e):
            if dont_show_again.value:
                self.settings._suppress_pdf_overwrite = True
            dialog.open = False
            self.page.update()
            self._reset_workspace()
            self._process_picked_file(name, path, ext)

        def on_cancel(e):
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Replace current content?", size=18, font_family=Fonts.HEADER, color=Colors.FOREGROUND),
            content=ft.Column([
                ft.Text(
                    "Loading a new file will clear the current text and log. Your previous translations are saved in History.",
                    size=14, color=Colors.INK_MUTED,
                ),
                ft.Container(content=dont_show_again, padding=ft.padding.only(top=8)),
            ], tight=True, spacing=4),
            actions=[
                ft.TextButton(content=ft.Text("Cancel", font_family=Fonts.FRAKTUR), on_click=on_cancel),
                ft.ElevatedButton(content=ft.Text("Continue", font_family=Fonts.FRAKTUR, weight="bold"), on_click=on_confirm, bgcolor=Colors.GOLD, color=Colors.BACKGROUND),
            ],
            bgcolor=Colors.SURFACE,
        )
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

    def _reset_workspace(self):
        """Clear the input, log, PDF, and book state to prepare for a new file."""
        try:
            self._call("global_clear_pdf")
            self.input_panel.set_text("")
            self.state.set_input_text("")
            self.state.clear_book_state()
            self.center_panel.end_log_session()
            self.center_panel.rebuild_tabs()
        except Exception:
            _log(f"ERROR in _reset_workspace:\n{traceback.format_exc()}")

    def _process_picked_file(self, name: str, path: str, ext: str):
        """Process the picked file after any confirmation is handled."""
        try:
            _log(f"File picked: {name} at {path}")

            # Reset book state when loading a new file
            self.state.clear_book_state()

            if ext == "pdf":
                self._call("global_clear_pdf")
                self.current_pdf_file = name
                self.center_panel.set_pdf_file(name, path)
                self._extract_text_background(path, name, is_image=False)
            elif ext in ("png", "jpg", "jpeg", "tiff", "bmp"):
                self._extract_text_background(path, name, is_image=True)
            elif ext in ("txt", "md"):
                text = PDFImportService.read_text_file(path)
                if text:
                    self.input_panel.set_text(text)
                    self._check_book_detection(text)
                    self._show_banner(f"Loaded {name}")
                else:
                    self._show_banner("File was empty.", is_error=True)
                self.page.update()
            else:
                self._show_banner(f"Unsupported file type: .{ext}", is_error=True)
        except Exception:
            _log(f"ERROR in _process_picked_file:\n{traceback.format_exc()}")
            self._show_banner("Upload failed. Check terminal for details.", is_error=True)

    def _extract_text_background(self, path, name, is_image=False):
        if getattr(self, '_extracting', False):
            _log("_extract_text_background skipped — already in progress")
            self._show_banner("An extraction is already in progress.", is_error=True)
            return

        self._extracting = True

        def _cancel():
            PDFImportService._worker_pool.cancel()

        self.loading_screen.show(title=f"Processing {name}", cancel_callback=_cancel)

        def _progress(message, progress):
            try:
                self.loading_screen.update_progress(message, progress)
            except Exception:
                pass

        def _do_extract():
            try:
                _log(f"Extracting text from {name} (is_image={is_image})")
                if is_image:
                    text = PDFImportService.extract_in_process("image", path, progress_callback=_progress)
                else:
                    text = PDFImportService.extract_in_process("pdf", path, progress_callback=_progress, use_ocr=True)

                self.loading_screen.hide()
                if text and text.strip():
                    _log(f"Extraction success: {len(text)} chars")
                    self.input_panel.set_text(text)
                    self._check_book_detection(text)
                    self._show_banner(f"Loaded {name}")
                else:
                    _log("Extraction returned empty text")
                    self._show_banner(f"No text could be extracted from {name}.", is_error=True)
                self._safe_update()
            except Exception as ex:
                self.loading_screen.hide()
                if "cancelled" in str(ex).lower():
                    _log("Extraction cancelled")
                    # Clean up PDF viewer and state
                    self._call("global_clear_pdf")
                    self.current_pdf_file = None
                    self._safe_update()
                else:
                    _log(f"ERROR extracting text from {name}:\n{traceback.format_exc()}")
                    self._show_banner(f"Extraction failed: {str(ex)}", is_error=True)
            finally:
                self._extracting = False

        import threading
        threading.Thread(target=_do_extract, daemon=True).start()

    # ------------------------------------------------------------------
    # Book detection (Task 8.3)
    # ------------------------------------------------------------------

    def _check_book_detection(self, text):
        """Check if extracted text qualifies as a book and trigger bulk mode UI."""
        try:
            book_processor = self.actions.get("book_processor")
            if book_processor and book_processor.detect_book(text):
                _log("Book detected — activating bulk mode UI")
                self.state.book_mode = True
                # Rebuild the layout so the LibraryView column appears
                rebuild_fn = self.actions.get("rebuild_tabs")
                if rebuild_fn:
                    rebuild_fn()
                # Show the "Book Detected" banner inside the now-visible LibraryView
                self.library_view.show_book_detected_banner(True)
                self._safe_update()
        except Exception:
            _log(f"ERROR in _check_book_detection:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self):
        workspace_content = self.center_panel.build()
        self._input_container = ft.Container(content=self.input_panel.build(), expand=int(self.left_width * 100))
        self._workspace_container = ft.Container(content=workspace_content, expand=int((1 - self.left_width) * 100))
        divider = DragDivider(on_drag=self._on_panel_drag)

        if self.state.book_mode:
            divider2 = DragDivider(on_drag=self._on_panel_drag)
            self._body_row = ft.Row([
                self._input_container,
                divider.build(),
                ft.Container(content=self.library_view.build(), width=260),
                divider2.build(),
                self._workspace_container,
            ], expand=True, spacing=0)
        else:
            self._body_row = ft.Row([self._input_container, divider.build(), self._workspace_container], expand=True, spacing=0)

        return ft.Column([
            ft.Container(
                content=ft.Row([self.translate_btn, self.upload_btn, self.export_btn, ft.Container(expand=True), self.history_btn], spacing=8),
                padding=10, bgcolor=Colors.SURFACE, border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
            ),
            self._body_row,
        ], expand=True, spacing=0)

    def _on_panel_drag(self, delta_x: float):
        try:
            total = self.page.window.width - 288
            if total <= 0:
                return
            new_width = max(0.2, min(0.8, self.left_width + delta_x / total))
            self.left_width = new_width
            self._input_container.expand = int(self.left_width * 100)
            self._workspace_container.expand = int((1 - self.left_width) * 100)
            self.page.update()
        except Exception:
            pass

    def cleanup(self):
        try:
            self.center_panel.pdf_viewer.cleanup()
        except Exception:
            pass
