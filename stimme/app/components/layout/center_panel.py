import flet as ft
import traceback
from app.contexts.settings import SettingsManager
from app.theme import Colors, Fonts
from app.components.widgets.img_icon import ImgIcon
from app.components.views.pdf_viewer import WebView_PDF_Viewer
from app.components.tabs.log_tab import LogTab


def _log(msg):
    print(f"[CenterPanel] {msg}")


class CenterPanel:
    """Tabbed workspace panel. Reads PDF/log/commentary state from AppState."""

    def __init__(self, page: ft.Page, settings: SettingsManager, sidebar=None, state=None, actions=None):
        self.page = page
        self.settings = settings
        self.sidebar = sidebar  # Only for thematic focus sync (last bidirectional ref)
        self.state = state
        self.actions = actions or {}

        # Icons
        self.quill_icon = ImgIcon("icon-quill.svg", 28, 28)
        self.book_icon = ImgIcon("icon-book.svg", 28, 28)
        self.sun_welcome_icon = ImgIcon("welcome.svg", 28, 28)
        self.theme_icon = ImgIcon("icon-theme.svg", 28, 28)
        self.glossary_icon = ImgIcon("icon-book-open.svg", 28, 28)

        # Components (these are UI objects, not state)
        self.pdf_viewer = WebView_PDF_Viewer(page)
        self.log_tab = LogTab(page)

        # Thematic focus textarea (synced with sidebar)
        self.thematic_focus = ft.TextField(
            multiline=True,
            min_lines=15,
            max_lines=20,
            value=settings.get_thematic_focus(),
            on_change=self.on_thematic_focus_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            hint_text="e.g. Render in a theological register...",
            hint_style=ft.TextStyle(color=Colors.INK_MUTED, italic=True, size=15, font_family=Fonts.SERIF),
            text_style=ft.TextStyle(size=15, font_family=Fonts.SERIF, italic=True),
            content_padding=ft.padding.all(16),
        )

        self.datasets_container = ft.Column(spacing=8)
        self.add_dataset_btn = ft.IconButton(
            icon=ft.Icons.ADD,
            icon_color=Colors.FOREGROUND,
            icon_size=20,
            bgcolor=Colors.SURFACE_RAISED,
            on_click=self.on_add_button_click,
            width=44, height=44,
            style=ft.ButtonStyle(padding=ft.padding.all(0)),
            tooltip="Select datasets",
        )

        self.tabs = None
        self.container = None
        self._show_datasets_tab = False
        self._show_glossary_tab = False
        self._show_corrections_tab = False
        self.rebuild_tabs()
        _log("Initialized")

    # ------------------------------------------------------------------
    # State accessors (read from AppState, fall back to defaults)
    # ------------------------------------------------------------------

    @property
    def _center_tab(self):
        return self.state.center_tab if self.state else 0

    @_center_tab.setter
    def _center_tab(self, value):
        if self.state:
            self.state.center_tab = value

    @property
    def _show_logs(self):
        return self.state.show_logs if self.state else False

    @property
    def _pdf_file(self):
        return self.state.pdf_file if self.state else None

    @property
    def _commentary(self):
        return self.state.commentary if self.state else None

    # ------------------------------------------------------------------
    # Thematic focus sync
    # ------------------------------------------------------------------

    def on_thematic_focus_change(self, e):
        try:
            new_value = self.thematic_focus.value
            self.settings.settings["thematic_focus"] = new_value
            if self.sidebar and self.sidebar.thematic_focus.value != new_value:
                self.sidebar.thematic_focus.value = new_value
                self.page.update()
            self._schedule_focus_save()
        except Exception:
            _log(f"ERROR in on_thematic_focus_change:\n{traceback.format_exc()}")

    def _schedule_focus_save(self):
        import threading
        if hasattr(self, '_focus_save_timer') and self._focus_save_timer:
            self._focus_save_timer.cancel()
        self._focus_save_timer = threading.Timer(1.0, self._do_focus_save)
        self._focus_save_timer.daemon = True
        self._focus_save_timer.start()

    def _do_focus_save(self):
        try:
            self.settings.save_settings()
        except Exception:
            _log(f"ERROR in _do_focus_save:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Dataset management
    # ------------------------------------------------------------------

    def on_add_button_click(self, e):
        try:
            # Guard: don't open if a dialog is already showing
            if self.page.dialog and hasattr(self.page.dialog, 'open') and self.page.dialog.open:
                _log("on_add_button_click skipped — dialog already open")
                return

            from pathlib import Path
            lancedb_path = Path(__file__).parent.parent.parent / "lancedb_vectors"
            available_datasets = []
            if lancedb_path.exists():
                for item in lancedb_path.iterdir():
                    if item.is_dir() and item.suffix == ".lance":
                        available_datasets.append(item.stem)
                    elif item.is_file() and item.suffix == ".csv":
                        available_datasets.append(item.stem)
            _log(f"Datasets found at {lancedb_path}: {available_datasets}")

            if not available_datasets:
                info_dialog = ft.AlertDialog(
                    title=ft.Text("No Datasets"),
                    content=ft.Text(f"No datasets found in:\n{lancedb_path}"),
                    actions=[ft.TextButton(content=ft.Text("OK", font_family=Fonts.FRAKTUR), on_click=lambda e: self.close_dialog(info_dialog))],
                )
                self.page.dialog = info_dialog
                info_dialog.open = True
                self.page.update()
                return

            current_datasets = set(self.settings.get_datasets())
            dataset_checkboxes = [
                ft.Checkbox(label=ds, value=ds in current_datasets, data=ds)
                for ds in sorted(available_datasets)
            ]

            def on_apply(dialog_e):
                try:
                    selected = [cb.data for cb in dataset_checkboxes if cb.value]
                    _log(f"Datasets selected: {selected}")
                    self.settings.settings["datasets"] = selected
                    self.settings.save_settings()
                    self.rebuild_tabs()
                    if self.sidebar:
                        self.sidebar.update_datasets_display()
                    picker_dialog.open = False
                    self.page.update()
                except Exception:
                    _log(f"ERROR in dataset on_apply:\n{traceback.format_exc()}")

            picker_dialog = ft.AlertDialog(
                title=ft.Text("Select Datasets"),
                content=ft.Column(dataset_checkboxes, tight=True, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton(content=ft.Text("Cancel", font_family=Fonts.FRAKTUR), on_click=lambda e: self.close_dialog(picker_dialog)),
                    ft.TextButton(content=ft.Text("Apply", font_family=Fonts.FRAKTUR), on_click=on_apply),
                ],
            )
            self.page.dialog = picker_dialog
            picker_dialog.open = True
            self.page.update()
        except Exception:
            _log(f"ERROR in on_add_button_click:\n{traceback.format_exc()}")

    def update_datasets_display(self):
        try:
            self.datasets_container.controls.clear()
            datasets = self.settings.get_datasets()
            if not datasets:
                self.datasets_container.controls.append(
                    ft.Text("None active.", italic=True, color=Colors.INK_MUTED)
                )
            else:
                row = ft.Row(wrap=True, spacing=8)
                for ds in datasets:
                    badge = ft.Container(
                        content=ft.Row([
                            ft.Text(ds),
                            ft.IconButton(ft.Icons.CLOSE, icon_size=12, on_click=self.remove_dataset(ds)),
                        ], tight=True),
                        bgcolor=Colors.SURFACE_RAISED, border_radius=4, padding=4,
                    )
                    row.controls.append(badge)
                self.datasets_container.controls.append(row)
        except Exception:
            _log(f"ERROR in update_datasets_display:\n{traceback.format_exc()}")

    def remove_dataset(self, dataset_name):
        def _remove(e):
            try:
                self.settings.remove_dataset(dataset_name)
                self.rebuild_tabs()
                if self.sidebar:
                    self.sidebar.update_datasets_display()
                self.page.update()
            except Exception:
                _log(f"ERROR in remove_dataset({dataset_name}):\n{traceback.format_exc()}")
        return _remove

    # ------------------------------------------------------------------
    # Actions (mutate AppState, then rebuild)
    # ------------------------------------------------------------------

    def set_pdf_file(self, pdf_file, pdf_path=None):
        """Load a PDF into the viewer and update state."""
        try:
            _log(f"set_pdf_file: {pdf_file}")
            if self.state:
                self.state.set_pdf(pdf_file, pdf_path)
            if pdf_path:
                self.pdf_viewer.load_pdf(pdf_path, pdf_file)
            self.rebuild_tabs()
            self.page.update()
        except Exception:
            _log(f"ERROR in set_pdf_file:\n{traceback.format_exc()}")

    def clear_pdf(self):
        """Clear PDF state and viewer."""
        try:
            _log("clear_pdf called")
            if self.state:
                self.state.clear_pdf()
            self.pdf_viewer.cleanup()
            self.rebuild_tabs()
            self.page.update()
        except Exception:
            _log(f"ERROR in clear_pdf:\n{traceback.format_exc()}")

    def set_commentary(self, commentary: str):
        """Set commentary text in state."""
        try:
            _log("set_commentary called")
            if self.state:
                self.state.set_commentary(commentary)
            self.rebuild_tabs()
        except Exception:
            _log(f"ERROR in set_commentary:\n{traceback.format_exc()}")

    def start_log_session(self):
        """Switch to terminal log view."""
        try:
            _log("start_log_session called")
            if self.state:
                self.state.start_log_session()
            self.log_tab = LogTab(self.page)
            self.log_tab.append("✨ Brain initializing...")
            self.rebuild_tabs()
            self.page.update()
        except Exception:
            _log(f"ERROR in start_log_session:\n{traceback.format_exc()}")

    def end_log_session(self):
        """Return to Welcome/PDF view."""
        try:
            _log("end_log_session called")
            if self.state:
                self.state.end_log_session()
            self.rebuild_tabs()
            self.page.update()
        except Exception:
            _log(f"ERROR in end_log_session:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Tab system (reads from AppState properties)
    # ------------------------------------------------------------------

    def rebuild_tabs(self):
        try:
            tab_headers = []
            tab_contents = []
            closeable_indices = set()

            # Primary slot: Logs OR PDF OR Welcome
            if self._show_logs:
                tab_headers.append(("System Log", ft.Icons.TERMINAL))
                tab_contents.append(self.log_tab.build())
            elif self._pdf_file:
                tab_headers.append(("PDF", ft.Icons.PICTURE_AS_PDF))
                tab_contents.append(self._build_pdf_tab())
            else:
                tab_headers.append(("Welcome", "/welcome.svg"))
                tab_contents.append(self._build_welcome_content())

            # Focus tab
            tab_headers.append(("Focus", self.theme_icon))
            tab_contents.append(self._build_focus_content())

            # Datasets tab (closeable, only shown when opened)
            if self._show_datasets_tab:
                closeable_indices.add(len(tab_headers))
                tab_headers.append(("Datasets", self.book_icon))
                tab_contents.append(self._build_datasets_content())

            # Glossary tab (closeable, only shown when opened)
            if self._show_glossary_tab:
                closeable_indices.add(len(tab_headers))
                tab_headers.append(("Glossary", self.glossary_icon))
                tab_contents.append(self._build_glossary_content())

            # Corrections tab (closeable, only shown when opened)
            if self._show_corrections_tab:
                closeable_indices.add(len(tab_headers))
                tab_headers.append(("Corrections", ft.Icons.EDIT_NOTE))
                tab_contents.append(self._build_corrections_content())

            # Commentary tab (only if scholar mode)
            if self.settings.get_scholar_mode():
                tab_headers.append(("Commentary", self.quill_icon))
                tab_contents.append(self._build_commentary_content())

            # Clamp tab index
            if self._center_tab >= len(tab_contents):
                self._center_tab = 0

            # Build header row
            header_row = ft.Row(spacing=2, scroll=ft.ScrollMode.AUTO)
            for i, (title, icon) in enumerate(tab_headers):
                is_active = (i == self._center_tab)
                if isinstance(icon, str) and icon.startswith("/"):
                    icon_ctrl = ft.Image(src=icon, width=16)
                elif isinstance(icon, ImgIcon):
                    icon_ctrl = icon.build()
                else:
                    icon_ctrl = ft.Icon(icon, size=16, color=Colors.GOLD if is_active else Colors.INK_MUTED)

                row_controls = [
                    icon_ctrl,
                    ft.Text(
                        title, size=13,
                        color=Colors.GOLD if is_active else Colors.INK_MUTED,
                        weight="bold" if is_active else None,
                    ),
                ]
                if i in closeable_indices:
                    row_controls.append(ft.IconButton(
                        ft.Icons.CLOSE, icon_size=12, icon_color=Colors.INK_MUTED,
                        padding=ft.padding.all(0), width=20, height=20,
                        on_click=lambda e, t=title: self._close_center_tab(t),
                    ))

                header_row.controls.append(
                    ft.Container(
                        content=ft.Row(row_controls, spacing=6),
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        bgcolor=Colors.BACKGROUND if is_active else Colors.SURFACE,
                        border_radius=ft.border_radius.only(top_left=6, top_right=6),
                        on_click=lambda e, idx=i: self.switch_tab(idx),
                    )
                )

            self.tabs = ft.Column(
                [
                    ft.Container(content=header_row, bgcolor=Colors.SURFACE),
                    ft.Container(content=tab_contents[self._center_tab], expand=True),
                ],
                expand=True,
            )

            if self.container is not None:
                self.container.content = self.tabs

        except Exception:
            _log(f"ERROR in rebuild_tabs:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Tab content builders
    # ------------------------------------------------------------------

    def _build_welcome_content(self):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Image(src="/stimme-s.png", width=165),
                    ft.Text(
                        "A scholarly workbench for the careful rendering of German into English.",
                        italic=True, size=15, color=Colors.INK_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
            expand=True,
            alignment=ft.alignment.center,
        )

    def _build_pdf_tab(self):
        def _close_pdf(e):
            try:
                _log("PDF close button clicked")
                fn = self.actions.get("global_clear_pdf")
                if fn:
                    fn()
                else:
                    self.clear_pdf()
            except Exception:
                _log(f"ERROR in _close_pdf:\n{traceback.format_exc()}")

        close_btn = ft.IconButton(
            ft.Icons.CLOSE, icon_size=14, icon_color=Colors.INK_MUTED,
            on_click=_close_pdf, tooltip="Close PDF",
            width=28, height=28, style=ft.ButtonStyle(padding=ft.padding.all(0)),
        )
        return ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Text(self._pdf_file or "PDF", size=13, color=Colors.INK_MUTED),
                    ft.Container(expand=True),
                    close_btn,
                ]),
                padding=ft.padding.symmetric(horizontal=12, vertical=4),
                bgcolor=Colors.SURFACE,
            ),
            ft.Container(content=self.pdf_viewer.build(), expand=True),
        ], expand=True, spacing=0)

    def _build_focus_content(self):
        return ft.Container(
            padding=32,
            content=ft.Column([
                ft.Row([self.quill_icon.build(), ft.Text("Thematic Focus", size=24, font_family=Fonts.HEADER)]),
                ft.Container(content=self.thematic_focus, expand=True),
            ], spacing=16),
            expand=True,
        )

    def _build_datasets_content(self):
        self.update_datasets_display()
        return ft.Container(
            padding=32,
            content=ft.Column([
                ft.Row([self.book_icon.build(), ft.Text("Datasets", size=24, font_family=Fonts.HEADER)]),
                self.datasets_container,
                self.add_dataset_btn,
            ], spacing=16, scroll=ft.ScrollMode.AUTO),
            expand=True,
        )

    def _build_commentary_content(self):
        commentary = self._commentary
        if commentary:
            content = ft.Markdown(commentary, selectable=True)
        else:
            content = ft.Text("Translation Commentary can be viewed here.", italic=True, color=Colors.INK_MUTED)
        return ft.Container(
            padding=32,
            content=ft.Column([
                ft.Row([self.quill_icon.build(), ft.Text("Commentary", size=24, font_family=Fonts.HEADER)]),
                ft.ListView(controls=[content], spacing=0, expand=True),
            ], spacing=16),
            expand=True,
        )

    def _build_glossary_content(self):
        """Build the glossary tab content using GlossaryView."""
        from app.components.views.glossary_view import GlossaryView
        return GlossaryView(self.page, actions=self.actions).build()

    def _close_center_tab(self, title: str):
        """Close a closeable center panel tab by title."""
        try:
            if title == "Datasets":
                self._show_datasets_tab = False
            elif title == "Glossary":
                self._show_glossary_tab = False
            elif title == "Corrections":
                self._show_corrections_tab = False
            self._center_tab = 0
            self.rebuild_tabs()
            self.page.update()
        except Exception:
            _log(f"ERROR in _close_center_tab({title}):\n{traceback.format_exc()}")

    def switch_to_glossary(self):
        """Open and switch the center panel to the Glossary tab."""
        self._show_glossary_tab = True
        self.rebuild_tabs()
        # Find the glossary tab index dynamically
        for i, (title, _) in enumerate(self._get_tab_titles()):
            if title == "Glossary":
                self._center_tab = i
                break
        self.rebuild_tabs()

    def switch_to_datasets(self):
        """Open and switch the center panel to the Datasets tab."""
        self._show_datasets_tab = True
        self.rebuild_tabs()
        # Find the datasets tab index dynamically
        for i, (title, _) in enumerate(self._get_tab_titles()):
            if title == "Datasets":
                self._center_tab = i
                break
        self.rebuild_tabs()

    def switch_to_corrections(self):
        """Open and switch the center panel to the Corrections tab."""
        self._show_corrections_tab = True
        self.rebuild_tabs()
        for i, (title, _) in enumerate(self._get_tab_titles()):
            if title == "Corrections":
                self._center_tab = i
                break
        self.rebuild_tabs()

    def _build_corrections_content(self):
        """Build the corrections tab content using CorrectionsTab."""
        from app.components.tabs.corrections_tab import CorrectionsTab
        from app.event_bus import EventBus

        correction_service = self.actions.get("correction_service")
        # Lazily resolve if not yet initialized
        if correction_service is None:
            getter = self.actions.get("get_correction_service")
            if getter:
                correction_service = getter()
        bus = self.actions.get("bus")
        if correction_service and bus:
            tab = CorrectionsTab(self.page, correction_service, bus)
            return tab.build()
        # Fallback if service not available yet
        return ft.Container(
            content=ft.Text(
                "Corrections service not available. Translate something first.",
                color=Colors.INK_MUTED, italic=True, font_family=Fonts.SERIF,
            ),
            alignment=ft.alignment.center,
            expand=True,
        )

    def _get_tab_titles(self):
        """Helper to get current tab titles for index lookup."""
        titles = []
        if self._show_logs:
            titles.append(("System Log", None))
        elif self._pdf_file:
            titles.append(("PDF", None))
        else:
            titles.append(("Welcome", None))
        titles.append(("Focus", None))
        if self._show_datasets_tab:
            titles.append(("Datasets", None))
        if self._show_glossary_tab:
            titles.append(("Glossary", None))
        if self._show_corrections_tab:
            titles.append(("Corrections", None))
        if self.settings.get_scholar_mode():
            titles.append(("Commentary", None))
        return titles

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def switch_tab(self, index):
        try:
            _log(f"switch_tab({index})")
            if self._show_logs and index != 0:
                if self.state:
                    self.state.show_logs = False
            self._center_tab = index
            self.rebuild_tabs()
            self.page.update()
        except Exception:
            _log(f"ERROR in switch_tab:\n{traceback.format_exc()}")

    def build(self):
        self.container = ft.Container(content=self.tabs, expand=True, bgcolor=Colors.BACKGROUND)
        return self.container

    def close_dialog(self, dialog):
        try:
            dialog.open = False
            self.page.update()
        except Exception:
            _log(f"ERROR in close_dialog:\n{traceback.format_exc()}")
