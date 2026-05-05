"""PreferencesWindow — floating draggable panel for application preferences.

Implements a "window-in-a-window" pattern: a draggable, resizable floating
container rendered as the top layer of an ``ft.Stack`` in the main Flet page.
This gives the user a separate-window experience (custom title bar with
minimize / close buttons, free-form dragging) without spawning a subprocess
or requiring Flet multi-window support.

The window integrates with the existing two-layer configuration architecture:
- **Global Foundation** (``config.json``) via ``ConfigurationService.set()``
- **Scholarly Persona** (``.stimme`` files) via persona dict serialization

Feature: settings-menu
Requirements: 1.1–1.7, 3.1–3.10, 9.1–9.5, 12.1, 12.2
"""

from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

import flet as ft

from app.services.schema_renderer import SchemaRenderer
from app.services.dirty_state_tracker import DirtyStateTracker
from app.services.action_handler import ActionHandler
from app.theme import Colors, Fonts

if TYPE_CHECKING:
    from app.event_bus import EventBus
    from app.services.configuration_service import ConfigurationService

logger = logging.getLogger(__name__)


def _log(msg: str) -> None:
    print(f"[PreferencesWindow] {msg}")


# ---------------------------------------------------------------------------
# Color constants removed — now using semantic tokens from Colors:
#   _SHADOW → Colors.BACKGROUND
#   _OBSIDIAN → Colors.SIDEBAR_BG
#   _PARCHMENT → Colors.PRIMARY
#   _TITLE_BAR_BG → Colors.SURFACE
# ---------------------------------------------------------------------------

# Floating window dimensions
_WIN_WIDTH = 840
_WIN_HEIGHT = 600
_TITLE_BAR_HEIGHT = 38
_MINIMIZED_WIDTH = 220
_MINIMIZED_HEIGHT = 36


class PreferencesWindow:
    """Floating draggable preferences panel.

    Rendered as the top layer of an ``ft.Stack`` in the main page.  The user
    can drag it by its title bar, minimize it to a small pill at the bottom,
    and close it with the X button.  All controls are lazily rendered per-tab
    and disposed on close to stay within the 5 MB memory ceiling.
    """

    def __init__(
        self,
        page: ft.Page,
        settings: "ConfigurationService",
        bus: "EventBus",
    ) -> None:
        self._page = page
        self._settings = settings
        self._bus = bus

        # Schema path — co-located with the app package
        self._schema_path = Path(__file__).resolve().parents[2] / "settings_schema.json"

        # Sub-components (created lazily on open)
        self._renderer: SchemaRenderer | None = None
        self._tracker = DirtyStateTracker()
        self._action_handler = ActionHandler(settings, bus)

        # Window state
        self._is_open = False
        self._is_minimized = False
        self._current_tab_id: str = ""
        self._current_values: dict[str, Any] = {}

        # Drag position (top-left of the floating container)
        self._pos_x: float = 0.0
        self._pos_y: float = 0.0

        # Flet controls (built on open, disposed on close)
        self._tab_sidebar: ft.Column | None = None
        self._tab_panel_container: ft.Container | None = None
        self._window_content: ft.Column | None = None
        self._file_picker: ft.FilePicker | None = None
        self._pending_file_setting_id: str | None = None

        # The floating container itself (added to / removed from the Stack)
        self._float_container: ft.Container | None = None
        self._minimized_pill: ft.Container | None = None

        # The Stack reference — set by the shell via ``register_stack()``
        self._stack: ft.Stack | None = None

        # Schema lookup cache for config_layer routing
        self._setting_schema_map: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Stack registration (called by AppShell.build)
    # ------------------------------------------------------------------

    def register_stack(self, stack: ft.Stack) -> None:
        """Store a reference to the page-level Stack so we can add/remove
        the floating container at runtime."""
        self._stack = stack

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the Preferences window. No-op if already open."""
        if self._is_open:
            if self._is_minimized:
                self._restore_from_minimized()
            else:
                _log("Already open — no-op")
            return

        if self._stack is None:
            _log("ERROR: Stack not registered — cannot open floating window")
            return

        try:
            _log("Opening Preferences window")

            # 1. Load schema
            self._renderer = SchemaRenderer(self._schema_path)
            self._build_setting_schema_map()

            # 2. Snapshot current config values
            self._current_values = self._settings.get_snapshot()
            self._tracker.snapshot(self._current_values)

            # 3. Build the window layout
            tabs = self._renderer.get_tabs()
            first_tab_id = tabs[0]["id"] if tabs else "interface"

            self._build_tab_sidebar(tabs, first_tab_id)
            self._tab_panel_container = ft.Container(
                expand=True,
                padding=ft.padding.all(24),
                bgcolor=Colors.SIDEBAR_BG,
            )

            # File picker for file_picker widgets
            self._file_picker = ft.FilePicker(on_result=self._on_file_picker_result)
            self._page.overlay.append(self._file_picker)

            # Render the first tab
            self._render_tab(first_tab_id)

            # Bottom bar: Save + Exit
            bottom_bar = self._build_bottom_bar()

            # Assemble the window body (sidebar + tab panel)
            main_row = ft.Row(
                controls=[
                    ft.Container(
                        content=self._tab_sidebar,
                        width=180,
                        bgcolor=Colors.BACKGROUND,
                        padding=ft.padding.symmetric(vertical=16),
                    ),
                    ft.VerticalDivider(width=1, color=Colors.DIVIDER),
                    self._tab_panel_container,
                ],
                expand=True,
                spacing=0,
            )

            self._window_content = ft.Column(
                controls=[main_row, bottom_bar],
                expand=True,
                spacing=0,
            )

            # Build the title bar
            title_bar = self._build_title_bar()

            # Assemble the full floating window
            window_body = ft.Column(
                controls=[title_bar, self._window_content],
                expand=True,
                spacing=0,
            )

            # Center the window initially
            self._pos_x = max(0, (self._page.width - _WIN_WIDTH) / 2) if self._page.width else 100
            self._pos_y = max(0, (self._page.height - _WIN_HEIGHT) / 2) if self._page.height else 60

            self._float_container = ft.Container(
                content=window_body,
                width=_WIN_WIDTH,
                height=_WIN_HEIGHT,
                left=self._pos_x,
                top=self._pos_y,
                bgcolor=Colors.SIDEBAR_BG,
                border_radius=10,
                border=ft.border.all(1, Colors.DIVIDER),
                shadow=ft.BoxShadow(
                    spread_radius=2,
                    blur_radius=20,
                    color="#40000000",
                    offset=ft.Offset(0, 8),
                ),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )

            # Add to the Stack
            self._stack.controls.append(self._float_container)
            self._is_open = True
            self._is_minimized = False
            self._page.update()

            _log("Preferences window opened")

        except Exception:
            _log(f"ERROR opening Preferences window:\n{traceback.format_exc()}")
            self._is_open = False

    def close(self, force: bool = False) -> None:
        """Close the window.

        If *force* is ``False`` and the dirty state is true, show a
        confirmation dialog instead of closing immediately.
        """
        if not self._is_open:
            return

        if not force and self._tracker.is_dirty:
            self._show_discard_dialog()
            return

        self._do_close()

    def auto_save_and_close(self, **kwargs: Any) -> None:
        """Save all pending changes and close.

        Called when a translation operation begins to prevent interference.
        """
        if not self._is_open:
            return

        _log("Auto-saving and closing (translation started)")
        try:
            self._on_save()
        except Exception:
            _log(f"ERROR in auto_save_and_close:\n{traceback.format_exc()}")
        finally:
            self._do_close()

    # ------------------------------------------------------------------
    # Title bar (drag + minimize + close)
    # ------------------------------------------------------------------

    def _build_title_bar(self) -> ft.GestureDetector:
        """Build the custom title bar with drag, minimize, and close."""
        title_text = ft.Text(
            "Einstellungen",
            font_family=Fonts.FRAKTUR,
            size=16,
            color=Colors.GOLD,
        )

        minimize_btn = ft.Container(
            content=ft.Text("—", size=14, color=Colors.INK_MUTED),
            width=30,
            height=26,
            alignment=ft.alignment.center,
            border_radius=4,
            on_click=self._on_minimize,
            on_hover=lambda e: _hover_btn(e, minimize_btn),
        )

        close_btn = ft.Container(
            content=ft.Text("✕", size=13, color=Colors.INK_MUTED),
            width=30,
            height=26,
            alignment=ft.alignment.center,
            border_radius=4,
            on_click=lambda e: self._on_exit(e),
            on_hover=lambda e: _hover_close_btn(e, close_btn),
        )

        bar_content = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(content=title_text, expand=True, padding=ft.padding.only(left=14)),
                    minimize_btn,
                    close_btn,
                    ft.Container(width=6),  # right padding
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
            ),
            height=_TITLE_BAR_HEIGHT,
            bgcolor=Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

        return ft.GestureDetector(
            content=bar_content,
            on_pan_update=self._on_title_bar_drag,
            mouse_cursor=ft.MouseCursor.MOVE,
        )

    def _on_title_bar_drag(self, e: ft.DragUpdateEvent) -> None:
        """Move the floating container by the drag delta."""
        if self._float_container is None:
            return

        self._pos_x = max(0, (self._float_container.left or 0) + e.delta_x)
        self._pos_y = max(0, (self._float_container.top or 0) + e.delta_y)

        self._float_container.left = self._pos_x
        self._float_container.top = self._pos_y

        try:
            self._float_container.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Minimize / Restore
    # ------------------------------------------------------------------

    def _on_minimize(self, e: ft.ControlEvent | None = None) -> None:
        """Collapse the window to a small pill at the bottom of the Stack."""
        if not self._is_open or self._is_minimized:
            return

        _log("Minimizing Preferences window")

        # Hide the full window
        if self._float_container is not None and self._float_container in self._stack.controls:
            self._stack.controls.remove(self._float_container)

        # Build the minimized pill
        self._minimized_pill = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(width=10),
                    ft.Text(
                        "Einstellungen",
                        font_family=Fonts.FRAKTUR,
                        size=13,
                        color=Colors.GOLD,
                    ),
                    ft.Container(
                        content=ft.Text("▲", size=11, color=Colors.INK_MUTED),
                        width=24,
                        height=22,
                        alignment=ft.alignment.center,
                        border_radius=4,
                        on_click=lambda e: self._restore_from_minimized(),
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=_MINIMIZED_WIDTH,
            height=_MINIMIZED_HEIGHT,
            bottom=8,
            right=8,
            bgcolor=Colors.SURFACE,
            border_radius=8,
            border=ft.border.all(1, Colors.DIVIDER),
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=8,
                color="#30000000",
                offset=ft.Offset(0, 4),
            ),
            on_click=lambda e: self._restore_from_minimized(),
        )

        self._stack.controls.append(self._minimized_pill)
        self._is_minimized = True

        try:
            self._page.update()
        except Exception:
            pass

    def _restore_from_minimized(self) -> None:
        """Restore the full window from the minimized pill."""
        if not self._is_minimized:
            return

        _log("Restoring Preferences window from minimized")

        # Remove the pill
        if self._minimized_pill is not None and self._minimized_pill in self._stack.controls:
            self._stack.controls.remove(self._minimized_pill)
        self._minimized_pill = None

        # Re-add the full window
        if self._float_container is not None:
            self._stack.controls.append(self._float_container)

        self._is_minimized = False

        try:
            self._page.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Tab navigation
    # ------------------------------------------------------------------

    def _on_tab_selected(self, tab_id: str) -> None:
        """Switch to the selected tab (lazy rendering)."""
        if tab_id == self._current_tab_id:
            return

        self._render_tab(tab_id)

        # Update sidebar highlight
        self._update_tab_sidebar_highlight(tab_id)

        try:
            self._page.update()
        except Exception:
            _log(f"ERROR updating page after tab switch:\n{traceback.format_exc()}")

    def _render_tab(self, tab_id: str) -> None:
        """Dispose old tab controls and build new ones."""
        if self._renderer is None:
            return

        # Dispose old controls
        if self._tab_panel_container is not None:
            self._tab_panel_container.content = None

        # Build new tab content
        tab_content = self._renderer.render_tab(
            tab_id, self._current_values, self._on_setting_changed,
        )

        self._tab_panel_container.content = ft.Container(
            content=tab_content,
            alignment=ft.alignment.top_center,
            expand=True,
            padding=ft.padding.symmetric(horizontal=32),
        )

        self._current_tab_id = tab_id

    # ------------------------------------------------------------------
    # Save / Exit
    # ------------------------------------------------------------------

    def _on_save(self, e: ft.ControlEvent | None = None) -> None:
        """Persist all changed values to the correct config layer."""
        changes = self._tracker.get_changes()
        if not changes:
            _log("No changes to save")
            return

        _log(f"Saving {len(changes)} change(s)")

        persona_changes: dict[str, Any] = {}
        global_changes: dict[str, Any] = {}

        # Route each change to the correct layer
        for setting_id, value in changes.items():
            schema_entry = self._setting_schema_map.get(setting_id, {})
            config_layer = schema_entry.get("config_layer", "global")

            if config_layer == "persona":
                persona_changes[setting_id] = value
            else:
                global_changes[setting_id] = value

        # Write global-layer changes via ConfigurationService
        for key, value in global_changes.items():
            try:
                self._settings.set(key, value)
            except Exception as exc:
                _log(f"ERROR saving global key '{key}': {exc}")
                self._bus.show_banner(
                    f"Failed to save setting '{key}': {exc}",
                    is_error=True,
                )

        # Write persona-layer changes to the mounted .stimme file
        if persona_changes:
            self._save_persona_changes(persona_changes)

        # Update current values and reset dirty state
        self._current_values.update(changes)
        self._tracker.reset()

        # Rebuild Active Registry and broadcast
        try:
            self._bus.emit("config_reloaded", registry=self._settings.get_snapshot())
        except Exception:
            _log(f"ERROR emitting config_reloaded:\n{traceback.format_exc()}")

        self._bus.show_banner("Settings saved.")

    def _save_persona_changes(self, persona_changes: dict[str, Any]) -> None:
        """Write persona-layer changes to the mounted .stimme file."""
        persona_path = self._settings.get_mounted_persona_path()
        if not persona_path:
            _log("No persona mounted — persona changes will be applied to global layer")
            # Fall back to global layer if no persona is mounted
            for key, value in persona_changes.items():
                try:
                    self._settings.set(key, value)
                except Exception as exc:
                    _log(f"ERROR saving persona key '{key}' to global: {exc}")
            return

        try:
            # Read existing persona, merge changes, write back
            p = Path(persona_path)
            if p.exists():
                existing = json.loads(p.read_text(encoding="utf-8"))
            else:
                existing = {}

            existing.update(persona_changes)
            from app.utils.file_ops import atomic_write
            atomic_write(
                p,
                json.dumps(existing, sort_keys=True, indent=2, ensure_ascii=False),
            )

            # Re-mount to refresh the Active Registry
            self._settings.mount_persona(p)
            _log(f"Persona changes saved to {p.name}")

        except Exception as exc:
            _log(f"ERROR saving persona changes: {exc}")
            self._bus.show_banner(
                f"Failed to save persona settings: {exc}",
                is_error=True,
            )

    def _on_exit(self, e: ft.ControlEvent | None = None) -> None:
        """Exit with dirty-state check."""
        self.close(force=False)

    # ------------------------------------------------------------------
    # Setting change handler
    # ------------------------------------------------------------------

    def _on_setting_changed(self, setting_id: str, value: Any) -> None:
        """Handle a setting value change from the UI."""
        # Handle special action buttons
        if isinstance(value, dict) and "__action__" in value:
            action_id = value["__action__"]
            schema_entry = self._setting_schema_map.get(setting_id, {})

            if schema_entry.get("requires_confirmation", False):
                self._show_confirmation_dialog(action_id, schema_entry)
            else:
                self._action_handler.execute(action_id)
            return

        # Handle file picker browse requests
        if value == "__browse__":
            self._open_file_picker(setting_id)
            return

        # Normal value change — update tracker and current values
        self._tracker.update(setting_id, value)
        self._current_values[setting_id] = value

        # Re-evaluate visible_if dependencies: if this setting is a
        # visibility target for other settings, re-render the current tab
        # so those settings appear or disappear.
        if self._has_visible_if_dependents(setting_id):
            self._render_tab(self._current_tab_id)
            try:
                self._page.update()
            except Exception:
                pass

    def _has_visible_if_dependents(self, setting_id: str) -> bool:
        """Check if any setting has a ``visible_if`` pointing to *setting_id*."""
        for schema_entry in self._setting_schema_map.values():
            if schema_entry.get("visible_if") == setting_id:
                return True
        return False

    # ------------------------------------------------------------------
    # File picker
    # ------------------------------------------------------------------

    def _open_file_picker(self, setting_id: str) -> None:
        """Open a file or folder picker for a file_picker-type setting."""
        schema_entry = self._setting_schema_map.get(setting_id, {})
        self._pending_file_setting_id = setting_id

        pick_folders = schema_entry.get("pick_folders", False)
        allowed_extensions = schema_entry.get("allowed_extensions")

        try:
            if pick_folders:
                self._file_picker.get_directory_path(
                    dialog_title=f"Select folder for {schema_entry.get('label', setting_id)}",
                )
            else:
                allowed = None
                if allowed_extensions:
                    allowed = [
                        ft.FilePickerFileType(
                            name="Allowed files",
                            extensions=allowed_extensions,
                        )
                    ]
                self._file_picker.pick_files(
                    dialog_title=f"Select file for {schema_entry.get('label', setting_id)}",
                    allowed_extensions=allowed_extensions,
                    allow_multiple=False,
                )
        except Exception:
            _log(f"ERROR opening file picker:\n{traceback.format_exc()}")

    def _on_file_picker_result(self, e: ft.FilePickerResultEvent) -> None:
        """Handle file picker result."""
        setting_id = self._pending_file_setting_id
        self._pending_file_setting_id = None

        if setting_id is None:
            return

        path = None
        if e.path:
            # Directory picker result
            path = e.path
        elif e.files and len(e.files) > 0:
            # File picker result
            path = e.files[0].path

        if path:
            self._tracker.update(setting_id, path)
            self._current_values[setting_id] = path
            # Re-render the tab to show the updated path
            self._render_tab(self._current_tab_id)
            try:
                self._page.update()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Confirmation dialogs
    # ------------------------------------------------------------------

    def _show_confirmation_dialog(
        self, action_id: str, setting: dict[str, Any],
    ) -> None:
        """Show a confirmation dialog for destructive actions.

        If ``confirmation_keyword`` is set, require the user to type that
        keyword before proceeding.
        """
        keyword = setting.get("confirmation_keyword")
        label = setting.get("label", action_id)

        if keyword:
            self._show_keyword_confirmation(action_id, label, keyword)
        else:
            self._show_simple_confirmation(action_id, label)

    def _show_simple_confirmation(self, action_id: str, label: str) -> None:
        """Show a simple 'Are you sure?' confirmation dialog."""

        def _on_confirm(e: ft.ControlEvent) -> None:
            confirm_dialog.open = False
            self._page.update()
            self._action_handler.execute(action_id)

        def _on_cancel(e: ft.ControlEvent) -> None:
            confirm_dialog.open = False
            self._page.update()

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Are you sure?",
                font_family=Fonts.FRAKTUR,
                size=18,
                color=Colors.GOLD,
            ),
            content=ft.Text(
                f'This will execute "{label}". This action cannot be undone.',
                size=14,
                font_family=Fonts.SERIF,
                color=Colors.FOREGROUND,
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cancel", font_family=Fonts.FRAKTUR),
                    on_click=_on_cancel,
                ),
                ft.ElevatedButton(
                    content=ft.Text("Confirm", font_family=Fonts.FRAKTUR, weight="bold"),
                    on_click=_on_confirm,
                    bgcolor=Colors.DESTRUCTIVE,
                    color=Colors.DESTRUCTIVE_FOREGROUND,
                ),
            ],
            bgcolor=Colors.SURFACE,
            shape=ft.RoundedRectangleBorder(radius=12),
        )

        self._page.dialog = confirm_dialog
        confirm_dialog.open = True
        self._page.update()

    def _show_keyword_confirmation(
        self, action_id: str, label: str, keyword: str,
    ) -> None:
        """Show a confirmation dialog requiring the user to type a keyword."""
        keyword_field = ft.TextField(
            hint_text=f'Type "{keyword}" to confirm',
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED, size=12,
                font_family=Fonts.SERIF, italic=True,
            ),
            text_style=ft.TextStyle(size=13, font_family=Fonts.MONO),
            content_padding=ft.padding.all(10),
            border_radius=6,
        )

        error_text = ft.Text(
            "", size=11, color=Colors.DESTRUCTIVE, visible=False,
        )

        def _on_confirm(e: ft.ControlEvent) -> None:
            if keyword_field.value and keyword_field.value.strip().upper() == keyword.upper():
                keyword_dialog.open = False
                self._page.update()
                self._action_handler.execute(action_id)
            else:
                error_text.value = f'Please type "{keyword}" exactly to confirm.'
                error_text.visible = True
                self._page.update()

        def _on_cancel(e: ft.ControlEvent) -> None:
            keyword_dialog.open = False
            self._page.update()

        keyword_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Confirm Destructive Action",
                font_family=Fonts.FRAKTUR,
                size=18,
                color=Colors.DESTRUCTIVE,
            ),
            content=ft.Column(
                controls=[
                    ft.Text(
                        f'This will execute "{label}". This action is irreversible.',
                        size=14,
                        font_family=Fonts.SERIF,
                        color=Colors.FOREGROUND,
                    ),
                    ft.Text(
                        f'Type "{keyword}" below to confirm:',
                        size=13,
                        font_family=Fonts.SERIF,
                        color=Colors.INK_MUTED,
                    ),
                    keyword_field,
                    error_text,
                ],
                spacing=12,
                tight=True,
                width=340,
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cancel", font_family=Fonts.FRAKTUR),
                    on_click=_on_cancel,
                ),
                ft.ElevatedButton(
                    content=ft.Text("Confirm", font_family=Fonts.FRAKTUR, weight="bold"),
                    on_click=_on_confirm,
                    bgcolor=Colors.DESTRUCTIVE,
                    color=Colors.DESTRUCTIVE_FOREGROUND,
                ),
            ],
            bgcolor=Colors.SURFACE,
            shape=ft.RoundedRectangleBorder(radius=12),
        )

        self._page.dialog = keyword_dialog
        keyword_dialog.open = True
        self._page.update()

    def _show_discard_dialog(self) -> None:
        """Show a dialog asking whether to discard unsaved changes."""

        def _on_discard(e: ft.ControlEvent) -> None:
            discard_dialog.open = False
            self._page.update()
            self._do_close()

        def _on_cancel(e: ft.ControlEvent) -> None:
            discard_dialog.open = False
            self._page.update()

        discard_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Unsaved Changes",
                font_family=Fonts.FRAKTUR,
                size=18,
                color=Colors.WARNING,
            ),
            content=ft.Text(
                "You have unsaved changes. Discard them and close?",
                size=14,
                font_family=Fonts.SERIF,
                color=Colors.FOREGROUND,
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cancel", font_family=Fonts.FRAKTUR),
                    on_click=_on_cancel,
                ),
                ft.ElevatedButton(
                    content=ft.Text("Discard", font_family=Fonts.FRAKTUR, weight="bold"),
                    on_click=_on_discard,
                    bgcolor=Colors.DESTRUCTIVE,
                    color=Colors.DESTRUCTIVE_FOREGROUND,
                ),
            ],
            bgcolor=Colors.SURFACE,
            shape=ft.RoundedRectangleBorder(radius=12),
        )

        self._page.dialog = discard_dialog
        discard_dialog.open = True
        self._page.update()

    # ------------------------------------------------------------------
    # Tab sidebar
    # ------------------------------------------------------------------

    def _build_tab_sidebar(
        self, tabs: list[dict[str, Any]], active_tab_id: str,
    ) -> None:
        """Build the left-hand tab sidebar."""
        tab_controls: list[ft.Control] = []

        for tab in tabs:
            tab_id = tab.get("id", "")
            tab_label = tab.get("label", tab_id)
            is_active = tab_id == active_tab_id

            tab_controls.append(
                ft.Container(
                    content=ft.Text(
                        tab_label,
                        size=14,
                        font_family=Fonts.SERIF,
                        color=Colors.PRIMARY if is_active else Colors.INK_MUTED,
                        weight=ft.FontWeight.W_500,
                    ),
                    bgcolor=Colors.SIDEBAR_BG if is_active else "transparent",
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                    on_click=lambda e, tid=tab_id: self._on_tab_selected(tid),
                    ink=True,
                    border_radius=0,
                    data=tab_id,
                )
            )

        self._tab_sidebar = ft.Column(
            controls=tab_controls,
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            alignment=ft.MainAxisAlignment.START,
        )

    def _update_tab_sidebar_highlight(self, active_tab_id: str) -> None:
        """Update the sidebar to highlight the selected tab."""
        if self._tab_sidebar is None:
            return

        for control in self._tab_sidebar.controls:
            if isinstance(control, ft.Container):
                is_active = control.data == active_tab_id
                control.bgcolor = Colors.SIDEBAR_BG if is_active else "transparent"
                text = control.content
                if isinstance(text, ft.Text):
                    text.color = Colors.PRIMARY if is_active else Colors.INK_MUTED

    # ------------------------------------------------------------------
    # Bottom bar
    # ------------------------------------------------------------------

    def _build_bottom_bar(self) -> ft.Container:
        """Build the Save + Exit button bar."""
        save_btn = ft.ElevatedButton(
            content=ft.Text(
                "Save",
                font_family=Fonts.FRAKTUR,
                size=15,
                weight="bold",
                color=Colors.BACKGROUND,
            ),
            on_click=self._on_save,
            bgcolor=Colors.PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=ft.padding.symmetric(horizontal=28, vertical=12),
            ),
        )

        exit_btn = ft.ElevatedButton(
            content=ft.Text(
                "Exit",
                font_family=Fonts.FRAKTUR,
                size=15,
                weight="bold",
                color=Colors.PRIMARY,
            ),
            on_click=self._on_exit,
            bgcolor=Colors.BACKGROUND,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
                side=ft.BorderSide(1, Colors.DIVIDER),
                padding=ft.padding.symmetric(horizontal=28, vertical=12),
            ),
        )

        return ft.Container(
            content=ft.Row(
                controls=[save_btn, exit_btn],
                alignment=ft.MainAxisAlignment.END,
                spacing=12,
            ),
            bgcolor=Colors.BACKGROUND,
            padding=ft.padding.symmetric(horizontal=24, vertical=12),
            border=ft.border.only(top=ft.BorderSide(1, Colors.DIVIDER)),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_close(self) -> None:
        """Actually close the window and dispose controls."""
        _log("Closing Preferences window")

        try:
            # Remove the floating container from the Stack
            if self._float_container is not None and self._stack is not None:
                if self._float_container in self._stack.controls:
                    self._stack.controls.remove(self._float_container)

            # Remove the minimized pill if present
            if self._minimized_pill is not None and self._stack is not None:
                if self._minimized_pill in self._stack.controls:
                    self._stack.controls.remove(self._minimized_pill)

            # Remove file picker from overlay
            if self._file_picker is not None and self._file_picker in self._page.overlay:
                self._page.overlay.remove(self._file_picker)

            # Dispose controls
            self._tab_sidebar = None
            self._tab_panel_container = None
            self._window_content = None
            self._file_picker = None
            self._float_container = None
            self._minimized_pill = None
            self._renderer = None
            self._setting_schema_map.clear()

            self._is_open = False
            self._is_minimized = False
            self._current_tab_id = ""

            self._page.update()
            _log("Preferences window closed")

        except Exception:
            _log(f"ERROR closing Preferences window:\n{traceback.format_exc()}")
            self._is_open = False

    def _build_setting_schema_map(self) -> None:
        """Build a flat lookup from setting ID → schema entry for fast access."""
        self._setting_schema_map.clear()
        if self._renderer is None:
            return

        for tab in self._renderer.get_tabs():
            for section in tab.get("sections", []):
                for setting in section.get("settings", []):
                    sid = setting.get("id", "")
                    if sid:
                        self._setting_schema_map[sid] = setting

    @property
    def is_open(self) -> bool:
        """Whether the Preferences window is currently open."""
        return self._is_open


# ---------------------------------------------------------------------------
# Module-level hover helpers (stateless, no self needed)
# ---------------------------------------------------------------------------

def _hover_btn(e: ft.ControlEvent, container: ft.Container) -> None:
    """Highlight a title-bar button on hover."""
    container.bgcolor = Colors.SURFACE if e.data == "true" else "transparent"
    try:
        container.update()
    except Exception:
        pass


def _hover_close_btn(e: ft.ControlEvent, container: ft.Container) -> None:
    """Highlight the close button with destructive color on hover."""
    if e.data == "true":
        container.bgcolor = Colors.DESTRUCTIVE
        if isinstance(container.content, ft.Text):
            container.content.color = Colors.PRIMARY
    else:
        container.bgcolor = "transparent"
        if isinstance(container.content, ft.Text):
            container.content.color = Colors.INK_MUTED
    try:
        container.update()
    except Exception:
        pass
