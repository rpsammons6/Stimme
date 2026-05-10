"""Data models for the Resource Reaper service.

Defines the core dataclasses used throughout the reaper system:
- TrackedResource: A weakref-tracked resource with lifecycle metadata
- ResourceManifest: Expected state snapshot derived from AppState
- ResourceInventory: Actual state snapshot from registered providers
- ReapReport: Structured audit log entry for each reap cycle
"""

from __future__ import annotations

import time
import weakref
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrackedResource:
    """A resource tracked by the Reaper via a weak reference.

    The weak reference allows the Reaper to monitor a resource without
    preventing the garbage collector from collecting it when all hard
    references are dropped elsewhere in the application.
    """

    key: str
    """Unique identifier (e.g., pdf_path, 'onnx:embedding')."""

    provider_name: str
    """Which provider owns this resource."""

    ref: weakref.ref
    """Weak reference to the actual object."""

    birth_time: float = field(default_factory=time.time)
    """When the resource was registered (epoch seconds)."""

    description: str = ""
    """Human-readable description for logging."""

    @property
    def is_alive(self) -> bool:
        """True if the weakref target has not been collected."""
        return self.ref() is not None

    @property
    def age_seconds(self) -> float:
        """Seconds since this resource was registered."""
        return time.time() - self.birth_time


@dataclass
class ResourceManifest:
    """Snapshot of what resources SHOULD exist based on AppState.

    Built at the start of each reap cycle by reading the current
    application state to determine which resources are legitimately
    in use and should not be cleaned up.
    """

    active_pdf_path: Optional[str]
    """Current PDF path or None if no PDF is loaded."""

    active_tab_count: int
    """Number of open translation tabs."""

    active_glossary_paths: list[str]
    """Paths of open glossary files."""

    brain_expected: bool
    """Whether TranslationBrain should be loaded."""

    active_tab_ids: set[int]
    """Tab IDs with active version history."""

    expected_overlay_ids: set[str]
    """Legitimate overlay control IDs."""

    timestamp: float = field(default_factory=time.time)
    """When this manifest was built."""


@dataclass
class ResourceInventory:
    """Snapshot of what resources ACTUALLY exist in memory.

    Aggregated from all registered resource providers. Contains only
    weak references to avoid preventing natural garbage collection.
    """

    resources: list[TrackedResource] = field(default_factory=list)
    """All tracked resources from all providers."""

    timestamp: float = field(default_factory=time.time)
    """When this inventory was built."""

    @property
    def live_resources(self) -> list[TrackedResource]:
        """Filter to only resources whose weakrefs are still alive."""
        return [r for r in self.resources if r.is_alive]


@dataclass
class ReapReport:
    """Structured log entry produced after each reap cycle.

    Contains all information needed to audit what the Reaper found
    and what actions it took during a single reconciliation pass.
    """

    timestamp: float = field(default_factory=time.time)
    """When this report was generated."""

    trigger: str = ""
    """Event that triggered this cycle (e.g., 'tab_closed', 'pressure_warning')."""

    manifest_count: int = 0
    """Number of resources in the manifest (expected to exist)."""

    inventory_count: int = 0
    """Number of resources in the inventory (actually exist)."""

    orphan_count: int = 0
    """Number of orphaned resources found."""

    orphan_descriptions: list[str] = field(default_factory=list)
    """Human-readable descriptions of orphaned resources."""

    cleaned_count: int = 0
    """Number of resources successfully cleaned."""

    errors: list[str] = field(default_factory=list)
    """Cleanup errors encountered during this cycle."""

    uss_mb: Optional[float] = None
    """USS reading at time of reap (populated for pressure-triggered cycles)."""

    threshold_crossed: Optional[str] = None
    """'warning' or 'critical' if this was a pressure-triggered cycle."""

    duration_ms: float = 0.0
    """How long the reap cycle took in milliseconds."""

    @property
    def is_clean(self) -> bool:
        """True if no orphans were found."""
        return self.orphan_count == 0
