import json
from pathlib import Path
from datetime import datetime

class HistoryManager:
    """Service for managing translation history"""
    
    def __init__(self):
        self.history_dir = Path.home() / ".stimme"
        self.history_file = self.history_dir / "history.json"
        self.history_dir.mkdir(exist_ok=True)
        self.history = []
        self.load_history()
    
    def load_history(self):
        """Load history from file"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
                # Migrate old entries to include markdown content
                self._migrate_old_entries()
            except Exception as e:
                print(f"Error loading history: {e}")
    
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
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def add_entry(self, source: str, translation: str, model: str, commentary: str = ""):
        """Add translation to history with markdown format"""
        # Create markdown formatted content
        markdown_content = f"""# Translation Entry

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Model:** {model}

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
            "markdown_content": markdown_content
        }
        self.history.insert(0, entry)  # Add to beginning (newest first)
        self.save_history()
    
    def get_history(self) -> list:
        """Get all history entries"""
        return self.history
    
    def clear_history(self):
        """Clear all history"""
        self.history = []
        self.save_history()
