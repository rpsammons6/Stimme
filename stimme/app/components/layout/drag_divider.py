"""
Draggable divider for resizable panels.
Usage: place between two containers and pass a callback that receives the drag delta.
"""

import flet as ft
from app.theme import Colors


class DragDivider:
    """A vertical draggable divider handle."""

    def __init__(self, on_drag, width=6):
        """
        Args:
            on_drag: callback(delta_x: float) called during drag with pixel offset
            width: visual width of the handle area
        """
        self.on_drag = on_drag
        self.width = width

    def build(self):
        return ft.GestureDetector(
            content=ft.Container(
                width=self.width,
                bgcolor="transparent",
                content=ft.Container(
                    width=2,
                    bgcolor=Colors.DIVIDER,
                    border_radius=1,
                ),
                alignment=ft.alignment.center,
            ),
            mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
            on_horizontal_drag_update=self._on_drag,
            drag_interval=16,  # ~60fps
        )

    def _on_drag(self, e: ft.DragUpdateEvent):
        if self.on_drag:
            self.on_drag(e.delta_x)
