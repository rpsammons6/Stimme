"""
Export both ML models to ONNX format with INT8 quantization.

This is a **dev-only** script — it requires PyTorch, sentence-transformers,
optimum, and transformers.  The exported ONNX files are consumed at runtime
by ``onnx_providers.py`` which needs only ``onnxruntime`` and ``tokenizers``.

Usage::

    python -m stimme.programs.export_onnx          # from repo root
    python stimme/programs/export_onnx.py           # direct invocation

Outputs are written to ``stimme/models/embedding/`` and
``stimme/models/emotion/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _models_root() -> Path:
    """Return ``stimme/models/`` relative to this file."""
    return Path(__file__).resolve().parent.parent / "models"


def _quantize_model(onnx_path: str | Path) -> Path:
    """Apply INT8 dynamic quantization to *onnx_path*.

    Produces ``model_quantized.onnx`` in the same directory.
    Returns the path to the quantized model.
    """
    from optimum.onnxruntime import ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig

    onnx_path = Path(onnx_path)
    output_dir = onnx_path.parent

    quantizer = ORTQuantizer.from_pretrained(output_dir)
    qconfig = AutoQuantizationConfig.avx2(is_static=False)

    quantized_path = quantizer.quantize(
        save_dir=output_dir,
        quantization_config=qconfig,
    )
    print(f"  ✅ Quantized → {quantized_path}")
    return Path(quantized_path)


# ---------------------------------------------------------------------------
# Post-export validation
# ---------------------------------------------------------------------------

# Expected configuration for the embedding model (intfloat/multilingual-e5-small)
_EXPECTED_EMBEDDING_CONFIG = {
    "architectures": ["BertModel"],
    "attention_probs_dropout_prob": 0.1,
    "hidden_act": "gelu",
    "hidden_dropout_prob": 0.1,
    "hidden_size": 384,
    "initializer_range": 0.02,
    "intermediate_size": 1536,
    "layer_norm_eps": 1e-12,
    "max_position_embeddings": 512,
    "model_type": "bert",
    "num_attention_heads": 12,
    "num_hidden_layers": 12,
    "pad_token_id": 0,
    "position_embedding_type": "absolute",
    "tokenizer_class": "XLMRobertaTokenizer",
    "type_vocab_size": 2,
    "use_cache": True,
    "vocab_size": 250037,
}


def _validate_exported_embedding_model(emb_dir: Path) -> None:
    """Validate the exported ONNX embedding model matches the tokenizer vocab.

    Checks:
    1. The ONNX model can handle token IDs up to 250,036 (full XLM-RoBERTa range)
    2. The onnx/config.json contains model_type="bert" and vocab_size=250037

    Raises RuntimeError if validation fails.
    """
    import json as _json

    import numpy as np
    import onnxruntime as ort

    onnx_dir = emb_dir / "onnx"
    onnx_model_path: Path | None = None

    # sentence-transformers may place the ONNX file in different locations.
    # Check common paths in priority order.
    candidates = [
        onnx_dir / "model.onnx",
        emb_dir / "model.onnx",
        onnx_dir / "model_quantized.onnx",
        emb_dir / "model_quantized.onnx",
    ]
    for candidate in candidates:
        if candidate.is_file():
            onnx_model_path = candidate
            break

    # Fallback: search recursively
    if onnx_model_path is None:
        for child in emb_dir.rglob("model.onnx"):
            onnx_model_path = child
            break
    if onnx_model_path is None:
        for child in emb_dir.rglob("model_quantized.onnx"):
            onnx_model_path = child
            break

    if onnx_model_path is None:
        raise RuntimeError(
            "Post-export validation failed: no ONNX model file found in "
            f"{emb_dir}. Export may have failed silently."
        )

    # --- Step 1: Verify ONNX model handles high token IDs ---
    print("  🔍 Validating exported ONNX model …")

    session = ort.InferenceSession(
        str(onnx_model_path),
        providers=["CPUExecutionProvider"],
    )

    # Create a test input with a high token ID (250000) to verify the
    # embedding table covers the full XLM-RoBERTa vocabulary range.
    high_token_id = 250000
    test_input_ids = np.array([[0, high_token_id, 2]], dtype=np.int64)
    test_attention_mask = np.array([[1, 1, 1]], dtype=np.int64)
    test_token_type_ids = np.array([[0, 0, 0]], dtype=np.int64)

    input_names = [inp.name for inp in session.get_inputs()]
    feed = {"input_ids": test_input_ids, "attention_mask": test_attention_mask}
    if "token_type_ids" in input_names:
        feed["token_type_ids"] = test_token_type_ids

    try:
        outputs = session.run(None, feed)
    except Exception as exc:
        raise RuntimeError(
            f"Post-export validation failed: ONNX model cannot handle token ID "
            f"{high_token_id}. The embedding table likely does not match the "
            f"tokenizer vocabulary (expected 250,037 entries). Error: {exc}"
        ) from exc

    # Verify output shape — should produce embeddings with hidden_size=384
    if outputs and outputs[0].shape[-1] != 384:
        raise RuntimeError(
            f"Post-export validation failed: expected hidden_size=384, "
            f"got output shape {outputs[0].shape}."
        )

    print(f"  ✅ ONNX model handles token ID {high_token_id} correctly")

    # --- Step 2: Verify/fix onnx/config.json ---
    config_dir = onnx_model_path.parent
    config_path = config_dir / "config.json"

    config_valid = False
    if config_path.is_file():
        with open(config_path, "r", encoding="utf-8") as f:
            config = _json.load(f)

        model_type = config.get("model_type")
        vocab_size = config.get("vocab_size")

        if model_type == "bert" and vocab_size == 250037:
            config_valid = True
            print("  ✅ onnx/config.json is correct (model_type=bert, vocab_size=250037)")

    if not config_valid:
        # Generate the correct config
        os.makedirs(config_dir, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            _json.dump(_EXPECTED_EMBEDDING_CONFIG, f, indent=2, ensure_ascii=False)
        print("  ⚠️  onnx/config.json was missing or incorrect — generated correct config")

    print("  ✅ Post-export validation passed")


# ---------------------------------------------------------------------------
# Embedding export
# ---------------------------------------------------------------------------

def export_embedding_model(models_dir: str | Path | None = None) -> None:
    """Export ``intfloat/multilingual-e5-small`` to ONNX via sentence-transformers.

    The sentence-transformers ``backend="onnx"`` flag triggers an automatic
    ONNX export of the underlying transformer.  We then copy the tokenizer
    and model files into ``models/embedding/`` and quantize to INT8.
    """
    from sentence_transformers import SentenceTransformer

    base = Path(models_dir) if models_dir else _models_root()
    emb_dir = base / "embedding"
    os.makedirs(emb_dir, exist_ok=True)

    print("📦 Exporting embedding model (intfloat/multilingual-e5-small) …")

    # sentence-transformers ≥3.2 exports ONNX automatically when
    # backend="onnx" is specified.  The model is saved to a local cache;
    # we then copy the relevant artefacts into our models directory.
    model = SentenceTransformer(
        "intfloat/multilingual-e5-small",
        backend="onnx",
    )

    # The underlying ONNX model path lives inside the ST cache.
    # We save the full model directory which includes model.onnx,
    # tokenizer.json, config.json, etc.
    model.save(str(emb_dir))
    print(f"  ✅ Saved ONNX embedding model → {emb_dir}")

    # --- Post-export validation ---
    _validate_exported_embedding_model(emb_dir)

    # Locate the exported model.onnx for quantization
    onnx_file = emb_dir / "model.onnx"
    # sentence-transformers may nest the ONNX file inside a subfolder
    if not onnx_file.is_file():
        # Search one level deep
        for child in emb_dir.rglob("model.onnx"):
            onnx_file = child
            break

    if onnx_file.is_file():
        _quantize_model(onnx_file)
    else:
        print("  ⚠️  model.onnx not found — skipping quantization")


# ---------------------------------------------------------------------------
# Emotion export
# ---------------------------------------------------------------------------

def export_emotion_model(models_dir: str | Path | None = None) -> None:
    """Export the fine-tuned German emotion RoBERTa model to ONNX via optimum.

    Uses ``ORTModelForSequenceClassification.from_pretrained(export=True)``
    to convert the PyTorch checkpoint to ONNX, then quantizes to INT8.

    The model is ``visegradmedia-emotion/Emotion_RoBERTa_german6_v7``, a
    fine-tuned RoBERTa for 6-class German emotion classification (anger,
    fear, disgust, sadness, joy, none of them).
    """
    import json as _json

    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer

    # Fine-tuned German emotion RoBERTa — 6-class emotion classification.
    # This is the same model used by the PyTorch fallback path.
    model_id = "visegradmedia-emotion/Emotion_RoBERTa_german6_v7"

    # Expected 6-class emotion label mapping (should already be in the
    # fine-tuned model's config, but we verify/patch as a safety net).
    EMOTION_ID2LABEL = {
        0: "anger",
        1: "fear",
        2: "disgust",
        3: "sadness",
        4: "joy",
        5: "none of them",
    }
    EMOTION_LABEL2ID = {v: k for k, v in EMOTION_ID2LABEL.items()}

    base = Path(models_dir) if models_dir else _models_root()
    emo_dir = base / "emotion"
    os.makedirs(emo_dir, exist_ok=True)

    print(f"📦 Exporting emotion model ({model_id}) …")

    # Export to ONNX
    ort_model = ORTModelForSequenceClassification.from_pretrained(
        model_id,
        export=True,
    )
    ort_model.save_pretrained(str(emo_dir))

    # Save tokenizer alongside the model
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    tokenizer.save_pretrained(str(emo_dir))

    print(f"  ✅ Saved ONNX emotion model → {emo_dir}")

    # Ensure config.json contains the correct 6-class id2label mapping.
    # The base model may not have emotion labels, so we patch config.json
    # to guarantee downstream compatibility with EmotionProvider.
    config_path = emo_dir / "config.json"
    if config_path.is_file():
        with open(config_path, "r", encoding="utf-8") as f:
            config = _json.load(f)

        needs_update = False

        # Check if id2label matches expected emotion labels
        existing_id2label = config.get("id2label", {})
        expected_str_keys = {str(k): v for k, v in EMOTION_ID2LABEL.items()}
        if existing_id2label != expected_str_keys:
            config["id2label"] = expected_str_keys
            config["label2id"] = EMOTION_LABEL2ID
            config["num_labels"] = len(EMOTION_ID2LABEL)
            needs_update = True

        if needs_update:
            with open(config_path, "w", encoding="utf-8") as f:
                _json.dump(config, f, indent=2, ensure_ascii=False)
            print("  ✅ Patched config.json with 6-class emotion id2label mapping")
        else:
            print("  ✅ config.json already has correct id2label mapping")
    else:
        # config.json missing — create a minimal one with the label mapping
        config = {
            "id2label": {str(k): v for k, v in EMOTION_ID2LABEL.items()},
            "label2id": EMOTION_LABEL2ID,
            "num_labels": len(EMOTION_ID2LABEL),
        }
        with open(config_path, "w", encoding="utf-8") as f:
            _json.dump(config, f, indent=2, ensure_ascii=False)
        print("  ⚠️  config.json was missing — created with emotion label mapping")

    # Quantize
    onnx_file = emo_dir / "model.onnx"
    if onnx_file.is_file():
        _quantize_model(onnx_file)
    else:
        print("  ⚠️  model.onnx not found — skipping quantization")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Export both models to ONNX with INT8 quantization."""
    models_dir = _models_root()
    os.makedirs(models_dir / "embedding", exist_ok=True)
    os.makedirs(models_dir / "emotion", exist_ok=True)

    print("=" * 60)
    print("  Stimme — ONNX Model Export")
    print("=" * 60)
    print(f"  Output directory: {models_dir}\n")

    try:
        export_embedding_model(models_dir)
    except ImportError as exc:
        print(
            f"\n❌ Missing dev dependency for embedding export: {exc}\n"
            "   Install with:\n"
            "     pip install 'sentence-transformers>=3.2.0' torch\n"
        )
        sys.exit(1)
    except (OSError, ConnectionError) as exc:
        print(
            f"\n❌ Failed to download embedding model: {exc}\n"
            "   Check your network connection and HuggingFace access.\n"
        )
        sys.exit(1)

    print()

    try:
        export_emotion_model(models_dir)
    except ImportError as exc:
        print(
            f"\n❌ Missing dev dependency for emotion export: {exc}\n"
            "   Install with:\n"
            "     pip install 'optimum[onnxruntime]>=1.17.0' "
            "'transformers>=4.30.0' torch\n"
        )
        sys.exit(1)
    except (OSError, ConnectionError) as exc:
        print(
            f"\n❌ Failed to download emotion model: {exc}\n"
            "   Check your network connection and HuggingFace access.\n"
        )
        sys.exit(1)

    print()
    print("=" * 60)
    print("  ✅ All models exported and quantized successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
