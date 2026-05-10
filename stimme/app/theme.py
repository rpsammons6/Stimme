# Stimme Color Scheme - Dark Mode & Light Mode
# Palette-driven theming with mode switching support

import logging

import flet as ft

logger = logging.getLogger(__name__)


class DarkPalette:
    """Dark Mode color palette"""
    OBSIDIAN = "#211C22"        # Deepest backgrounds (Sidebar)
    SHADOW = "#2D232E"          # Main background and dark ink text
    FLINT = "#39323A"           # Surfaces, borders, and input fields
    TAUPE = "#534B52"           # Secondary accents and deep decorative elements
    SILT = "#ACA49D"            # Muted/Dimmed text and disabled states
    BONE = "#E0DDCF"            # Main foreground and soft accents
    PARCHMENT = "#F1F0EA"       # Brightest text, call-to-actions
    AMBER = "#F1A355"           # Warning states
    CRIMSON = "#FF4D84"         # Destructive/Error states
    SAGE = "#869363"            # Success (Natural green)


class LightPalette:
    """Light Mode color palette"""
    WHITE = "#FFFFFF"            # Input fields, cards (brightest surface)
    VELLUM = "#FDF7E4"          # Main background / page base
    CREAM = "#F5EDD6"           # Slightly raised surfaces / sidebar
    EARTHITE = "#BBAB8C"        # Muted accents, deep sidebar
    SANDSTONE = "#DED0B6"       # Borders, dividers, disabled states
    CLAY = "#7E6363"            # Muted text and secondary icons
    UMBER = "#503C3C"           # Primary text and icons (High contrast)
    ESPRESSO = "#3A2A2A"        # Brightest/strongest text (CTA equivalent)
    AMBER = "#C47F17"           # Warning states (darker amber for light bg)
    TERRACOTTA = "#B85C5C"      # Error / Destructive (Warm red)
    SAGE = "#5E7A3A"            # Success (darker sage for light bg contrast)


# ---------------------------------------------------------------------------
# Palette map dictionaries — one entry per semantic token, per mode
# ---------------------------------------------------------------------------

DARK_MAP: dict[str, str] = {
    "BACKGROUND": DarkPalette.SHADOW,
    "FOREGROUND": DarkPalette.BONE,
    "SURFACE": DarkPalette.FLINT,
    "SURFACE_RAISED": "#474448",
    "PRIMARY": DarkPalette.PARCHMENT,
    "PRIMARY_FOREGROUND": DarkPalette.SHADOW,
    "SECONDARY": DarkPalette.TAUPE,
    "SECONDARY_FOREGROUND": DarkPalette.BONE,
    "MUTED": DarkPalette.FLINT,
    "MUTED_FOREGROUND": DarkPalette.SILT,
    "ACCENT": DarkPalette.BONE,
    "ACCENT_FOREGROUND": DarkPalette.SHADOW,
    "INK": DarkPalette.PARCHMENT,
    "INK_MUTED": DarkPalette.SILT,
    "GOLD": DarkPalette.PARCHMENT,
    "GOLD_DEEP": DarkPalette.TAUPE,
    "BORDER": "#4A444A",
    "INPUT": "#433D42",
    "DIVIDER": "#433D42",
    "RING": "#EBE9E0",
    "SIDEBAR_BG": DarkPalette.OBSIDIAN,
    "SIDEBAR_FG": "#D4CFC6",
    "SIDEBAR_PRIMARY": DarkPalette.PARCHMENT,
    "SIDEBAR_PRIMARY_FG": DarkPalette.SHADOW,
    "SIDEBAR_ACCENT": DarkPalette.FLINT,
    "SIDEBAR_ACCENT_FG": DarkPalette.BONE,
    "SIDEBAR_BORDER": DarkPalette.FLINT,
    "SIDEBAR_RING": "#EBE9E0",
    "DESTRUCTIVE": DarkPalette.CRIMSON,
    "DESTRUCTIVE_FOREGROUND": "#F7F6F3",
    "WARNING": DarkPalette.AMBER,
    "WARNING_FOREGROUND": "#1F1A1C",
    "SUCCESS": DarkPalette.SAGE,
    "SUCCESS_FOREGROUND": DarkPalette.PARCHMENT,
}

LIGHT_MAP: dict[str, str] = {
    "BACKGROUND": LightPalette.VELLUM,
    "FOREGROUND": LightPalette.UMBER,
    "SURFACE": LightPalette.WHITE,
    "SURFACE_RAISED": LightPalette.CREAM,
    "PRIMARY": LightPalette.ESPRESSO,
    "PRIMARY_FOREGROUND": LightPalette.VELLUM,
    "SECONDARY": LightPalette.CREAM,
    "SECONDARY_FOREGROUND": LightPalette.UMBER,
    "MUTED": LightPalette.SANDSTONE,
    "MUTED_FOREGROUND": LightPalette.CLAY,
    "ACCENT": LightPalette.UMBER,
    "ACCENT_FOREGROUND": LightPalette.VELLUM,
    "INK": LightPalette.UMBER,
    "INK_MUTED": LightPalette.CLAY,
    "GOLD": LightPalette.ESPRESSO,
    "GOLD_DEEP": LightPalette.EARTHITE,
    "BORDER": LightPalette.SANDSTONE,
    "INPUT": LightPalette.WHITE,
    "DIVIDER": LightPalette.SANDSTONE,
    "RING": LightPalette.UMBER,
    "SIDEBAR_BG": LightPalette.CREAM,
    "SIDEBAR_FG": LightPalette.UMBER,
    "SIDEBAR_PRIMARY": LightPalette.ESPRESSO,
    "SIDEBAR_PRIMARY_FG": LightPalette.VELLUM,
    "SIDEBAR_ACCENT": LightPalette.SANDSTONE,
    "SIDEBAR_ACCENT_FG": LightPalette.UMBER,
    "SIDEBAR_BORDER": LightPalette.SANDSTONE,
    "SIDEBAR_RING": LightPalette.UMBER,
    "DESTRUCTIVE": LightPalette.TERRACOTTA,
    "DESTRUCTIVE_FOREGROUND": LightPalette.WHITE,
    "WARNING": LightPalette.AMBER,
    "WARNING_FOREGROUND": LightPalette.ESPRESSO,
    "SUCCESS": LightPalette.SAGE,
    "SUCCESS_FOREGROUND": LightPalette.WHITE,
}

_THEME_LABEL_TO_MODE: dict[str, str] = {
    "Dunkel": "dark",
    "Licht": "light",
}


class Colors:
    """Active color tokens — mapped from the current palette.

    Call ``Colors.apply("dark")`` or ``Colors.apply("light")`` to switch.
    Tokens are initialised to the dark palette at import time so that
    early references (e.g. the loading screen) have valid values.
    """
    _mode = "dark"  # "dark" or "light"

    @classmethod
    def apply(cls, mode: str) -> None:
        """Rewire all semantic tokens from the given palette.

        Args:
            mode: ``"dark"`` or ``"light"``. Invalid values fall back to
                  ``"dark"`` with a warning.
        """
        logger.debug("Colors.apply() called with mode=%r", mode)
        if mode not in {"dark", "light"}:
            logger.warning(
                "Invalid theme mode %r — falling back to 'dark'", mode
            )
            mode = "dark"

        palette_map = DARK_MAP if mode == "dark" else LIGHT_MAP
        for token_name, color_value in palette_map.items():
            setattr(cls, token_name, color_value)
        cls._mode = mode


# Bootstrap: set all tokens from DARK_MAP so early imports have valid values.
Colors.apply("dark")


class Fonts:
    SERIF = "CormorantGaramond"
    MONO = "JetBrains Mono"
    FRAKTUR = "UnifrakturCook-Bold"     # For Translate button
    HEADER = "UnifrakturCook-Bold"      # For headers


class ImgIcon:
    """Renders an image asset as an icon (supports SVG, PNG, WebP).

    SVGs are automatically tinted with ``Colors.PRIMARY`` so they adapt
    to dark/light mode.  PNGs and WebPs render as-is.
    """

    def __init__(self, asset_name: str, width: int = 28, height: int = 28, color=None):
        self.asset_name = asset_name
        self.width = width
        self.height = height
        self.color = color

    def build(self) -> ft.Image:
        is_svg = self.asset_name.lower().endswith(".svg")
        tint = self.color if self.color is not None else (Colors.PRIMARY if is_svg else None)
        return ft.Image(
            src=f"/{self.asset_name}",
            width=self.width,
            height=self.height,
            fit=ft.ImageFit.CONTAIN,
            color=tint,
        )


class UI:
    """Global UI Component Factory for Stimme"""

    @staticmethod
    def icon(name, size=28, color=None):
        """Build a tinted SVG icon image.

        Args:
            name: Asset path relative to assets_dir (e.g. "SVGs/noun-home.svg").
            size: Width and height in pixels.
            color: Override tint color. Defaults to Colors.PRIMARY for SVGs.
        """
        icon_component = ImgIcon(name, size, size, color=color).build()
        icon_component.filter_quality = ft.FilterQuality.HIGH
        return icon_component

    @staticmethod
    def text_field(hint="", value="", multiline=False, mono=False, read_only=False, on_change=None):
        return ft.TextField(
            value=value,
            hint_text=hint,
            multiline=multiline,
            read_only=read_only,
            on_change=on_change,
            min_lines=2 if multiline else 1,
            max_lines=3 if multiline else 1,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            cursor_color=Colors.GOLD,
            selection_color=Colors.SECONDARY,
            hint_style=ft.TextStyle(
                color=Colors.INK_MUTED,
                size=12,
                font_family=Fonts.MONO if mono else Fonts.SERIF,
                italic=not mono
            ),
            text_style=ft.TextStyle(
                size=13,
                font_family=Fonts.MONO if mono else Fonts.SERIF,
            ),
            content_padding=ft.padding.all(12),
            border_radius=6,
        )

    @staticmethod
    def switch(value=False, on_change=None):
        return ft.Switch(
            value=value,
            on_change=on_change,
            active_color=Colors.GOLD,
            track_outline_color=Colors.DIVIDER,
        )

    @staticmethod
    def section_header(title, icon_widget=None, large=False):
        controls = []
        if icon_widget:
            controls.append(icon_widget)
        controls.append(
            ft.Text(
                title,
                size=24 if large else 13,
                font_family=Fonts.HEADER,
                weight=ft.FontWeight.W_700,
                color=Colors.GOLD,
            )
        )
        return ft.Container(
            content=ft.Row(controls=controls, spacing=8),
            padding=ft.padding.only(bottom=8, top=4)
        )

    @staticmethod
    def dropdown(options_dicts, value=None, on_change=None):
        return ft.Dropdown(
            options=[ft.dropdown.Option(m["id"], m["display"]) for m in options_dicts],
            value=value,
            on_change=on_change,
            bgcolor=Colors.SURFACE,
            border_color=Colors.DIVIDER,
            color=Colors.FOREGROUND,
            text_style=ft.TextStyle(font_family=Fonts.SERIF),
            border_radius=6,
        )

    @staticmethod
    def card(content):
        return ft.Container(
            content=content,
            bgcolor=Colors.SURFACE,
            border=ft.border.all(1, Colors.DIVIDER),
            border_radius=6,
            padding=ft.padding.all(12)
        )

    @staticmethod
    def badge(text, on_delete):
        return ft.Container(
            content=ft.Row([
                ft.Text(text, size=12, color=Colors.INK),
                ft.IconButton(icon=ft.Icons.CLOSE, icon_size=12, on_click=on_delete)
            ], tight=True),
            bgcolor=Colors.SURFACE_RAISED,
            border_radius=4,
            padding=4
        )

    @staticmethod
    def settings_row(title, subtitle, control):
        """Creates the standard Label/Sublabel + Switch/Button row"""
        return ft.Row(
            controls=[
                ft.Column([
                    ft.Text(title, size=13, color=Colors.FOREGROUND),
                    ft.Text(subtitle, size=11, color=Colors.INK_MUTED)
                ], spacing=2, expand=True),
                control
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )
