# Stimme — Philological German-to-English Translation Engine

A desktop application for high-register German-to-English translation, built for scholars working with historical and philosophical texts. Stimme uses Anthropic's Claude API for translation synthesis, ONNX Runtime for lightweight ML inference (semantic search, emotion analysis), and a LanceDB vector store for RAG-enhanced scholarly context.

## What's New (v1.1)

This release completes Phase 1 of the development roadmap:

- **Configuration Service** — A unified two-layer config system replacing the old SettingsManager. Global settings live in `~/.stimme/config.json`, scholarly personas in portable `.stimme` files. Both merge into a single Active Registry at boot.
- **Secrets Manager** — API keys are now stored in the OS keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service) instead of plaintext. A "Secure My Key" button migrates existing `.env` keys to the keyring.
- **State Recovery** — Automatic session snapshots every 60 seconds to `~/.stimme/session_recovery.json`. On crash, the app detects the snapshot and offers to restore your work. Worker process crashes are detected and reported with a red banner.
- **Ram-o'-Meter** — A developer diagnostic tool (`ram_meter.py`) that measures per-component memory usage across the UI and backend. Probe-based discovery, subprocess isolation, configurable budgets, and a detailed Philological Performance Report to stdout.
- **ONNX-Only Runtime** — Production dependencies have been stripped of all PyTorch references. Embedding and emotion models run on ONNX Runtime with INT8 quantization. PyTorch is only needed for model export (dev dependency).
- **Codebase Reorganization** — The flat `app/components/` directory has been reorganized into `layout/`, `views/`, `tabs/`, `widgets/`, and `shared/`. Services layer fully extracted.
- **Property-Based Testing** — Hypothesis-driven correctness properties for budget resolution, probe discovery, failure categorization, and verdict evaluation.

## Quick Start

### Prerequisites
- Python 3.9+
- Claude API key from [Anthropic](https://console.anthropic.com/)
- Tesseract OCR + Poppler (optional, for scanned PDF processing)

### Installation

```bash
git clone https://github.com/rpsammons6/Stimme.git
cd Stimme/stimme
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Edit .env and add your CLAUDE_API_KEY
# (or enter it in the app sidebar — it will be stored in your OS keyring)
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
- **PDF Processing** — Digital text extraction via pypdfium2, OCR fallback via Tesseract + Poppler for scanned documents
- **Export** — TXT, HTML, and Markdown output formats with configurable export directory
- **Translation History** — Searchable history with re-translation and version diffing
- **Scholarly Personas** — Portable `.stimme` preset files for prompt tuning, model directives, RAG weights, and thematic focus
- **Session Recovery** — Automatic crash recovery with periodic state snapshots
- **Secure Key Storage** — OS keyring integration with migration from plaintext `.env`
- **Cross-Platform** — Windows, macOS, and Linux via Flet

## Developer Tools

### Benchmark

```bash
python benchmark.py
```

Measures translation latency, token throughput, and RAG retrieval times across all configured models.

### Ram-o'-Meter

```bash
python ram_meter.py                    # Run all probes
python ram_meter.py --probe "ONNX Providers"  # Single probe
python ram_meter.py --verbose          # Include module-level memory breakdown
python ram_meter.py --timeout 120      # Custom per-probe timeout (seconds)
```

Produces a Philological Performance Report showing per-component memory usage (USS delta), budget pass/fail verdicts, process family enumeration, and failure diagnostics. Budget overrides can be set in `~/.stimme/config.json` under the `ram_budgets` key.

### Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

The test suite includes example-based unit tests and Hypothesis property-based tests covering budget resolution, probe discovery, failure categorization, and verdict evaluation.

### Exporting ONNX Models (Dev Only)

```bash
pip install -r requirements-dev.txt
python programs/export_onnx.py
```

Exports the embedding and emotion models to ONNX format with INT8 quantization. Requires PyTorch, sentence-transformers, and optimum (dev dependencies only).

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
├── ram_meter.py                # Memory diagnostic tool
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
│   └── services/
│       ├── configuration_service.py  # Unified config facade (global + persona)
│       ├── state_service.py          # Session recovery and crash detection
│       ├── secrets_manager.py        # OS keyring API key management
│       ├── book_processor.py         # Bulk translation pipeline
│       ├── glossary_manager.py       # Term pinning and injection
│       ├── translation_service.py    # Single-text translation orchestration
│       ├── pdf_import.py             # PDF text extraction + OCR fallback
│       └── ...                       # Corrections, history, export, etc.
├── programs/
│   ├── brain.py                # Claude API + RAG translation engine
│   ├── onnx_providers.py       # ONNX embedding + emotion inference
│   ├── pdf_engine.py           # PDF rendering and text extraction
│   ├── ocr_engine.py           # Tesseract/Poppler OCR pipeline
│   └── export_onnx.py          # Dev-only: export models to ONNX format
├── tests/
│   ├── test_ram_meter.py              # Unit tests for Ram-o'-Meter
│   ├── test_ram_meter_properties.py   # Property-based tests (Hypothesis)
│   └── ram_meter/                     # Ram-o'-Meter framework and probes
├── models/
│   ├── embedding/              # Bundled ONNX embedding model (multilingual-e5-small)
│   └── emotion/                # Bundled ONNX emotion model (distilbert-german)
└── lancedb_vectors/            # Vector database (corpus + idioms)
```

## Troubleshooting

- **"OCR not available"** — Install Tesseract and Poppler for your OS (see above)
- **"Translation failed"** — Check your Claude API key in the sidebar and your internet connection
- **"No vector database found"** — The app works without it, but RAG context improves translation quality
- **Ram-o'-Meter shows "Budget Exceeded"** — The component uses more memory than its configured budget. Adjust budgets in `~/.stimme/config.json` under `ram_budgets`, or investigate the component's memory footprint

---

*Made with love for the philological tradition.*
