import gc
import flet as ft
import threading
import traceback
from app.components.layout.sidebar import Sidebar
from app.components.layout.home_tab import HomeTab
from app.components.views.parallel_view import ParallelView
from app.components.views.pdf_viewer import WebView_PDF_Viewer
from app.state import AppState
from app.contexts.settings import SettingsManager
from app.theme import Colors, Fonts, UI
from app.components.views.history_view import HistoryView
from app.services.export_service import ExportService
from app.services.history import HistoryManager
from app.services.book_processor import BookProcessor
from app.services.glossary_manager import GlossaryManager
from app.services.re_translation_engine import ReTranslationEngine
from app.services.correction_service import CorrectionService
from app.event_bus import EventBus


def _log(msg):
    print(f"[AppShell] {msg}")


class AppShell:
    def __init__(self, page: ft.Page):
        _log("Initializing...")
        self.page = page
        self.bus = EventBus(page)
        self.state = AppState()
        self.settings = SettingsManager()

        # 1. Global Utilities
        self.export_service = ExportService(self.settings)
        self.history_manager = HistoryManager()
        self.glossary_manager = GlossaryManager()

        self.export_picker = ft.FilePicker(on_result=self._on_export_dir_result)
        self.page.overlay.append(self.export_picker)

        # 2. Tabs and Layout
        self.tab_bar_row = ft.Row(controls=[], spacing=4, scroll=ft.ScrollMode.ADAPTIVE)
        self.tab_bar_container = ft.Container(
            content=self.tab_bar_row,
            padding=ft.padding.only(left=8, top=4),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
            height=44,
        )
        self.content_container = ft.Container(expand=True)

        # Track the active ParallelView so we can cleanup its PDF viewer on tab close
        self._active_parallel_view = None

        # 3. Shell actions — passed to components so they never need a ref to shell
        self.actions = {
            "open_history": self.open_history,
            "show_export_dialog": self.show_export_dialog,
            "open_export_picker": self.open_export_picker,
            "global_clear_pdf": self.global_clear_pdf,
            "add_translation_result": self.add_translation_result,
            "rebuild_center_tabs": lambda: self.home_tab.center_panel.rebuild_tabs(),
            "open_dataset_picker": lambda e=None: self.home_tab.center_panel.on_add_button_click(e),
            "glossary_manager": self.glossary_manager,
            "open_glossary_tab": self._open_glossary_in_center,
            "open_datasets_tab": self._open_datasets_in_center,
            "open_corrections_tab": self._open_corrections_in_center,
            "refresh_glossary_sidebar": self._refresh_glossary_sidebar,
            "bus": self.bus,
            "history_manager": self.history_manager,
        }

        # HistoryView needs actions (specifically add_translation_result) so it's created after the dict
        self.history_view = HistoryView(page, actions=self.actions)

        # 4. Components — each gets bus, state, settings, and actions
        self.home_tab = HomeTab(
            page=self.page,
            state=self.state,
            settings=self.settings,
            bus=self.bus,
            actions=self.actions,
        )
        self.sidebar = Sidebar(
            page=self.page,
            settings=self.settings,
            bus=self.bus,
            actions=self.actions,
        )

        # CenterPanel needs to know about sidebar for thematic focus sync
        # (will be replaced by EventBus in a future pass)
        self.home_tab.center_panel.sidebar = self.sidebar

        # 5. BookProcessor — created AFTER HomeTab so translation_service is available
        self.book_processor = BookProcessor(
            self.settings,
            self.home_tab.translation_service,
            self.bus,
        )
        self.actions["book_processor"] = self.book_processor
        self.actions["scan_structure"] = self._scan_structure
        self.actions["start_bulk_translate"] = self._start_bulk_translate
        self.actions["cancel_bulk_translate"] = self._cancel_bulk_translate
        self.actions["set_input_text"] = self._set_input_text
        self.actions["rebuild_tabs"] = self.rebuild_tabs
        self.actions["set_translate_busy"] = self._set_toolbar_translate_busy

        # 6. HITL services — created AFTER HomeTab so translation_service is available
        self.re_translation_engine = ReTranslationEngine(
            translation_service=self.home_tab.translation_service,
            settings=self.settings,
            bus=self.bus,
            app_state=self.state,
        )
        self._correction_service: CorrectionService | None = None
        self.actions["version_store"] = self.state.version_store
        self.actions["re_translation_engine"] = self.re_translation_engine
        self.actions["correction_service"] = None  # lazily resolved via _get_correction_service
        self.actions["settings"] = self.settings

        # 7. EventBus listeners for bulk mode
        self.bus.on("book_detected", self._on_book_detected)
        self.bus.on("book_translation_complete", self._on_book_translation_complete)

        # EventBus listener for HITL version refresh
        self.bus.on("version_added", self._on_version_added)

        self.rebuild_tabs()
        _log("Initialized")

    # ------------------------------------------------------------------ #
    #  Export directory picker
    # ------------------------------------------------------------------ #

    def open_export_picker(self):
        try:
            _log("open_export_picker called")
            self.export_picker.get_directory_path(dialog_title="Choose Export Folder")
        except Exception:
            _log(f"ERROR in open_export_picker:\n{traceback.format_exc()}")

    def _on_export_dir_result(self, e: ft.FilePickerResultEvent):
        try:
            if e.path:
                _log(f"Export dir selected: {e.path}")
                self.settings.set_export_directory(e.path)
                self.sidebar.export_directory_field.value = e.path
                self.page.update()
        except Exception:
            _log(f"ERROR in _on_export_dir_result:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  History
    # ------------------------------------------------------------------ #

    def open_history(self):
        try:
            _log("open_history called")
            self.history_view.show()
        except Exception:
            _log(f"ERROR in open_history:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  Export dialog
    # ------------------------------------------------------------------ #

    def show_export_dialog(self):
        try:
            _log("show_export_dialog called")
            session_translations = self.state.translation_tabs
            history_entries = self.history_manager.get_history()

            has_session = bool(session_translations)
            has_history = bool(history_entries)

            if not has_session and not has_history:
                self.bus.show_banner("Nothing to export yet. Translate something first.", is_error=True)
                return

            format_radio = ft.RadioGroup(
                value="txt",
                content=ft.Column([
                    ft.Radio(value="txt",      label="Plain Text (.txt)"),
                    ft.Radio(value="html",     label="HTML (.html)"),
                    ft.Radio(value="markdown", label="Markdown (.md)"),
                ], spacing=4),
            )

            scope_options = []
            if has_session:
                scope_options.append(ft.Radio(value="session", label=f"Current session ({len(session_translations)} translation(s))"))
            if has_history:
                scope_options.append(ft.Radio(value="history_all", label=f"All history ({len(history_entries)} translation(s))"))
                scope_options.append(ft.Radio(value="history_pick", label="Pick from history..."))

            scope_radio = ft.RadioGroup(
                value="session" if has_session else "history_all",
                content=ft.Column(scope_options, spacing=4),
            )

            history_checkboxes = []
            for i, h in enumerate(history_entries[:50]):
                preview = (h.get("source", "")[:60] + "...") if len(h.get("source", "")) > 60 else h.get("source", "")
                history_checkboxes.append(ft.Checkbox(label=preview, value=False, data=i))

            history_pick_column = ft.Column(controls=history_checkboxes, scroll=ft.ScrollMode.ADAPTIVE, height=200, visible=False)

            def on_scope_change(e):
                history_pick_column.visible = (scope_radio.value == "history_pick")
                self.page.update()
            scope_radio.on_change = on_scope_change

            def do_export(dialog_e):
                try:
                    fmt = format_radio.value
                    scope = scope_radio.value
                    if scope == "session":
                        items = session_translations
                    elif scope == "history_all":
                        items = [{"source_full": h.get("source", ""), "translation": h.get("translation", ""), "commentary": h.get("commentary", ""), "metrics": {}} for h in history_entries]
                    elif scope == "history_pick":
                        selected_indices = [cb.data for cb in history_checkboxes if cb.value]
                        if not selected_indices:
                            self.bus.show_banner("No items selected.", is_error=True)
                            return
                        items = [{"source_full": history_entries[i].get("source", ""), "translation": history_entries[i].get("translation", ""), "commentary": history_entries[i].get("commentary", ""), "metrics": {}} for i in selected_indices]
                    else:
                        items = []
                    if not items:
                        self.bus.show_banner("Nothing selected to export.", is_error=True)
                        return
                    if len(items) == 1:
                        ok, msg = self.export_service.export_single_translation(items[0], fmt)
                    else:
                        ok, msg = self.export_service.export_multiple_translations(items, fmt)
                    export_dialog.open = False
                    self.page.update()
                    if ok:
                        self.bus.show_banner(f"Exported → {msg}", is_error=False)
                    else:
                        self.bus.show_banner(msg, is_error=True)
                except Exception:
                    _log(f"ERROR in do_export:\n{traceback.format_exc()}")

            export_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Row([UI.icon("icon-export.svg", 24), ft.Text("Export Translations", font_family=Fonts.HEADER, size=20)], spacing=8),
                content=ft.Container(width=500, padding=ft.padding.all(8), content=ft.Column([
                    ft.Text("Format", size=13, weight="bold", color=Colors.INK_MUTED), format_radio,
                    ft.Divider(color=Colors.DIVIDER),
                    ft.Text("Scope", size=13, weight="bold", color=Colors.INK_MUTED), scope_radio, history_pick_column,
                ], spacing=12, tight=True)),
                actions=[
                    ft.TextButton(content=ft.Text("Cancel", font_family=Fonts.FRAKTUR), on_click=lambda _: self._close_dialog(export_dialog)),
                    ft.ElevatedButton(content=ft.Text("Export", font_family=Fonts.FRAKTUR, weight="bold"), on_click=do_export, bgcolor=Colors.GOLD, color=Colors.BACKGROUND),
                ],
                bgcolor=Colors.SURFACE,
            )
            self.page.dialog = export_dialog
            export_dialog.open = True
            self.page.update()
        except Exception:
            _log(f"ERROR in show_export_dialog:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  PDF
    # ------------------------------------------------------------------ #

    def global_clear_pdf(self):
        try:
            _log("global_clear_pdf called")
            self.state.clear_pdf()
            self.home_tab.center_panel.pdf_viewer.cleanup()
            self.home_tab.center_panel.pdf_viewer = None
            self.home_tab.center_panel.pdf_viewer = WebView_PDF_Viewer(self.page)
            self.home_tab.current_pdf_file = None
            self.home_tab.center_panel.rebuild_tabs()
            self.bus.safe_update()
        except Exception:
            _log(f"ERROR in global_clear_pdf:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  Tab management
    # ------------------------------------------------------------------ #

    def rebuild_tabs(self):
        try:
            from app.mem_debug import log_mem, log_overlay, log_surviving_refs, log_ram

            # Cleanup previous ParallelView to release PDF data, FilePicker, etc.
            if self._active_parallel_view is not None:
                log_ram("rebuild_tabs BEFORE cleanup")
                log_mem("rebuild_tabs BEFORE cleanup")
                log_overlay(self.page, "rebuild_tabs BEFORE cleanup")
                self._active_parallel_view.cleanup()
                self._active_parallel_view = None
                gc.collect()
                log_ram("rebuild_tabs AFTER cleanup")
                log_mem("rebuild_tabs AFTER cleanup")
                log_overlay(self.page, "rebuild_tabs AFTER cleanup")
                log_surviving_refs()

            tabs = []
            is_home = self.state.is_home_active
            tabs.append(self._create_tab_header("Home", ft.Icons.HOME, is_home, lambda _: self.switch_to_home()))
            for i, trans in enumerate(self.state.translation_tabs):
                is_active = i == self.state.active_translation_index
                tabs.append(self._create_tab_header(
                    trans["source_preview"], ft.Icons.TRANSLATE, is_active,
                    lambda e, idx=i: self.switch_to_translation(idx), closable=True, close_idx=i,
                ))
            self.tab_bar_row.controls = tabs
            if is_home:
                self.content_container.content = self.home_tab.build()
            else:
                active_trans = self.state.get_active_translation()
                if active_trans:
                    # CorrectionService is resolved on-demand inside ParallelView
                    # via the "get_correction_service" callable — avoids loading
                    # the BERT model until the user actually commits a correction.
                    if "get_correction_service" not in self.actions:
                        self.actions["get_correction_service"] = self._get_correction_service
                    pv = ParallelView(active_trans, page=self.page, actions=self.actions)
                    self.content_container.content = pv.build()
                    self._active_parallel_view = pv
            self.page.update()
        except Exception:
            _log(f"ERROR in rebuild_tabs:\n{traceback.format_exc()}")

    def _create_tab_header(self, title, icon, is_active, on_click, closable=False, close_idx=None):
        display_title = title if len(title) <= 30 else title[:27] + "..."
        controls = [
            ft.Icon(icon, size=16, color=Colors.GOLD if is_active else Colors.INK_MUTED),
            ft.Text(display_title, size=13, color=Colors.INK if is_active else Colors.INK_MUTED, no_wrap=True),
        ]
        if closable:
            controls.append(ft.IconButton(
                ft.Icons.CLOSE, icon_size=12, icon_color=Colors.INK_MUTED,
                padding=ft.padding.all(0), width=20, height=20,
                on_click=lambda e, idx=close_idx: self.close_translation_tab(idx),
            ))
        return ft.Container(
            content=ft.Row(controls, spacing=6, tight=True),
            bgcolor=Colors.BACKGROUND if is_active else Colors.SURFACE,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            border_radius=ft.border_radius.only(top_left=6, top_right=6),
            on_click=on_click,
        )

    def switch_to_home(self):
        self.state.active_translation_index = -1
        self.rebuild_tabs()

    def switch_to_translation(self, index):
        if 0 <= index < len(self.state.translation_tabs):
            self.state.active_translation_index = index
        self.rebuild_tabs()

    def close_translation_tab(self, index):
        try:
            from app.mem_debug import log_ram
            log_ram(f"close_translation_tab({index}) START")
            _log(f"close_translation_tab({index})")
            self.state.close_translation_tab(index)
            # If no translation tabs remain, clear the home-tab PDF viewer
            # so its base64 page data is released from RAM.
            if not self.state.has_translations:
                self.global_clear_pdf()
            self.rebuild_tabs()
            log_ram(f"close_translation_tab({index}) END")
        except Exception:
            _log(f"ERROR in close_translation_tab:\n{traceback.format_exc()}")

    def add_translation_result(self, source_text, translation, commentary=None, metrics=None, pdf_path=None, history_timestamp=None):
        self.state.add_translation(source_text, translation, commentary, metrics, pdf_path=pdf_path, history_timestamp=history_timestamp)
        self.rebuild_tabs()

    def _open_glossary_in_center(self):
        """Switch the center panel to the Glossary tab."""
        try:
            self.home_tab.center_panel.switch_to_glossary()
            self.page.update()
        except Exception:
            _log(f"ERROR in _open_glossary_in_center:\n{traceback.format_exc()}")

    def _open_datasets_in_center(self):
        """Switch the center panel to the Datasets tab."""
        try:
            self.home_tab.center_panel.switch_to_datasets()
            self.page.update()
        except Exception:
            _log(f"ERROR in _open_datasets_in_center:\n{traceback.format_exc()}")

    def _open_corrections_in_center(self):
        """Switch the center panel to the Corrections tab."""
        try:
            self.home_tab.center_panel.switch_to_corrections()
            self.page.update()
        except Exception:
            _log(f"ERROR in _open_corrections_in_center:\n{traceback.format_exc()}")

    def _refresh_glossary_sidebar(self):
        """Refresh the sidebar glossary display."""
        try:
            self.sidebar.update_glossary_display()
            self.page.update()
        except Exception:
            _log(f"ERROR in _refresh_glossary_sidebar:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  Bulk mode actions (Task 8.1)
    # ------------------------------------------------------------------ #

    def _scan_structure(self):
        """Run structural scan in a background thread, update state, emit event."""
        try:
            text = self.home_tab.input_panel.get_text()
            if not text or not text.strip():
                self.bus.show_banner("No text to scan.", is_error=True)
                return

            # Pass PDF path if available so the scout can read PDF structure
            pdf_path = self.state.pdf_path

            def _do_scan():
                try:
                    _log("Starting structural scan...")
                    chapters = self.book_processor.scan_structure(
                        text, pdf_path=pdf_path
                    )
                    self.state.set_book_state(chapters)
                    self.bus.emit("book_detected", chapters=chapters)
                    self.bus.show_banner(f"Found {len(chapters)} chapter(s)")
                    self.rebuild_tabs()
                except Exception as ex:
                    _log(f"ERROR in _scan_structure:\n{traceback.format_exc()}")
                    self.bus.show_banner(f"Scan failed: {str(ex)}", is_error=True)

            threading.Thread(target=_do_scan, daemon=True).start()
        except Exception:
            _log(f"ERROR in _scan_structure:\n{traceback.format_exc()}")

    def _start_bulk_translate(self, selected_indices):
        """Start bulk translation in a background thread."""
        try:
            chapters = self.state.book_chapters
            if not chapters:
                self.bus.show_banner("No chapters to translate.", is_error=True)
                return

            if not self.settings.has_api_key():
                self.bus.show_banner("API key is missing. Please configure it in the sidebar.", is_error=True)
                # Reset the translate buttons since we're not starting
                if hasattr(self.home_tab, 'library_view'):
                    self.home_tab.library_view._set_translating(False)
                    self.bus.safe_update()
                return

            self.state.bulk_cancel_requested = False

            def _do_translate():
                try:
                    # Get glossary block for injection into each chunk translation
                    glossary_block = self.glossary_manager.get_prompt_block()

                    _log(f"Starting bulk translation of {len(selected_indices)} chapters...")
                    result = self.book_processor.translate_chapters(
                        chapters, selected_indices, glossary_block=glossary_block
                    )
                    self.state.book_translation = result
                    if result.full_translation:
                        self._call_action(
                            "add_translation_result",
                            "Book Translation",
                            result.full_translation,
                            None,
                            result.total_metrics,
                        )
                        # Add book translation to history
                        try:
                            model_id = self.settings.get_model()
                            self.history_manager.add_book_entry(result, model_id)
                        except Exception:
                            _log(f"WARNING: Failed to add book entry to history:\n{traceback.format_exc()}")
                    _log("Bulk translation complete")
                except Exception as ex:
                    _log(f"ERROR in _start_bulk_translate:\n{traceback.format_exc()}")
                    self.bus.show_banner(f"Bulk translation failed: {str(ex)}", is_error=True)

            threading.Thread(target=_do_translate, daemon=True).start()
        except Exception:
            _log(f"ERROR in _start_bulk_translate:\n{traceback.format_exc()}")

    def _cancel_bulk_translate(self):
        """Cancel the in-progress bulk translation."""
        try:
            _log("Cancelling bulk translation...")
            self.book_processor.cancel()
            self.state.bulk_cancel_requested = True
        except Exception:
            _log(f"ERROR in _cancel_bulk_translate:\n{traceback.format_exc()}")

    def _set_input_text(self, text):
        """Set text in the input panel."""
        try:
            self.home_tab.input_panel.set_text(text)
            self.bus.safe_update()
        except Exception:
            _log(f"ERROR in _set_input_text:\n{traceback.format_exc()}")

    def _call_action(self, action_name, *args, **kwargs):
        """Call a shell action by name."""
        fn = self.actions.get(action_name)
        if fn:
            fn(*args, **kwargs)

    def _set_toolbar_translate_busy(self, busy: bool):
        """Set the toolbar translate button state (called by LibraryView to sync)."""
        try:
            btn = self.home_tab.translate_btn
            btn.disabled = busy
            row = btn.content
            if isinstance(row, ft.Row):
                for ctrl in row.controls:
                    if isinstance(ctrl, ft.Icon):
                        row.controls[row.controls.index(ctrl)] = UI.icon("icon-hourglass.svg", 20) if busy else ft.Icon(ft.Icons.TRANSLATE, size=20)
                        break
                for ctrl in row.controls:
                    if isinstance(ctrl, ft.Text):
                        ctrl.value = "Processing..." if busy else "Translate"
                        break
        except Exception:
            _log(f"ERROR in _set_toolbar_translate_busy:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  Bulk mode EventBus handlers (Task 8.4)
    # ------------------------------------------------------------------ #

    def _on_book_detected(self, **kwargs):
        """Handle 'book_detected' event — update LibraryView with chapters."""
        try:
            chapters = kwargs.get("chapters", [])
            if chapters and hasattr(self.home_tab, 'library_view'):
                self.home_tab.library_view.update_chapters(chapters)
                self.rebuild_tabs()
        except Exception:
            _log(f"ERROR in _on_book_detected:\n{traceback.format_exc()}")

    def _on_book_translation_complete(self, **kwargs):
        """Handle 'book_translation_complete' event — show appropriate banner."""
        try:
            translated = kwargs.get("chapters_translated", 0)
            errored = kwargs.get("chapters_errored", 0)

            # Errors take priority
            if errored > 0 and translated == 0:
                self.bus.show_banner(
                    f"Translation failed — all {errored} chapter(s) encountered errors. Check your API key and connection.",
                    is_error=True,
                )
            elif errored > 0:
                self.bus.show_banner(
                    f"Translation partially complete — {translated} chapter(s) done, {errored} failed.",
                    is_error=True,
                )
            elif self.state.bulk_cancel_requested:
                msg = f"Bulk translation cancelled. {translated} chapter(s) completed." if translated else "Bulk translation cancelled."
                self.bus.show_banner(msg, is_error=True)
            else:
                self.bus.show_banner("Book translation complete!")
        except Exception:
            _log(f"ERROR in _on_book_translation_complete:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  HITL helpers
    # ------------------------------------------------------------------ #

    def _get_correction_service(self) -> CorrectionService | None:
        """Lazy-initialize CorrectionService once TranslationBrain is ready."""
        if self._correction_service is not None:
            return self._correction_service
        try:
            ts = self.home_tab.translation_service
            ts._initialize_brain()
            if ts.brain:
                self._correction_service = CorrectionService(ts.brain)
        except Exception:
            _log(f"ERROR initializing CorrectionService:\n{traceback.format_exc()}")
        return self._correction_service

    def _on_version_added(self, **kwargs):
        """Handle version_added event — refresh the active ParallelView."""
        try:
            self.rebuild_tabs()
        except Exception:
            _log(f"ERROR in _on_version_added:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _close_dialog(self, dialog):
        dialog.open = False
        self.page.update()

    # ------------------------------------------------------------------ #
    #  Build
    # ------------------------------------------------------------------ #

    def build(self):
        from app.components.layout.drag_divider import DragDivider
        self._main_container = ft.Container(content=ft.Column(
            [self.tab_bar_container, self.content_container], expand=True, spacing=0
        ), expand=True)
        self._sidebar_container = ft.Container(
            content=self.sidebar.build(), width=288, bgcolor=Colors.SIDEBAR_BG
        )
        sidebar_divider = DragDivider(on_drag=self._on_sidebar_drag)
        return ft.Row([self._main_container, sidebar_divider.build(), self._sidebar_container], expand=True, spacing=0)

    def _on_sidebar_drag(self, delta_x: float):
        try:
            current_width = self._sidebar_container.width or 288
            new_width = max(200, min(450, current_width - delta_x))
            self._sidebar_container.width = int(new_width)
            self.page.update()
        except Exception:
            pass
