"""Auto-download quantized ONNX model files from HuggingFace Hub.

On first run (or when model files are missing), this module downloads the
pre-exported INT8-quantized ONNX models from a HuggingFace repository so
that users never need PyTorch or dev dependencies installed.

The download is a one-time operation (~178 MB total).  Subsequent runs
detect the existing files and skip the download.
"""

from __future__ import annotations

import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HF_REPO_ID = "rpsammons6/stimme-models"

# (local_subdir, local_filename, hf_filename, friendly_name)
_MODEL_FILES: list[tuple[str, str, str, str]] = [
    ("embedding/onnx", "model_quantized.onnx", "embedding/model_quantized.onnx", "Embedding Model"),
    ("emotion", "model_quantized.onnx", "emotion/model_quantized.onnx", "Emotion Model"),
]


def _resolve_models_dir() -> Path:
    """Resolve the models directory (same logic as onnx_providers)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        frozen_path = Path(meipass) / "models"
        if frozen_path.is_dir():
            return frozen_path
    return Path(__file__).resolve().parent.parent / "models"


def models_present(models_dir: Path | None = None) -> bool:
    """Return True if all required ONNX model files exist on disk."""
    base = models_dir or _resolve_models_dir()
    for subdir, filename, _, _ in _MODEL_FILES:
        if not (base / subdir / filename).is_file():
            return False
    return True


def _check_connectivity() -> bool:
    """Quick check: can we reach huggingface.co?"""
    try:
        urllib.request.urlopen("https://huggingface.co", timeout=5)
        return True
    except (urllib.error.URLError, OSError):
        return False


def _download_with_progress(url: str, dest: Path, label: str) -> None:
    """Download a file with a tqdm progress bar (falls back to plain print)."""
    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = None

    # Open the connection to get Content-Length
    response = urllib.request.urlopen(url, timeout=60)
    total = int(response.headers.get("Content-Length", 0))

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".onnx.tmp")

    chunk_size = 1024 * 256  # 256 KB chunks

    if tqdm and total > 0:
        with open(tmp, "wb") as f, tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"  {label}",
            bar_format="{desc}: {percentage:3.0f}%|{bar:20}| {n_fmt}/{total_fmt}, {rate_fmt}",
        ) as pbar:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                pbar.update(len(chunk))
    else:
        # No tqdm or unknown size — simple print
        downloaded = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded * 100 // total
                    mb_done = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    print(f"\r  {label}: {pct}% ({mb_done:.1f}/{mb_total:.1f} MB)", end="", flush=True)
        if total > 0:
            print()  # newline after progress

    # Atomic rename
    if dest.exists():
        dest.unlink()
    tmp.rename(dest)


def download_models(models_dir: Path | None = None) -> bool:
    """Download missing ONNX model files from HuggingFace Hub.

    Returns True if all models are now present.
    """
    base = models_dir or _resolve_models_dir()

    missing: list[tuple[str, str, str, str]] = []
    for subdir, filename, hf_path, friendly in _MODEL_FILES:
        if not (base / subdir / filename).is_file():
            missing.append((subdir, filename, hf_path, friendly))

    if not missing:
        return True

    # Check internet first
    print("\n📦 ONNX models not found — downloading from HuggingFace...")
    print(f"   Repository: {HF_REPO_ID}")
    print(f"   This is a one-time download (~178 MB total).\n")

    if not _check_connectivity():
        print("❌ No internet connection detected.")
        print("   ONNX models are required for embedding and emotion analysis.")
        print("   Please connect to the internet and restart the application.\n")
        return False

    success = True
    for subdir, filename, hf_path, friendly in missing:
        local_path = base / subdir / filename
        url = f"https://huggingface.co/{HF_REPO_ID}/resolve/main/{hf_path}"

        try:
            _download_with_progress(url, local_path, friendly)
            size_mb = local_path.stat().st_size / (1024 * 1024)
            print(f"  ✅ {friendly} ({size_mb:.1f} MB)\n")
        except urllib.error.URLError as exc:
            logger.error("Failed to download %s: %s", friendly, exc)
            print(f"  ❌ Failed to download {friendly}: {exc}")
            print("     Please check your internet connection and try again.\n")
            # Clean up partial file
            tmp = local_path.with_suffix(".onnx.tmp")
            for f in (tmp, local_path):
                if f.exists():
                    try:
                        f.unlink()
                    except OSError:
                        pass
            success = False
        except OSError as exc:
            logger.error("Failed to write %s: %s", friendly, exc)
            print(f"  ❌ Failed to save {friendly}: {exc}\n")
            success = False

    if success:
        print("✅ All ONNX models downloaded successfully.\n")
    else:
        print("⚠️  Some models failed to download.")
        print("   The app will run with reduced functionality.")
        print("   Restart with an internet connection to complete setup.\n")

    return success


def ensure_models(models_dir: Path | None = None) -> bool:
    """Ensure ONNX model files are present, downloading if necessary.

    This is the main entry point. Call before initializing providers.
    Returns True if models are available.
    """
    if models_present(models_dir):
        return True
    return download_models(models_dir)
