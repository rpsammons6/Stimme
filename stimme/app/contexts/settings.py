import json
import os
from pathlib import Path
from app.constants import DEFAULT_MODEL, DEFAULT_PLUGINS

class SettingsManager:
    """Manages application settings and persistence"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".stimme"
        self.config_file = self.config_dir / "settings.json"
        self.config_dir.mkdir(exist_ok=True)
        
        self.settings = {
            "model": DEFAULT_MODEL,
            "scholar_mode": False,
            "thematic_focus": "",
            "api_key": "",
            "datasets": DEFAULT_PLUGINS.copy(),
            "ocr_language": "deu",
            "remember_api_key": True,  # New setting for API key persistence
            "export_directory": str(Path.home() / "Documents" / "Stimme Exports")  # Default export directory
        }
        
        self.load_settings()
        
        # Ensure export directory exists
        export_dir = self.get_export_directory()
        os.makedirs(export_dir, exist_ok=True)
    
    def load_settings(self):
        """Load settings from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    saved = json.load(f)
                    self.settings.update(saved)
            except Exception as e:
                print(f"Error loading settings: {e}")
    
    def save_settings(self):
        """Save settings to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def set_model(self, model: str):
        """Set model"""
        self.settings["model"] = model
        self.save_settings()
    
    def get_model(self) -> str:
        """Get model"""
        return self.settings["model"]
    
    def set_scholar_mode(self, enabled: bool):
        """Set scholar mode"""
        self.settings["scholar_mode"] = enabled
        self.save_settings()
    
    def get_scholar_mode(self) -> bool:
        """Get scholar mode"""
        return self.settings["scholar_mode"]
    
    def set_thematic_focus(self, focus: str):
        """Set thematic focus"""
        self.settings["thematic_focus"] = focus
        self.save_settings()
    
    def get_thematic_focus(self) -> str:
        """Get thematic focus"""
        return self.settings["thematic_focus"]
    
    def set_api_key(self, key: str):
        """Set API key"""
        if self.get_remember_api_key():
            self.settings["api_key"] = key
            self.save_settings()
        else:
            # Don't save to file, only set in memory
            self.settings["api_key"] = key
        # Also set as environment variable for backend
        os.environ["CLAUDE_API_KEY"] = key
    
    def get_api_key(self) -> str:
        """Get API key"""
        # Check environment variable first, then settings
        env_key = os.getenv("CLAUDE_API_KEY", "")
        if env_key:
            return env_key
        return self.settings["api_key"]
    
    def has_api_key(self) -> bool:
        """Check if API key is configured and valid"""
        key = self.get_api_key()
        return bool(key and key.strip() and key.startswith("sk-ant-"))
    
    def set_remember_api_key(self, remember: bool):
        """Set whether to remember API key"""
        self.settings["remember_api_key"] = remember
        if not remember:
            # If user chooses not to remember, clear the saved key
            self.settings["api_key"] = ""
        self.save_settings()
    
    def get_remember_api_key(self) -> bool:
        """Get whether to remember API key"""
        return self.settings.get("remember_api_key", True)
    
    def set_ocr_language(self, language: str):
        """Set OCR language"""
        self.settings["ocr_language"] = language
        self.save_settings()
    
    def get_ocr_language(self) -> str:
        """Get OCR language"""
        return self.settings.get("ocr_language", "deu")
    
    def add_dataset(self, dataset: str):
        """Add dataset"""
        print(f"🔍 SETTINGS: add_dataset called with: '{dataset}'")  # Debug
        print(f"📊 SETTINGS: Current datasets: {self.settings['datasets']}")  # Debug
        
        if dataset not in self.settings["datasets"]:
            print(f"✅ SETTINGS: Adding new dataset: '{dataset}'")  # Debug
            self.settings["datasets"].append(dataset)
            self.save_settings()
            print(f"📊 SETTINGS: Updated datasets: {self.settings['datasets']}")  # Debug
            print(f"💾 SETTINGS: Settings saved")  # Debug
        else:
            print(f"⚠️  SETTINGS: Dataset already exists: '{dataset}'")  # Debug
    
    def remove_dataset(self, dataset: str):
        """Remove dataset"""
        if dataset in self.settings["datasets"]:
            self.settings["datasets"].remove(dataset)
            self.save_settings()
    
    def get_datasets(self) -> list:
        """Get datasets"""
        return self.settings["datasets"]
    
    def set_export_directory(self, directory: str):
        """Set export directory"""
        self.settings["export_directory"] = directory
        self.save_settings()
    
    def get_export_directory(self) -> str:
        """Get export directory"""
        return self.settings.get("export_directory", str(Path.home() / "Documents" / "Stimme Exports"))
