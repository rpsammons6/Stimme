import flet as ft
import threading
import traceback
from app.services.configuration_service import ConfigurationService
from app.theme import Colors, Fonts, UI
from app.constants import AVAILABLE_MODELS


def _log(msg):
    print(f"[Sidebar] {msg}")


class Sidebar:
    def __init__(self, page: ft.Page, settings: ConfigurationService, bus=None, actions=None):
        self.page = page
        self.settings = settings
        self.bus = bus
        self.actions = actions or {}

        # 1. Icons
        self.monk_icon = UI.icon("SVGs/noun-apple-5527427.svg")
        self.quill_icon = UI.icon("SVGs/noun-edit-5527393.svg")
        self.book_icon = UI.icon("SVGs/noun-book-5527435.svg")
        self.key_icon = UI.icon("SVGs/noun-key-5527436.svg")
        self.scroll_icon = UI.icon("SVGs/noun-folder-5441888.svg")
        self.theme_icon = UI.icon("SVGs/noun-puzzle-5441853.svg")
        self.openbook_icon = UI.icon("SVGs/noun-database-5527402.svg")

        # 2. Input Fields
        self.export_directory_field = UI.text_field(
            value=settings.get_export_directory(), read_only=True, hint="Choose export destination…"
        )
        self.thematic_focus = UI.text_field(
            value=settings.get_thematic_focus(), multiline=True,
            on_change=self.on_thematic_focus_change, hint="e.g. theological, archaic register…"
        )
        self.api_key_field = UI.text_field(
            value=settings.get_api_key() if settings.get_remember_api_key() else "",
            on_change=self.on_api_key_change, mono=True, hint="sk-ant-…"
        )
        self.api_key_field.password = True

        # 3. Dropdowns & Switches
        self.model_dropdown = UI.dropdown(AVAILABLE_MODELS, value=settings.get_model(), on_change=self.on_model_change)
        self.scholar_mode_switch = UI.switch(value=settings.get_scholar_mode(), on_change=self.on_scholar_mode_change)
        self.remember_api_key_switch = UI.switch(value=settings.get_remember_api_key(), on_change=self.on_remember_api_key_change)

        # 4. Buttons
        self.browse_export_btn = ft.Container(
            content=UI.icon("SVGs/noun-folder-5441888.svg", 20),
            on_click=self.on_browse_export_directory,
            ink=True,
            border_radius=6,
            bgcolor=Colors.SURFACE_RAISED,
            padding=ft.padding.all(8),
        )
        self.add_dataset_btn = ft.Container(
            content=ft.Row([
                UI.icon("SVGs/noun-database-5527402.svg", size=16),
                ft.Text("Quick Add", size=12, color=Colors.GOLD),
            ], spacing=6),
            on_click=self.on_add_button_click,
            ink=True,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=Colors.SURFACE_RAISED,
            tooltip="Select datasets",
        )
        self.view_datasets_btn = ft.Container(
            content=ft.Row([
                UI.icon("SVGs/noun-database-5527402.svg", size=16),
                ft.Text("View Datasets", size=12, color=Colors.GOLD),
            ], spacing=6),
            on_click=self._on_view_datasets_click,
            ink=True,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=Colors.SURFACE_RAISED,
        )
        self.datasets_container = ft.Column(spacing=6)

        # Section content containers
        self.model_content = ft.Column(controls=[self.model_dropdown], spacing=8, visible=False)
        self.scholar_content = ft.Column(controls=[
            UI.card(UI.settings_row("Philological commentary", "Annotate the translation", self.scholar_mode_switch)),
        ], spacing=8, visible=False)
        self.focus_content = ft.Column(controls=[self.thematic_focus], spacing=8, visible=False)
        self.export_content = ft.Column(controls=[
            UI.card(ft.Row([ft.Container(content=self.export_directory_field, expand=True), self.browse_export_btn], spacing=8)),
        ], spacing=8, visible=False)
        self.datasets_content = ft.Column(controls=[self.datasets_container, ft.Row([self.add_dataset_btn, self.view_datasets_btn], spacing=6)], spacing=8, visible=False)

        # Glossary Section
        self.glossary_icon = UI.icon("SVGs/noun-book-5527435.svg")
        self.add_glossary_btn = ft.Container(
            content=ft.Row([
                UI.icon("SVGs/noun-edit-5527393.svg", size=16),
                ft.Text("Quick Add", size=12, color=Colors.GOLD),
            ], spacing=6),
            on_click=self.on_add_glossary_term_click,
            ink=True,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=Colors.SURFACE_RAISED,
            tooltip="Add glossary term",
        )
        self.view_glossary_btn = ft.Container(
            content=ft.Row([
                UI.icon("SVGs/noun-book-5527435.svg", size=16),
                ft.Text("View Glossary", size=12, color=Colors.GOLD),
            ], spacing=6),
            on_click=self._on_view_glossary_click,
            ink=True,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=Colors.SURFACE_RAISED,
        )
        self.glossary_container = ft.Column(spacing=6, visible=False)

        # Active Glossary Selector dropdowns
        self.primary_glossary_dropdown = ft.Dropdown(
            label="Primary Glossary",
            hint_text="Select primary glossary…",
            options=[],
            on_change=self._on_primary_glossary_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            label_style=ft.TextStyle(size=11, color=Colors.GOLD, weight="bold"),
            text_style=ft.TextStyle(size=12),
            border_radius=6,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
        )
        self.secondary_glossary_dropdown = ft.Dropdown(
            label="Secondary Glossary",
            hint_text="None (optional)",
            options=[],
            on_change=self._on_secondary_glossary_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            label_style=ft.TextStyle(size=11, color=Colors.INK_MUTED),
            text_style=ft.TextStyle(size=12),
            border_radius=6,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
        )

        # Import/Export buttons
        self.import_glossary_btn = ft.Container(
            content=ft.Row([
                UI.icon("SVGs/noun-open-folder-5441848.svg", size=16),
                ft.Text("Import", size=12, color=Colors.GOLD),
            ], spacing=6),
            on_click=self._on_import_glossary_click,
            ink=True,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=Colors.SURFACE_RAISED,
            tooltip="Import .glossary or .csv file",
        )
        self.export_glossary_btn = ft.Container(
            content=ft.Row([
                UI.icon("SVGs/noun-download-5441865.svg", size=16),
                ft.Text("Export", size=12, color=Colors.GOLD),
            ], spacing=6),
            on_click=self._on_export_glossary_click,
            ink=True,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=Colors.SURFACE_RAISED,
            tooltip="Export active glossary",
        )

        # File pickers for import/export
        self._import_picker = ft.FilePicker(on_result=self._on_import_picker_result)
        self._export_picker = ft.FilePicker(on_result=self._on_export_picker_result)
        page.overlay.append(self._import_picker)
        page.overlay.append(self._export_picker)

        # API Keys Section
        self.api_status_icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE if settings.has_api_key() else ft.Icons.ERROR,
            size=16, color=Colors.SUCCESS if settings.has_api_key() else Colors.DESTRUCTIVE,
        )
        self.keys_content = ft.Column(controls=[
            self.api_key_field,
            ft.Row([
                ft.Text("Remember API key", size=11, color=Colors.FOREGROUND),
                self.remember_api_key_switch,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ], spacing=8, visible=False)

        # Register EventBus listener for glossary_changed to auto-refresh
        if bus:
            bus.on("glossary_changed", self._on_glossary_changed_event)

    # ------------------------------------------------------------------
    # EventBus handlers
    # ------------------------------------------------------------------

    def _on_glossary_changed_event(self, **kwargs):
        """Handle glossary_changed events from the EventBus.

        Refreshes the glossary dropdowns and pinned terms display.
        """
        try:
            self.refresh_glossary_dropdowns()
            self.update_glossary_display()
        except Exception:
            _log(f"ERROR in _on_glossary_changed_event:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Section content provider
    # ------------------------------------------------------------------

    def get_section_content(self, section_id: str) -> ft.Control:
        """Return an ft.Column of controls for the given section ID.

        Used by the AppShell to populate the detail panel when a section
        icon is clicked in the icon rail.
        """
        if section_id == "model":
            return ft.Column([
                self.model_dropdown,
            ], spacing=12)

        elif section_id == "scholar":
            return ft.Column([
                UI.card(UI.settings_row(
                    "Philological commentary",
                    "Annotate the translation",
                    self.scholar_mode_switch,
                )),
            ], spacing=12)

        elif section_id == "focus":
            return ft.Column([
                self.thematic_focus,
            ], spacing=12)

        elif section_id == "export":
            return ft.Column([
                UI.card(ft.Row([
                    ft.Container(content=self.export_directory_field, expand=True),
                    self.browse_export_btn,
                ], spacing=8)),
            ], spacing=12)

        elif section_id == "datasets":
            return ft.Column([
                self.datasets_container,
                ft.Row([self.add_dataset_btn, self.view_datasets_btn], spacing=6),
            ], spacing=12)

        elif section_id == "glossary":
            return ft.Column([
                self.primary_glossary_dropdown,
                self.secondary_glossary_dropdown,
                ft.Divider(height=1, color=Colors.DIVIDER),
                ft.Row([self.import_glossary_btn, self.export_glossary_btn], spacing=6),
                ft.Divider(height=1, color=Colors.DIVIDER),
                self.glossary_container,
                ft.Row([self.add_glossary_btn, self.view_glossary_btn], spacing=6),
            ], spacing=12)

        elif section_id == "keys":
            return ft.Column([
                self.api_key_field,
                ft.Row([
                    ft.Text("Remember API key", size=11, color=Colors.FOREGROUND),
                    self.remember_api_key_switch,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=12)

        else:
            return ft.Column([
                ft.Text(f"Unknown section: {section_id}", size=11, color=Colors.INK_MUTED),
            ])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call(self, action_name, *args, **kwargs):
        fn = self.actions.get(action_name)
        if fn:
            fn(*args, **kwargs)
        else:
            _log(f"WARNING: action '{action_name}' not available")

    # ------------------------------------------------------------------
    # Logic handlers
    # ------------------------------------------------------------------

    def on_model_change(self, e):
        try:
            if self.model_dropdown.value:
                _log(f"Model changed to: {self.model_dropdown.value}")
                self.settings.set_model(self.model_dropdown.value)
        except Exception:
            _log(f"ERROR in on_model_change:\n{traceback.format_exc()}")

    def on_browse_export_directory(self, e):
        try:
            _log("on_browse_export_directory clicked")
            self._call("open_export_picker")
        except Exception:
            _log(f"ERROR in on_browse_export_directory:\n{traceback.format_exc()}")

    def on_scholar_mode_change(self, e):
        try:
            _log(f"Scholar mode: {self.scholar_mode_switch.value}")
            self.settings.set_scholar_mode(self.scholar_mode_switch.value)
            self._call("rebuild_center_tabs")
            self.page.update()
        except Exception:
            _log(f"ERROR in on_scholar_mode_change:\n{traceback.format_exc()}")

    def on_thematic_focus_change(self, e):
        try:
            new_value = self.thematic_focus.value
            self.settings.settings["thematic_focus"] = new_value
            # Sync will be handled by EventBus in a future pass;
            # for now the center panel reads from settings directly on rebuild
            self._schedule_focus_save()
        except Exception:
            _log(f"ERROR in on_thematic_focus_change:\n{traceback.format_exc()}")

    def _schedule_focus_save(self):
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

    def on_api_key_change(self, e):
        try:
            self.settings.set_api_key(self.api_key_field.value)
            has_key = self.settings.has_api_key()
            self.api_status_icon.name = ft.Icons.CHECK_CIRCLE if has_key else ft.Icons.ERROR
            self.api_status_icon.color = Colors.SUCCESS if has_key else Colors.DESTRUCTIVE
            self.page.update()
        except Exception:
            _log(f"ERROR in on_api_key_change:\n{traceback.format_exc()}")

    def on_remember_api_key_change(self, e):
        try:
            remember = self.remember_api_key_switch.value
            _log(f"Remember API key: {remember}")
            self.settings.set_remember_api_key(remember)
            if not remember:
                self.api_key_field.value = ""
                self.page.update()
        except Exception:
            _log(f"ERROR in on_remember_api_key_change:\n{traceback.format_exc()}")

    def on_add_button_click(self, e):
        """Open the dataset picker dialog via shell action."""
        try:
            self._call("open_dataset_picker", e)
        except Exception:
            _log(f"ERROR in on_add_button_click:\n{traceback.format_exc()}")

    def remove_dataset(self, dataset_name):
        def _remove(e):
            try:
                _log(f"Removing dataset: {dataset_name}")
                self.settings.remove_dataset(dataset_name)
                self.update_datasets_display()
                self._call("rebuild_center_tabs")
                self.page.update()
            except Exception:
                _log(f"ERROR in remove_dataset({dataset_name}):\n{traceback.format_exc()}")
        return _remove


    def _on_view_glossary_click(self, e):
        """Open the active glossary in a new tab in the center panel."""
        try:
            glossary_mgr = self.actions.get("glossary_manager")
            if not glossary_mgr:
                _log("No glossary_manager in actions — cannot view glossary")
                return

            # Get the primary active glossary
            primary = glossary_mgr.primary_glossary
            if primary is None:
                bus = self.actions.get("bus")
                if bus:
                    bus.show_banner("No active glossary selected. Choose one from the dropdown above.", is_error=True)
                return

            # Open it in a dedicated glossary file tab
            open_glossary_file_tab = self.actions.get("open_glossary_file_tab")
            if open_glossary_file_tab:
                open_glossary_file_tab(primary)
        except Exception:
            _log(f"ERROR in _on_view_glossary_click:\n{traceback.format_exc()}")

    def _on_view_datasets_click(self, e):
        """Open the Datasets tab in the center panel."""
        try:
            open_datasets = self.actions.get("open_datasets_tab")
            if open_datasets:
                open_datasets()
        except Exception:
            _log(f"ERROR in _on_view_datasets_click:\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Active Glossary Selector handlers
    # ------------------------------------------------------------------

    def refresh_glossary_dropdowns(self):
        """Refresh the Primary/Secondary glossary dropdown options from GlossaryManager."""
        try:
            glossary_mgr = self.actions.get("glossary_manager")
            if not glossary_mgr:
                return

            files = glossary_mgr.list_glossary_files()
            active = glossary_mgr.active_glossaries

            # Build options list
            primary_options = []
            secondary_options = [ft.dropdown.Option("__none__", "None")]

            for f in files:
                name = f.stem
                primary_options.append(ft.dropdown.Option(str(f), name))
                secondary_options.append(ft.dropdown.Option(str(f), name))

            self.primary_glossary_dropdown.options = primary_options
            self.secondary_glossary_dropdown.options = secondary_options

            # Set current values
            active_paths = glossary_mgr._active_paths
            if len(active_paths) > 0:
                self.primary_glossary_dropdown.value = str(active_paths[0])
            else:
                self.primary_glossary_dropdown.value = None

            if len(active_paths) > 1:
                self.secondary_glossary_dropdown.value = str(active_paths[1])
            else:
                self.secondary_glossary_dropdown.value = "__none__"

        except Exception:
            _log(f"ERROR in refresh_glossary_dropdowns:\n{traceback.format_exc()}")

    def _on_primary_glossary_change(self, e):
        """Handle primary glossary dropdown selection change."""
        try:
            glossary_mgr = self.actions.get("glossary_manager")
            if not glossary_mgr or not e.control.value:
                return

            from pathlib import Path
            path = Path(e.control.value)
            glossary_mgr.set_active(path, slot="primary")
            _log(f"Primary glossary set to: {path.stem}")
        except Exception:
            _log(f"ERROR in _on_primary_glossary_change:\n{traceback.format_exc()}")

    def _on_secondary_glossary_change(self, e):
        """Handle secondary glossary dropdown selection change."""
        try:
            glossary_mgr = self.actions.get("glossary_manager")
            if not glossary_mgr:
                return

            value = e.control.value
            if value == "__none__" or not value:
                # Remove secondary glossary
                if len(glossary_mgr._active_paths) > 1:
                    glossary_mgr._active_paths.pop(1)
                    # Persist
                    if glossary_mgr._config_service is not None:
                        glossary_mgr._config_service.set(
                            "active_glossaries",
                            [str(p) for p in glossary_mgr._active_paths],
                        )
                    if glossary_mgr._event_bus is not None:
                        glossary_mgr._event_bus.emit("glossary_changed")
                return

            from pathlib import Path
            path = Path(value)
            glossary_mgr.set_active(path, slot="secondary")
            _log(f"Secondary glossary set to: {path.stem}")
        except Exception:
            _log(f"ERROR in _on_secondary_glossary_change:\n{traceback.format_exc()}")



    # ------------------------------------------------------------------
    # Import / Export handlers
    # ------------------------------------------------------------------

    def _on_import_glossary_click(self, e):
        """Open file picker for importing a .glossary or .csv file."""
        try:
            self._import_picker.pick_files(
                dialog_title="Import Glossary",
                allowed_extensions=["glossary", "csv"],
                allow_multiple=False,
            )
        except Exception:
            _log(f"ERROR in _on_import_glossary_click:\n{traceback.format_exc()}")

    def _on_export_glossary_click(self, e):
        """Open file picker for exporting the active glossary."""
        try:
            glossary_mgr = self.actions.get("glossary_manager")
            if not glossary_mgr or not glossary_mgr.primary_glossary:
                bus = self.actions.get("bus")
                if bus:
                    bus.show_banner("No active glossary to export.", is_error=True)
                return

            self._export_picker.save_file(
                dialog_title="Export Glossary",
                allowed_extensions=["glossary", "csv"],
                file_name=f"{glossary_mgr.primary_glossary.name}.glossary",
            )
        except Exception:
            _log(f"ERROR in _on_export_glossary_click:\n{traceback.format_exc()}")

    def _on_import_picker_result(self, e: ft.FilePickerResultEvent):
        """Handle the result of the import file picker."""
        try:
            if not e.files or len(e.files) == 0:
                return  # User cancelled

            from pathlib import Path

            file_path = Path(e.files[0].path)
            suffix = file_path.suffix.lower()

            # Validate extension
            if suffix not in (".glossary", ".csv"):
                bus = self.actions.get("bus")
                if bus:
                    bus.show_banner(
                        "Only .glossary and .csv files are supported.",
                        is_error=True,
                    )
                return

            glossary_mgr = self.actions.get("glossary_manager")
            if not glossary_mgr:
                return

            try:
                glossary, conflicts = glossary_mgr.import_glossary(file_path)
            except ValueError as ve:
                bus = self.actions.get("bus")
                if bus:
                    if suffix == ".csv":
                        bus.show_banner(
                            "Error: Failed to import .csv to Glossaries. "
                            "Please compare the format of your CSV to the documentation and try again.",
                            is_error=True,
                        )
                    else:
                        bus.show_banner(f"Import failed: {ve}", is_error=True)
                return
            except FileNotFoundError as fnf:
                bus = self.actions.get("bus")
                if bus:
                    bus.show_banner(f"File not found: {fnf}", is_error=True)
                return

            # If there are conflicts, show the conflict resolution dialog
            if conflicts:
                from app.components.views.glossary.dialogs.conflict_resolution import (
                    ConflictResolutionDialog,
                )

                def _on_resolved(resolved_pairs):
                    self.refresh_glossary_dropdowns()
                    self.update_glossary_display()

                dialog = ConflictResolutionDialog(
                    page=self.page,
                    conflicts=conflicts,
                    actions=self.actions,
                    on_resolved=_on_resolved,
                )
                dialog.show()
            else:
                # No conflicts — success
                bus = self.actions.get("bus")
                if bus:
                    bus.show_banner(f"Imported '{file_path.stem}' successfully.")
                    bus.emit("glossary_changed")
                self.refresh_glossary_dropdowns()
                self.update_glossary_display()

        except Exception:
            _log(f"ERROR in _on_import_picker_result:\n{traceback.format_exc()}")
            bus = self.actions.get("bus")
            if bus:
                bus.show_banner("Import failed unexpectedly.", is_error=True)

    def _on_export_picker_result(self, e: ft.FilePickerResultEvent):
        """Handle the result of the export file picker."""
        try:
            if not e.path:
                return  # User cancelled

            from pathlib import Path

            dest_path = Path(e.path)
            suffix = dest_path.suffix.lower()

            glossary_mgr = self.actions.get("glossary_manager")
            if not glossary_mgr:
                return

            try:
                if suffix == ".csv":
                    glossary_mgr.export_csv(dest_path)
                elif suffix == ".glossary":
                    glossary_mgr.export_glossary(dest_path)
                else:
                    # Default to .glossary if no extension
                    if not suffix:
                        dest_path = dest_path.with_suffix(".glossary")
                    glossary_mgr.export_glossary(dest_path)

                bus = self.actions.get("bus")
                if bus:
                    bus.show_banner(f"Exported to '{dest_path.name}' successfully.")
            except ValueError as ve:
                bus = self.actions.get("bus")
                if bus:
                    bus.show_banner(f"Export failed: {ve}", is_error=True)

        except Exception:
            _log(f"ERROR in _on_export_picker_result:\n{traceback.format_exc()}")
            bus = self.actions.get("bus")
            if bus:
                bus.show_banner("Export failed unexpectedly.", is_error=True)

    def update_glossary_display(self):
        """Refresh the sidebar glossary section — shows only pinned terms."""
        try:
            self.glossary_container.controls.clear()
            self.refresh_glossary_dropdowns()
            glossary_mgr = self.actions.get("glossary_manager")
            if not glossary_mgr:
                self.glossary_container.controls.append(
                    ft.Text("Glossary not available.", size=11, color=Colors.INK_MUTED, italic=True)
                )
                self.glossary_container.controls.append(
                    ft.Row([self.add_glossary_btn, self.view_glossary_btn], spacing=6)
                )
                return
            pinned = glossary_mgr.get_pinned_terms()
            if not pinned:
                self.glossary_container.controls.append(
                    ft.Text("No pinned terms.", size=11, color=Colors.INK_MUTED, italic=True)
                )
            else:
                badges_row = ft.Row(wrap=True, spacing=6, run_spacing=6)
                for term in pinned:
                    badges_row.controls.append(self._glossary_badge(term))
                self.glossary_container.controls.append(badges_row)
            self.glossary_container.controls.append(
                ft.Row([self.add_glossary_btn, self.view_glossary_btn], spacing=6)
            )
        except Exception:
            _log(f"ERROR in update_glossary_display:\n{traceback.format_exc()}")

    def _glossary_badge(self, term):
        """Create a clickable pinned badge: 'German → Target [×]'. Click to edit, × to unpin."""
        display_target = term.context_target if term.context_target != "N/A" else term.english
        label = f"{term.german} → {display_target}"
        if term.field_tag and term.field_tag != "N/A":
            label += f" [{term.field_tag}]"
        return ft.Container(
            content=ft.Row([
                ft.Text(label, size=12, color=Colors.INK),
                ft.IconButton(
                    icon=ft.Icons.CLOSE, icon_size=12,
                    on_click=self._unpin_glossary_term(term.german),
                    icon_color=Colors.INK_MUTED,
                    tooltip="Unpin from sidebar",
                ),
            ], tight=True, spacing=4),
            bgcolor=Colors.SURFACE_RAISED,
            border_radius=4,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            on_click=lambda e, t=term: self._edit_glossary_term(t),
            ink=True,
        )

    def _unpin_glossary_term(self, german: str):
        """Return a handler that unpins the term from the sidebar."""
        def _handler(e):
            try:
                glossary_mgr = self.actions.get("glossary_manager")
                if glossary_mgr:
                    glossary_mgr.unpin_term(german)
                    self.update_glossary_display()
                    self.page.update()
            except Exception:
                _log(f"ERROR unpinning glossary term '{german}':\n{traceback.format_exc()}")
        return _handler

    def _edit_glossary_term(self, term):
        """Open a pre-filled dialog to edit a pinned glossary term."""
        try:
            if self.page.dialog and hasattr(self.page.dialog, 'open') and self.page.dialog.open:
                return

            german_field = UI.text_field(hint="e.g. Geist")
            german_field.value = term.german
            german_field.read_only = True  # Can't change the key
            english_field = UI.text_field(hint="e.g. Spirit")
            english_field.value = term.english
            context_target_field = UI.text_field(hint="e.g. deconstruct")
            context_target_field.value = term.context_target if term.context_target != "N/A" else ""
            field_tag_field = UI.text_field(hint="e.g. Philosophy, Legal, Science…")
            field_tag_field.value = term.field_tag if term.field_tag != "N/A" else ""
            nuance_note_field = UI.text_field(hint="Briefly explain the semantic shift…", multiline=True)
            nuance_note_field.value = term.nuance_note if term.nuance_note != "N/A" else ""

            error_text = ft.Text("", size=11, color=Colors.DESTRUCTIVE, visible=False)

            def on_save(dialog_e):
                try:
                    english = english_field.value.strip() if english_field.value else ""
                    context_target = context_target_field.value.strip() if context_target_field.value else ""
                    field_tag = field_tag_field.value.strip() if field_tag_field.value else ""
                    nuance_note = nuance_note_field.value.strip() if nuance_note_field.value else ""

                    if not english:
                        error_text.value = "English field is required."
                        error_text.visible = True
                        self.page.update()
                        return

                    glossary_mgr = self.actions.get("glossary_manager")
                    if glossary_mgr:
                        glossary_mgr.add_term(term.german, english, context_target, field_tag, nuance_note)
                        # Re-pin since add_term creates a new entry
                        glossary_mgr.pin_term(term.german)
                        self.update_glossary_display()

                    edit_dialog.open = False
                    self.page.update()
                except Exception:
                    _log(f"ERROR in glossary edit on_save:\n{traceback.format_exc()}")

            def on_cancel(dialog_e):
                edit_dialog.open = False
                self.page.update()

            edit_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Edit: {term.german}", font_family=Fonts.HEADER, size=18, color=Colors.GOLD),
                content=ft.Column([
                    ft.Text("German Term", size=12, color=Colors.INK_MUTED),
                    german_field,
                    ft.Text("English (default equivalent) *", size=12, color=Colors.INK_MUTED),
                    english_field,
                    ft.Text("Context-Sensitive Target", size=12, color=Colors.INK_MUTED),
                    context_target_field,
                    ft.Text("Field Tag", size=12, color=Colors.INK_MUTED),
                    field_tag_field,
                    ft.Text("Nuance Note", size=12, color=Colors.INK_MUTED),
                    nuance_note_field,
                    error_text,
                ], spacing=8, tight=True, width=340, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton(content=ft.Text("Cancel", font_family=Fonts.FRAKTUR), on_click=on_cancel),
                    ft.ElevatedButton(content=ft.Text("Save", font_family=Fonts.FRAKTUR, weight="bold"), on_click=on_save, bgcolor=Colors.GOLD, color=Colors.BACKGROUND),
                ],
                bgcolor=Colors.SURFACE,
                shape=ft.RoundedRectangleBorder(radius=12),
            )

            self.page.dialog = edit_dialog
            edit_dialog.open = True
            self.page.update()
        except Exception:
            _log(f"ERROR in _edit_glossary_term:\n{traceback.format_exc()}")

    def on_add_glossary_term_click(self, e):
        """Open a dialog to add a new glossary term."""
        try:
            if self.page.dialog and hasattr(self.page.dialog, 'open') and self.page.dialog.open:
                _log("on_add_glossary_term_click skipped — dialog already open")
                return

            german_field = UI.text_field(hint="e.g. Geist")
            english_field = UI.text_field(hint="e.g. Spirit")
            context_target_field = UI.text_field(hint="e.g. deconstruct")
            field_tag_field = UI.text_field(hint="e.g. Philosophy, Legal, Science…")
            nuance_note_field = UI.text_field(hint="Briefly explain the semantic shift…", multiline=True)

            error_text = ft.Text("", size=11, color=Colors.DESTRUCTIVE, visible=False)

            def on_save(dialog_e):
                try:
                    german = german_field.value.strip() if german_field.value else ""
                    english = english_field.value.strip() if english_field.value else ""
                    context_target = context_target_field.value.strip() if context_target_field.value else ""
                    field_tag = field_tag_field.value.strip() if field_tag_field.value else ""
                    nuance_note = nuance_note_field.value.strip() if nuance_note_field.value else ""

                    if not german or not english:
                        error_text.value = "German and English fields are required."
                        error_text.visible = True
                        self.page.update()
                        return

                    glossary_mgr = self.actions.get("glossary_manager")
                    if glossary_mgr:
                        glossary_mgr.add_term(german, english, context_target, field_tag, nuance_note)
                        self.update_glossary_display()

                    add_dialog.open = False
                    self.page.update()
                except Exception:
                    _log(f"ERROR in glossary on_save:\n{traceback.format_exc()}")

            def on_cancel(dialog_e):
                add_dialog.open = False
                self.page.update()

            add_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Add Glossary Term", font_family=Fonts.HEADER, size=18, color=Colors.GOLD),
                content=ft.Column([
                    ft.Text("German Term *", size=12, color=Colors.INK_MUTED),
                    german_field,
                    ft.Text("English (default equivalent) *", size=12, color=Colors.INK_MUTED),
                    english_field,
                    ft.Text("Context-Sensitive Target", size=12, color=Colors.INK_MUTED),
                    context_target_field,
                    ft.Text("Field Tag", size=12, color=Colors.INK_MUTED),
                    field_tag_field,
                    ft.Text("Nuance Note", size=12, color=Colors.INK_MUTED),
                    nuance_note_field,
                    error_text,
                ], spacing=8, tight=True, width=340, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton(content=ft.Text("Cancel", font_family=Fonts.FRAKTUR), on_click=on_cancel),
                    ft.ElevatedButton(content=ft.Text("Save", font_family=Fonts.FRAKTUR, weight="bold"), on_click=on_save, bgcolor=Colors.GOLD, color=Colors.BACKGROUND),
                ],
                bgcolor=Colors.SURFACE,
                shape=ft.RoundedRectangleBorder(radius=12),
            )

            self.page.dialog = add_dialog
            add_dialog.open = True
            self.page.update()
        except Exception:
            _log(f"ERROR in on_add_glossary_term_click:\n{traceback.format_exc()}")

    def update_datasets_display(self):
        try:
            self.datasets_container.controls.clear()
            datasets = self.settings.get_datasets()
            if not datasets:
                self.datasets_container.controls.append(
                    ft.Text("No datasets active.", size=11, color=Colors.INK_MUTED, italic=True)
                )
            else:
                badges_row = ft.Row(wrap=True, spacing=6, run_spacing=6)
                for dataset in datasets:
                    badges_row.controls.append(UI.badge(dataset, self.remove_dataset(dataset)))
                self.datasets_container.controls.append(badges_row)
        except Exception:
            _log(f"ERROR in update_datasets_display:\n{traceback.format_exc()}")




