# Stimme Color Scheme - Dark Mode & Light Mode
# Palette-driven theming with mode switching support

import flet as ft


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
    VELLUM = "#FDF7E4"          # Main background and page base
    EARTHITE = "BBAB8C"         # Sidebar
    SANDSTONE = "#DED0B6"       # Borders, inputs, and disabled states
    UMBER = "#503C3C"           # Primary text and icons (High contrast)
    CLAY = "#7E6363"            # Muted text and secondary icons
    TERRACOTTA = "#B85C5C"      # Error / Destructive (Warm red)
    SAGE = "#869363"            # Success (Natural green)


class Colors:
    """Active color tokens — mapped from the current palette.
    
    Currently wired to DarkPalette. When theme switching is implemented,
    these will be reassigned from LightPalette dynamically.
    """
    _mode = "dark"  # "dark" or "light" — future toggle

    # --- Dark Mode mappings (active) ---
    BACKGROUND = DarkPalette.SHADOW
    FOREGROUND = DarkPalette.BONE
    SURFACE = DarkPalette.FLINT
    SURFACE_RAISED = "#474448"          # Slightly lifted from Flint

    # Primary (Parchment)
    PRIMARY = DarkPalette.PARCHMENT
    PRIMARY_FOREGROUND = DarkPalette.SHADOW

    # Secondary (Taupe)
    SECONDARY = DarkPalette.TAUPE
    SECONDARY_FOREGROUND = DarkPalette.BONE

    # Muted
    MUTED = DarkPalette.FLINT
    MUTED_FOREGROUND = DarkPalette.SILT

    # Accent
    ACCENT = DarkPalette.BONE
    ACCENT_FOREGROUND = DarkPalette.SHADOW

    # Semantic text
    INK = DarkPalette.PARCHMENT
    INK_MUTED = DarkPalette.SILT
    GOLD = DarkPalette.PARCHMENT
    GOLD_DEEP = DarkPalette.TAUPE

    # Borders and inputs
    BORDER = "#4A444A"
    INPUT = "#433D42"
    DIVIDER = "#433D42"
    RING = "#EBE9E0"

    # Sidebar specific
    SIDEBAR_BG = DarkPalette.OBSIDIAN
    SIDEBAR_FG = "#D4CFC6"
    SIDEBAR_PRIMARY = DarkPalette.PARCHMENT
    SIDEBAR_PRIMARY_FG = DarkPalette.SHADOW
    SIDEBAR_ACCENT = DarkPalette.FLINT
    SIDEBAR_ACCENT_FG = DarkPalette.BONE
    SIDEBAR_BORDER = DarkPalette.FLINT
    SIDEBAR_RING = "#EBE9E0"

    # Status colors
    DESTRUCTIVE = DarkPalette.CRIMSON
    DESTRUCTIVE_FOREGROUND = "#F7F6F3"
    WARNING = DarkPalette.AMBER
    WARNING_FOREGROUND = "#1F1A1C"
    SUCCESS = DarkPalette.SAGE
    SUCCESS_FOREGROUND = DarkPalette.PARCHMENT


class Fonts:
    SERIF = "CormorantGaramond"
    MONO = "JetBrains Mono"
    FRAKTUR = "UnifrakturCook-Bold"     # For Translate button
    HEADER = "UnifrakturCook-Bold"      # For headers


class UI:
    """Global UI Component Factory for Stimme"""

    @staticmethod
    def icon(name, size=28):
        from app.components.widgets.img_icon import ImgIcon
        icon_component = ImgIcon(name, size, size).build()
        if isinstance(icon_component, ft.Image):
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
