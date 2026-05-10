"""ResourceReaper — centralized reconciliation-based cleanup service.

Compares what resources SHOULD exist (manifest from AppState) against
what ACTUALLY exists (inventory from registered providers), then cleans
the difference. Uses a lock+queue pattern for thread safety and emits
structured ReapReport audit logs via EventBus.
"""

from __future__ import annotations

import collections
import gc
import logging
import threading
import time
from typing import TYPE_CHECKING

from app.services.reaper.models import (
    ReapReport,
    ResourceInventory,
    ResourceManifest,
)

if TYPE_CHECKING:
    import flet as ft

    from app.event_bus import EventBus
    from app.services.configuration_service import ConfigurationService
    from app.services.reaper.providers import ResourceProvider
    from app.state import AppState

logger = logging.getLogger(__name__)


class ResourceReaper:
    """Centralized reconciliation-based resource cleanup service.

    The Reaper operates on a manifest vs. inventory diff model:
    after each triggering event it compares what *should* exist
    (derived from AppState) against what *actually* exists (reported
    by registered resource providers), then cleans the difference.
    """

    # Default grace period in seconds — resources younger than this
    # are immune from reaping to allow UI transitions to settle.
    _GRACE_PERIOD_SECONDS: float = 2.0

    def __init__(
        self,
        app_state: "AppState",
        bus: "EventBus",
        settings: "ConfigurationService",
        page: "ft.Page",
    ) -> None:
        self._app_state = app_state
        self._bus = bus
        self._settings = settings
        self._page = page

        # Provider registry: name -> provider instance
        self._providers: dict[str, "ResourceProvider"] = {}

        # Thread safety: lock + pending trigger queue
        self._lock = threading.Lock()
        self._pending_triggers: collections.deque[str] = collections.deque()

        # Stop signal for the pressure monitor daemon
        self._stop_event = threading.Event()

        # Register EventBus listeners for automatic reap triggering
        self._bus.on("translation_complete", lambda **kwargs: self.reap("translation_complete"))
        self._bus.on("tab_closed", lambda **kwargs: self.reap("tab_closed"))
        self._bus.on("pdf_replaced", lambda **kwargs: self.reap("pdf_replaced"))
        self._bus.on("book_translation_complete", lambda **kwargs: self.reap("book_translation_complete"))
        self._bus.on("window_close", lambda **kwargs: self.stop())

    # ------------------------------------------------------------------
    # Provider registration
    # ------------------------------------------------------------------

    def register_provider(self, name: str, provider: "ResourceProvider") -> None:
        """Register a resource provider for inclusion in reap cycles.

        Args:
            name: Unique name for this provider (e.g., 'pdf', 'models').
            provider: An object implementing the ResourceProvider protocol.
        """
        self._providers[name] = provider
        logger.debug("[Reaper] Registered provider: %s", name)

    # ------------------------------------------------------------------
    # Manifest building
    # ------------------------------------------------------------------

    def _build_manifest(self) -> ResourceManifest:
        """Build a ResourceManifest from the current AppState.

        Reads the application state to determine which resources are
        legitimately in use and should not be cleaned up.
        """
        state = self._app_state

        # Active PDF path
        active_pdf_path = state.pdf_path

        # Tab count
        active_tab_count = len(state.translation_tabs)

        # Glossary paths — derive from active paths if GlossaryManager
        # is accessible, otherwise use an empty list.
        glossary_paths: list[str] = []
        if hasattr(state, "glossary_paths"):
            glossary_paths = list(state.glossary_paths)

        # Brain expected: if translating or tabs exist
        brain_expected = state.translating or active_tab_count > 0

        # Active tab IDs (indices of translation tabs)
        active_tab_ids: set[int] = set(range(active_tab_count))

        # Expected overlay IDs — delegate to the overlay provider if registered
        expected_overlay_ids: set[str] = set()
        overlay_provider = self._providers.get("overlay")
        if overlay_provider is not None:
            try:
                expected_overlay_ids = overlay_provider.get_manifest_keys(state)
            except Exception as exc:
                logger.warning(
                    "[Reaper] Failed to get overlay manifest keys: %s", exc
                )

        return ResourceManifest(
            active_pdf_path=active_pdf_path,
            active_tab_count=active_tab_count,
            active_glossary_paths=glossary_paths,
            brain_expected=brain_expected,
            active_tab_ids=active_tab_ids,
            expected_overlay_ids=expected_overlay_ids,
        )

    # ------------------------------------------------------------------
    # Inventory building
    # ------------------------------------------------------------------

    def _build_inventory(self) -> ResourceInventory:
        """Query all registered providers and aggregate into a ResourceInventory.

        If a provider raises an exception, it is skipped and the error
        is logged. The Reaper does not deregister failing providers.
        """
        inventory = ResourceInventory()

        for name, provider in self._providers.items():
            try:
                resources = provider.get_inventory()
                inventory.resources.extend(resources)
            except Exception as exc:
                logger.error(
                    "[Reaper] Provider '%s' get_inventory() failed: %s",
                    name,
                    exc,
                )

        return inventory

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def _reconcile(self, trigger: str) -> ReapReport:
        """Core reconciliation: manifest vs inventory diff with grace period.

        Computes orphans (in inventory but not in manifest), applies the
        grace period filter, executes cleanup for each orphan, and builds
        a ReapReport.
        """
        t0 = time.perf_counter()

        # 1. Build manifest from AppState
        manifest = self._build_manifest()

        # 2. Build inventory from all providers
        inventory = self._build_inventory()

        # 3. Compute orphans: in inventory but NOT in manifest
        # Collect all manifest keys across all providers
        all_manifest_keys: dict[str, set[str]] = {}
        for provider_name, provider in self._providers.items():
            try:
                keys = provider.get_manifest_keys(self._app_state)
                all_manifest_keys[provider_name] = keys
            except Exception as exc:
                logger.error(
                    "[Reaper] Provider '%s' get_manifest_keys() failed: %s",
                    provider_name,
                    exc,
                )
                # If we can't get manifest keys, treat as empty (safe: grace
                # period protects new resources)
                all_manifest_keys[provider_name] = set()

        orphans = []
        for resource in inventory.live_resources:
            manifest_keys = all_manifest_keys.get(resource.provider_name, set())
            if resource.key not in manifest_keys:
                # Grace period check: skip if younger than 2 seconds
                if resource.age_seconds < self._GRACE_PERIOD_SECONDS:
                    continue
                orphans.append(resource)

        # 4. Execute cleanup for each orphan
        cleaned = 0
        errors: list[str] = []
        for orphan in orphans:
            try:
                provider = self._providers.get(orphan.provider_name)
                if provider is not None:
                    provider.cleanup(orphan)
                    cleaned += 1
                else:
                    errors.append(
                        f"{orphan.key}: provider '{orphan.provider_name}' not found"
                    )
            except Exception as exc:
                errors.append(f"{orphan.key}: {exc}")

        # 5. Build report
        # Total manifest count across all providers
        manifest_count = sum(len(keys) for keys in all_manifest_keys.values())
        duration_ms = (time.perf_counter() - t0) * 1000

        return ReapReport(
            trigger=trigger,
            manifest_count=manifest_count,
            inventory_count=len(inventory.live_resources),
            orphan_count=len(orphans),
            orphan_descriptions=[r.description or r.key for r in orphans],
            cleaned_count=cleaned,
            errors=errors,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Thread-safe reap
    # ------------------------------------------------------------------

    def reap(self, trigger: str = "manual") -> ReapReport:
        """Execute a reap cycle. Thread-safe; queues if already running.

        Acquires the lock with blocking=False. If the lock is already
        held (another cycle is running), the trigger is queued and an
        empty report is returned immediately.

        After reconciliation, gc.collect() runs OUTSIDE the lock to
        avoid blocking other threads during collection. Queued triggers
        are then processed.
        """
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            self._pending_triggers.append(trigger)
            logger.debug("[Reaper] Lock held, queued trigger: %s", trigger)
            return ReapReport(trigger=trigger)

        try:
            report = self._reconcile(trigger)
        finally:
            self._lock.release()

        # gc.collect() outside the lock
        gc.collect()

        # Log and emit
        self._log_report(report)
        self._bus.emit("reap_complete", report=report)

        # Process queued triggers
        while self._pending_triggers:
            next_trigger = self._pending_triggers.popleft()
            self.reap(trigger=next_trigger)

        return report

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def _log_report(self, report: ReapReport) -> None:
        """Write the ReapReport to the application log.

        Full report when orphans are found; single-line confirmation
        when the state is clean.
        """
        if report.is_clean:
            logger.info(
                "[Reaper] Clean state — trigger=%s, inventory=%d, duration=%.1fms",
                report.trigger,
                report.inventory_count,
                report.duration_ms,
            )
        else:
            logger.info(
                "[Reaper] Reaped — trigger=%s, manifest=%d, inventory=%d, "
                "orphans=%d, cleaned=%d, errors=%d, duration=%.1fms | %s",
                report.trigger,
                report.manifest_count,
                report.inventory_count,
                report.orphan_count,
                report.cleaned_count,
                len(report.errors),
                report.duration_ms,
                ", ".join(report.orphan_descriptions),
            )
            if report.errors:
                for err in report.errors:
                    logger.warning("[Reaper] Cleanup error: %s", err)

    # ------------------------------------------------------------------
    # RAM pressure monitoring
    # ------------------------------------------------------------------

    def start_pressure_monitor(self) -> None:
        """Start the 30s USS polling daemon thread.

        The thread runs as a daemon so it does not prevent application
        exit. It polls USS every 30 seconds and triggers reap cycles
        when memory thresholds are crossed.
        """
        thread = threading.Thread(
            target=self._pressure_loop,
            name="ReaperPressureMonitor",
            daemon=True,
        )
        thread.start()
        logger.info("[Reaper] Pressure monitor started (30s interval)")

    def _pressure_loop(self) -> None:
        """Daemon thread: poll USS every 30s, trigger reap on threshold breach.

        Reads the warning and critical thresholds from ConfigurationService
        on each iteration so they can be changed at runtime. Limits to one
        pressure-based action per 30-second interval.

        Handles psutil.AccessDenied and other exceptions gracefully by
        logging and continuing on the next interval.
        """
        import psutil

        while not self._stop_event.is_set():
            # Wait for 30 seconds or until stop is signalled
            self._stop_event.wait(timeout=30.0)
            if self._stop_event.is_set():
                break

            try:
                uss_bytes = psutil.Process().memory_full_info().uss
                uss_mb = uss_bytes / (1024 * 1024)
            except psutil.AccessDenied:
                logger.warning(
                    "[Reaper] psutil.AccessDenied — cannot read USS, skipping pressure check"
                )
                continue
            except Exception as exc:
                logger.warning(
                    "[Reaper] Pressure monitor error reading USS: %s", exc
                )
                continue

            # Read thresholds from configuration (allow runtime changes)
            critical_threshold = self._settings.get("reaper_critical_threshold", 250)
            warning_threshold = self._settings.get("reaper_warning_threshold", 180)

            # One action per interval: critical takes priority over warning
            if uss_mb >= critical_threshold:
                logger.warning(
                    "[Reaper] CRITICAL pressure: USS=%.1fMB >= %dMB — triggering deep clean",
                    uss_mb,
                    critical_threshold,
                )
                self._deep_clean(uss_mb)
            elif uss_mb >= warning_threshold:
                logger.warning(
                    "[Reaper] WARNING pressure: USS=%.1fMB >= %dMB — triggering reap",
                    uss_mb,
                    warning_threshold,
                )
                report = self.reap(
                    trigger=f"pressure_warning(USS={uss_mb:.1f}MB)"
                )
                report.uss_mb = uss_mb
                report.threshold_crossed = "warning"
            else:
                logger.debug(
                    "[Reaper] Pressure OK: USS=%.1fMB (warn=%dMB, crit=%dMB)",
                    uss_mb,
                    warning_threshold,
                    critical_threshold,
                )

    def _deep_clean(self, uss_mb: float) -> None:
        """Aggressive cleanup triggered by critical RAM pressure.

        Goes beyond normal orphan reconciliation to forcibly clear all
        caches and evict all sessions regardless of manifest state.

        Steps:
        1. Clear VersionStore LRU cache entirely
        2. Force ONNX session eviction via ModelResourceProvider
        3. Clear all page caches from PDFResourceProvider
        4. Run UIOverlayProvider cleanup on all inventory
        5. Run gc.collect()

        Args:
            uss_mb: The USS reading that triggered this deep clean.
        """
        t0 = time.perf_counter()
        errors: list[str] = []
        cleaned = 0

        # 1. Clear VersionStore LRU cache entirely via CacheResourceProvider
        cache_provider = self._providers.get("cache")
        if cache_provider is not None:
            try:
                inventory = cache_provider.get_inventory()
                # Force-clean ALL entries, not just orphans
                if hasattr(cache_provider, "_version_store"):
                    cache_provider._version_store._versions.clear()
                    cache_provider._version_store._active.clear()
                    cleaned += 1
                else:
                    for resource in inventory:
                        try:
                            cache_provider.cleanup(resource)
                            cleaned += 1
                        except Exception as exc:
                            errors.append(f"cache:{resource.key}: {exc}")
            except Exception as exc:
                errors.append(f"cache_provider: {exc}")

        # 2. Force ONNX session eviction via ModelResourceProvider
        model_provider = self._providers.get("models")
        if model_provider is not None:
            try:
                inventory = model_provider.get_inventory()
                for resource in inventory:
                    try:
                        model_provider.cleanup(resource)
                        cleaned += 1
                    except Exception as exc:
                        errors.append(f"models:{resource.key}: {exc}")
            except Exception as exc:
                errors.append(f"model_provider: {exc}")

        # 3. Clear all page caches from PDFResourceProvider
        pdf_provider = self._providers.get("pdf")
        if pdf_provider is not None:
            try:
                inventory = pdf_provider.get_inventory()
                for resource in inventory:
                    try:
                        pdf_provider.cleanup(resource)
                        cleaned += 1
                    except Exception as exc:
                        errors.append(f"pdf:{resource.key}: {exc}")
            except Exception as exc:
                errors.append(f"pdf_provider: {exc}")

        # 4. Run UIOverlayProvider cleanup on all inventory
        overlay_provider = self._providers.get("overlay")
        if overlay_provider is not None:
            try:
                inventory = overlay_provider.get_inventory()
                for resource in inventory:
                    try:
                        overlay_provider.cleanup(resource)
                        cleaned += 1
                    except Exception as exc:
                        errors.append(f"overlay:{resource.key}: {exc}")
            except Exception as exc:
                errors.append(f"overlay_provider: {exc}")

        # 5. Force garbage collection
        gc.collect()

        duration_ms = (time.perf_counter() - t0) * 1000

        # Build and log report
        report = ReapReport(
            trigger=f"pressure_critical(USS={uss_mb:.1f}MB)",
            cleaned_count=cleaned,
            errors=errors,
            uss_mb=uss_mb,
            threshold_crossed="critical",
            duration_ms=duration_ms,
        )

        self._log_report(report)
        self._bus.emit("reap_complete", report=report)

        if errors:
            for err in errors:
                logger.warning("[Reaper] Deep clean error: %s", err)

        logger.info(
            "[Reaper] Deep clean complete — cleaned=%d, errors=%d, duration=%.1fms",
            cleaned,
            len(errors),
            duration_ms,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Stop the pressure monitor and execute a final reap cycle.

        Sets the stop event to terminate the pressure monitor daemon
        thread, then runs one last reconciliation pass to release any
        remaining orphaned resources.
        """
        self._stop_event.set()
        logger.info("[Reaper] Stopping — executing final reap cycle")
        self.reap(trigger="shutdown")
