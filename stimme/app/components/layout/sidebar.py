import flet as ft
import traceback
from app.contexts.settings import SettingsManager
from app.theme import Colors, Fonts, UI
from app.constants import AVAILABLE_MODELS


def _log(msg):
    print(f"[Sidebar] {msg}")


class Sidebar:
    def __init__(self, page: ft.Page, settings: SettingsManager, bus=None, actions=None):
        self.page = page
        self.settings = settings
        self.bus = bus
        self.actions = actions or {}

        # 1. Icons
        self.monk_icon = UI.icon("icon-monk.svg")
        self.quill_icon = UI.icon("icon-quill.svg")
        self.book_icon = UI.icon("icon-book.svg")
        self.key_icon = UI.icon("icon-key.svg")
        self.scroll_icon = UI.icon("icon-scroll.svg")
        self.theme_icon = UI.icon("icon-theme.svg")
        self.openbook_icon = UI.icon("icon-book-open.svg")

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
        self.browse_export_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN, icon_color=Colors.FOREGROUND,
            bgcolor=Colors.SURFACE_RAISED, on_click=self.on_browse_export_directory,
        )
        self.add_dataset_btn = ft.Container(
            content=ft.Row([
                UI.icon("icon-book.svg", size=16),
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
                UI.icon("icon-book-open.svg", size=16),
                ft.Text("View Datasets", size=12, color=Colors.GOLD),
            ], spacing=6),
            on_click=self._on_view_datasets_click,
            ink=True,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=Colors.SURFACE_RAISED,
        )
        self.datasets_container = ft.Column(spacing=6)

        # 5. Collapsible section state & chevrons
        self._sections_open = {
            "model": False,
            "scholar": False,
            "focus": False,
            "export": False,
            "datasets": False,
            "glossary": False,
            "keys": False,
        }
        self._chevrons = {
            name: ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=Colors.INK_MUTED)
            for name in self._sections_open
        }

        # Section content containers (all start hidden)
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
        self.glossary_icon = UI.icon("icon-book.svg")
        self.add_glossary_btn = ft.Container(
            content=ft.Row([
                UI.icon("icon-edit.svg", size=16),
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
                UI.icon("icon-book-open.svg", size=16),
                ft.Text("View Glossary", size=12, color=Colors.GOLD),
            ], spacing=6),
            on_click=self._on_view_glossary_click,
            ink=True,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=Colors.SURFACE_RAISED,
        )
        self.glossary_container = ft.Column(spacing=6, visible=False)

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

    def _toggle_section(self, name, content_control):
        """Generic toggle for any collapsible section."""
        try:
            self._sections_open[name] = not self._sections_open[name]
            is_open = self._sections_open[name]
            self._chevrons[name].name = ft.Icons.KEYBOARD_ARROW_UP if is_open else ft.Icons.KEYBOARD_ARROW_DOWN
            content_control.visible = is_open
            if name == "glossary" and is_open:
                self.update_glossary_display()
            self.page.update()
        except Exception:
            _log(f"ERROR in _toggle_section({name}):\n{traceback.format_exc()}")

    def toggle_model(self, e):
        self._toggle_section("model", self.model_content)

    def toggle_scholar(self, e):
        self._toggle_section("scholar", self.scholar_content)

    def toggle_focus(self, e):
        self._toggle_section("focus", self.focus_content)

    def toggle_export(self, e):
        self._toggle_section("export", self.export_content)

    def toggle_datasets(self, e):
        self._toggle_section("datasets", self.datasets_content)

    def toggle_glossary(self, e):
        self._toggle_section("glossary", self.glossary_container)

    def _on_view_glossary_click(self, e):
        """Open the Glossary tab in the center panel."""
        try:
            open_glossary = self.actions.get("open_glossary_tab")
            if open_glossary:
                open_glossary()
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

    def toggle_keys(self, e):
        self._toggle_section("keys", self.keys_content)

    def update_glossary_display(self):
        """Refresh the sidebar glossary section — shows only pinned terms."""
        try:
            self.glossary_container.controls.clear()
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

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _collapsible_header(self, title, icon_widget, chevron, on_tap, extra_icons=None):
        """Build a clickable collapsible section header row."""
        row_controls = [icon_widget]
        row_controls.append(
            ft.Text(title, size=13, font_family=Fonts.HEADER, color=Colors.GOLD, weight="bold")
        )
        row_controls.append(ft.Container(expand=True))
        if extra_icons:
            row_controls.extend(extra_icons)
        row_controls.append(chevron)
        return ft.GestureDetector(
            on_tap=on_tap, mouse_cursor=ft.MouseCursor.CLICK,
            content=ft.Row(row_controls),
        )

    def build(self):
        self.update_datasets_display()
        return ft.Container(
            expand=True, width=288, bgcolor=Colors.SIDEBAR_BG,
            border=ft.border.only(left=ft.BorderSide(1, Colors.DIVIDER)),
            padding=ft.padding.all(20),
            content=ft.Column(expand=True, spacing=0, controls=[
                ft.ListView(expand=True, spacing=16, controls=[
                    # Logo
                    ft.Container(
                        content=ft.Image(src="/stimme-logo.png", width=192, height=120, fit=ft.ImageFit.CONTAIN),
                        alignment=ft.alignment.center, padding=ft.padding.only(bottom=10),
                    ),
                    # Model
                    ft.Column([
                        self._collapsible_header("Model", self.monk_icon, self._chevrons["model"], self.toggle_model),
                        self.model_content,
                    ], spacing=8),
                    # Scholar Mode
                    ft.Column([
                        self._collapsible_header("Scholar Mode", self.quill_icon, self._chevrons["scholar"], self.toggle_scholar),
                        self.scholar_content,
                    ], spacing=8),
                    # Thematic Focus
                    ft.Column([
                        self._collapsible_header("Thematic Focus", self.theme_icon, self._chevrons["focus"], self.toggle_focus),
                        self.focus_content,
                    ], spacing=8),
                    # Export Directory
                    ft.Column([
                        self._collapsible_header("Export Directory", self.scroll_icon, self._chevrons["export"], self.toggle_export),
                        self.export_content,
                    ], spacing=8),
                    # Datasets
                    ft.Column([
                        self._collapsible_header("Datasets", self.openbook_icon, self._chevrons["datasets"], self.toggle_datasets),
                        self.datasets_content,
                    ], spacing=8),
                    # Glossary
                    ft.Column([
                        self._collapsible_header("Glossary", self.glossary_icon, self._chevrons["glossary"], self.toggle_glossary),
                        self.glossary_container,
                    ], spacing=8),
                    # API Keys
                    ft.Column([
                        self._collapsible_header("API Keys", self.key_icon, self._chevrons["keys"], self.toggle_keys, extra_icons=[self.api_status_icon]),
                        self.keys_content,
                    ], spacing=8),
                ]),
                # Settings button pinned to bottom
                ft.Container(
                    content=ft.Row([
                        UI.icon("icon-settings.svg", size=20),
                        ft.Text("Settings", size=14, font_family=Fonts.FRAKTUR, color=Colors.GOLD),
                    ], spacing=8),
                    padding=ft.padding.only(top=12),
                    on_click=lambda _: None,
                    ink=True,
                    border_radius=6,
                ),
            ]),
        )
