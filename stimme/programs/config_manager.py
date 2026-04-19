import json
import os

class ConfigManager:
    def __init__(self):
        self.config_file = "config.json"
        self.defaults = {
            "export_dir": os.path.join(os.getcwd(), "exports"),
            "history_dir": os.path.join(os.getcwd(), "history"),
            "model_id": "claude-3-5-sonnet-latest"
        }
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return self.defaults

    def save_config(self, new_config):
        with open(self.config_file, 'w') as f:
            json.dump(new_config, f)