"""
GlossaryView: A full-tab view displaying all glossary terms in a scrollable list.
Opened via the "View Glossary" button in the sidebar.
Right-click a term to pin it to the sidebar for quick editing.
"""

import flet as ft
import traceback
from app.theme import Colors, Fonts, UI


def _log(msg):
    print(f"[GlossaryView] {msg}")


class GlossaryView:
    """Renders the full glossary as a scrollable table inside a closeable tab."""

    def __init__(self, page: ft.Page, actions: dict = None):
        self._page = page
        self._actions = actions or {}

    def _pin_term(self, german: str):
        """Pin a term to the sidebar."""
        try:
            glossary_mgr = self._actions.get("glossary_manager")
            if glossary_mgr:
                glossary_mgr.pin_term(german)
                # Refresh sidebar immediately
                refresh = self._actions.get("refresh_glossary_sidebar")
                if refresh:
                    refresh()
                bus = self._actions.get("bus")
                if bus:
                    bus.show_banner(f"📌 Pinned to sidebar: {german}")
        except Exception:
            _log(f"ERROR pinning term '{german}':\n{traceback.format_exc()}")

    def _unpin_term(self, german: str):
        """Unpin a term from the sidebar."""
        try:
            glossary_mgr = self._actions.get("glossary_manager")
            if glossary_mgr:
                glossary_mgr.unpin_term(german)
                # Refresh sidebar immediately
                refresh = self._actions.get("refresh_glossary_sidebar")
                if refresh:
                    refresh()
                bus = self._actions.get("bus")
                if bus:
                    bus.show_banner(f"Unpinned from sidebar: {german}")
        except Exception:
            _log(f"ERROR unpinning term '{german}':\n{traceback.format_exc()}")

    def _on_term_right_click(self, e, term):
        """Show a lightweight context menu at the cursor position with pin/delete options."""
        is_pinned = term.pinned
        pin_text = "Unpin from Sidebar" if is_pinned else "Pin to Sidebar"
        pin_icon = ft.Icons.PUSH_PIN if is_pinned else ft.Icons.PUSH_PIN_OUTLINED

        def on_pin(menu_e):
            if is_pinned:
                self._unpin_term(term.german)
            else:
                self._pin_term(term.german)
            self._close_menu()

        def on_delete(menu_e):
            glossary_mgr = self._actions.get("glossary_manager")
            if glossary_mgr:
                glossary_mgr.remove_term(term.german)
                refresh = self._actions.get("refresh_glossary_sidebar")
                if refresh:
                    refresh()
                bus = self._actions.get("bus")
                if bus:
                    bus.show_banner(f"Deleted: {term.german}")
                # Rebuild the glossary tab to reflect removal
                open_glossary = self._actions.get("open_glossary_tab")
                if open_glossary:
                    open_glossary()
            self._close_menu()

        # Get cursor position from the event
        x = getattr(e, 'global_x', None) or getattr(e, 'local_x', 200)
        y = getattr(e, 'global_y', None) or getattr(e, 'local_y', 200)

        menu = ft.Container(
            content=ft.Column([
                ft.TextButton(
                    content=ft.Row([
                        ft.Icon(pin_icon, size=16, color=Colors.GOLD),
                        ft.Text(pin_text, size=13, color=Colors.INK),
                    ], spacing=8),
                    on_click=on_pin,
                ),
                ft.Divider(height=1, color=Colors.DIVIDER),
                ft.TextButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.DELETE_OUTLINE, size=16, color=Colors.DESTRUCTIVE),
                        ft.Text("Delete Term", size=13, color=Colors.DESTRUCTIVE),
                    ], spacing=8),
                    on_click=on_delete,
                ),
            ], spacing=0, tight=True),
            bgcolor=Colors.SURFACE,
            border=ft.border.all(1, Colors.DIVIDER),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=4, vertical=4),
            shadow=ft.BoxShadow(blur_radius=8, color="#33000000"),
            left=x,
            top=y,
        )

        # Full-screen transparent backdrop that dismisses the menu on any click
        backdrop = ft.GestureDetector(
            content=ft.Container(
                expand=True,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
            on_tap=lambda _: self._close_menu(),
            on_secondary_tap=lambda _: self._close_menu(),
        )

        # Clear any existing menu first
        self._page.overlay.clear()
        self._page.overlay.append(backdrop)
        self._page.overlay.append(menu)
        self._page.update()

    def _close_menu(self):
        """Remove the context menu overlay."""
        self._page.overlay.clear()
        self._page.update()

    def build(self) -> ft.Control:
        glossary_mgr = self._actions.get("glossary_manager")
        terms = glossary_mgr.get_terms() if glossary_mgr else []

        if not terms:
            return ft.Container(
                content=ft.Column([
                    ft.Image(src="/empty-history-icon.webp", width=48, height=48),
                    ft.Text("No glossary terms yet.", size=14, color=Colors.INK_MUTED, italic=True),
                    ft.Text("Add terms from the sidebar or right-click in a translation.", size=12, color=Colors.INK_MUTED),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                alignment=ft.alignment.center,
                expand=True,
            )

        # Build header row
        header = ft.Container(
            content=ft.Row([
                ft.Text("", width=24),  # pin indicator column
                ft.Text("German", size=12, weight="bold", color=Colors.GOLD, width=160),
                ft.Text("English", size=12, weight="bold", color=Colors.GOLD, width=160),
                ft.Text("Context Target", size=12, weight="bold", color=Colors.GOLD, width=140),
                ft.Text("Field", size=12, weight="bold", color=Colors.GOLD, width=100),
                ft.Text("Note", size=12, weight="bold", color=Colors.GOLD, expand=True),
            ], spacing=12),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

        # Build term rows
        rows = []
        for term in terms:
            context_target = term.context_target if term.context_target != "N/A" else "—"
            field_tag = term.field_tag if term.field_tag != "N/A" else "—"
            nuance = term.nuance_note if hasattr(term, 'nuance_note') and term.nuance_note and term.nuance_note != "N/A" else "—"

            pin_icon = ft.Icon(
                ft.Icons.PUSH_PIN, size=14, color=Colors.GOLD
            ) if term.pinned else ft.Container(width=14)

            row_container = ft.Container(
                content=ft.Row([
                    pin_icon,
                    ft.Text(term.german, size=13, color=Colors.INK, weight="bold", width=160),
                    ft.Text(term.english, size=13, color=Colors.FOREGROUND, width=160),
                    ft.Text(context_target, size=12, color=Colors.INK_MUTED, width=140),
                    ft.Text(field_tag, size=12, color=Colors.INK_MUTED, italic=True, width=100),
                    ft.Text(nuance, size=12, color=Colors.INK_MUTED, expand=True, no_wrap=False),
                ], spacing=12),
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
                border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
            )

            rows.append(
                ft.GestureDetector(
                    content=row_container,
                    on_secondary_tap_down=lambda e, t=term: self._on_term_right_click(e, t),
                )
            )

        term_count = ft.Text(
            f"{len(terms)} term{'s' if len(terms) != 1 else ''}",
            size=11, color=Colors.INK_MUTED, italic=True,
        )

        return ft.Column([
            ft.Container(
                content=ft.Row([
                    UI.icon("icon-book-open.svg", size=24),
                    ft.Text("Glossary", size=24, font_family=Fonts.HEADER),
                    ft.Container(expand=True),
                    term_count,
                ], spacing=10),
                padding=ft.padding.symmetric(horizontal=16, vertical=12),
            ),
            ft.Text("  Right-click a term to pin/unpin it to the sidebar.", size=11, color=Colors.INK_MUTED, italic=True),
            header,
            ft.ListView(controls=rows, expand=True, spacing=0),
        ], expand=True, spacing=0)
