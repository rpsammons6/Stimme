"""
Application constants for Stimme.
Defines model registry, OCR languages, paths, and configuration.
"""

import os
from pathlib import Path

# ============================================================================
# MODEL REGISTRY - Available Claude Models
# ============================================================================

AVAILABLE_MODELS = [
    {
        "id": "claude-opus-4-7",
        "display": "Claude Opus 4 (Highest Quality)",
        "description": "Slowest but highest quality translation",
        "speed": "slow",
        "quality": "highest"
    },
    {
        "id": "claude-sonnet-4-6",
        "display": "Claude Sonnet 4 (Best Value)",
        "description": "Balanced speed and quality",
        "speed": "medium",
        "quality": "high"
    },
    {
        "id": "claude-haiku-4-5-20251001",
        "display": "Claude Haiku 4 (Fastest)",
        "description": "Cheapest and fastest translation",
        "speed": "fast",
        "quality": "good"
    }
]

# Default model
DEFAULT_MODEL = "claude-sonnet-4-6"

# ============================================================================
# OCR SCRIPT REGISTRY - Tesseract Language Codes
# ============================================================================

OCR_LANGUAGES = [
    {
        "code": "deu_frak",
        "display": "Archaic / Fraktur",
        "description": "Historical German texts in Fraktur script"
    },
    {
        "code": "deu",
        "display": "Modern German",
        "description": "Contemporary German texts"
    },
    {
        "code": "eng",
        "display": "English",
        "description": "English texts"
    }
]

# Default OCR language
DEFAULT_OCR_LANGUAGE = "deu"

# ============================================================================
# PATH CONSTANTS - Directory Structure
# ============================================================================

# Base directory (project root)
BASE_DIR = Path(__file__).parent.parent.resolve()

# Data directories
VECTOR_DB_PATH = BASE_DIR / "lancedb_vectors"
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = BASE_DIR / "history"
PROGRAMS_DIR = BASE_DIR / "programs"

# Ensure directories exist
VECTOR_DB_PATH.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)

# ============================================================================
# API CONFIGURATION
# ============================================================================

def get_api_key() -> str:
    """Get Claude API key from environment"""
    return os.getenv("CLAUDE_API_KEY", "")

def has_api_key() -> bool:
    """Check if API key is configured"""
    key = get_api_key()
    return bool(key and key.strip())

# ============================================================================
# ACTIVE PLUGINS - Default Datasets
# ============================================================================

DEFAULT_PLUGINS = ["idioms", "corpus"]

# ============================================================================
# UI CONSTANTS
# ============================================================================

# Loading messages
LOADING_MESSAGES = [
    "Consulting the library…",
    "Analyzing sentiment…",
    "Retrieving context…",
    "Translating…"
]

# Error messages
ERROR_NO_TEXT = "Please enter some German text to translate."
ERROR_NO_API_KEY = "API key is missing. Please configure it in the sidebar."
ERROR_TRANSLATION_FAILED = "Translation failed. Please try again."

# Success messages
SUCCESS_TRANSLATION = "Translation complete!"
SUCCESS_FILE_LOADED = "File loaded successfully."

# ============================================================================
# MARKDOWN TEMPLATE - Dark Mode CSS for WebView
# ============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            background-color: #0a0a0a;
            color: #e8e6e3;
            font-family: 'Cormorant Garamond', Georgia, serif;
            font-size: 18px;
            line-height: 1.75;
            padding: 32px;
            max-width: 900px;
            margin: 0 auto;
        }}
        
        h1, h2, h3, h4, h5, h6 {{
            font-family: 'Cormorant Garamond', Georgia, serif;
            color: #d4af37;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            font-weight: 600;
        }}
        
        h1 {{ font-size: 2.5em; }}
        h2 {{ font-size: 2em; }}
        h3 {{ font-size: 1.5em; }}
        
        p {{
            margin-bottom: 1em;
        }}
        
        strong {{
            color: #d4af37;
            font-weight: 600;
        }}
        
        em {{
            font-style: italic;
            color: #c9c5c0;
        }}
        
        code {{
            font-family: 'JetBrains Mono', 'Courier New', monospace;
            background-color: #1a1a1a;
            color: #d4af37;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
        }}
        
        pre {{
            background-color: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 6px;
            padding: 16px;
            overflow-x: auto;
            margin: 1em 0;
        }}
        
        pre code {{
            background-color: transparent;
            padding: 0;
        }}
        
        blockquote {{
            border-left: 3px solid #d4af37;
            padding-left: 16px;
            margin: 1em 0;
            color: #c9c5c0;
            font-style: italic;
        }}
        
        ul, ol {{
            margin-left: 2em;
            margin-bottom: 1em;
        }}
        
        li {{
            margin-bottom: 0.5em;
        }}
        
        hr {{
            border: none;
            border-top: 1px solid #2a2a2a;
            margin: 2em 0;
        }}
        
        a {{
            color: #d4af37;
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
        
        .commentary-header {{
            text-align: center;
            color: #d4af37;
            font-size: 1.2em;
            margin: 2em 0;
            opacity: 0.9;
        }}
        
        .divider {{
            display: flex;
            align-items: center;
            text-align: center;
            margin: 2em 0;
        }}
        
        .divider::before,
        .divider::after {{
            content: '';
            flex: 1;
            border-bottom: 1px solid #d4af37;
            opacity: 0.4;
        }}
        
        .divider span {{
            padding: 0 16px;
            color: #d4af37;
            opacity: 0.7;
        }}
    </style>
</head>
<body>
    {content}
</body>
</html>
"""
