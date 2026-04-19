import json
import os
from datetime import datetime

class HistoryManager:
    def __init__(self, base_dir=None):
        # If no directory is provided, default to 'history' in the current working directory
        if base_dir is None:
            self.history_dir = os.path.join(os.getcwd(), "history")
        else:
            self.history_dir = base_dir

        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)

    def save_entry(self, source, translation, commentary=None):
        timestamp = datetime.now().isoformat()
        # Clean the filename (Requirement 16.3)
        safe_source = "".join([c if c.isalnum() else "_" for c in source[:30]])
        filename = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}_{safe_source}.json"
        
        data = {
            "timestamp": timestamp,
            "source_text": source,
            "translation": translation,
            "commentary": commentary
        }
        
        with open(os.path.join(self.history_dir, filename), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)