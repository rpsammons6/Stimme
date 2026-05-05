"""
DirtyStateTracker — detects unsaved changes in the Preferences window.

Maintains a deep-copied snapshot of configuration values taken when the
Preferences window opens.  As the user modifies settings, :meth:`update`
records each change.  The :attr:`is_dirty` property and :meth:`get_changes`
method compare current values against the snapshot so the window can warn
on unsaved changes and persist only the delta on save.
"""

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


class DirtyStateTracker:
    """Tracks modified settings by comparing against an initial snapshot.

    Parameters
    ----------
    (none — call :meth:`snapshot` after construction to initialise.)

    Examples
    --------
    >>> tracker = DirtyStateTracker()
    >>> tracker.snapshot({"temperature": 0.7, "theme": "Dunkel"})
    >>> tracker.is_dirty
    False
    >>> tracker.update("temperature", 0.5)
    >>> tracker.is_dirty
    True
    >>> tracker.get_changes()
    {'temperature': 0.5}
    """

    def __init__(self) -> None:
        self._snapshot: dict[str, Any] = {}
        self._current: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snapshot(self, values: dict[str, Any]) -> None:
        """Take a deep-copy snapshot of the current config values.

        This should be called once when the Preferences window opens so
        that later comparisons can detect which values the user changed.

        Parameters
        ----------
        values:
            A flat ``{setting_id: value}`` dict from the Active Registry.
        """
        self._snapshot = copy.deepcopy(values)
        self._current = copy.deepcopy(values)

    def update(self, setting_id: str, value: Any) -> None:
        """Record a value change for a single setting.

        Parameters
        ----------
        setting_id:
            The unique setting identifier (matches the schema ``id``).
        value:
            The new value chosen by the user.
        """
        self._current[setting_id] = value

    @property
    def is_dirty(self) -> bool:
        """``True`` if any current value differs from the snapshot."""
        return any(
            self._current.get(k) != self._snapshot.get(k)
            for k in set(self._current) | set(self._snapshot)
        )

    def get_changes(self) -> dict[str, Any]:
        """Return only the settings whose values differ from the snapshot.

        Returns
        -------
        dict[str, Any]
            A dict of ``{setting_id: new_value}`` for every setting that
            was modified since the last :meth:`snapshot` or :meth:`reset`.
        """
        return {
            k: v
            for k, v in self._current.items()
            if v != self._snapshot.get(k)
        }

    def reset(self) -> None:
        """Reset the snapshot to the current values.

        Called after a successful save so that the tracker no longer
        considers the just-saved values as dirty.
        """
        self._snapshot = copy.deepcopy(self._current)
