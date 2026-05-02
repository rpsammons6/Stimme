import flet as ft
from app.theme import Colors, Fonts


class LogTab:
    """
    Terminal-style log panel shown in the Welcome tab slot during translation.
    Streams log lines in real time with a blinking cursor animation.
    """

    CURSOR = "█"

    def __init__(self, page: ft.Page):
        self.page = page
        self._lines: list[str] = []
        self._done = False

        # Blinking cursor text
        self._cursor_visible = True
        self._cursor_ctrl = ft.Text(
            self.CURSOR,
            size=13,
            color=Colors.GOLD,
            font_family=Fonts.MONO,
            opacity=1.0,
            animate_opacity=ft.animation.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
        )

        self._log_column = ft.ListView(
            controls=[],
            spacing=2,
            expand=True,
        )

        self._container = ft.Container(
            expand=True,
            bgcolor="#2D232E",          # slightly darker than BACKGROUND for terminal feel
            border_radius=ft.border_radius.only(bottom_left=6, bottom_right=6),
            padding=ft.padding.all(20),
            content=ft.Column(
                controls=[
                    # Header bar
                    ft.Row(
                        controls=[
                            ft.Container(expand=True),
                            ft.Text(
                                "Translation Log",
                                size=13,
                                color=Colors.GOLD,
                                font_family=Fonts.HEADER,
                            ),
                            ft.Container(expand=True),
                        ],
                        spacing=6,
                    ),
                    ft.Divider(height=1, color=Colors.DIVIDER),
                    self._log_column,
                    self._cursor_ctrl,
                ],
                spacing=8,
                expand=True,
            ),
            # Slide-in from bottom on first render
            offset=ft.transform.Offset(0, 0.08),
            animate_offset=ft.animation.Animation(320, ft.AnimationCurve.EASE_OUT),
            opacity=0.0,
            animate_opacity=ft.animation.Animation(280, ft.AnimationCurve.EASE_OUT),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, line: str):
        """Add a log line. Updates are batched — the UI refreshes at most
        every 100ms rather than on every single line."""
        self._lines.append(line)
        color = self._line_color(line)
        self._log_column.controls.append(
            ft.Text(
                line,
                size=12,
                color=color,
                font_family=Fonts.MONO,
                selectable=True,
                no_wrap=False,
            )
        )
        # Batch updates: only flush to the UI if we haven't recently
        import time
        now = time.monotonic()
        if not hasattr(self, '_last_flush') or (now - self._last_flush) > 0.1:
            self._last_flush = now
            try:
                self._log_column.update()
            except Exception:
                pass

    def mark_done(self):
        """Hide the blinking cursor when translation finishes."""
        self._done = True
        self._cursor_ctrl.value = ""
        try:
            # Flush any remaining buffered log lines
            self._log_column.update()
            self._cursor_ctrl.update()
        except Exception:
            pass

    def build(self) -> ft.Control:
        # Trigger slide-in animation on next frame
        import threading
        def _animate():
            import time
            time.sleep(0.05)
            self._container.offset = ft.transform.Offset(0, 0)
            self._container.opacity = 1.0
            try:
                self.page.update()
            except Exception:
                pass
            # Start cursor blink loop
            self._blink_cursor()

        threading.Thread(target=_animate, daemon=True).start()
        return self._container

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _blink_cursor(self):
        import time
        import threading

        def _loop():
            while not self._done:
                self._cursor_ctrl.opacity = 0.0 if self._cursor_visible else 1.0
                self._cursor_visible = not self._cursor_visible
                try:
                    self._cursor_ctrl.update()
                except Exception:
                    break
                time.sleep(0.55)

        threading.Thread(target=_loop, daemon=True).start()

    @staticmethod
    def _line_color(line: str) -> str:
        if line.startswith("✅") or "success" in line.lower():
            return "#A8D8A8"   # soft green
        if line.startswith("❌") or "error" in line.lower() or "failed" in line.lower():
            return "#FF8A80"   # soft red
        if line.startswith("⚠️") or "warning" in line.lower():
            return "#FFD180"   # amber
        if line.startswith("🧹") or line.startswith("🎭") or line.startswith("🧠"):
            return "#B39DDB"   # soft purple for brain ops
        if line.startswith("Loading"):
            return Colors.INK_MUTED
        return "#C8C0B8"       # default warm grey
