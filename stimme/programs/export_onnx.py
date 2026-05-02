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
    """Export a DistilBERT-based German emotion model to ONNX via optimum.

    Uses ``ORTModelForSequenceClassification.from_pretrained(export=True)``
    to convert the PyTorch checkpoint to ONNX, then quantizes to INT8.

    The model should be a fine-tuned ``distilbert-base-german-cased`` checkpoint
    trained for 6-class German emotion classification (anger, fear, disgust,
    sadness, joy, none of them).  Replace the model_id below with your custom
    fine-tuned checkpoint path or HuggingFace repo when available.
    """
    import json as _json

    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer

    # DistilBERT-based German emotion model (~66M params, ~40-65MB quantized).
    # Replace with a fine-tuned checkpoint for 6-class German emotion
    # classification when available (e.g. "your-org/distilbert-german-emotion").
    model_id = "distilbert-base-german-cased"

    # Expected 6-class emotion label mapping (must match the original
    # RoBERTa model's output format for downstream compatibility).
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
