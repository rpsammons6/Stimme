# Stimme - AI-Powered German Translation App

A sophisticated desktop application for translating German texts using Claude AI with RAG-enhanced scholarly context.

## 🚀 Quick Start

### Prerequisites
- **Python 3.9+**
- **Claude API Key** from [Anthropic Console](https://console.anthropic.com/)

### Installation

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd stimme
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your CLAUDE_API_KEY
   ```

3. **Download vector database** (optional but recommended):
   - Download `lancedb_vectors` folder from releases
   - Place in project root for enhanced translation context

4. **Install OCR dependencies** (optional, for PDF scanning):
   - **macOS**: `brew install tesseract poppler`
   - **Windows**: Download [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and [Poppler](https://blog.alivate.com.au/poppler-windows/)
   - **Linux**: `sudo apt-get install tesseract-ocr poppler-utils`

### Launch the App

```bash
python main.py
```

## ✨ Features

- **Multi-Model Support**: Claude Opus 4, Sonnet 4, Haiku 4
- **RAG-Enhanced Context**: Specialized German scholarly knowledge
- **PDF Processing**: Digital extraction + OCR for scanned documents
- **Scholar Mode**: Detailed philological commentary
- **Multi-Tab Interface**: Manage multiple translations
- **Export System**: TXT, HTML, Markdown formats
- **Translation History**: Full markdown-formatted history
- **Cross-Platform**: Windows, macOS, Linux

## 🛠️ Troubleshooting

**"OCR not available"**: Install Tesseract and Poppler for your OS  
**"No vector database found"**: App works without it, but download for better context  
**"Translation failed"**: Check Claude API key and internet connection  

## 📁 Project Structure

```
stimme/
├── main.py              # Launch the app
├── requirements.txt     # Dependencies
├── .env.example        # Configuration template
├── app/                # UI components and services
├── programs/           # Core translation engine
└── lancedb_vectors/    # Vector database (download separately)
```

---

*Made with love*