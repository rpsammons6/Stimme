***

# 🗺️ Stimme: Development Roadmap

The following features are slated for development as we move toward **Version 1.1** and beyond. Our goal is to transform the engine into a comprehensive "Digital Scriptorium" for high-register German scholarship.

## 🛠️ Phase 1: Core UX & Stability
*Refining the researcher's primary workspace.*

- [ ] **Comprehensive Settings Menu**
  - **Infrastructure:** Local path configuration for Tesseract OCR and Poppler binaries.
  - **LLM Tuning:** Adjustable Temperature and Max Token sliders for the Claude synthesis engine.
  - **Storage:** User-definable default directories for Export and History.
- [ ] **Advanced Translation Tab Suite**
  - **Dual-Mode Editor:** Seamless toggle between a beautiful Markdown Preview and a syntax-highlighted Text Editor.
  - **Synoptic Scroll (Sync-Lock):** Linked vertical scrolling between German source and English translation panels.
  - **"Commit to Memory":** The ability to manually edit a translation and save that correction back into a localized LanceDB table for future RAG retrieval.
- [ ] **Unified Scriptorium Logs**
  - Toggleable bottom-drawer terminal showing the "Inner Thoughts" of the engine.
  - Real-time status updates: *RAG search distances, BERT sentiment labels, and API token usage.*
  - Improved splash screen communication during model pre-loading.

## 🏛️ Phase 2: The Philological Toolkit
*Deepening the linguistic and historical analysis.*

- [ ] **Lexicographical Sidebar (Grimm & Leodict)**
  - **Interactive Lemmas:** Highlight any German word to trigger a dual-lookup.
  - **Historical Depth:** Integration with the *Grimm Deutsches Wörterbuch* for 18th/19th-century etymology.
  - **Context Injection:** Show how specific dictionary definitions influenced the AI’s current word choice.
- [ ] **Footnote & Citation Preservation**
  - **Structural Recognition:** Detect common academic footnote formats (superscripts, Roman numerals).
  - **Anchored Translation:** Extract and translate footer text separately, re-anchoring them as Markdown/LaTeX footnotes in the English output.
- [ ] **Enhanced History Workspace**
  - Transform the History view from a sidebar into a comprehensive, searchable spreadsheet-style tab.
  - Metadata sorting by: *Date, Author, Field, and Emotional Intensity.*

## 📊 Phase 3: Semantic Visualization
*Applying quantitative methods to qualitative research.*

- [ ] **Atmospheric Manifold (Semantic Map)**
  - An Obsidian-inspired graph view representing the "Emotional Shape" of a work.
  - Map the **Valence (X)**, **Arousal (Y)**, and **Dominance (Z)** coordinates into a 3D scatter plot.
  - **Clustering:** Identify thematic shifts across long documents (e.g., detecting the shift from expository logic to aggressive polemics in Schopenhauer).
- [ ] **Context-Menu Expansion**
  - Right-click functionality for specific philological actions: *"Re-translate with higher register," "Find synonyms in Gold Corpus,"* or *"Cross-reference with Bible/Legal databases."*

## 🌍 Future Horizons (v2.0+)
- [ ] **Multilingual Expansion:** Decoupling the prompt logic to support master-level philology in Latin, French, and Ancient Greek.
- [ ] **TEI-XML Exporting:** Semantic tagging of Names, Dates, and Places for integration into Digital Humanities pipelines.

***