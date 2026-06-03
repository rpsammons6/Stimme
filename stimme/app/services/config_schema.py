"""
Validation schemas and shared constants for the ConfigurationService.

Each schema entry maps a key name to a ``(type, min, max, default)`` tuple:
- *type*: expected Python type (``str``, ``int``, ``float``, ``bool``, ``list``, ``dict``)
- *min / max*: valid numeric bounds (``None`` for non-numeric types)
- *default*: the built-in fallback value

Public helpers:
- ``validate_value(key, value, schema)`` — type-check and range-clamp a single value
- ``defaults(schema)`` — return a dict of all default values from a schema
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema entry format: (type, min, max, default)
# min/max are None for non-numeric types.
# ---------------------------------------------------------------------------

GLOBAL_SCHEMA: dict[str, tuple] = {
    # Infrastructure paths
    "tesseract_path":             (str,   None, None, ""),
    "poppler_path":               (str,   None, None, ""),
    "lancedb_path":               (str,   None, None, ""),
    "export_directory":           (str,   None, None, "~/Documents/Stimme Exports"),
    "history_directory":          (str,   None, None, ""),
    "datasets_directory":         (str,   None, None, ""),
    # System preferences
    "ui_language":                (str,   None, None, "EN"),
    "theme":                      (str,   None, None, "dunkel"),
    "diagnostics_hud":            (bool,  None, None, False),
    "console_log_enabled":        (bool,  None, None, False),
    "console_log_filter":         (list,  None, None, []),
    # Secrets pointers
    "api_key_source":             (str,   None, None, "env_file"),
    "remember_api_key":           (bool,  None, None, True),
    # App lifecycle
    "last_opened_pdf":            (str,   None, None, ""),
    "last_used_glossary":         (str,   None, None, ""),
    "active_preset_path":         (str,   None, None, ""),
    "window_width":               (int,   200,  5000, 1200),
    "window_height":              (int,   200,  5000, 800),
    "sidebar_visible":            (bool,  None, None, True),
    # LLM backend
    "llm_backend":                (str,   None, None, "cloud"),
    "local_llm_endpoint":         (str,   None, None, "http://localhost:11434"),
    "local_llm_model":            (str,   None, None, "llama3"),
    "local_llm_timeout":          (int,   1,    600,  120),
    # OCR preprocessing
    "ocr_language":               (str,   None, None, "deu"),
    "ocr_dpi_scale":              (float, 1.0,  4.0,  2.0),
    "ocr_denoise_intensity":      (int,   0,    10,   2),
    "ocr_binarization_threshold": (int,   0,    255,  127),
    "ocr_contrast_enhancement":   (float, 1.0,  3.0,  1.5),
    # Network
    "proxy_http":                 (str,   None, None, ""),
    "proxy_socks":                (str,   None, None, ""),
    "network_timeout":            (int,   1,    300,  30),
    # Hotkeys
    "hotkey_map":                 (dict,  None, None, {}),
    # Ram-o'-Meter budget overrides
    "ram_budgets":                (dict,  None, None, {}),
    # Datasets
    "active_datasets":            (list,  None, None, ["idioms", "corpus"]),
    # Billing
    "show_billing_info":          (bool,  None, None, False),
    # Compat: model key (maps to preferred_model in persona layer)
    "model":                      (str,   None, None, "claude-sonnet-4-6"),
}

PERSONA_SCHEMA: dict[str, tuple] = {
    # Prompts
    "master_prompt":              (str,   None, None, ""),
    "local_prompt":               (str,   None, None, ""),
    # Model directives
    "preferred_model":            (str,   None, None, ""),
    # Hyperparameters
    "temperature":                (float, 0.1,  1.0,  0.7),
    "top_p":                      (float, 0.0,  1.0,  1.0),
    "max_tokens":                 (int,   1,    100000, 4096),
    # RAG weights
    "vector_distance_threshold":  (float, 0.0,  2.0,  0.5),
    "context_limit":              (int,   1,    50,   5),
    # VAD multipliers
    "vad_enabled":                (bool,  None, None, True),
    "valence_multiplier":         (float, 0.0,  2.0,  1.0),
    "arousal_multiplier":         (float, 0.0,  2.0,  1.0),
    "dominance_multiplier":       (float, 0.0,  2.0,  1.0),
    # Memory settings
    "cross_chunk_memory":         (bool,  None, None, True),
    "summary_length":             (int,   10,   10000, 200),
    # Glossary binding
    "glossary_path":              (str,   None, None, ""),
    "glossary_override_strength": (str,   None, None, "strict"),
    # Scholar mode
    "scholar_mode":               (bool,  None, None, False),
    # Thematic focus
    "thematic_focus":             (str,   None, None, ""),
    # Source language override (persona can override global)
    "source_language":            (str,   None, None, "German"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_value(
    key: str,
    value: Any,
    schema: dict[str, tuple],
) -> tuple[Any, bool]:
    """Type-check and range-clamp a single configuration value.

    Parameters
    ----------
    key:
        The configuration key name (must exist in *schema*).
    value:
        The raw value to validate.
    schema:
        One of ``GLOBAL_SCHEMA`` or ``PERSONA_SCHEMA``.

    Returns
    -------
    (validated_value, was_healed)
        *validated_value* is the value after any type fallback or range
        clamping.  *was_healed* is ``True`` when the original value was
        modified (wrong type → default, or out-of-range → clamped).
    """
    expected_type, range_min, range_max, default = schema[key]

    # --- Type check ---
    # Python's bool is a subclass of int, so reject bools explicitly when
    # the expected type is int or float (bool should only match bool fields).
    if isinstance(value, bool) and expected_type is not bool:
        logger.warning(
            "Schema heal: key=%s invalid_value=%r (expected %s), using fallback=%r",
            key, value, expected_type.__name__, default,
        )
        return default, True

    # Allow int where float is expected (e.g. 1 is valid for a float field).
    if expected_type is float and isinstance(value, int):
        value = float(value)

    if not isinstance(value, expected_type):
        logger.warning(
            "Schema heal: key=%s invalid_value=%r (expected %s), using fallback=%r",
            key, value, expected_type.__name__, default,
        )
        return default, True

    # --- Range clamp (numeric types only) ---
    if range_min is not None and range_max is not None:
        clamped = max(range_min, min(value, range_max))
        if clamped != value:
            logger.warning(
                "Schema clamp: key=%s value=%r outside [%s, %s], clamped to %r",
                key, value, range_min, range_max, clamped,
            )
            return clamped, True

    return value, False


def defaults(schema: dict[str, tuple]) -> dict[str, Any]:
    """Return a dict of all default values from *schema*.

    Mutable defaults (``list``, ``dict``) are deep-copied so callers
    cannot accidentally mutate the schema definitions.
    """
    import copy
    return {key: copy.deepcopy(entry[3]) for key, entry in schema.items()}
