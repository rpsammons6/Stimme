"""
ONNX Runtime providers for embedding and emotion inference.

This module provides EmbeddingProvider and EmotionProvider classes that load
ONNX-exported models at runtime, with transparent PyTorch fallback when ONNX
model files have not yet been exported via export_onnx.py.

CRITICAL: No torch/transformers/sentence_transformers imports at module level.
Fallback imports are scoped inside methods to keep packaged builds torch-free.
"""

import gc
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

# ---------------------------------------------------------------------------
# Execution provider lists — split by workload type
# ---------------------------------------------------------------------------
# Embeddings: CPU-only.  The model is small (112MB) and CPU inference is fast
# enough.  Skipping DirectML avoids the ~800MB GPU runtime init overhead that
# would inflate RSS and slow cold boot for no measurable gain.
_CPU_PROVIDERS = [
    "CPUExecutionProvider",
]

# Emotion classification: GPU-accelerated when available.  The heavier model
# benefits from DirectML / CoreML, and the GPU init cost is amortised over
# repeated inference calls.
_GPU_PROVIDERS = [
    "DmlExecutionProvider",       # Windows DirectML (GPU)
    "CoreMLExecutionProvider",    # macOS Apple Silicon
    "CPUExecutionProvider",       # Universal fallback
]


def _resolve_models_dir(models_dir: str | None = None) -> Path:
    """Resolve the models directory for both source and frozen environments.

    Priority:
      1. Explicit *models_dir* argument (if provided and exists).
      2. ``sys._MEIPASS / "models"`` — PyInstaller frozen bundle.
      3. ``<this_file>/../../models`` — running from source.
    """
    if models_dir is not None:
        p = Path(models_dir)
        if p.is_dir():
            return p

    # Frozen app (PyInstaller)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        frozen_path = Path(meipass) / "models"
        if frozen_path.is_dir():
            return frozen_path

    # Source-tree: stimme/programs/onnx_providers.py -> stimme/models
    source_path = Path(__file__).resolve().parent.parent / "models"
    return source_path


def _create_session(
    model_path: str | Path,
    providers: list[str] | None = None,
) -> ort.InferenceSession:
    """Create an ONNX Runtime InferenceSession with the given providers.

    Args:
        model_path: Path to the ``.onnx`` model file.
        providers: Execution provider priority list.  Defaults to
            ``_CPU_PROVIDERS`` when *None*.
    """
    model_path = str(model_path)
    if providers is None:
        providers = _CPU_PROVIDERS
    # Enable memory-mapped weights so the OS pages in only what's needed,
    # keeping RSS low for large models.
    sess_options = ort.SessionOptions()
    sess_options.add_session_config_entry("session.use_mmap", "1")
    # onnxruntime silently ignores providers it cannot load, so we can
    # safely pass the full priority list on every platform.
    session = ort.InferenceSession(
        model_path, sess_options=sess_options, providers=providers
    )
    active = session.get_providers()
    print(f"✅ ONNX session loaded: {Path(model_path).name}  "
          f"[providers: {', '.join(active)}]")
    return session


# ---------------------------------------------------------------------------
# SessionReaper — TTL-based ONNX session eviction
# ---------------------------------------------------------------------------

class SessionReaper:
    """Background daemon that evicts idle ONNX sessions after a TTL expires.

    Usage::

        reaper = SessionReaper(check_interval=60.0)
        reaper.register("embedding", provider, ttl=300.0)
        # … provider is used for inference …
        reaper.stop()
    """

    def __init__(self, check_interval: float = 60.0):
        self._providers: dict[str, tuple[object, float]] = {}  # name -> (provider, ttl)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._check_interval = check_interval
        self._thread = threading.Thread(
            target=self._reap_loop, daemon=True, name="SessionReaper"
        )
        self._thread.start()

    # -- public API ----------------------------------------------------------

    def register(self, name: str, provider: object, ttl: float = 300.0) -> None:
        """Register a provider for TTL-based eviction.

        *provider* must expose ``_last_access`` (float), ``_session``
        (nullable), and ``_session_lock`` (threading.Lock) attributes.
        """
        with self._lock:
            self._providers[name] = (provider, ttl)

    def touch(self, name: str) -> None:
        """Update the last-access timestamp for *name*."""
        with self._lock:
            entry = self._providers.get(name)
        if entry is not None:
            provider, _ = entry
            provider._last_access = time.time()

    def stop(self) -> None:
        """Signal the reaper thread to exit and wait for it to finish."""
        self._stop_event.set()
        self._thread.join(timeout=self._check_interval + 5)

    # -- internal ------------------------------------------------------------

    def _reap_loop(self) -> None:
        """Periodically check registered providers and evict idle sessions."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._check_interval)
            if self._stop_event.is_set():
                break

            with self._lock:
                snapshot = list(self._providers.items())

            for name, (provider, ttl) in snapshot:
                try:
                    idle = time.time() - getattr(provider, "_last_access", 0.0)
                    if idle > ttl and getattr(provider, "_session", None) is not None:
                        lock = getattr(provider, "_session_lock", None)
                        if lock is not None:
                            with lock:
                                provider._session = None
                        else:
                            provider._session = None
                        gc.collect()
                        print(f"♻️  REAPER: Evicted '{name}' session "
                              f"(idle {idle:.0f}s > TTL {ttl:.0f}s)")
                except Exception as exc:
                    # Swallow errors so the daemon stays alive (Property 6).
                    print(f"⚠️  REAPER: Error checking '{name}': {exc}")


# ---------------------------------------------------------------------------
# EmbeddingProvider
# ---------------------------------------------------------------------------

class EmbeddingProvider:
    """Encode text to 384-dim vectors via ONNX Runtime (or PyTorch fallback)."""

    def __init__(self, models_dir: str | None = None):
        self._onnx = False
        self._session: ort.InferenceSession | None = None
        self._tokenizer: Tokenizer | None = None
        self._fallback_model = None  # lazy SentenceTransformer
        self._last_access: float = time.time()
        self._session_lock = threading.Lock()
        self._model_path: Path | None = None

        base = _resolve_models_dir(models_dir)
        emb_dir = base / "embedding"

        # sentence-transformers exports ONNX files into an ``onnx/``
        # subdirectory.  Check both the flat layout and the nested one.
        model_file: Path | None = None
        for search_dir in (emb_dir, emb_dir / "onnx"):
            quantized = search_dir / "model_quantized.onnx"
            full = search_dir / "model.onnx"
            candidate = quantized if quantized.is_file() else full
            if candidate.is_file():
                model_file = candidate
                break

        tokenizer_path = emb_dir / "tokenizer.json"

        if model_file is not None and tokenizer_path.is_file():
            try:
                self._session = _create_session(model_file, _CPU_PROVIDERS)
                self._model_path = model_file
                self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
                self._tokenizer.enable_truncation(max_length=512)
                self._onnx = True
            except Exception as exc:
                print(f"⚠️  EmbeddingProvider: ONNX load failed ({exc}), "
                      "falling back to PyTorch")
                self._init_fallback()
        else:
            print("⚠️  EmbeddingProvider: ONNX model files not found, "
                  "falling back to PyTorch")
            self._init_fallback()

    # -- fallback (scoped import) ------------------------------------------

    def _init_fallback(self):
        """Load PyTorch SentenceTransformer as fallback (scoped import)."""
        try:
            from sentence_transformers import SentenceTransformer  # noqa: local
        except ImportError:
            raise ImportError(
                "ONNX model files not found and PyTorch fallback packages are not installed. "
                "Run `python programs/export_onnx.py` to export ONNX models first, "
                "or install dev dependencies: pip install -r requirements-dev.txt"
            )
        self._fallback_model = SentenceTransformer(
            "intfloat/multilingual-e5-small"
        )
        self._onnx = False

    # -- public API ---------------------------------------------------------

    @property
    def is_onnx(self) -> bool:
        """True when running the ONNX backend."""
        return self._onnx

    def encode(self, text: str) -> np.ndarray:
        """Encode *text* to a 384-dim L2-normalised float vector.

        The ``query: `` prefix required by the e5 model family is prepended
        automatically in both ONNX and fallback paths.
        """
        self._last_access = time.time()

        if not text or not text.strip():
            return np.zeros(384, dtype=np.float32)

        if self._onnx:
            return self._encode_onnx(text)
        return self._encode_fallback(text)

    # -- internals ----------------------------------------------------------

    def _encode_onnx(self, text: str) -> np.ndarray:
        # Reload session if it was evicted by the TTL reaper
        # Reload session if it was evicted by the TTL reaper
        if self._session is None:
            with self._session_lock:
                if self._session is None:
                    self._session = _create_session(self._model_path, _CPU_PROVIDERS)

        prefixed = f"query: {text}"
        encoding = self._tokenizer.encode(prefixed)

        input_ids = np.array([encoding.ids], dtype=np.int64)
        attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

        feeds = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }

        # Only pass inputs the model actually expects
        expected_names = {inp.name for inp in self._session.get_inputs()}
        feeds = {k: v for k, v in feeds.items() if k in expected_names}

        outputs = self._session.run(None, feeds)
        # last_hidden_state: (1, seq_len, hidden_dim)
        hidden = outputs[0]

        # Attention-mask-weighted mean pooling
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        summed = (hidden * mask_expanded).sum(axis=1)
        counts = mask_expanded.sum(axis=1).clip(min=1e-9)
        pooled = summed / counts  # (1, 384)

        # L2 normalise
        vec = pooled[0]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return vec.astype(np.float32)

    def _encode_fallback(self, text: str) -> np.ndarray:
        prefixed = f"query: {text}"
        vec = self._fallback_model.encode(prefixed)
        return np.asarray(vec, dtype=np.float32)


# ---------------------------------------------------------------------------
# EmotionProvider
# ---------------------------------------------------------------------------

class EmotionProvider:
    """Classify text emotion via ONNX Runtime (or PyTorch fallback)."""

    def __init__(self, models_dir: str | None = None):
        self._onnx = False
        self._session: ort.InferenceSession | None = None
        self._tokenizer: Tokenizer | None = None
        self._id2label: dict[int, str] | None = None
        self._fallback_pipe = None  # lazy transformers pipeline
        self._last_access: float = time.time()
        self._session_lock = threading.Lock()
        self._model_path: Path | None = None

        base = _resolve_models_dir(models_dir)
        emo_dir = base / "emotion"

        # Prefer quantised model, fall back to float32
        quantized = emo_dir / "model_quantized.onnx"
        full = emo_dir / "model.onnx"
        tokenizer_path = emo_dir / "tokenizer.json"
        config_path = emo_dir / "config.json"

        model_file = quantized if quantized.is_file() else full

        if model_file.is_file() and tokenizer_path.is_file() and config_path.is_file():
            try:
                self._session = _create_session(model_file, _GPU_PROVIDERS)
                self._model_path = model_file
                self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
                self._tokenizer.enable_truncation(max_length=512)

                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                # id2label keys in config.json are strings ("0", "1", …)
                self._id2label = {
                    int(k): v for k, v in config["id2label"].items()
                }
                self._onnx = True
            except Exception as exc:
                print(
                    f"⚠️  EmotionProvider: ONNX load failed ({exc}), "
                    "falling back to PyTorch"
                )
                self._init_fallback()
        else:
            print(
                "⚠️  EmotionProvider: ONNX model files not found, "
                "falling back to PyTorch"
            )
            self._init_fallback()

    # -- fallback (scoped import) ------------------------------------------

    def _init_fallback(self):
        """Load PyTorch transformers pipeline as fallback (scoped import)."""
        try:
            from transformers import pipeline  # noqa: local
        except ImportError:
            raise ImportError(
                "ONNX model files not found and PyTorch fallback packages are not installed. "
                "Run `python programs/export_onnx.py` to export ONNX models first, "
                "or install dev dependencies: pip install -r requirements-dev.txt"
            )

        self._fallback_pipe = pipeline(
            "text-classification",
            model="visegradmedia-emotion/Emotion_RoBERTa_german6_v7",
            top_k=None,  # return all labels so classify() can slice top_k
        )
        self._onnx = False

    # -- public API ---------------------------------------------------------

    @property
    def is_onnx(self) -> bool:
        """True when running the ONNX backend."""
        return self._onnx

    def classify(self, text: str, top_k: int = 3) -> list[dict]:
        """Classify *text* emotion, returning label-score pairs sorted descending.

        Args:
            text: Input text to classify.
            top_k: Number of top results to return.

        Returns:
            ``[{"label": str, "score": float}, ...]`` sorted by score desc.
        """
        self._last_access = time.time()

        if not text or not text.strip():
            # Graceful empty-input handling: return top_k entries with 0 scores
            if self._onnx and self._id2label:
                labels = list(self._id2label.values())
            elif self._fallback_pipe is not None:
                # Use a dummy call to discover labels, or return generic
                labels = [f"label_{i}" for i in range(top_k)]
            else:
                labels = [f"label_{i}" for i in range(top_k)]
            return [{"label": labels[i % len(labels)], "score": 0.0}
                    for i in range(top_k)]

        if self._onnx:
            return self._classify_onnx(text, top_k)
        return self._classify_fallback(text, top_k)

    # -- internals ----------------------------------------------------------

    def _classify_onnx(self, text: str, top_k: int) -> list[dict]:
        # Reload session if it was evicted by the TTL reaper
        if self._session is None:
            with self._session_lock:
                if self._session is None:
                    self._session = _create_session(self._model_path, _GPU_PROVIDERS)

        encoding = self._tokenizer.encode(text)

        input_ids = np.array([encoding.ids], dtype=np.int64)
        attention_mask = np.array([encoding.attention_mask], dtype=np.int64)

        feeds: dict[str, np.ndarray] = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }

        # Only pass inputs the model actually expects
        expected_names = {inp.name for inp in self._session.get_inputs()}
        feeds = {k: v for k, v in feeds.items() if k in expected_names}

        outputs = self._session.run(None, feeds)
        logits = outputs[0][0]  # shape: (num_labels,)

        # Softmax
        exp_logits = np.exp(logits - np.max(logits))  # numerical stability
        probs = exp_logits / exp_logits.sum()

        # Build label-score pairs and sort descending
        results = [
            {"label": self._id2label[i], "score": float(probs[i])}
            for i in range(len(probs))
        ]
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _classify_fallback(self, text: str, top_k: int) -> list[dict]:
        raw = self._fallback_pipe(text)
        # pipeline with top_k=None returns [[{...}, ...]] (nested list)
        results = raw[0] if raw and isinstance(raw[0], list) else raw
        sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)
        return sorted_results[:top_k]
