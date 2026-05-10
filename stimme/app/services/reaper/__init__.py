"""Resource Reaper — centralized reconciliation-based cleanup service.

Public API:
    ResourceReaper  — Core service (reaper.py)
    ResourceProvider — Protocol for pluggable providers (providers.py)
    TrackedResource — Weakref-tracked resource dataclass
    ReapReport — Structured audit log entry
"""

from app.services.reaper.models import (
    ReapReport,
    ResourceInventory,
    ResourceManifest,
    TrackedResource,
)
from app.services.reaper.providers import ResourceProvider
from app.services.reaper.reaper import ResourceReaper

__all__ = [
    "ResourceReaper",
    "ResourceProvider",
    "TrackedResource",
    "ResourceManifest",
    "ResourceInventory",
    "ReapReport",
]
