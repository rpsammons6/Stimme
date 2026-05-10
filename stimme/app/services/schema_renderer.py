"""
Schema-driven UI renderer for the Stimme Preferences window.

Reads ``settings_schema.json`` and auto-generates Flet controls for each
tab, section, and setting.  New tabs or settings can be added by editing
the JSON alone — zero renderer code changes required.

Public API
----------
- ``SchemaRenderer(schema_path)`` — load and parse the schema
- ``get_tabs()`` — ordered list of tab definitions
- ``render_tab(tab_id, current_values, on_change)`` — build Flet controls
- ``serialize_schema()`` — round-trip back to JSON
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Callable

import flet as ft

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Recognised widget types — used for validation and dispatch
# ---------------------------------------------------------------------------
VALID_WIDGET_TYPES = frozenset({
    "slider",
    "switch",
    "dropdown",
    "text_field",
    "textarea",
    "file_picker",
    "button",
    "password_field",
})

VALID_CONFIG_LAYERS = frozenset({"global", "persona"})

# ---------------------------------------------------------------------------
# Hardcoded fallback schema (minimal Interface tab)
# ---------------------------------------------------------------------------
_DEFAULT_SCHEMA: dict[str, Any] = {
    "schema_version": 1.0,
    "tabs": [
        {
            "id": "interface",
            "label": "Interface",
            "header_fraktur": "Oberfläche",
            "sections": [
                {
                    "title": "Aesthetics",
                    "settings": [
                        {
                            "id": "theme",
                            "label": "Visual Mode",
                            "type": "dropdown",
                            "config_layer": "global",
                            "options": ["Dunkel", "Licht"],
                            "default": "Dunkel",
                            "help_text": "Switch between Dark and Light palettes.",
                        }
                    ],
                }
            ],
        }
    ],
}


class SchemaRenderer:
    """Reads ``settings_schema.json`` and generates Flet UI controls.

    The renderer is a generic engine that maps widget-type strings to Flet
    control constructors.  No per-setting rendering code exists — the schema
    is the single source of truth.
    """

    # Map widget type strings → builder methods (populated in __init__)
    WIDGET_MAP: dict[str, Callable[..., ft.Control | None]]

    def __init__(self, schema_path: Path) -> None:
        self._schema_path = Path(schema_path)
        self._schema: dict[str, Any] = {}

        # Bind builder methods so WIDGET_MAP dispatches correctly
        self.WIDGET_MAP = {
            "slider": self._build_slider,
            "switch": self._build_switch,
            "dropdown": self._build_dropdown,
            "text_field": self._build_text_field,
            "textarea": self._build_textarea,
            "file_picker": self._build_file_picker,
            "button": self._build_button,
            "password_field": self._build_password_field,
        }

        self._schema = self.load_schema()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_schema(self) -> dict[str, Any]:
        """Parse the JSON schema file into an internal representation.

        Falls back to a hardcoded default layout on any parse error so the
        Preferences window always has *something* to render.
        """
        try:
            raw = self._schema_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or "tabs" not in parsed:
                logger.error(
                    "Schema file %s is missing 'tabs' key — using default",
                    self._schema_path,
                )
                return copy.deepcopy(_DEFAULT_SCHEMA)
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error(
                "Invalid JSON in schema file %s: %s — using default",
                self._schema_path,
                exc,
            )
            return copy.deepcopy(_DEFAULT_SCHEMA)
        except OSError as exc:
            logger.error(
                "Cannot read schema file %s: %s — using default",
                self._schema_path,
                exc,
            )
            return copy.deepcopy(_DEFAULT_SCHEMA)

    def serialize_schema(self) -> str:
        """Serialize the internal representation back to a JSON string."""
        return json.dumps(self._schema, indent=2, ensure_ascii=False)

    def get_tabs(self) -> list[dict[str, Any]]:
        """Return the ordered list of tab definitions from the schema."""
        return self._schema.get("tabs", [])

    def render_tab(
        self,
        tab_id: str,
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control:
        """Build Flet controls for a single tab.

        Parameters
        ----------
        tab_id:
            The tab identifier from the schema.
        current_values:
            Current config values from the Active Registry.
        on_change:
            Callback invoked as ``on_change(setting_id, new_value)`` when
            any setting value changes.

        Returns
        -------
        ft.Column
            A scrollable column containing all sections and settings for
            the requested tab.
        """
        from app.theme import Colors, Fonts

        tab_def = self._find_tab(tab_id)
        if tab_def is None:
            logger.warning("Tab '%s' not found in schema", tab_id)
            return ft.Column()

        controls: list[ft.Control] = []

        # Fraktur header at the top of the tab panel
        header_text = tab_def.get("header_fraktur", tab_def.get("label", ""))
        controls.append(
            ft.Container(
                content=ft.Text(
                    header_text,
                    size=28,
                    font_family=Fonts.FRAKTUR,
                    color=Colors.GOLD,
                    weight=ft.FontWeight.W_700,
                ),
                alignment=ft.alignment.center,
                padding=ft.padding.only(bottom=16, top=8),
            )
        )

        # Render each section
        for section in tab_def.get("sections", []):
            section_controls = self._render_section(
                section, current_values, on_change
            )
            if section_controls:
                controls.extend(section_controls)

        return ft.Column(
            controls=controls,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            expand=True,
        )

    # ------------------------------------------------------------------
    # Section rendering
    # ------------------------------------------------------------------

    def _render_section(
        self,
        section: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> list[ft.Control]:
        """Render a single section: subheader + settings."""
        from app.theme import Colors, Fonts

        controls: list[ft.Control] = []

        # Section subheader in CormorantGaramond semi unicase
        title = section.get("title", "")
        if title:
            controls.append(
                ft.Container(
                    content=ft.Text(
                        title.upper(),
                        size=14,
                        font_family=Fonts.SERIF,
                        weight=ft.FontWeight.W_600,
                        color=Colors.INK_MUTED,
                    ),
                    padding=ft.padding.only(top=16, bottom=4),
                )
            )

        # Render each setting in the section
        for setting in section.get("settings", []):
            control = self._build_setting(setting, current_values, on_change)
            if control is not None:
                controls.append(control)

        return controls

    # ------------------------------------------------------------------
    # Setting dispatch
    # ------------------------------------------------------------------

    def _build_setting(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        """Build a single setting control based on its widget type.

        Skips unrecognised widget types with a logged warning.  Handles
        ``visible_if`` conditional visibility and ``requires_restart``
        notices.
        """
        from app.theme import Colors, Fonts

        setting_id = setting.get("id", "")
        widget_type = setting.get("type", "")

        # Skip settings with missing required fields
        if not setting_id or not widget_type:
            logger.warning(
                "Skipping setting with missing id or type: %s", setting
            )
            return None

        # --- visible_if: hide when the target evaluates to falsy ----------
        visible_if = setting.get("visible_if")
        if visible_if is not None:
            target_value = current_values.get(visible_if)
            if not target_value:
                return None

        # --- Dispatch to the correct widget builder -----------------------
        builder = self.WIDGET_MAP.get(widget_type)
        if builder is None:
            logger.warning(
                "Unrecognised widget type '%s' for setting '%s' — skipping",
                widget_type,
                setting_id,
            )
            return None

        widget = builder(setting, current_values, on_change)
        if widget is None:
            return None

        # --- Compose the row: label + help text + widget ------------------
        label_text = setting.get("label", setting_id)
        help_text = setting.get("help_text", "")

        label_column_parts: list[ft.Control] = [
            ft.Text(
                label_text,
                size=14,
                font_family=Fonts.SERIF,
                color=Colors.FOREGROUND,
            )
        ]
        if help_text:
            label_column_parts.append(
                ft.Text(
                    help_text,
                    size=11,
                    font_family=Fonts.SERIF,
                    color=Colors.INK_MUTED,
                    italic=True,
                )
            )

        # requires_restart notice
        if setting.get("requires_restart"):
            label_column_parts.append(
                ft.Text(
                    "⟳ Restart required for this change to take effect.",
                    size=11,
                    font_family=Fonts.SERIF,
                    color=Colors.WARNING,
                    italic=True,
                )
            )

        # Buttons get a full-width layout (no side-by-side label)
        if widget_type == "button":
            return ft.Container(
                content=ft.Column(
                    controls=[*label_column_parts, widget],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=ft.padding.symmetric(vertical=6),
            )

        # Textarea gets a stacked layout (label above, textarea below)
        if widget_type == "textarea":
            return ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Column(label_column_parts, spacing=2),
                        widget,
                    ],
                    spacing=6,
                ),
                padding=ft.padding.symmetric(vertical=6),
            )

        # Default: label on the left, widget on the right
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(label_column_parts, spacing=2, expand=True),
                    widget,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(vertical=6),
        )

    # ------------------------------------------------------------------
    # Widget builders
    # ------------------------------------------------------------------

    def _build_slider(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        from app.theme import Colors, Fonts

        setting_id = setting["id"]
        min_val = setting.get("min", 0)
        max_val = setting.get("max", 100)
        step = setting.get("step", 1)
        default = setting.get("default", min_val)
        current = current_values.get(setting_id, default)

        # Clamp current value to valid range
        current = max(min_val, min(max_val, current))

        # Editable value display — click to type, shows live value while sliding
        value_field = ft.TextField(
            value=str(round(current, 2)),
            text_size=12,
            text_style=ft.TextStyle(font_family=Fonts.MONO),
            color=Colors.FOREGROUND,
            width=64,
            text_align=ft.TextAlign.RIGHT,
            content_padding=ft.padding.symmetric(horizontal=6, vertical=4),
            border_color=Colors.DIVIDER,
            focused_border_color=Colors.GOLD,
            bgcolor=Colors.SURFACE,
            border_radius=4,
            dense=True,
        )

        # Mutable ref so closures can share the slider instance
        slider_ref: list[ft.Slider] = []

        def _on_slider_change(e: ft.ControlEvent) -> None:
            val = round(e.control.value, 2)
            value_field.value = str(val)
            on_change(setting_id, val)

        def _on_field_submit(e: ft.ControlEvent) -> None:
            """Validate typed value, clamp to range, sync slider."""
            raw = value_field.value.strip()
            try:
                val = float(raw)
            except (ValueError, TypeError):
                # Revert to current slider value
                val = slider_ref[0].value if slider_ref else current
            # Clamp to valid range
            val = max(min_val, min(max_val, val))
            # Snap to step if step is defined
            if step:
                val = round(round((val - min_val) / step) * step + min_val, 2)
            value_field.value = str(val)
            if slider_ref:
                slider_ref[0].value = val
            on_change(setting_id, val)

        value_field.on_submit = _on_field_submit
        value_field.on_blur = _on_field_submit

        slider = ft.Slider(
            value=current,
            min=min_val,
            max=max_val,
            divisions=max(1, int((max_val - min_val) / step)) if step else None,
            on_change=_on_slider_change,
            active_color=Colors.GOLD,
            inactive_color=Colors.SURFACE,
            expand=True,
        )
        slider_ref.append(slider)

        return ft.Row(
            controls=[slider, value_field],
            spacing=8,
            width=300,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_switch(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        from app.theme import Colors

        setting_id = setting["id"]
        default = setting.get("default", False)
        current = current_values.get(setting_id, default)

        def _on_switch_change(e: ft.ControlEvent) -> None:
            on_change(setting_id, e.control.value)

        return ft.Switch(
            value=bool(current),
            on_change=_on_switch_change,
            active_color=Colors.GOLD,
            track_outline_color=Colors.DIVIDER,
        )

    def _build_dropdown(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        from app.theme import Colors, Fonts

        setting_id = setting["id"]
        options = setting.get("options", [])
        default = setting.get("default", "")
        current = current_values.get(setting_id, default)

        def _on_dropdown_change(e: ft.ControlEvent) -> None:
            on_change(setting_id, e.control.value)

        return ft.Dropdown(
            options=[ft.dropdown.Option(opt) for opt in options],
            value=str(current) if current in options else (options[0] if options else None),
            on_change=_on_dropdown_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            text_style=ft.TextStyle(font_family=Fonts.SERIF),
            border_radius=6,
            width=200,
        )

    def _build_text_field(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        from app.theme import Colors, Fonts

        setting_id = setting["id"]
        default = setting.get("default", "")
        current = current_values.get(setting_id, default)
        placeholder = setting.get("placeholder", "")

        def _on_text_change(e: ft.ControlEvent) -> None:
            on_change(setting_id, e.control.value)

        return ft.TextField(
            value=str(current),
            hint_text=placeholder,
            on_change=_on_text_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            selection_color=Colors.SECONDARY,
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED, size=12, font_family=Fonts.SERIF, italic=True
            ),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.all(10),
            border_radius=6,
            width=280,
        )

    def _build_textarea(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        from app.theme import Colors, Fonts

        setting_id = setting["id"]
        default = setting.get("default", "")
        current = current_values.get(setting_id, default)
        placeholder = setting.get("placeholder", "")

        def _on_textarea_change(e: ft.ControlEvent) -> None:
            on_change(setting_id, e.control.value)

        return ft.TextField(
            value=str(current),
            hint_text=placeholder,
            multiline=True,
            min_lines=4,
            max_lines=10,
            on_change=_on_textarea_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            selection_color=Colors.SECONDARY,
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED, size=12, font_family=Fonts.SERIF, italic=True
            ),
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.all(12),
            border_radius=6,
            expand=True,
        )

    def _build_file_picker(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        """Build a text field + browse button for file/folder selection.

        The actual ``ft.FilePicker`` must be attached to the page at runtime
        by the ``PreferencesWindow``.  Here we render a read-only text field
        showing the current path and a "Browse" button that the window will
        wire up to the real picker.
        """
        from app.theme import Colors, Fonts

        setting_id = setting["id"]
        default = setting.get("default", "")
        current = current_values.get(setting_id, default)

        path_field = ft.TextField(
            value=str(current),
            read_only=True,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            text_style=ft.TextStyle(size=12, font_family=Fonts.MONO),
            content_padding=ft.padding.all(8),
            border_radius=6,
            expand=True,
        )

        def _on_browse_click(e: ft.ControlEvent) -> None:
            # Signal the on_change callback with a special sentinel so the
            # PreferencesWindow knows to open a file picker dialog.
            on_change(setting_id, "__browse__")

        browse_btn = ft.ElevatedButton(
            text="Browse",
            on_click=_on_browse_click,
            bgcolor=Colors.SURFACE,
            color=Colors.FOREGROUND,
            style=ft.ButtonStyle(
                text_style=ft.TextStyle(font_family=Fonts.SERIF, size=12),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        # Store the path field reference on the button so the window can
        # update it after the user picks a file/folder.
        browse_btn.data = {"path_field": path_field, "setting_id": setting_id}

        return ft.Row(
            controls=[path_field, browse_btn],
            spacing=8,
            expand=True,
        )

    def _build_button(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        from app.theme import Colors, Fonts

        setting_id = setting["id"]
        label = setting.get("label", setting_id)
        style_name = setting.get("style", "default")
        action_id = setting.get("action", setting_id)

        is_danger = style_name == "danger"

        def _on_button_click(e: ft.ControlEvent) -> None:
            # Signal the on_change callback with the action ID so the
            # PreferencesWindow / ActionHandler can dispatch it.
            on_change(setting_id, {"__action__": action_id})

        if is_danger:
            bg_color = Colors.DESTRUCTIVE
            fg_color = Colors.DESTRUCTIVE_FOREGROUND
        else:
            bg_color = Colors.SURFACE
            fg_color = Colors.FOREGROUND

        btn = ft.ElevatedButton(
            text=label,
            on_click=_on_button_click,
            bgcolor=bg_color,
            color=fg_color,
            style=ft.ButtonStyle(
                text_style=ft.TextStyle(font_family=Fonts.SERIF, size=13),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        # Attach metadata so the PreferencesWindow can check confirmation
        # requirements before executing the action.
        btn.data = {
            "action": action_id,
            "requires_confirmation": setting.get("requires_confirmation", False),
            "confirmation_keyword": setting.get("confirmation_keyword"),
        }

        return btn

    def _build_password_field(
        self,
        setting: dict[str, Any],
        current_values: dict[str, Any],
        on_change: Callable[[str, Any], None],
    ) -> ft.Control | None:
        from app.theme import Colors, Fonts

        setting_id = setting["id"]
        default = setting.get("default", "")
        current = current_values.get(setting_id, default)
        placeholder = setting.get("placeholder", "")

        def _on_password_change(e: ft.ControlEvent) -> None:
            on_change(setting_id, e.control.value)

        return ft.TextField(
            value=str(current),
            hint_text=placeholder,
            password=True,
            can_reveal_password=True,
            on_change=_on_password_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            selection_color=Colors.SECONDARY,
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED, size=12, font_family=Fonts.SERIF, italic=True
            ),
            text_style=ft.TextStyle(size=13, font_family=Fonts.MONO),
            content_padding=ft.padding.all(10),
            border_radius=6,
            width=280,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_tab(self, tab_id: str) -> dict[str, Any] | None:
        """Look up a tab definition by its ``id``."""
        for tab in self.get_tabs():
            if tab.get("id") == tab_id:
                return tab
        return None
