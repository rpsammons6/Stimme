"""
Lightweight memory diagnostics for tracking down leaks.

Usage:
    from app.mem_debug import log_mem, log_refs

    log_mem("before cleanup")   # prints RSS + object counts
    log_refs(some_obj, "my_obj")  # prints referrer chain for an object
"""

import gc
import os

_TAG = "[MEM_DEBUG]"


def _rss_mb() -> float:
    """Return current process RSS in MB (cross-platform)."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except ImportError:
        pass
    # Fallback: read /proc on Linux
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    return -1.0


def log_ram(label: str = ""):
    """Print just the RSS — quick and clean for tracking RAM over time."""
    rss = _rss_mb()
    print(f"🧠 RAM [{label}]: {rss:.1f} MB")


def log_mem(label: str = ""):
    """Print RSS and key object counts."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gc.collect()
    rss = _rss_mb()

    # Count objects of interest
    import flet as ft
    from app.components.views.pdf_viewer import WebView_PDF_Viewer
    from app.components.views.parallel_view import ParallelView

    pdf_viewers = 0
    parallel_views = 0
    flet_images = 0
    file_pickers = 0
    large_strings = 0  # base64 blobs (>100KB)
    large_string_bytes = 0
    gesture_detectors = 0

    for obj in gc.get_objects():
        try:
            if isinstance(obj, WebView_PDF_Viewer):
                pdf_viewers += 1
            elif isinstance(obj, ParallelView):
                parallel_views += 1
            elif isinstance(obj, ft.Image):
                flet_images += 1
            elif isinstance(obj, ft.FilePicker):
                file_pickers += 1
            elif isinstance(obj, ft.GestureDetector):
                gesture_detectors += 1
            elif isinstance(obj, str) and len(obj) > 100_000:
                large_strings += 1
                large_string_bytes += len(obj)
        except (ReferenceError, TypeError):
            pass

    print(
        f"{_TAG} [{label}] "
        f"RSS={rss:.1f}MB | "
        f"WebView_PDF_Viewers={pdf_viewers} | "
        f"ParallelViews={parallel_views} | "
        f"ft.Images={flet_images} | "
        f"GestureDetectors={gesture_detectors} | "
        f"FilePickers={file_pickers} | "
        f"LargeStrings(>100KB)={large_strings} ({large_string_bytes // 1024}KB)"
    )


def log_refs(obj, name: str = "obj", depth: int = 2):
    """Print the referrer chain for a specific object up to `depth` levels."""
    gc.collect()
    print(f"{_TAG} --- referrers of {name} (id={id(obj)}) ---")
    _print_referrers(obj, depth, indent=0, seen=set())
    print(f"{_TAG} --- end referrers ---")


def _print_referrers(obj, depth, indent, seen):
    if depth <= 0:
        return
    obj_id = id(obj)
    if obj_id in seen:
        return
    seen.add(obj_id)

    referrers = gc.get_referrers(obj)
    for ref in referrers:
        # Skip frames and this module's own structures
        if isinstance(ref, dict) and "__name__" in ref:
            continue
        if isinstance(ref, type):
            continue
        try:
            ref_type = type(ref).__name__
            ref_summary = repr(ref)[:120]
        except Exception:
            ref_type = "???"
            ref_summary = "<unrepresentable>"

        prefix = "  " * indent
        print(f"{_TAG} {prefix}← {ref_type}: {ref_summary}")
        _print_referrers(ref, depth - 1, indent + 1, seen)


def log_overlay(page, label: str = ""):
    """Print the contents of page.overlay to detect FilePicker accumulation."""
    try:
        count = len(page.overlay)
        types = {}
        for ctrl in page.overlay:
            t = type(ctrl).__name__
            types[t] = types.get(t, 0) + 1
        print(f"{_TAG} [{label}] page.overlay count={count} | types={types}")
    except Exception:
        print(f"{_TAG} [{label}] page.overlay: <error reading>")


def log_surviving_refs():
    """After cleanup, find surviving WebView_PDF_Viewer/ParallelView instances and print what holds them."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gc.collect()

    import flet as ft
    from app.components.views.pdf_viewer import WebView_PDF_Viewer
    from app.components.views.parallel_view import ParallelView

    # Collect surviving instances
    surviving_pv = []
    surviving_pdf = []
    for obj in gc.get_objects():
        try:
            if isinstance(obj, WebView_PDF_Viewer):
                surviving_pdf.append(obj)
            elif isinstance(obj, ParallelView):
                surviving_pv.append(obj)
        except (ReferenceError, TypeError):
            pass

    for i, pv in enumerate(surviving_pv):
        cleaned = pv._page is None  # our cleanup sets _page = None
        print(f"{_TAG} [SURVIVING] ParallelView #{i} cleaned={cleaned} id={id(pv)}")
        _print_referrer_summary(pv, f"ParallelView #{i}")

    for i, pdf in enumerate(surviving_pdf):
        cleaned = pdf._page is None  # our cleanup sets _page = None
        print(f"{_TAG} [SURVIVING] WebView_PDF_Viewer #{i} cleaned={cleaned} id={id(pdf)}")
        _print_referrer_summary(pdf, f"WebView_PDF_Viewer #{i}")


def _print_referrer_summary(obj, label: str):
    """Print a concise summary of what's holding a reference to obj."""
    referrers = gc.get_referrers(obj)
    for ref in referrers:
        # Skip stack frames and module dicts
        if isinstance(ref, type):
            continue
        ref_type = type(ref).__name__

        # For dicts, try to identify the owner
        if isinstance(ref, dict):
            # Check if it's an instance __dict__
            owners = gc.get_referrers(ref)
            for owner in owners:
                if isinstance(owner, type):
                    continue
                if hasattr(owner, '__dict__') and owner.__dict__ is ref:
                    owner_type = type(owner).__name__
                    # Find which attribute holds our object
                    for attr_name, attr_val in ref.items():
                        if attr_val is obj:
                            print(f"{_TAG}   held by {owner_type}.{attr_name} (id={id(owner)})")
                            break
                    else:
                        print(f"{_TAG}   held by {owner_type}.__dict__ (id={id(owner)})")
                    break
            else:
                # Standalone dict — show keys that reference our object
                holding_keys = [k for k, v in ref.items() if v is obj]
                if holding_keys:
                    print(f"{_TAG}   held by dict keys={holding_keys}")
                else:
                    print(f"{_TAG}   held by dict (id={id(ref)})")
        elif isinstance(ref, list):
            # Check if it's a Flet controls list or similar
            owners = gc.get_referrers(ref)
            owner_types = []
            for owner in owners:
                if isinstance(owner, type):
                    continue
                if hasattr(owner, 'controls') and owner.controls is ref:
                    owner_types.append(f"{type(owner).__name__}.controls")
                elif hasattr(owner, '__dict__'):
                    for attr_name, attr_val in owner.__dict__.items():
                        if attr_val is ref:
                            owner_types.append(f"{type(owner).__name__}.{attr_name}")
                            break
            if owner_types:
                print(f"{_TAG}   held by list owned by: {owner_types}")
            else:
                print(f"{_TAG}   held by list len={len(ref)} (id={id(ref)})")
        elif ref_type == "frame":
            continue  # skip stack frames
        elif ref_type == "cell":
            # Closure cell — find the function that owns it
            cell_owners = gc.get_referrers(ref)
            for co in cell_owners:
                if callable(co) and hasattr(co, '__qualname__'):
                    print(f"{_TAG}   held by closure cell in {co.__qualname__}")
                    break
            else:
                print(f"{_TAG}   held by closure cell")
        else:
            try:
                print(f"{_TAG}   held by {ref_type} (id={id(ref)}) repr={repr(ref)[:100]}")
            except Exception:
                print(f"{_TAG}   held by {ref_type} (id={id(ref)})")
