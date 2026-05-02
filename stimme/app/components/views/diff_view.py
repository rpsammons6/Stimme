"""Side-by-side diff view for comparing two translation versions."""

from __future__ import annotations

from typing import Callable, List

import flet as ft

from app.models.hitl_models import DiffOp
from app.theme import Colors, Fonts


# Muted highlight colors that harmonize with the dark scholarly palette
_GREEN_BG = "#4A6B4A"  # muted green for insertions
_RED_BG = "#6B4A4A"  # muted red for deletions


class DiffView:
    """Renders a side-by-side diff comparison of two translation versions.

    Left column shows Version A with deletions highlighted in red.
    Right column shows Version B with insertions highlighted in green.
    """

    def __init__(
        self,
        diff_ops: List[DiffOp],
        version_a_label: str,
        version_b_label: str,
        on_accept: Callable,
        on_close: Callable,
    ) -> None:
        self.diff_ops = diff_ops
        self.version_a_label = version_a_label
        self.version_b_label = version_b_label
        self.on_accept = on_accept
        self.on_close = on_close

    def _build_spans(self, side: str) -> List[ft.TextSpan]:
        """Build color-coded text spans for one side of the diff.

        Args:
            side: 'left' for Version A (old), 'right' for Version B (new).
        """
        spans: List[ft.TextSpan] = []

        for op in self.diff_ops:
            if op.tag == "equal":
                words = op.old_words if side == "left" else op.new_words
                if words:
                    spans.append(
                        ft.TextSpan(
                            text=" ".join(words) + " ",
                            style=ft.TextStyle(color=Colors.INK),
                        )
                    )

            elif op.tag == "delete":
                if side == "left" and op.old_words:
                    spans.append(
                        ft.TextSpan(
                            text=" ".join(op.old_words) + " ",
                            style=ft.TextStyle(
                                color=Colors.INK,
                                bgcolor=_RED_BG,
                            ),
                        )
                    )
                # Right side: nothing to show for a pure deletion

            elif op.tag == "insert":
                if side == "right" and op.new_words:
                    spans.append(
                        ft.TextSpan(
                            text=" ".join(op.new_words) + " ",
                            style=ft.TextStyle(
                                color=Colors.INK,
                                bgcolor=_GREEN_BG,
                            ),
                        )
                    )
                # Left side: nothing to show for a pure insertion

            elif op.tag == "replace":
                if side == "left" and op.old_words:
                    spans.append(
                        ft.TextSpan(
                            text=" ".join(op.old_words) + " ",
                            style=ft.TextStyle(
                                color=Colors.INK,
                                bgcolor=_RED_BG,
                            ),
                        )
                    )
                elif side == "right" and op.new_words:
                    spans.append(
                        ft.TextSpan(
                            text=" ".join(op.new_words) + " ",
                            style=ft.TextStyle(
                                color=Colors.INK,
                                bgcolor=_GREEN_BG,
                            ),
                        )
                    )

        return spans

    def _build_column(self, label: str, side: str) -> ft.Control:
        """Build one side of the diff (header + spans)."""
        spans = self._build_spans(side)

        header = ft.Text(
            label,
            size=12,
            weight=ft.FontWeight.W_600,
            color=Colors.GOLD,
            font_family=Fonts.MONO,
        )

        body = ft.Text(
            spans=spans,
            size=13,
            font_family=Fonts.SERIF,
            selectable=True,
        ) if spans else ft.Text(
            "(empty)",
            size=13,
            color=Colors.INK_MUTED,
            italic=True,
            font_family=Fonts.SERIF,
        )

        return ft.Container(
            content=ft.Column(
                controls=[header, body],
                spacing=8,
            ),
            expand=True,
            padding=ft.padding.all(12),
        )

    def build(self) -> ft.Control:
        """Build the diff view with color-coded word spans."""
        left_col = self._build_column(self.version_a_label, "left")
        right_col = self._build_column(self.version_b_label, "right")

        divider = ft.VerticalDivider(width=1, color=Colors.DIVIDER)

        diff_row = ft.Row(
            controls=[left_col, divider, right_col],
            spacing=0,
            expand=True,
        )

        accept_btn = ft.TextButton(
            text="Accept This Version",
            style=ft.ButtonStyle(
                color=Colors.GOLD,
                text_style=ft.TextStyle(size=12, weight=ft.FontWeight.W_600, font_family=Fonts.FRAKTUR),
            ),
            on_click=lambda e: self.on_accept(),
        )

        close_btn = ft.TextButton(
            text="Close",
            style=ft.ButtonStyle(
                color=Colors.INK_MUTED,
                text_style=ft.TextStyle(size=12, font_family=Fonts.FRAKTUR),
            ),
            on_click=lambda e: self.on_close(),
        )

        button_row = ft.Row(
            controls=[accept_btn, close_btn],
            alignment=ft.MainAxisAlignment.END,
            spacing=8,
        )

        return ft.Container(
            content=ft.Column(
                controls=[diff_row, ft.Divider(height=1, color=Colors.DIVIDER), button_row],
                spacing=8,
            ),
            bgcolor=Colors.SURFACE,
            border=ft.border.all(1, Colors.BORDER),
            border_radius=6,
            padding=ft.padding.all(12),
        )
