"""
Stimme Performance Benchmark Suite
===================================
Measures the Three Pillars: Latency, Throughput, Resource Efficiency.

Usage:
    cd stimme
    python benchmark.py                  # Run all benchmarks
    python benchmark.py --skip-ocr       # Skip PDF/OCR tests (no test PDF)
    python benchmark.py --iterations 10  # Custom warm-start iterations
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import psutil

# Ensure programs/ is importable
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "programs"))


# ---------------------------------------------------------------------------
# Data classes for results
# ---------------------------------------------------------------------------

@dataclass
class TimingResult:
    label: str
    seconds: float
    ram_before_mb: float = 0.0
    ram_after_mb: float = 0.0

    @property
    def ram_delta_mb(self) -> float:
        return self.ram_after_mb - self.ram_before_mb

    def __str__(self) -> str:
        delta = f" | ΔRAM: {self.ram_delta_mb:+.1f}MB" if self.ram_before_mb else ""
        return f"  {self.label}: {self.seconds:.4f}s{delta}"


@dataclass
class BenchmarkReport:
    title: str
    results: List[TimingResult] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def add(self, result: TimingResult):
        self.results.append(result)

    def note(self, msg: str):
        self.notes.append(msg)

    def print(self):
        print(f"\n{'=' * 60}")
        print(f"  {self.title}")
        print(f"{'=' * 60}")
        for r in self.results:
            print(r)
        for n in self.notes:
            print(f"  ℹ {n}")
        print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROCESS = psutil.Process(os.getpid())


def ram_mb() -> float:
    """Current process RSS in MB."""
    return _PROCESS.memory_info().rss / (1024 * 1024)


def cpu_pct() -> float:
    """Snapshot CPU percent (short interval)."""
    return psutil.cpu_percent(interval=0.1)


def timed(label: str, fn, *args, **kwargs) -> TimingResult:
    """Run fn, return a TimingResult with wall time and RAM delta."""
    gc.collect()
    before = ram_mb()
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    t1 = time.perf_counter()
    after = ram_mb()
    return TimingResult(label, t1 - t0, before, after)


# ---------------------------------------------------------------------------
# Benchmark: Cold Boot
# ---------------------------------------------------------------------------

def bench_cold_boot() -> BenchmarkReport:
    """Measure how long it takes to import and instantiate TranslationBrain."""
    report = BenchmarkReport("Cold Boot (TranslationBrain init)")

    gc.collect()
    before = ram_mb()
    t0 = time.perf_counter()

    from brain import TranslationBrain
    brain = TranslationBrain()

    t1 = time.perf_counter()
    after = ram_mb()

    report.add(TimingResult("Total cold boot", t1 - t0, before, after))
    report.note(f"Idle RAM after boot: {after:.1f}MB")

    # Target check
    if t1 - t0 < 3.0:
        report.note("✅ PASS — Cold boot < 3.0s")
    elif t1 - t0 < 8.0:
        report.note("⚠️  WARN — Cold boot between 3.0s and 8.0s")
    else:
        report.note("❌ FAIL — Cold boot > 8.0s (bloated)")

    if after < 200:
        report.note("✅ PASS — Idle RAM < 200MB")
    elif after < 500:
        report.note("⚠️  WARN — Idle RAM between 200MB and 500MB")
    else:
        report.note("❌ FAIL — Idle RAM > 500MB (bloated)")

    # -- ONNX / fallback mode detection ------------------------------------
    _report_onnx_mode(report, brain)

    return report, brain


def _report_onnx_mode(report: BenchmarkReport, brain) -> None:
    """Append ONNX-vs-fallback status and active Execution Providers."""
    # Embedding provider
    if hasattr(brain, "embed_model") and brain.embed_model is not None:
        ep = brain.embed_model
        mode = "ONNX" if ep.is_onnx else "PyTorch fallback"
        report.note(f"Embedding backend: {mode}")
        if ep.is_onnx and hasattr(ep, "_session") and ep._session is not None:
            providers = ep._session.get_providers()
            report.note(f"  Execution providers: {', '.join(providers)}")
    else:
        report.note("Embedding backend: not loaded")

    # Emotion provider
    if hasattr(brain, "emotion_provider") and brain.emotion_provider is not None:
        em = brain.emotion_provider
        mode = "ONNX" if em.is_onnx else "PyTorch fallback"
        report.note(f"Emotion backend: {mode}")
        if em.is_onnx and hasattr(em, "_session") and em._session is not None:
            providers = em._session.get_providers()
            report.note(f"  Execution providers: {', '.join(providers)}")
    else:
        report.note("Emotion backend: not loaded")


# ---------------------------------------------------------------------------
# Benchmark: RAG Retrieval
# ---------------------------------------------------------------------------

NIETZSCHE_TEXT = (
    "Einst warf auch Zarathustra seinen Wahn jenseits des Menschen, "
    "gleich allen Hinterweltlern. Eines leidenden und zerquälten Gottes "
    "Werk schien mir da die Welt. Traum schien mir da die Welt und "
    "Dichtung eines Gottes; farbiger Rauch vor den Augen eines göttlich "
    "Unzufriedenen."
)


def bench_rag_retrieval(brain) -> BenchmarkReport:
    """Measure RAG context retrieval speed."""
    report = BenchmarkReport("RAG Retrieval Latency")

    if brain.db is None:
        report.note("⚠️  SKIP — No vector database connected")
        return report

    result = timed("RAG search", brain.get_context, NIETZSCHE_TEXT)
    report.add(result)

    if result.seconds < 0.1:
        report.note("✅ PASS — RAG search < 100ms")
    elif result.seconds < 0.5:
        report.note("⚠️  WARN — RAG search between 100ms and 500ms")
    else:
        report.note("❌ FAIL — RAG search > 500ms")

    return report


# ---------------------------------------------------------------------------
# Benchmark: Sentiment / Emotion Analysis
# ---------------------------------------------------------------------------

def bench_sentiment(brain) -> BenchmarkReport:
    """Measure RoBERTa emotion classification speed."""
    report = BenchmarkReport("Sentiment Analysis (RoBERTa)")

    if not hasattr(brain, "emotion_provider") or brain.emotion_provider is None:
        # Fallback: check for legacy emotion_pipe attribute
        if hasattr(brain, "emotion_pipe") and brain.emotion_pipe is not None:
            result = timed("Emotion inference", brain.emotion_pipe, NIETZSCHE_TEXT)
        else:
            report.note("⚠️  SKIP — No emotion provider loaded")
            return report
    else:
        result = timed("Emotion inference", brain.emotion_provider.classify, NIETZSCHE_TEXT)
    report.add(result)

    if result.seconds < 0.3:
        report.note("✅ PASS — Sentiment < 300ms")
    elif result.seconds < 0.5:
        report.note("⚠️  WARN — Sentiment between 300ms and 500ms")
    else:
        report.note("❌ FAIL — Sentiment > 500ms")

    return report


# ---------------------------------------------------------------------------
# Benchmark: Embedding (SentenceTransformer)
# ---------------------------------------------------------------------------

def bench_embedding(brain) -> BenchmarkReport:
    """Measure SentenceTransformer encode speed."""
    report = BenchmarkReport("Embedding (multilingual-e5-small)")

    if not hasattr(brain, "embed_model") or brain.embed_model is None:
        report.note("⚠️  SKIP — No embedding model loaded")
        return report

    result = timed("Encode", brain.embed_model.encode, NIETZSCHE_TEXT)
    report.add(result)

    if result.seconds < 0.05:
        report.note("✅ PASS — Embedding < 50ms")
    elif result.seconds < 0.2:
        report.note("⚠️  WARN — Embedding between 50ms and 200ms")
    else:
        report.note("❌ FAIL — Embedding > 200ms")

    return report


# ---------------------------------------------------------------------------
# Benchmark: Warm Start / Memory Leak Detection
# ---------------------------------------------------------------------------

def bench_warm_start(brain, iterations: int = 5) -> BenchmarkReport:
    """Run RAG + embedding + emotion N times, check for memory leaks and resource ceilings."""
    report = BenchmarkReport(f"Warm Start Leak Detection ({iterations} iterations)")

    if brain.db is None:
        report.note("⚠️  SKIP — No vector database for warm-start test")
        return report

    has_emotion = (
        hasattr(brain, "emotion_provider")
        and brain.emotion_provider is not None
    )

    gc.collect()
    baseline = ram_mb()
    times: list[float] = []
    spike_fail = False

    for i in range(iterations):
        gc.collect()
        pre_iter = ram_mb()
        t0 = time.perf_counter()

        # Simulate a full pre-translation pipeline
        brain.get_context(NIETZSCHE_TEXT)
        brain.embed_model.encode(NIETZSCHE_TEXT)
        if has_emotion:
            brain.emotion_provider.classify(NIETZSCHE_TEXT)

        t1 = time.perf_counter()
        post_iter = ram_mb()
        times.append(t1 - t0)

        # Per-request resource ceiling: < 50 MB spike
        spike = post_iter - pre_iter
        label = "Cold" if i == 0 else f"Warm #{i}"
        report.add(TimingResult(label, t1 - t0, pre_iter, post_iter))

        if spike > 50:
            report.note(f"❌ FAIL — Iteration {i} RAM spike {spike:+.1f}MB > 50MB ceiling")
            spike_fail = True

    if not spike_fail:
        report.note("✅ PASS — All iterations within 50MB per-request ceiling")

    # Residual check: wait 2s, gc, then compare to baseline
    time.sleep(2)
    gc.collect()
    final = ram_mb()
    residual = final - baseline

    avg_warm = sum(times[1:]) / len(times[1:]) if len(times) > 1 else times[0]
    report.note(f"Average warm latency: {avg_warm:.4f}s")
    report.note(f"RAM baseline: {baseline:.1f}MB → final: {final:.1f}MB (Δ{residual:+.1f}MB)")

    if residual < 5:
        report.note("✅ PASS — Residual RAM < 5MB after gc")
    elif residual < 50:
        report.note("⚠️  WARN — Residual RAM between 5MB and 50MB")
    else:
        report.note("❌ FAIL — Residual RAM > 50MB (memory leak)")

    # Check for degradation: is the last iteration slower than the 2nd?
    if len(times) >= 3:
        if times[-1] > times[1] * 1.5:
            report.note("❌ WARN — Last iteration 50%+ slower than 2nd (possible leak)")
        else:
            report.note("✅ PASS — No timing degradation detected")

    return report


# ---------------------------------------------------------------------------
# Benchmark: PDF / OCR Throughput
# ---------------------------------------------------------------------------

def bench_pdf_ocr(pdf_path: str) -> BenchmarkReport:
    """Measure PDF extraction throughput."""
    report = BenchmarkReport(f"PDF/OCR Throughput ({os.path.basename(pdf_path)})")

    if not os.path.isfile(pdf_path):
        report.note(f"⚠️  SKIP — File not found: {pdf_path}")
        return report

    try:
        import fitz
    except ImportError:
        report.note("⚠️  SKIP — PyMuPDF (fitz) not installed")
        return report

    gc.collect()
    before = ram_mb()
    t0 = time.perf_counter()

    doc = fitz.open(pdf_path)
    page_count = len(doc)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()

    t1 = time.perf_counter()
    after = ram_mb()

    total = t1 - t0
    per_page = total / page_count if page_count > 0 else 0

    report.add(TimingResult("Total extraction", total, before, after))
    report.note(f"Pages: {page_count}")
    report.note(f"Per-page: {per_page:.3f}s")
    report.note(f"Extracted chars: {len(full_text):,}")

    if per_page < 0.1:
        report.note("✅ PASS — < 0.1s per page")
    elif per_page < 0.5:
        report.note("⚠️  WARN — 0.1s–0.5s per page")
    else:
        report.note("❌ FAIL — > 0.5s per page")

    return report


# ---------------------------------------------------------------------------
# Benchmark: Import Audit
# ---------------------------------------------------------------------------

def bench_model_sizes() -> BenchmarkReport:
    """Report on-disk size of each ONNX model file in models/ directory."""
    report = BenchmarkReport("ONNX Model File Sizes")
    models_dir = BASE_DIR / "models"

    if not models_dir.is_dir():
        report.note("⚠️  SKIP — models/ directory not found")
        return report

    onnx_files = sorted(models_dir.rglob("*.onnx"))
    if not onnx_files:
        report.note("⚠️  SKIP — No .onnx files found in models/")
        return report

    for onnx_file in onnx_files:
        size_mb = onnx_file.stat().st_size / (1024 * 1024)
        rel = onnx_file.relative_to(models_dir)
        report.add(TimingResult(str(rel), 0.0, size_mb, size_mb))
        report.note(f"{onnx_file.name}: {size_mb:.1f}MB")

    return report


def bench_import_times() -> BenchmarkReport:
    """Measure import times for heavy modules."""
    report = BenchmarkReport("Module Import Times")

    # NOTE: sentence_transformers and transformers are excluded from in-process
    # import timing because they drag in PyTorch (~800MB RSS), which defeats
    # the purpose of the ONNX-only production runtime.  If you need to measure
    # their import cost, run them in a subprocess instead.
    modules = [
        ("flet", "flet"),
        ("onnxruntime", "onnxruntime"),
        ("anthropic", "anthropic"),
        ("PyMuPDF (fitz)", "fitz"),
        ("lancedb", "lancedb"),
        ("PyPDF2", "PyPDF2"),
        ("psutil", "psutil"),
    ]

    for label, mod_name in modules:
        # Evict from cache to measure true import time
        was_loaded = mod_name in sys.modules
        if was_loaded:
            report.add(TimingResult(f"{label} (already loaded)", 0.0))
            continue

        t0 = time.perf_counter()
        try:
            __import__(mod_name)
            t1 = time.perf_counter()
            report.add(TimingResult(label, t1 - t0))
        except ImportError:
            report.note(f"⚠️  {label}: not installed")

    return report


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(reports: list[BenchmarkReport]):
    """Print a final summary table with overall PASS/FAIL status."""
    print("\n" + "=" * 60)
    print("  STIMME PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"  {'Metric':<35} {'Value':>12}")
    print(f"  {'-' * 35} {'-' * 12}")

    for r in reports:
        if r.title == "ONNX Model File Sizes":
            for result in r.results:
                size_mb = result.ram_after_mb
                print(f"  {result.label:<35} {size_mb:>9.1f}MB")
        else:
            for result in r.results:
                print(f"  {result.label:<35} {result.seconds:>10.4f}s")

    final_ram = ram_mb()
    print(f"\n  Final process RAM: {final_ram:.1f}MB")
    print(f"  CPU: {cpu_pct():.1f}%")

    # Overall PASS/FAIL: scan all notes for failures
    all_notes = [n for r in reports for n in r.notes]
    failures = [n for n in all_notes if "❌ FAIL" in n]
    if failures:
        print(f"\n  ❌ OVERALL: FAIL ({len(failures)} check(s) failed)")
        for f in failures:
            print(f"     {f.strip()}")
    else:
        print("\n  ✅ OVERALL: PASS — All performance targets met")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stimme Performance Benchmark")
    parser.add_argument("--skip-ocr", action="store_true", help="Skip PDF/OCR tests")
    parser.add_argument("--iterations", type=int, default=5, help="Warm-start iterations")
    parser.add_argument("--pdf", type=str, default=None, help="Path to test PDF for OCR benchmark")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════════╗")
    print("║        STIMME — Philological Performance Report          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  PID: {os.getpid()} | RAM at start: {ram_mb():.1f}MB")

    reports: list[BenchmarkReport] = []

    # 0. Cold boot (run first before anything is loaded)
    r_boot, brain = bench_cold_boot()
    r_boot.print()
    reports.append(r_boot)

    # 1. ONNX model file sizes
    r = bench_model_sizes()
    r.print()
    reports.append(r)

    # 2. Import times
    r = bench_import_times()
    r.print()
    reports.append(r)

    # 3. RAG retrieval
    r = bench_rag_retrieval(brain)
    r.print()
    reports.append(r)

    # 4. Sentiment
    r = bench_sentiment(brain)
    r.print()
    reports.append(r)

    # 5. Embedding
    r = bench_embedding(brain)
    r.print()
    reports.append(r)

    # 6. Warm start / leak detection
    r = bench_warm_start(brain, iterations=args.iterations)
    r.print()
    reports.append(r)

    # 7. PDF/OCR (optional)
    if not args.skip_ocr:
        pdf = args.pdf
        if pdf is None:
            # Try to find a test PDF
            candidates = list(Path(BASE_DIR).rglob("*.pdf"))
            if candidates:
                pdf = str(candidates[0])
        if pdf:
            r = bench_pdf_ocr(pdf)
            r.print()
            reports.append(r)
        else:
            print("\n  ⚠️  No PDF found for OCR benchmark. Use --pdf <path> or --skip-ocr")

    # Summary
    print_summary(reports)


if __name__ == "__main__":
    main()
