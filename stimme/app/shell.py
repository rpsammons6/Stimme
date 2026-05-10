import atexit
import math
import flet as ft
import threading
import traceback
from pathlib import Path
from app.components.layout.sidebar import Sidebar
from app.components.layout.menu_bar import MenuBarComponent
from app.components.layout.home_tab import HomeTab
from app.components.views.parallel_view import ParallelView
from app.components.views.glossary.glossary_tab_view import GlossaryTabView
from app.state import AppState
from app.services.configuration_service import ConfigurationService
from app.theme import Colors, Fonts, UI, _THEME_LABEL_TO_MODE
from app.components.views.history_view import HistoryView
from app.services.export_service import ExportService
from app.services.history import HistoryManager
from app.services.book_processor import BookProcessor
from app.services.glossary_manager import GlossaryManager
from app.services.glossary_journal import GlossaryJournal
from app.services.re_translation_engine import ReTranslationEngine
from app.services.correction_service import CorrectionService
from app.services.state_service import StateService
from app.services.pdf_import import PDFImportService
from app.services.subprocess_runner import SubprocessRunner
from app.event_bus import EventBus
from app.components.views.preferences_window import PreferencesWindow
from app.components.shared.diagnostics_hud import DiagnosticsHUD
from app.components.shared.banner_overlay import BannerOverlay
from app.components.shared.eigenstimme_badge import EigenstimmeBadge
from app.services.reaper import ResourceReaper
from app.services.reaper.providers import (
    PDFResourceProvider,
    ModelResourceProvider,
    CacheResourceProvider,
    UIOverlayProvider,
)


def _log(msg):
    print(f"[AppShell] {msg}")


RAIL_SECTIONS: list[tuple[str, str, str]] = [
    ("SVGs/noun-apple-5527427.svg", "Model", "model"),
    ("SVGs/noun-edit-5527393.svg", "Scholar Mode", "scholar"),
    ("SVGs/noun-puzzle-5441853.svg", "Thematic Focus", "focus"),
    ("SVGs/noun-folder-5441888.svg", "Export Directory", "export"),
    ("SVGs/noun-database-5527402.svg", "Datasets", "datasets"),
    ("SVGs/noun-book-5527435.svg", "Glossary", "glossary"),
    ("SVGs/noun-key-5527436.svg", "API Keys", "keys"),
]


class AppShell:
    def __init__(self, page: ft.Page):
        _log("Initializing...")
        self.page = page
        self.bus = EventBus(page)
        self.state = AppState()

        # Project root: stimme/ directory (where main.py lives)
        stimme_dir = Path(__file__).resolve().parent.parent
        self.settings = ConfigurationService(self.bus, stimme_dir=stimme_dir)

        # Subprocess runner for memory-intensive tasks (benchmark, OCR)
        self._subprocess_runner = SubprocessRunner(self.bus, self.settings)
        atexit.register(self._subprocess_runner.shutdown_all)

        # Wire SubprocessRunner into PDFImportService for OCR isolation
        PDFImportService._subprocess_runner = self._subprocess_runner

        # State recovery service
        self.state_service = StateService(self.state, self.bus, stimme_dir)

        # Connect worker crash monitoring to the PDF import worker pool
        PDFImportService._worker_pool.on_process_spawned = self.state_service.monitor_worker

        # 1. Global Utilities
        self.export_service = ExportService(self.settings)
        self.history_manager = HistoryManager()
        self.glossary_journal = GlossaryJournal(stimme_dir)
        self.glossary_manager = GlossaryManager(
            journal=self.glossary_journal,
            config_service=self.settings,
            event_bus=self.bus,
        )

        self.export_picker = ft.FilePicker(on_result=self._on_export_dir_result)
        self.page.overlay.append(self.export_picker)

        # File picker for menu-triggered Open Glossary action
        self._glossary_open_picker = ft.FilePicker(on_result=self._on_menu_open_glossary_result)
        self.page.overlay.append(self._glossary_open_picker)

        # 2. Tabs and Layout
        self.tab_bar_row = ft.Row(controls=[], spacing=4, scroll=ft.ScrollMode.ADAPTIVE)
        self.tab_bar_container = ft.Container(
            content=self.tab_bar_row,
            padding=ft.padding.only(left=8, top=4),
            bgcolor=Colors.BACKGROUND,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
            height=44,
        )
        self.content_container = ft.Container(expand=True)

        # Track the active ParallelView so we can cleanup its PDF viewer on tab close
        self._active_parallel_view = None

        # Track open glossary file tabs (GlossaryTabView instances)
        self._glossary_tabs: list[GlossaryTabView] = []
        self._active_glossary_tab_index: int = -1  # -1 means no glossary tab active

        # Inject glossary dirty checker into AppState for exit guard delegation
        self.state.set_dirty_checker(self.has_dirty_glossaries)

        # Icon rail / detail panel state
        self._active_section: str | None = None
        self._last_section: str | None = None
        self._rail_expanded: bool = False
        self._rail_labels: dict[str, ft.Text] = {}
        self._rail_chevrons: dict[str, ft.Icon] = {}
        self._rail_content_slots: dict[str, ft.Container] = {}
        self._rail_row_containers: dict[str, ft.Container] = {}

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
            "open_glossary_file_tab": self.open_glossary_file_tab,
            "on_open_glossary_tab": self.open_glossary_file_tab,
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
        self.actions["export_picker"] = self.export_picker
        self.actions["cancel_benchmark"] = lambda: self._subprocess_runner.cancel("benchmark")

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

        # 6b. Resource Reaper — centralized cleanup service
        pdf_provider = PDFResourceProvider()
        self.reaper = ResourceReaper(
            app_state=self.state,
            bus=self.bus,
            settings=self.settings,
            page=self.page,
        )
        self.reaper.register_provider("pdf", pdf_provider)
        self.reaper.register_provider("models", ModelResourceProvider(
            self.home_tab.translation_service.brain._reaper
        ))
        self.reaper.register_provider("cache", CacheResourceProvider(self.state.version_store))
        self.reaper.register_provider("overlay", UIOverlayProvider(self.page))
        self.reaper.start_pressure_monitor()
        atexit.register(self.reaper.stop)

        # Pass pdf_provider via actions so CenterPanel can register viewers
        self.actions["pdf_provider"] = pdf_provider

        # 7. EventBus listeners for bulk mode
        self.bus.on("book_detected", self._on_book_detected)
        self.bus.on("book_translation_complete", self._on_book_translation_complete)

        # EventBus listener for HITL version refresh
        self.bus.on("version_added", self._on_version_added)

        # EventBus listener for runtime theme switching
        self.bus.on("config_changed", self._on_config_changed)

        # EventBus listener for menu actions (File menu glossary operations)
        self.bus.on("menu_action", self._on_menu_action)

        # 8. Preferences window — separate Flet window for full settings control
        self.preferences_window = PreferencesWindow(self.page, self.settings, self.bus)
        self.actions["open_preferences"] = self.preferences_window.open
        self.bus.on("translation_started", self.preferences_window.auto_save_and_close)
        self.page.on_keyboard_event = self._on_keyboard_event

        # 9. Diagnostics HUD — toggled via settings
        self.diagnostics_hud = DiagnosticsHUD(self.page, self.bus)
        self.bus.set_update_latency_callback(self.diagnostics_hud.record_update_latency)
        # Check if HUD should be visible on boot
        if self.settings.get("diagnostics_hud", False):
            self.diagnostics_hud.set_visible(True)

        # 10. Eigenstimme badge — shows when local LLM mode is active
        self.eigenstimme_badge = EigenstimmeBadge(
            bus=self.bus,
            initial_backend=self.settings.get_llm_backend(),
        )

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
                title=ft.Row([UI.icon("SVGs/noun-download-5441865.svg", 24), ft.Text("Export Translations", font_family=Fonts.HEADER, size=20)], spacing=8),
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
            self.home_tab.current_pdf_file = None
            # Delegate cleanup to the Reaper — it will reconcile the now-orphaned
            # PDF viewer via PDFResourceProvider on the next reap cycle.
            self.reaper.reap("pdf_cleared")
            self.home_tab.center_panel.rebuild_tabs()
            self.bus.safe_update()
        except Exception:
            _log(f"ERROR in global_clear_pdf:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  Tab management
    # ------------------------------------------------------------------ #

    def rebuild_tabs(self):
        try:
            # Cleanup previous ParallelView to release PDF data, FilePicker, etc.
            if self._active_parallel_view is not None:
                self._active_parallel_view.cleanup()
                self._active_parallel_view = None
                # Delegate GC and orphan reconciliation to the Reaper
                self.reaper.reap("rebuild_tabs")

            tabs = []
            is_home = self.state.is_home_active and self._active_glossary_tab_index < 0
            tabs.append(self._create_tab_header("Home", UI.icon("SVGs/noun-home-5441835.svg", 16), is_home, lambda _: self.switch_to_home()))
            for i, trans in enumerate(self.state.translation_tabs):
                is_active = (i == self.state.active_translation_index) and self._active_glossary_tab_index < 0
                tabs.append(self._create_tab_header(
                    trans["source_preview"], ft.Icons.TRANSLATE, is_active,
                    lambda e, idx=i: self.switch_to_translation(idx), closable=True, close_idx=i,
                ))
            # Glossary file tabs
            for gi, gtv in enumerate(self._glossary_tabs):
                is_active = (gi == self._active_glossary_tab_index)
                tabs.append(self._create_tab_header(
                    gtv.get_tab_title(), UI.icon("SVGs/noun-book-5527435.svg", 16), is_active,
                    lambda e, idx=gi: self._switch_to_glossary_tab(idx),
                    closable=True, close_idx=-(gi + 1),
                ))
            self.tab_bar_row.controls = tabs
            if self._active_glossary_tab_index >= 0 and self._active_glossary_tab_index < len(self._glossary_tabs):
                # Glossary file tab is active
                gtv = self._glossary_tabs[self._active_glossary_tab_index]
                self.content_container.content = gtv.build()
            elif is_home:
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
        # If icon is already a Control (e.g. ft.Image from UI.icon()), use it directly;
        # otherwise wrap the string/enum in ft.Icon().
        if isinstance(icon, ft.Control):
            icon_control = icon
        else:
            icon_control = ft.Icon(icon, size=16, color=Colors.GOLD if is_active else Colors.INK_MUTED)
        controls = [
            icon_control,
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
            bgcolor=Colors.SURFACE if is_active else Colors.BACKGROUND,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            border_radius=ft.border_radius.only(top_left=6, top_right=6),
            expand=is_active and not closable,
            on_click=on_click,
        )

    def switch_to_home(self):
        self.state.active_translation_index = -1
        self._active_glossary_tab_index = -1
        self.rebuild_tabs()

    def switch_to_translation(self, index):
        if 0 <= index < len(self.state.translation_tabs):
            # Cancel benchmark subprocess if navigating away from log view
            # Feature: subprocess-isolation, Requirements: 2.5
            if self.state.show_logs:
                self._subprocess_runner.cancel("benchmark")
            self.state.active_translation_index = index
            self._active_glossary_tab_index = -1
        self.rebuild_tabs()

    def close_translation_tab(self, index):
        try:
            _log(f"close_translation_tab({index})")

            # Negative indices are glossary file tabs
            if index < 0:
                self.close_glossary_tab(-(index + 1))
                return

            self.state.close_translation_tab(index)
            # Emit tab_closed event — the Reaper listens via EventBus
            self.bus.emit("tab_closed", index=index)
            # If no translation tabs remain, clear the home-tab PDF viewer
            # so its base64 page data is released from RAM.
            if not self.state.has_translations:
                self.global_clear_pdf()
            self.rebuild_tabs()
        except Exception:
            _log(f"ERROR in close_translation_tab:\n{traceback.format_exc()}")

    def add_translation_result(self, source_text, translation, commentary=None, metrics=None, pdf_path=None, history_timestamp=None):
        self.state.add_translation(source_text, translation, commentary, metrics, pdf_path=pdf_path, history_timestamp=history_timestamp)
        self.rebuild_tabs()

    # ------------------------------------------------------------------ #
    #  Glossary file tab management
    # ------------------------------------------------------------------ #

    def open_glossary_file_tab(self, glossary):
        """Create a new GlossaryTabView for the given glossary file and add to tab bar.

        If the glossary is already open in a tab, switches to that tab instead.
        """
        try:
            # Check if this glossary is already open
            for gi, gtv in enumerate(self._glossary_tabs):
                if gtv.glossary.file_path == glossary.file_path:
                    # Switch to existing tab
                    self._switch_to_glossary_tab(gi)
                    return

            # Create a new GlossaryTabView
            gtv = GlossaryTabView(
                page=self.page,
                glossary=glossary,
                actions=self.actions,
            )
            gtv.set_on_dirty_changed(self._on_glossary_tab_dirty_changed)
            self._glossary_tabs.append(gtv)

            # Switch to the new tab
            gi = len(self._glossary_tabs) - 1
            self._switch_to_glossary_tab(gi)
        except Exception:
            _log(f"ERROR in open_glossary_file_tab:\n{traceback.format_exc()}")

    def close_glossary_tab(self, glossary_index: int):
        """Close a glossary tab, prompting save if dirty.

        Args:
            glossary_index: Index into self._glossary_tabs list.
        """
        try:
            if glossary_index < 0 or glossary_index >= len(self._glossary_tabs):
                return

            gtv = self._glossary_tabs[glossary_index]

            if gtv.state.is_dirty:
                # Show save prompt dialog
                self._show_save_changes_dialog(gtv, glossary_index)
            else:
                self._remove_glossary_tab(glossary_index)
        except Exception:
            _log(f"ERROR in close_glossary_tab:\n{traceback.format_exc()}")

    def _switch_to_glossary_tab(self, glossary_index: int):
        """Switch to a glossary file tab by its index."""
        try:
            if 0 <= glossary_index < len(self._glossary_tabs):
                # Cancel benchmark subprocess if navigating away from log view
                # Feature: subprocess-isolation, Requirements: 2.5
                if self.state.show_logs:
                    self._subprocess_runner.cancel("benchmark")
                self._active_glossary_tab_index = glossary_index
                self.rebuild_tabs()
        except Exception:
            _log(f"ERROR in _switch_to_glossary_tab:\n{traceback.format_exc()}")

    def _remove_glossary_tab(self, glossary_index: int):
        """Remove a glossary tab without saving."""
        try:
            if 0 <= glossary_index < len(self._glossary_tabs):
                self._glossary_tabs.pop(glossary_index)
                # Adjust active index if needed
                if self._active_glossary_tab_index >= len(self._glossary_tabs):
                    self._active_glossary_tab_index = -1
                elif self._active_glossary_tab_index == glossary_index:
                    self._active_glossary_tab_index = -1
                elif self._active_glossary_tab_index > glossary_index:
                    self._active_glossary_tab_index -= 1
                self.rebuild_tabs()
        except Exception:
            _log(f"ERROR in _remove_glossary_tab:\n{traceback.format_exc()}")

    def has_dirty_glossaries(self) -> bool:
        """Return True if any open glossary tab has unsaved changes."""
        return any(gtv.state.is_dirty for gtv in self._glossary_tabs)

    def get_dirty_glossary_count(self) -> int:
        """Return the number of glossary tabs with unsaved changes."""
        return sum(1 for gtv in self._glossary_tabs if gtv.state.is_dirty)

    def save_all_dirty_glossaries(self) -> tuple[bool, str | None]:
        """Save all dirty glossary tabs. Returns (success, error_message).

        Iterates all open glossary tabs, saves each dirty one via
        GlossaryManager.save_glossary(). If any save fails, returns
        immediately with the error details.

        Progressive Success (Forensic Transparency): Each tab's is_dirty
        flag is cleared immediately after its successful save. If the 4th
        of 5 glossaries fails, the first 3 are already marked clean — the
        user can see exactly which tab still has the asterisk (*) in its
        title, identifying the problematic file at a glance.
        """
        for gtv in self._glossary_tabs:
            if gtv.state.is_dirty:
                try:
                    self.glossary_manager.save_glossary(gtv.glossary)
                    gtv.state.is_dirty = False
                except (ValueError, OSError, PermissionError) as exc:
                    name = gtv.glossary.name or "Unknown"
                    return False, f"Failed to save '{name}': {exc}"
        return True, None

    def _on_glossary_tab_dirty_changed(self, tab_view: GlossaryTabView):
        """Update tab title when a glossary tab's dirty state changes."""
        try:
            self.rebuild_tabs()
        except Exception:
            _log(f"ERROR in _on_glossary_tab_dirty_changed:\n{traceback.format_exc()}")

    def _show_save_changes_dialog(self, gtv: GlossaryTabView, glossary_index: int):
        """Show a Save/Don't Save/Cancel dialog for a dirty glossary tab."""
        try:
            name = gtv.glossary.name or "Untitled"

            def on_save(e):
                self.bus.close_dialog()
                gtv.save()
                self._remove_glossary_tab(glossary_index)

            def on_dont_save(e):
                self.bus.close_dialog()
                self._remove_glossary_tab(glossary_index)

            def on_cancel(e):
                self.bus.close_dialog()

            from app.theme import Fonts as _Fonts

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Save Changes?", size=16, weight="bold", color=Colors.GOLD),
                content=ft.Text(
                    f'Do you want to save changes to "{name}"?',
                    size=13,
                    color=Colors.FOREGROUND,
                ),
                actions=[
                    ft.TextButton(
                        "Cancel",
                        on_click=on_cancel,
                        style=ft.ButtonStyle(color=Colors.INK_MUTED),
                    ),
                    ft.TextButton(
                        "Don't Save",
                        on_click=on_dont_save,
                        style=ft.ButtonStyle(color=Colors.DESTRUCTIVE),
                    ),
                    ft.TextButton(
                        "Save",
                        on_click=on_save,
                        style=ft.ButtonStyle(color=Colors.GOLD),
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                bgcolor=Colors.BACKGROUND,
            )

            self.bus.show_dialog(dialog)
        except Exception:
            _log(f"ERROR in _show_save_changes_dialog:\n{traceback.format_exc()}")

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
    #  Menu action handler
    # ------------------------------------------------------------------ #

    def _on_menu_action(self, action: str = "", **kwargs):
        """Handle menu_action events from the MenuBar."""
        try:
            if action == "file.new_glossary":
                self._menu_new_glossary()
            elif action == "file.open_glossary":
                self._menu_open_glossary()
            elif action == "file.save_glossary":
                self._menu_save_glossary()
            elif action == "scriptorium.health_check":
                self._run_health_check_in_console()
            elif action == "scriptorium.benchmark":
                self._run_benchmark_in_console()
        except Exception:
            _log(f"ERROR in _on_menu_action({action}):\n{traceback.format_exc()}")

    def _run_health_check_in_console(self):
        """Open LogTab and run dependency health check in background."""
        try:
            _log("_run_health_check_in_console: starting log session")
            self.home_tab.center_panel.start_log_session(title="Dependency Health Check")
            log_cb = self.home_tab.center_panel.log_tab.append
            done_cb = self.home_tab.center_panel.log_tab.mark_done
            _log("_run_health_check_in_console: log session started, spawning worker")

            def _worker():
                _log("_run_health_check_in_console._worker: thread started")
                try:
                    self.home_tab.action_handler._do_run_dependency_check(log_callback=log_cb)
                    _log("_run_health_check_in_console._worker: check completed")
                except Exception as exc:
                    _log(f"_run_health_check_in_console._worker: EXCEPTION: {exc}")
                    log_cb(f"❌ Error: {exc}")
                finally:
                    _log("_run_health_check_in_console._worker: calling mark_done()")
                    done_cb()
                    _log("_run_health_check_in_console._worker: done")

            threading.Thread(target=_worker, daemon=True).start()
            _log("_run_health_check_in_console: worker thread spawned")
        except Exception:
            _log(f"ERROR in _run_health_check_in_console:\n{traceback.format_exc()}")

    def _run_benchmark_in_console(self):
        """Open LogTab and run performance benchmark in a subprocess.

        Uses SubprocessRunner to spawn the benchmark in an isolated child
        process. When the child exits, the OS reclaims all RAM (ONNX sessions,
        embeddings, LanceDB) unconditionally.

        Feature: subprocess-isolation
        Requirements: 2.1, 2.2, 2.3, 2.6, 4.1, 4.4
        """
        try:
            _log("_run_benchmark_in_console: starting log session")
            self.home_tab.center_panel.start_log_session(title="Performance Benchmark")
            log_tab = self.home_tab.center_panel.log_tab
            _log("_run_benchmark_in_console: log session started, submitting to subprocess runner")

            task_ctx = self._subprocess_runner.build_task_context()

            from app.workers.benchmark_worker import run_benchmark

            self._subprocess_runner.submit(
                category="benchmark",
                worker_target=run_benchmark,
                worker_args=(task_ctx,),
                on_output=lambda line: (log_tab.append(line), self.bus.safe_update()),
                on_done=lambda result: (log_tab.mark_done(), self.bus.safe_update()),
                on_error=lambda msg: (log_tab.append(f"❌ {msg}"), log_tab.mark_done(), self.bus.safe_update()),
            )
            _log("_run_benchmark_in_console: benchmark subprocess submitted")
        except Exception:
            _log(f"ERROR in _run_benchmark_in_console:\n{traceback.format_exc()}")

    def _menu_new_glossary(self):
        """Handle File → New Glossary menu action."""
        try:
            from app.components.views.glossary.dialogs.new_glossary import NewGlossaryDialog

            def _on_created(glossary):
                self.open_glossary_file_tab(glossary)

            dialog = NewGlossaryDialog(
                page=self.page,
                actions=self.actions,
                on_created=_on_created,
            )
            dialog.show()
        except Exception:
            _log(f"ERROR in _menu_new_glossary:\n{traceback.format_exc()}")

    def _menu_open_glossary(self):
        """Handle File → Open Glossary menu action."""
        try:
            self._glossary_open_picker.pick_files(
                dialog_title="Open Glossary",
                allowed_extensions=["glossary", "csv"],
                allow_multiple=False,
            )
        except Exception:
            _log(f"ERROR in _menu_open_glossary:\n{traceback.format_exc()}")

    def _menu_save_glossary(self):
        """Handle File → Save Glossary menu action. Saves the active glossary tab."""
        try:
            if self._active_glossary_tab_index >= 0 and self._active_glossary_tab_index < len(self._glossary_tabs):
                gtv = self._glossary_tabs[self._active_glossary_tab_index]
                gtv.save()
                self.rebuild_tabs()
            else:
                _log("No active glossary tab to save")
        except Exception:
            _log(f"ERROR in _menu_save_glossary:\n{traceback.format_exc()}")

    def _on_menu_open_glossary_result(self, e: ft.FilePickerResultEvent):
        """Handle the result of the menu-triggered Open Glossary file picker."""
        try:
            if not e.files or len(e.files) == 0:
                return  # User cancelled

            from pathlib import Path

            file_path = Path(e.files[0].path)
            suffix = file_path.suffix.lower()

            # Validate extension
            if suffix not in (".glossary", ".csv"):
                self.bus.show_banner(
                    "Only .glossary and .csv files are supported.",
                    is_error=True,
                )
                return

            try:
                if suffix == ".glossary":
                    glossary = self.glossary_manager.load_glossary(file_path)
                    self.open_glossary_file_tab(glossary)
                elif suffix == ".csv":
                    # CSV files are imported (converted to .glossary format)
                    glossary, conflicts = self.glossary_manager.import_glossary(file_path)
                    if conflicts:
                        from app.components.views.glossary.dialogs.conflict_resolution import (
                            ConflictResolutionDialog,
                        )

                        def _on_resolved(resolved_pairs):
                            self.open_glossary_file_tab(glossary)
                            self.bus.emit("glossary_changed")

                        dialog = ConflictResolutionDialog(
                            page=self.page,
                            conflicts=conflicts,
                            actions=self.actions,
                            on_resolved=_on_resolved,
                        )
                        dialog.show()
                    else:
                        self.open_glossary_file_tab(glossary)
                        self.bus.emit("glossary_changed")
            except ValueError as ve:
                if suffix == ".csv":
                    self.bus.show_banner(
                        "Error: Failed to import .csv to Glossaries. "
                        "Please compare the format of your CSV to the documentation and try again.",
                        is_error=True,
                    )
                else:
                    self.bus.show_banner(f"Failed to open glossary: {ve}", is_error=True)
            except FileNotFoundError:
                self.bus.show_banner(f"File not found: {file_path.name}", is_error=True)
            except Exception as ex:
                self.bus.show_banner(f"Failed to open glossary: {ex}", is_error=True)

        except Exception:
            _log(f"ERROR in _on_menu_open_glossary_result:\n{traceback.format_exc()}")

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
                        chapters, selected_indices, glossary_block=glossary_block,
                        glossary_manager=self.glossary_manager,
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

    def _on_config_changed(self, key: str, value, **kwargs):
        """Handle config_changed event — apply theme when theme key changes."""
        try:
            if key == "theme":
                mode = _THEME_LABEL_TO_MODE.get(value, "dark")
                Colors.apply(mode)
                # Update Flet's native theme so Material widgets follow suit
                self.page.theme_mode = (
                    ft.ThemeMode.DARK if mode == "dark" else ft.ThemeMode.LIGHT
                )
                self.page.bgcolor = Colors.BACKGROUND
                self.page.theme = ft.Theme(
                    font_family="CormorantGaramond",
                    use_material3=True,
                    color_scheme=ft.ColorScheme(
                        primary=Colors.GOLD,
                        surface=Colors.SURFACE,
                        background=Colors.BACKGROUND,
                    ),
                    splash_color=ft.Colors.TRANSPARENT,
                )
                # Global rebuild: re-initialize the entire control tree so
                # every component naturally reads the updated Colors tokens.
                self._rebuild_ui()
        except Exception:
            _log(f"ERROR in _on_config_changed:\n{traceback.format_exc()}")

    def _rebuild_ui(self):
        """Replace the page content with a freshly built control tree.

        Called after Colors.apply() so every component constructor and
        build() method picks up the new palette from the semantic tokens.
        Preserves user state (input text, etc.) across the rebuild.
        """
        try:
            # Clean up the old HomeTab's file picker from the overlay
            old_picker = getattr(self.home_tab, 'file_picker', None)
            if old_picker and old_picker in self.page.overlay:
                self.page.overlay.remove(old_picker)

            # Remove shell-level pickers from overlay before rebuild
            for picker in (self.export_picker, self._glossary_open_picker):
                if picker in self.page.overlay:
                    self.page.overlay.remove(picker)

            # Re-create components that cache colors at init time
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
            self.home_tab.center_panel.sidebar = self.sidebar

            # Restore input text from AppState into the new TextField
            if self.state.input_text:
                self.home_tab.input_panel.set_text(self.state.input_text)

            # Rebuild the tab bar container colors
            self.tab_bar_container.bgcolor = Colors.BACKGROUND
            self.tab_bar_container.border = ft.border.only(
                bottom=ft.BorderSide(1, Colors.DIVIDER)
            )
            self.rebuild_tabs()

            # Reset inspector state so panel starts collapsed after theme switch
            self._active_section = None
            self._last_section = getattr(self, '_last_section', None)

            # Replace the root stack content with a fresh build
            new_root = self.build()
            self.page.controls.clear()
            self.page.add(new_root)

            # Re-attach shell-level pickers to the fresh page overlay
            self.page.overlay.append(self.export_picker)
            self.page.overlay.append(self._glossary_open_picker)

            # The old stack (and the preferences float container) is gone.
            # Reset the open flag so the window can be re-opened.
            self.preferences_window._is_open = False
            self.preferences_window._is_minimized = False
        except Exception:
            _log(f"ERROR in _rebuild_ui:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _close_dialog(self, dialog):
        dialog.open = False
        self.page.update()

    # ------------------------------------------------------------------ #
    #  Expanding Rail Builder Methods
    # ------------------------------------------------------------------ #

    def _build_rail_row(self, icon_asset: str, label: str, section_id: str) -> ft.Container:
        """Build a single Rail_Row with icon, label, and chevron."""
        # Icon container: 48x48, always visible
        icon_container = ft.Container(
            content=UI.icon(icon_asset, 24),
            width=48,
            height=48,
            alignment=ft.alignment.center,
        )

        # Label: visible only when expanded
        label_text = ft.Text(
            label,
            font_family=Fonts.HEADER,
            size=13,
            color=Colors.GOLD,
            visible=False,
            no_wrap=True,
        )

        # Chevron: visible only when expanded, with animated rotation
        chevron_icon = ft.Icon(
            name=ft.Icons.CHEVRON_RIGHT,
            size=16,
            color=Colors.FOREGROUND,
            visible=False,
            rotate=ft.Rotate(angle=0),
            animate_rotation=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )

        # Spacer between label and chevron
        spacer = ft.Container(expand=True)

        # Inner row layout
        inner_row = ft.Row(
            controls=[icon_container, label_text, spacer, chevron_icon],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Outer container for the row
        row_container = ft.Container(
            content=inner_row,
            height=48,
            on_click=lambda e, sid=section_id: self._on_rail_section_click(sid),
            ink=True,
            bgcolor="transparent",
            tooltip=label,
        )

        # Store references for later state updates
        self._rail_labels[section_id] = label_text
        self._rail_chevrons[section_id] = chevron_icon
        self._rail_row_containers[section_id] = row_container

        return row_container

    def _build_section_content_slot(self, section_id: str) -> ft.Container:
        """Build a content container for a section (initially hidden)."""
        try:
            content = self.sidebar.get_section_content(section_id)
        except Exception as e:
            content = ft.Text(
                f"Error loading section: {e}",
                color=Colors.INK_MUTED,
                size=11,
            )

        content_column = ft.Column(
            controls=[content],
            scroll=ft.ScrollMode.AUTO,
        )

        slot = ft.Container(
            content=content_column,
            visible=False,
            padding=ft.padding.only(left=16, right=12, top=8, bottom=8),
            animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
        )

        self._rail_content_slots[section_id] = slot
        return slot

    def _build_expanding_rail(self) -> ft.Container:
        """Build the expanding rail container with all rows and content slots."""
        # Logo section: 32x32 image, centered, with padding below
        logo_section = ft.Container(
            content=ft.Image(
                src="/stimme-logo.png",
                width=32,
                height=32,
                fit=ft.ImageFit.CONTAIN,
            ),
            alignment=ft.alignment.center,
            padding=ft.padding.only(bottom=16, top=12),
        )

        # Build rail rows and content slots for each section
        column_controls: list[ft.Control] = [logo_section]
        for icon_asset, label, section_id in RAIL_SECTIONS:
            row = self._build_rail_row(icon_asset, label, section_id)
            content_slot = self._build_section_content_slot(section_id)
            column_controls.append(row)
            column_controls.append(content_slot)

        # Spacer pushes settings to the bottom
        column_controls.append(ft.Container(expand=True))

        # Settings row: icon + label, on_click opens PreferencesWindow
        settings_icon_container = ft.Container(
            content=UI.icon("SVGs/noun-settings-5527430.svg", 24),
            width=48,
            height=48,
            alignment=ft.alignment.center,
        )
        settings_label = ft.Text(
            "Settings",
            font_family=Fonts.HEADER,
            size=13,
            color=Colors.GOLD,
            visible=False,
            no_wrap=True,
        )
        # Store settings label so expand/collapse can toggle its visibility
        self._rail_labels["settings"] = settings_label

        settings_inner_row = ft.Row(
            controls=[settings_icon_container, settings_label],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        settings_row = ft.Container(
            content=settings_inner_row,
            height=48,
            on_click=lambda e: self._on_rail_section_click("settings"),
            ink=True,
            bgcolor="transparent",
            tooltip="Settings",
        )
        self._rail_row_containers["settings"] = settings_row
        column_controls.append(settings_row)

        # Inner column containing all controls
        inner_column = ft.Column(
            controls=column_controls,
            spacing=4,
            expand=True,
        )

        # Outer expanding container
        self._rail_container = ft.Container(
            content=inner_column,
            width=48,
            animate_size=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            bgcolor=Colors.SIDEBAR_BG,
            border=ft.border.only(left=ft.BorderSide(1, Colors.DIVIDER)),
        )

        return self._rail_container

    # ------------------------------------------------------------------ #
    #  Expanding Rail State Transitions
    # ------------------------------------------------------------------ #

    def _expand_rail(self) -> None:
        """Animate rail to 240px and show labels/chevrons."""
        self._rail_container.width = 240
        for label in self._rail_labels.values():
            label.visible = True
        for chevron in self._rail_chevrons.values():
            chevron.visible = True
        self._rail_expanded = True
        # Suppress tooltips when labels are visible
        for section_id, container in self._rail_row_containers.items():
            container.tooltip = None

    def _collapse_rail(self) -> None:
        """Animate rail to 48px and hide labels/chevrons/content."""
        self._rail_container.width = 48
        for label in self._rail_labels.values():
            label.visible = False
        for chevron in self._rail_chevrons.values():
            chevron.visible = False
            chevron.rotate = ft.Rotate(angle=0)
        for slot in self._rail_content_slots.values():
            slot.visible = False
        for section_id, container in self._rail_row_containers.items():
            container.bgcolor = "transparent"
            # Restore tooltips
            label_ref = self._rail_labels.get(section_id)
            if label_ref:
                container.tooltip = label_ref.value
        self._rail_expanded = False

    def _toggle_rail(self) -> None:
        """Toggle between collapsed and expanded states (Ctrl+B handler)."""
        if self._rail_expanded:
            self._last_section = self._active_section
            self._active_section = None
            self._collapse_rail()
        else:
            section = self._last_section or "model"
            self._active_section = section
            self._expand_rail()
            self._set_active_section(section)
        self.page.update()

    def _set_active_section(self, section_id: str | None) -> None:
        """Show/hide section content, enforce single-expand, update chevrons."""
        # Hide old section content
        if self._active_section and self._active_section in self._rail_content_slots:
            self._rail_content_slots[self._active_section].visible = False
            self._rail_chevrons[self._active_section].rotate = ft.Rotate(angle=0)
            self._rail_row_containers[self._active_section].bgcolor = "transparent"
        # Update active section
        self._active_section = section_id
        # Show new section content
        if section_id and section_id in self._rail_content_slots:
            self._rail_content_slots[section_id].visible = True
            self._rail_chevrons[section_id].rotate = ft.Rotate(angle=math.pi / 2)
            self._rail_row_containers[section_id].bgcolor = Colors.SURFACE_RAISED
        self.page.update()

    def _on_rail_section_click(self, section_id: str) -> None:
        """Handle a Rail_Row click — expand rail if collapsed, toggle section accordion."""
        if section_id == "settings":
            self.preferences_window.open()
            return
        if not self._rail_expanded:
            self._rail_expanded = True
            self._expand_rail()
            self._set_active_section(section_id)
        elif self._active_section == section_id:
            self._set_active_section(None)
        else:
            self._set_active_section(section_id)
        self.page.update()

    # ------------------------------------------------------------------ #
    #  Build
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    #  Keyboard shortcuts
    # ------------------------------------------------------------------ #

    def _on_keyboard_event(self, e: ft.KeyboardEvent):
        """Global keyboard handler. Ctrl+, opens Preferences, Ctrl+B toggles rail."""
        try:
            if e.ctrl and e.key == ",":
                self.preferences_window.open()
            elif e.ctrl and e.key == "B":
                self._toggle_rail()
        except Exception:
            _log(f"Keyboard event error: {traceback.format_exc()}")



    # ------------------------------------------------------------------ #
    #  Build
    # ------------------------------------------------------------------ #

    def build(self):
        self._main_container = ft.Container(
            content=ft.Column(
                [self.tab_bar_container, self.content_container],
                expand=True,
                spacing=0,
            ),
            expand=True,
        )

        # Expanding rail (replaces old icon rail + detail panel)
        self._expanding_rail = self._build_expanding_rail()

        # Menu bar slot
        self._menu_bar_component = MenuBarComponent(
            bus=self.bus,
            actions={
                "toggle_sidebar": self._toggle_rail,
                "open_preferences": self.preferences_window.open,
            },
        )
        # We wrap the menu bar in a Container to match the Workspace color
        menu_bar_slot = ft.Container(
            content=self._menu_bar_component.build(),
            bgcolor=Colors.BACKGROUND,
            padding=ft.padding.only(left=8)  # Aligns text with the tabs below
        )
        status_bar_slot = ft.Container(height=0)

        # Body: main content | expanding rail
        body = ft.Row(
            [self._main_container, self._expanding_rail],
            expand=True,
            spacing=0,
        )

        page_column = ft.Column(
            [menu_bar_slot, body, status_bar_slot],
            expand=True,
            spacing=0,
        )

        # Banner overlay — floats below menu bar, above page content
        self._banner_overlay = BannerOverlay(bus=self.bus)
        self.bus.register_banner_overlay(self._banner_overlay)

        # Wrap in a Stack so the PreferencesWindow and HUD can float on top
        self._root_stack = ft.Stack(
            controls=[
                page_column,
                self._banner_overlay.control,
                self.eigenstimme_badge.control,
                self.diagnostics_hud.control,
            ],
            expand=True,
        )
        self.preferences_window.register_stack(self._root_stack)
        return self._root_stack
