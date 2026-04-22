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
            "export_directory": str(Path.home() / "Documents" / "Stimme Exports"),  # Default export directory
            "llm_backend": "cloud",
            "local_llm_endpoint": "http://localhost:11434",
            "local_llm_model": "llama3",
            "local_llm_timeout": 120
        }
        
        self.load_settings()
        
        # Ensure export directory exists (non-fatal if it fails)
        try:
            export_dir = self.get_export_directory()
            os.makedirs(export_dir, exist_ok=True)
        except Exception as e:
            print(f"⚠️  SETTINGS: Could not create export directory: {e}")
    
    def load_settings(self):
        """Load settings from file, recovering gracefully from corruption"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    self.settings.update(saved)
                else:
                    print(f"⚠️  SETTINGS: File contained non-dict data, using defaults")
                    self._backup_and_reset()
            except json.JSONDecodeError as e:
                print(f"⚠️  SETTINGS: Corrupted JSON, backing up and using defaults: {e}")
                self._backup_and_reset()
            except Exception as e:
                print(f"⚠️  SETTINGS: Error loading, using defaults: {e}")

    def _backup_and_reset(self):
        """Backup corrupted settings file and save fresh defaults"""
        try:
            backup_path = self.config_file.with_suffix(".json.bak")
            if self.config_file.exists():
                import shutil
                shutil.copy2(self.config_file, backup_path)
                print(f"  SETTINGS: Corrupted file backed up to {backup_path}")
            self.save_settings()
        except Exception as e:
            print(f"  SETTINGS: Could not backup: {e}")
    
    def save_settings(self):
        """Save settings to file"""
        try:
            self.config_dir.mkdir(exist_ok=True)  # Ensure dir exists (may have been deleted)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"⚠️  SETTINGS: Error saving: {e}")
    
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
        """Get API key — prefers the sidebar-entered key, falls back to env var."""
        # Prefer the in-memory / persisted key (set via sidebar)
        saved_key = self.settings.get("api_key", "")
        if saved_key and saved_key.strip() and saved_key.startswith("sk-"):
            return saved_key
        # Fall back to environment variable
        env_key = os.getenv("CLAUDE_API_KEY", "")
        if env_key and env_key.strip() and env_key.startswith("sk-"):
            return env_key
        # Return whatever we have (may be empty or a placeholder)
        return saved_key or env_key
    
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
        """Remove dataset (safe — no error if already removed)"""
        if dataset in self.settings["datasets"]:
            self.settings["datasets"].remove(dataset)
            self.save_settings()
    
    def get_datasets(self) -> list:
        """Get datasets"""
        return self.settings["datasets"]
    
    def set_export_directory(self, directory: str):
        """Set export directory (validates it's a plausible path)"""
        if not directory or not directory.strip():
            return  # Ignore empty paths
        self.settings["export_directory"] = directory
        self.save_settings()
        # Try to create it now, but don't fail if we can't
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            print(f"⚠️  SETTINGS: Could not create export directory '{directory}': {e}")
    
    def get_export_directory(self) -> str:
        """Get export directory"""
        return self.settings.get("export_directory", str(Path.home() / "Documents" / "Stimme Exports"))

    # --- Local LLM configuration ---

    def set_llm_backend(self, backend: str):
        """Set LLM backend ('cloud' or 'local')"""
        self.settings["llm_backend"] = backend
        self.save_settings()

    def get_llm_backend(self) -> str:
        """Get LLM backend selection"""
        return self.settings.get("llm_backend", "cloud")

    def set_local_llm_endpoint(self, endpoint: str):
        """Set local LLM server endpoint URL"""
        self.settings["local_llm_endpoint"] = endpoint
        self.save_settings()

    def get_local_llm_endpoint(self) -> str:
        """Get local LLM server endpoint URL"""
        return self.settings.get("local_llm_endpoint", "http://localhost:11434")

    def set_local_llm_model(self, model: str):
        """Set local LLM model name"""
        self.settings["local_llm_model"] = model
        self.save_settings()

    def get_local_llm_model(self) -> str:
        """Get local LLM model name"""
        return self.settings.get("local_llm_model", "llama3")

    def set_local_llm_timeout(self, timeout: int):
        """Set local LLM request timeout in seconds"""
        self.settings["local_llm_timeout"] = timeout
        self.save_settings()

    def get_local_llm_timeout(self) -> int:
        """Get local LLM request timeout in seconds"""
        return self.settings.get("local_llm_timeout", 120)
