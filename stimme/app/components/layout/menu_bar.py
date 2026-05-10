# stimme/app/components/layout/menu_bar.py

import flet as ft
from app.theme import Colors, Fonts


class MenuBarComponent:
    """Builds the global application menu bar.

    Uses PopupMenuButton controls in a flat Row to achieve a Blender-style
    thin menu strip with no Material surface/elevation artifacts.
    """

    def __init__(self, bus, actions: dict):
        """
        Args:
            bus: EventBus instance for emitting menu_action events.
            actions: Dict of action callables from AppShell
                     (e.g., {"toggle_sidebar": fn, "open_preferences": fn}).
        """
        self.bus = bus
        self.actions = actions

    def build(self) -> ft.Container:
        """Construct and return the menu bar wrapped in a styled container."""
        menu_row = ft.Row(
            controls=[
                self._file_menu(),
                self._edit_menu(),
                self._view_menu(),
                self._scriptorium_menu(),
                self._terminal_menu(),
                self._help_menu(),
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=menu_row,
            bgcolor=Colors.SIDEBAR_BG,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.BORDER)),
            padding=ft.padding.only(left=8),
            height=26,
        )

    # ------------------------------------------------------------------ #
    #  Menu builders
    # ------------------------------------------------------------------ #

    def _file_menu(self) -> ft.PopupMenuButton:
        return ft.PopupMenuButton(
            content=self._menu_label("File"),
            items=[
                self._active_item("New Glossary", on_click=self._emit("file.new_glossary")),
                self._active_item("Open Glossary", on_click=self._emit("file.open_glossary")),
                self._active_item("Save Glossary", on_click=self._emit("file.save_glossary"), shortcut="Ctrl+S"),
                ft.PopupMenuItem(),  # divider
                self._active_item("Import Glossary", on_click=self._emit("file.import_glossary")),
                self._active_item("Import PDF", on_click=self._emit("file.import_pdf")),
                ft.PopupMenuItem(),  # divider
                self._active_item("Export Glossary", on_click=self._emit("file.export_glossary")),
                self._active_item("Export Translation", on_click=self._emit("file.export_translation")),
            ],
            **self._popup_style(),
        )

    def _edit_menu(self) -> ft.PopupMenuButton:
        return ft.PopupMenuButton(
            content=self._menu_label("Edit"),
            items=[
                self._placeholder_item("Find & Replace", shortcut="Ctrl+F"),
                self._placeholder_item("Undo", shortcut="Ctrl+Z"),
                self._placeholder_item("Redo", shortcut="Ctrl+Y"),
                ft.PopupMenuItem(),  # divider
                self._placeholder_item("Global Search"),
            ],
            **self._popup_style(),
        )

    def _view_menu(self) -> ft.PopupMenuButton:
        return ft.PopupMenuButton(
            content=self._menu_label("View"),
            items=[
                self._active_item("Toggle Sidebar", on_click=self._action("toggle_sidebar"), shortcut="Ctrl+B"),
                self._placeholder_item("Toggle Terminal"),
                self._placeholder_item("Toggle Diagnostics HUD"),
                ft.PopupMenuItem(),  # divider
                self._placeholder_item("Sync-Scroll"),
            ],
            **self._popup_style(),
        )

    def _scriptorium_menu(self) -> ft.PopupMenuButton:
        return ft.PopupMenuButton(
            content=self._menu_label("Scriptorium"),
            items=[
                self._placeholder_item("Re-index Vector DB"),
                self._active_item("Run Health Check", on_click=self._emit("scriptorium.health_check")),
                self._active_item("Benchmark Check", on_click=self._emit("scriptorium.benchmark")),
            ],
            **self._popup_style(),
        )

    def _terminal_menu(self) -> ft.PopupMenuButton:
        return ft.PopupMenuButton(
            content=self._menu_label("Terminal"),
            items=[
                self._placeholder_item("Open Console"),
                self._placeholder_item("Clear Console"),
                ft.PopupMenuItem(),  # divider
                self._placeholder_item("Export Session Logs"),
            ],
            **self._popup_style(),
        )

    def _help_menu(self) -> ft.PopupMenuButton:
        return ft.PopupMenuButton(
            content=self._menu_label("Help"),
            items=[
                self._placeholder_item("Check for Updates"),
                self._placeholder_item("Local Documentation"),
                self._placeholder_item("Bug Reporting"),
                ft.PopupMenuItem(),  # divider
                self._active_item("Preferences", on_click=self._action("open_preferences"), shortcut="Ctrl+,"),
            ],
            **self._popup_style(),
        )

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _popup_style(self) -> dict:
        """Shared style kwargs for all PopupMenuButton menus."""
        return dict(
            bgcolor=Colors.SIDEBAR_BG,
            surface_tint_color=ft.Colors.TRANSPARENT,
            shadow_color=Colors.BORDER,
            elevation=2,
            menu_position=ft.PopupMenuPosition.UNDER,
            shape=ft.RoundedRectangleBorder(radius=4),
            menu_padding=ft.padding.symmetric(vertical=2),
            padding=0,
            splash_radius=0,
        )

    def _menu_label(self, text: str) -> ft.Container:
        """Top-level menu label with EB Garamond small-caps styling.

        Wrapped in a Container for padding/hover area.
        """
        return ft.Container(
            content=ft.Text(
                text,
                font_family=Fonts.SERIF,
                size=12,
                color=Colors.FOREGROUND,
                weight=ft.FontWeight.W_500,
                style=ft.TextStyle(letter_spacing=1.5),
            ),
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
        )

    def _active_item(self, label: str, on_click=None, shortcut: str = None) -> ft.PopupMenuItem:
        """An enabled menu item that triggers an action."""
        return ft.PopupMenuItem(
            content=self._item_row(label, shortcut, active=True),
            on_click=on_click,
            height=28,
            padding=ft.padding.symmetric(horizontal=12, vertical=0),
        )

    def _placeholder_item(self, label: str, shortcut: str = None) -> ft.PopupMenuItem:
        """A disabled menu item with '(Coming Soon)' suffix."""
        return ft.PopupMenuItem(
            content=self._item_row(f"{label} (Coming Soon)", shortcut, active=False),
            disabled=True,
            height=28,
            padding=ft.padding.symmetric(horizontal=12, vertical=0),
        )

    def _item_row(self, label: str, shortcut: str = None, active: bool = True) -> ft.Row:
        """Build the content row for a menu item (label + optional shortcut hint)."""
        color = Colors.FOREGROUND if active else Colors.MUTED_FOREGROUND
        controls = [
            ft.Text(label, font_family=Fonts.SERIF, size=12, color=color),
        ]
        if shortcut:
            controls.append(
                ft.Text(shortcut, font_family=Fonts.MONO, size=10, color=Colors.MUTED_FOREGROUND)
            )
        return ft.Row(
            controls=controls,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            expand=True,
        )

    def _emit(self, action_id: str):
        """Return a click handler that emits a menu_action event."""
        def handler(e):
            self.bus.emit("menu_action", action=action_id)
        return handler

    def _action(self, action_name: str):
        """Return a click handler that calls a named action from the actions dict."""
        def handler(e):
            fn = self.actions.get(action_name)
            if fn:
                fn()
        return handler
