import json
from pathlib import Path
from datetime import datetime

from app.models.bulk_models import BookTranslation

class HistoryManager:
    """Service for managing translation history"""
    
    def __init__(self):
        self.history_dir = Path.home() / ".stimme"
        self.history_file = self.history_dir / "history.json"
        self.history_dir.mkdir(exist_ok=True)
        self.history = []
        self.load_history()
    
    def load_history(self):
        """Load history from file, recovering gracefully from corruption"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.history = data
                else:
                    print(f"⚠️  HISTORY: File contained non-list data, resetting")
                    self.history = []
                    self._backup_and_reset()
                # Migrate old entries to include markdown content
                self._migrate_old_entries()
            except json.JSONDecodeError as e:
                print(f"⚠️  HISTORY: Corrupted JSON, backing up and resetting: {e}")
                self.history = []
                self._backup_and_reset()
            except Exception as e:
                print(f"⚠️  HISTORY: Error loading history, starting fresh: {e}")
                self.history = []
        else:
            # File doesn't exist (first run or was deleted)
            self.history = []

    def _backup_and_reset(self):
        """Backup corrupted file and start fresh"""
        try:
            backup_path = self.history_file.with_suffix(".json.bak")
            if self.history_file.exists():
                import shutil
                shutil.copy2(self.history_file, backup_path)
                print(f"  HISTORY: Corrupted file backed up to {backup_path}")
            self.save_history()
        except Exception as e:
            print(f"  HISTORY: Could not backup: {e}")
    
    def _migrate_old_entries(self):
        """Migrate old history entries to include markdown content"""
        updated = False
        for entry in self.history:
            if "markdown_content" not in entry:
                # Create markdown content for old entries
                try:
                    timestamp = datetime.fromisoformat(entry.get("timestamp", ""))
                    time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    time_str = "Unknown time"
                
                markdown_content = f"""# Translation Entry

**Date:** {time_str}  
**Model:** {entry.get("model", "Unknown")}

## Source Text
{entry.get("source", "")}

## Translation
{entry.get("translation", "")}

## Commentary
{entry.get("commentary", "") if entry.get("commentary") else "No commentary provided"}

---
"""
                entry["markdown_content"] = markdown_content
                updated = True
        
        if updated:
            self.save_history()
            print("✅ HISTORY: Migrated old entries to include markdown content")
    
    def save_history(self):
        """Save history to file"""
        try:
            self.history_dir.mkdir(exist_ok=True)  # Ensure dir exists
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"⚠️  HISTORY: Error saving: {e}")
    
    def add_entry(self, source: str, translation: str, model: str, commentary: str = "", pdf_path: str = None, iteration_count: int = 0):
        """Add translation to history with markdown format"""
        # Create markdown formatted content
        pdf_line = f"\n**Source PDF:** {pdf_path}" if pdf_path else ""
        iteration_line = f"\n**HITL Iterations:** {iteration_count}" if iteration_count > 0 else ""
        markdown_content = f"""# Translation Entry

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Model:** {model}{pdf_line}{iteration_line}

## Source Text
{source}

## Translation
{translation}

## Commentary
{commentary if commentary else "No commentary provided"}

---
"""
        
        entry = {
            "source": source,
            "translation": translation,
            "model": model,
            "commentary": commentary,
            "timestamp": datetime.now().isoformat(),
            "markdown_content": markdown_content,
        }
        if pdf_path:
            entry["pdf_path"] = pdf_path
        if iteration_count > 0:
            entry["iteration_count"] = iteration_count
        self.history.insert(0, entry)  # Add to beginning (newest first)
        self.save_history()

    def add_book_entry(self, book_translation: BookTranslation, model: str):
        """Add a completed book translation to history with chapter metadata."""
        chapter_summary = ", ".join(
            f"{ch.title} ({ch.word_count} words)"
            for ch in book_translation.chapters
        )
        total_words = sum(ch.word_count for ch in book_translation.chapters)
        chapter_count = len(book_translation.chapters)
        commentary = f"Book translation — {chapter_count} chapter(s): {chapter_summary}"

        markdown_content = f"""# Book Translation Entry

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Model:** {model}  
**Chapters:** {chapter_count}  
**Total Words:** {total_words}

## Chapters
{chr(10).join(f"- {ch.title} ({ch.word_count} words)" for ch in book_translation.chapters)}

## Translation
{book_translation.full_translation}

## Commentary
{commentary}

---
"""

        entry = {
            "source": f"Book: {chapter_count} chapters — {chapter_summary}",
            "translation": book_translation.full_translation,
            "model": model,
            "commentary": commentary,
            "timestamp": datetime.now().isoformat(),
            "markdown_content": markdown_content,
            "is_book": True,
            "chapter_count": chapter_count,
            "total_words": total_words,
        }
        self.history.insert(0, entry)
        self.save_history()
    
    def get_history_slice(self, offset: int = 0, limit: int = 10) -> tuple[list, int]:
        """Return (entries[offset:offset+limit], total_count)."""
        total = len(self.history)
        return self.history[offset:offset + limit], total

    def get_history(self) -> list:
        """Get all history entries"""
        return self.history
    
    def clear_history(self):
        """Clear all history"""
        self.history = []
        self.save_history()

    def update_pdf_path(self, timestamp: str, new_path: str):
        """Update the pdf_path for a history entry identified by its timestamp."""
        for entry in self.history:
            if entry.get("timestamp") == timestamp:
                entry["pdf_path"] = new_path
                self.save_history()
                print(f"✅ HISTORY: Updated pdf_path for entry {timestamp}")
                return
        print(f"⚠️  HISTORY: No entry found with timestamp {timestamp}")
