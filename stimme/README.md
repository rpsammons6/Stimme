# Stimme — Philological German-to-English Translation Engine

A desktop application for high-register German-to-English translation, built for scholars working with historical and philosophical texts. Stimme uses Anthropic's Claude API for translation synthesis, ONNX Runtime for lightweight ML inference (semantic search, emotion analysis), and a LanceDB vector store for RAG-enhanced scholarly context.

## What's New

This release completes a major codebase overhaul: the flat `app/components/` directory has been reorganized into logical sub-folders (`layout/`, `views/`, `tabs/`, `widgets/`, `shared/`), production dependencies have been stripped of all PyTorch references in favor of an ONNX-only runtime, hardcoded API keys and debug logging have been scrubbed, and a parallel side-by-side translation view with synchronized scrolling, version history, correction editing, and a "Commit to Memory" feedback loop has been added. The application also now supports bulk book translation with automatic chapter detection, a user-managed glossary for term pinning, and a human-in-the-loop correction pipeline backed by LanceDB vector storage.

## Quick Start

### Prerequisites
- Python 3.9+
- Claude API key from [Anthropic](https://console.anthropic.com/)
- Tesseract OCR + Poppler (optional, for scanned PDF processing)

### Installation

```bash
git clone <repository-url>
cd stimme
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Edit .env and add your CLAUDE_API_KEY
```

### Launch

```bash
python main.py
```

## Features

- **Claude-Powered Translation** — Opus 4, Sonnet 4, and Haiku models with Scholar Mode for philological commentary
- **Parallel View** — Side-by-side source/translation with synchronized scrolling, segment highlighting, and version navigation
- **Bulk Book Translation** — Automatic chapter detection via a scout model, sliding-window chunking, and per-chapter progress tracking
- **Human-in-the-Loop Corrections** — Edit translations inline, commit corrections to a LanceDB vector table for future RAG retrieval
- **Glossary Engine** — Pin, edit, and inject domain-specific term mappings into every translation prompt
- **RAG Context** — Semantic search over a bundled scholarly corpus and idiom database using ONNX-accelerated embeddings
- **PDF Processing** — Digital text extraction via pypdfium2/pdfplumber, OCR fallback via Tesseract + Poppler for scanned documents
- **Export** — TXT, HTML, and Markdown output formats with configurable export directory
- **Translation History** — Searchable history with re-translation and version diffing
- **Cross-Platform** — Windows, macOS, and Linux via Flet

## OCR Setup (Optional)

Only needed if you work with scanned PDFs. Stimme auto-detects installed paths.

- **macOS**: `brew install tesseract poppler`
- **Windows**: Install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and [Poppler](https://blog.alivate.com.au/poppler-windows/)
- **Linux**: `sudo apt-get install tesseract-ocr poppler-utils`

## Project Structure

```
stimme/
├── main.py                     # Application entry point
├── benchmark.py                # Performance benchmarking
├── requirements.txt            # Production dependencies (ONNX-only, no PyTorch)
├── requirements-dev.txt        # Dev dependencies (adds PyTorch, pytest, hypothesis)
├── .env.example                # Configuration template
├── app/
│   ├── shell.py                # Top-level application shell
│   ├── state.py                # Application state management
│   ├── event_bus.py            # Pub/sub event system
│   ├── components/
│   │   ├── layout/             # Shell-level panels and dividers
│   │   ├── views/              # Content display (parallel, glossary, history, PDF, etc.)
│   │   ├── tabs/               # Tab containers (corrections, log)
│   │   ├── widgets/            # Small reusable controls
│   │   └── shared/             # Cross-cutting utilities (loading screen)
│   ├── services/               # Translation, PDF import, glossary, corrections, etc.
│   └── contexts/               # Settings management
├── programs/
│   ├── brain.py                # Claude API + RAG translation engine
│   ├── pdf_engine.py           # PDF rendering and text extraction
│   ├── ocr_engine.py           # Tesseract/Poppler OCR pipeline
│   └── export_onnx.py          # Dev-only: export models to ONNX format
├── models/
│   ├── embedding/              # Bundled ONNX embedding model
│   └── emotion/                # Bundled ONNX emotion model
└── lancedb_vectors/            # Vector database (corpus + idioms)
```

## Troubleshooting

- **"OCR not available"** — Install Tesseract and Poppler for your OS (see above)
- **"Translation failed"** — Check your Claude API key in the sidebar and your internet connection
- **"No vector database found"** — The app works without it, but RAG context improves translation quality

---

*Made with love for the philological tradition.*
