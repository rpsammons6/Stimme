#!/usr/bin/env python3
"""Ram-o'-Meter — Stimme Memory Diagnostic Tool.

A developer-only diagnostic script that produces a single-shot
"Philological Performance Report" detailing per-component memory usage
across Stimme's UI and backend subsystems.

Usage::

    python ram_meter.py                     # run all probes
    python ram_meter.py --probe "ONNX"      # run a single probe
    python ram_meter.py --timeout 30        # custom timeout per probe
    python ram_meter.py --verbose           # include module-level breakdown

Follows the same standalone-script pattern as ``benchmark.py``.
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal observer-effect imports (Requirement 1.1)
# Only psutil, gc, sys, os, and standard-library helpers at module scope.
# ---------------------------------------------------------------------------
from tests.ram_meter.memory_utils import (
    enumerate_process_family,
    measure_rss_mb,
)
from tests.ram_meter.models import ProcessFamilyEntry

logger = logging.getLogger(__name__)

# Minimum allowed timeout in seconds (Requirement 13.2 / CLI Errors)
_MIN_TIMEOUT = 5
_DEFAULT_TIMEOUT = 60


# ----------------------------------------------------------------------- #
# CLI
# ----------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters
    ----------
    argv:
        Argument list to parse.  Defaults to ``sys.argv[1:]``.
    """
    parser = argparse.ArgumentParser(
        description="Stimme Ram-o'-Meter — Memory Diagnostic Tool",
    )
    parser.add_argument(
        "--probe",
        type=str,
        default=None,
        help="Run a single named probe instead of the full suite.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=_DEFAULT_TIMEOUT,
        help=(
            f"Per-probe subprocess timeout in seconds "
            f"(default: {_DEFAULT_TIMEOUT}, minimum: {_MIN_TIMEOUT})."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include module-level memory breakdown in failure diagnostics.",
    )

    args = parser.parse_args(argv)

    # Clamp timeout to minimum (Requirement 13.2 / CLI Errors)
    if args.timeout < _MIN_TIMEOUT:
        warnings.warn(
            f"--timeout {args.timeout}s is below minimum; clamped to {_MIN_TIMEOUT}s.",
            stacklevel=2,
        )
        args.timeout = _MIN_TIMEOUT

    return args


# ----------------------------------------------------------------------- #
# Orchestrator
# ----------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> None:
    """Entry point for the Ram-o'-Meter diagnostic tool."""

    args = parse_args(argv)

    # ── 1. Record baseline RSS (observer effect) ──────────────────────
    baseline_rss = measure_rss_mb()

    # ── 2. Discover probes ────────────────────────────────────────────
    from tests.ram_meter.discovery import discover_probes  # noqa: PLC0415

    probe_paths = discover_probes(probe_filter=args.probe)

    if not probe_paths:
        if args.probe:
            print(f"Error: no probe matching '{args.probe}' found.", file=sys.stderr)
            sys.exit(1)
        # Empty suite — still produce a report (Requirement 6.5)
        print("Warning: no probes discovered. Producing empty report.")

    # ── 3. Execute probes in isolated subprocesses ────────────────────
    from tests.ram_meter.executor import run_all_probes  # noqa: PLC0415

    results = run_all_probes(probe_paths, timeout=args.timeout)

    # ── 4. Load budget overrides from config ──────────────────────────
    from tests.ram_meter.budget import (  # noqa: PLC0415
        load_budget_overrides,
        resolve_budget,
    )

    overrides = load_budget_overrides()

    # ── 5. Determine Base UI Floor ────────────────────────────────────
    # The Base UI Floor is the USS delta reported by the Flet base probe
    # (is_ui_component=True).  If no such probe ran, fall back to 0.
    base_ui_floor: float = 0.0
    for r in results:
        if r.is_ui_component:
            base_ui_floor = r.uss_delta_mb
            break

    # ── 6. Resolve budgets and evaluate verdicts ──────────────────────
    from tests.ram_meter.verdict import evaluate_verdict  # noqa: PLC0415

    verdicts = []
    for result in results:
        effective_budget, budget_source = resolve_budget(
            result, overrides, base_ui_floor,
        )
        verdict = evaluate_verdict(result, effective_budget, budget_source)
        verdicts.append(verdict)

    # ── 7. Enumerate process family ───────────────────────────────────
    raw_family = enumerate_process_family()
    process_family = [
        ProcessFamilyEntry(
            name=entry["name"],
            pid=entry["pid"],
            rss_mb=entry["rss_mb"],
        )
        for entry in raw_family
    ]

    # ── 8. Compute observer overhead ──────────────────────────────────
    observer_overhead = measure_rss_mb() - baseline_rss

    # ── 9. Build and print the Philological Performance Report ────────
    from tests.ram_meter.report import (  # noqa: PLC0415
        build_report_data,
        print_report,
    )

    report_data = build_report_data(
        verdicts=verdicts,
        process_family=process_family,
        observer_overhead=observer_overhead,
        base_ui_floor=base_ui_floor if base_ui_floor > 0 else None,
    )
    print_report(report_data, verbose=args.verbose)


if __name__ == "__main__":
    main()
