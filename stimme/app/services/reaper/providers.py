"""Resource providers for the Resource Reaper service.

Defines the ResourceProvider protocol and built-in implementations:
- PDFResourceProvider: Tracks PDFViewer instances and page caches
- ModelResourceProvider: Wraps SessionReaper for ONNX session tracking
- CacheResourceProvider: Tracks VersionStore entries exceeding limits
- UIOverlayProvider: Monitors page.overlay for stale controls
"""

from __future__ import annotations

import time
import weakref
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import flet as ft

from app.services.reaper.models import TrackedResource

if TYPE_CHECKING:
    from app.state import AppState
    from app.models.version_store import VersionStore
    from programs.onnx_providers import SessionReaper


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ResourceProvider(Protocol):
    """Protocol for pluggable resource tracking and cleanup.

    Each provider is responsible for a single category of resources
    (PDF viewers, ONNX sessions, caches, overlay controls). The Reaper
    queries all registered providers during each reconciliation cycle.
    """

    def get_inventory(self) -> list[TrackedResource]:
        """Return current resource holdings as TrackedResource entries."""
        ...

    def cleanup(self, resource: TrackedResource) -> None:
        """Release a specific orphaned resource."""
        ...

    def get_manifest_keys(self, app_state: "AppState") -> set[str]:
        """Return the set of resource keys that SHOULD exist based on state."""
        ...


# ---------------------------------------------------------------------------
# PDFResourceProvider
# ---------------------------------------------------------------------------


class PDFResourceProvider:
    """Tracks PDFViewer instances and their page caches via weakrefs.

    Viewers are registered when created and tracked with weak references
    so the Reaper never prevents natural garbage collection.
    """

    def __init__(self) -> None:
        self._viewers: dict[str, TrackedResource] = {}

    def register_viewer(self, viewer: object, key: str) -> None:
        """Track a PDFViewer instance with a weakref.

        Args:
            viewer: The PDFViewer instance to track.
            key: Unique identifier (typically the pdf_path or a generated id).
        """
        ref = weakref.ref(viewer)
        self._viewers[key] = TrackedResource(
            key=key,
            provider_name="pdf",
            ref=ref,
            birth_time=time.time(),
            description=f"PDFViewer({key})",
        )

    def get_inventory(self) -> list[TrackedResource]:
        """Return all live (non-collected) PDFViewer weakrefs."""
        # Prune dead refs before returning
        dead_keys = [k for k, tr in self._viewers.items() if not tr.is_alive]
        for k in dead_keys:
            del self._viewers[k]
        return list(self._viewers.values())

    def cleanup(self, resource: TrackedResource) -> None:
        """Null base64 src, close engine, clear cache, shut down executor.

        Delegates to the viewer's own cleanup() method which handles all
        of these steps, then removes the tracking entry.
        """
        viewer = resource.ref()
        if viewer is not None:
            # Null the base64 image source
            if hasattr(viewer, "_image") and viewer._image is not None:
                viewer._image.src_base64 = ""

            # Close the ScholarlyPDFEngine
            if hasattr(viewer, "_engine") and viewer._engine is not None:
                try:
                    viewer._engine.close()
                except Exception:
                    pass
                viewer._engine = None

            # Clear the page cache
            if hasattr(viewer, "_cache"):
                for k in list(viewer._cache.keys()):
                    viewer._cache[k] = None
                viewer._cache.clear()

            # Shut down the background executor
            if hasattr(viewer, "_executor") and viewer._executor is not None:
                try:
                    viewer._executor.shutdown(wait=False)
                except Exception:
                    pass
                viewer._executor = None

        # Remove from tracking
        self._viewers.pop(resource.key, None)

    def get_manifest_keys(self, app_state: "AppState") -> set[str]:
        """Return {app_state.pdf_path} if a PDF is active, else empty set."""
        if app_state.pdf_path:
            return {app_state.pdf_path}
        return set()


# ---------------------------------------------------------------------------
# ModelResourceProvider
# ---------------------------------------------------------------------------


class ModelResourceProvider:
    """Wraps SessionReaper to expose ONNX sessions as trackable resources.

    Queries the SessionReaper's internal provider registry to determine
    which sessions are currently loaded, and can force-evict them
    regardless of TTL.
    """

    def __init__(self, session_reaper: "SessionReaper") -> None:
        self._session_reaper = session_reaper

    def get_inventory(self) -> list[TrackedResource]:
        """Return currently loaded ONNX sessions from SessionReaper registry."""
        resources: list[TrackedResource] = []
        with self._session_reaper._lock:
            snapshot = list(self._session_reaper._providers.items())

        for name, (provider, _ttl) in snapshot:
            session = getattr(provider, "_session", None)
            if session is not None:
                ref = weakref.ref(session)
                resources.append(TrackedResource(
                    key=f"onnx:{name}",
                    provider_name="models",
                    ref=ref,
                    birth_time=getattr(provider, "_last_access", time.time()),
                    description=f"ONNX session '{name}'",
                ))
        return resources

    def cleanup(self, resource: TrackedResource) -> None:
        """Force-evict an ONNX session regardless of TTL."""
        # Extract the session name from the key (format: "onnx:<name>")
        name = resource.key.removeprefix("onnx:")

        with self._session_reaper._lock:
            entry = self._session_reaper._providers.get(name)

        if entry is not None:
            provider, _ = entry
            lock = getattr(provider, "_session_lock", None)
            if lock is not None:
                with lock:
                    provider._session = None
            else:
                provider._session = None

    def get_manifest_keys(self, app_state: "AppState") -> set[str]:
        """Return session names that should remain loaded.

        If the brain is expected (translations are active or in progress),
        all registered sessions should stay. Otherwise, return empty set
        to allow eviction.
        """
        brain_expected = (
            app_state.translating
            or len(app_state.translation_tabs) > 0
        )
        if brain_expected:
            with self._session_reaper._lock:
                return {f"onnx:{name}" for name in self._session_reaper._providers}
        return set()


# ---------------------------------------------------------------------------
# CacheResourceProvider
# ---------------------------------------------------------------------------


class CacheResourceProvider:
    """Tracks in-memory caches (VersionStore) with size limits.

    Reports entries exceeding the configured maximum as orphan candidates.
    Evicts oldest entries to bring the cache within budget.
    """

    def __init__(self, version_store: "VersionStore", max_entries: int = 50) -> None:
        self._version_store = version_store
        self._max_entries = max_entries

    def get_inventory(self) -> list[TrackedResource]:
        """Return cache entries exceeding the configured limit.

        Each tab's version data counts as one entry. If total entries
        exceed max_entries, the oldest tabs (by lowest tab_id) are
        reported as candidates for eviction.
        """
        resources: list[TrackedResource] = []
        versions_dict = self._version_store._versions

        if len(versions_dict) <= self._max_entries:
            return resources

        # Sort tab IDs — oldest (lowest) first for eviction priority
        sorted_tab_ids = sorted(versions_dict.keys())
        excess_count = len(sorted_tab_ids) - self._max_entries

        for tab_id in sorted_tab_ids[:excess_count]:
            # Use a weakref to the VersionStore itself (dicts aren't weakref-able).
            # The ref stays alive as long as the store exists, which is correct —
            # cleanup uses the key to identify what to evict.
            ref = weakref.ref(self._version_store)
            resources.append(TrackedResource(
                key=f"cache:tab:{tab_id}",
                provider_name="cache",
                ref=ref,
                birth_time=time.time(),
                description=f"VersionStore entries for tab {tab_id}",
            ))
        return resources

    def cleanup(self, resource: TrackedResource) -> None:
        """Evict oldest entries to bring cache within budget."""
        # Extract tab_id from key (format: "cache:tab:<id>")
        key_parts = resource.key.split(":")
        if len(key_parts) >= 3:
            try:
                tab_id = int(key_parts[2])
            except ValueError:
                return

            # Remove the tab's version data
            self._version_store._versions.pop(tab_id, None)
            self._version_store._active.pop(tab_id, None)

    def get_manifest_keys(self, app_state: "AppState") -> set[str]:
        """Return keys for active tab version entries (should not be evicted).

        Active tabs have their version data protected from eviction.
        """
        keys: set[str] = set()
        for i, _tab in enumerate(app_state.translation_tabs):
            keys.add(f"cache:tab:{i}")
        return keys


# ---------------------------------------------------------------------------
# UIOverlayProvider
# ---------------------------------------------------------------------------


class UIOverlayProvider:
    """Monitors page.overlay for stale FilePickers, closed dialogs, etc.

    Identifies duplicate controls, closed AlertDialogs, and other stale
    overlay entries that accumulate over the application's lifetime.
    """

    def __init__(self, page: ft.Page) -> None:
        self._page = page

    def get_inventory(self) -> list[TrackedResource]:
        """Scan page.overlay for duplicate FilePickers, closed AlertDialogs, and stale controls."""
        resources: list[TrackedResource] = []

        if self._page is None or not hasattr(self._page, "overlay"):
            return resources

        overlay = self._page.overlay
        if overlay is None:
            return resources

        # Track FilePicker types to detect duplicates
        file_pickers: dict[str, list[int]] = {}
        # Track all controls for stale detection
        for idx, control in enumerate(overlay):
            control_id = getattr(control, "uid", None) or str(id(control))

            # Detect duplicate FilePickers
            if isinstance(control, ft.FilePicker):
                picker_key = getattr(control, "uid", None) or type(control).__name__
                if picker_key not in file_pickers:
                    file_pickers[picker_key] = []
                file_pickers[picker_key].append(idx)

            # Detect closed AlertDialogs
            elif isinstance(control, ft.AlertDialog):
                if getattr(control, "open", True) is False:
                    ref = weakref.ref(control)
                    resources.append(TrackedResource(
                        key=f"overlay:{control_id}",
                        provider_name="overlay",
                        ref=ref,
                        birth_time=time.time(),
                        description=f"Closed AlertDialog at index {idx}",
                    ))

        # Report duplicate FilePickers (keep only the first of each type)
        for picker_key, indices in file_pickers.items():
            if len(indices) > 1:
                # All duplicates after the first are stale
                for dup_idx in indices[1:]:
                    control = overlay[dup_idx]
                    control_id = getattr(control, "uid", None) or str(id(control))
                    ref = weakref.ref(control)
                    resources.append(TrackedResource(
                        key=f"overlay:{control_id}",
                        provider_name="overlay",
                        ref=ref,
                        birth_time=time.time(),
                        description=f"Duplicate FilePicker '{picker_key}' at index {dup_idx}",
                    ))

        return resources

    def cleanup(self, resource: TrackedResource) -> None:
        """Remove the stale control from page.overlay."""
        control = resource.ref()
        if control is None:
            return

        if self._page is None or not hasattr(self._page, "overlay"):
            return

        overlay = self._page.overlay
        if overlay is None:
            return

        try:
            overlay.remove(control)
        except (ValueError, AttributeError):
            # Control already removed or overlay changed
            pass

    def get_manifest_keys(self, app_state: "AppState") -> set[str]:
        """Return IDs of legitimately needed overlay controls.

        Controls that are actively open or serve as the primary instance
        of their type are considered legitimate.
        """
        keys: set[str] = set()

        if self._page is None or not hasattr(self._page, "overlay"):
            return keys

        overlay = self._page.overlay
        if overlay is None:
            return keys

        seen_picker_types: set[str] = set()

        for control in overlay:
            control_id = getattr(control, "uid", None) or str(id(control))

            # First FilePicker of each type is legitimate
            if isinstance(control, ft.FilePicker):
                picker_key = getattr(control, "uid", None) or type(control).__name__
                if picker_key not in seen_picker_types:
                    seen_picker_types.add(picker_key)
                    keys.add(f"overlay:{control_id}")

            # Open AlertDialogs are legitimate
            elif isinstance(control, ft.AlertDialog):
                if getattr(control, "open", False) is True:
                    keys.add(f"overlay:{control_id}")

            # All other controls are assumed legitimate
            else:
                keys.add(f"overlay:{control_id}")

        return keys
