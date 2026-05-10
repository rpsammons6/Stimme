"""Worker modules for subprocess-isolated tasks.

This package contains entry points for child processes spawned by SubprocessRunner.
Worker modules MUST NOT import app.shell, app.components, flet, or any UI code.
"""
