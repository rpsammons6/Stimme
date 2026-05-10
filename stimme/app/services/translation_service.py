"""
Translation service that bridges the frontend and backend.
Handles the actual translation calls to the brain.py backend.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, Optional, Dict, Any

from app.constants import ERROR_NO_API_KEY
from app.services.configuration_service import ConfigurationService
from app.services.history import HistoryManager
from app.services.llm_backend_router import LLMBackendRouter

class TranslationService:
    """Service for handling translation requests"""
    
    def __init__(self, settings: ConfigurationService):
        self.settings = settings
        self.router = LLMBackendRouter(settings)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.history = HistoryManager()

    @property
    def brain(self):
        """Backward-compatible access to the underlying TranslationBrain.

        External code (e.g. CorrectionService, ReTranslationEngine) may need
        the raw TranslationBrain instance.  The router lazily creates it.
        """
        return self.router._get_brain()

    def _initialize_brain(self):
        """Backward-compatible lazy init — delegates to the router."""
        self.router._get_brain()
    
    async def translate_async(
        self, 
        text: str, 
        progress_callback: Optional[callable] = None,
        log_callback: Optional[callable] = None,
        cache_control: bool = False,
        pdf_path: Optional[str] = None,
        glossary_block: str = "",
        glossary_manager=None,
    ) -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
        """
        Translate text asynchronously.
        """
        if not text or not text.strip():
            return False, "Please enter some German text to translate.", None, None
            
        if not self.settings.has_api_key():
            return False, ERROR_NO_API_KEY, None, None
        
        # Pre-translate glossary save guard
        if glossary_manager is not None and glossary_manager.is_dirty:
            try:
                _log = log_callback or print
                _log("[SYSTEM]: Saving glossary before inference...")
                glossary_manager.save()
            except Exception as e:
                _log_err = log_callback or print
                _log_err(f"[SYSTEM]: Glossary save failed: {e}")
        
        try:
            model_id = self.settings.get_model()
            thematic_focus = self.settings.get_thematic_focus()
            scholar_mode = self.settings.get_scholar_mode()
            
            if progress_callback:
                await progress_callback("Initializing translation…")
            
            loop = asyncio.get_event_loop()
            
            # Get the API key from settings (sidebar) to pass directly to brain
            api_key = self.settings.get_api_key()
            
            # This is the inner function that runs in the background thread
            def _translate():
                return self.router.translate(
                    text=text,
                    model_id=model_id,
                    user_instructions=thematic_focus,
                    provide_commentary=scholar_mode,
                    log_callback=log_callback,
                    cache_control=cache_control,
                    api_key=api_key,
                    glossary_block=glossary_block,
                    vad_settings={
                        "enabled": self.settings.get("vad_enabled", True),
                        "valence_multiplier": self.settings.get("valence_multiplier", 1.0),
                        "arousal_multiplier": self.settings.get("arousal_multiplier", 1.0),
                        "dominance_multiplier": self.settings.get("dominance_multiplier", 1.0),
                    },
                )
            
            # Execute translation in the thread pool
            translation, commentary, metrics = await loop.run_in_executor(
                self.executor, _translate
            )
            
            if progress_callback:
                await progress_callback("Translation complete!")
            
            # Save to history
            self.history.add_entry(
                source=text,
                translation=translation,
                model=model_id,
                commentary=commentary or "",
                pdf_path=pdf_path,
            )
            
            return True, translation, commentary, metrics
            
        except Exception as e:
            error_msg = self._friendly_error(e)
            return False, error_msg, None, None
    
    def translate_sync(
        self, 
        text: str,
        log_callback: Optional[callable] = None,
        cache_control: bool = False,
        pdf_path: Optional[str] = None,
        glossary_block: str = "",
        glossary_manager=None,
    ) -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
        """
        Synchronous translation for simple use cases.
        """
        if not text or not text.strip():
            return False, "Please enter some German text to translate.", None, None
            
        if not self.settings.has_api_key():
            return False, ERROR_NO_API_KEY, None, None
        
        # Pre-translate glossary save guard
        if glossary_manager is not None and glossary_manager.is_dirty:
            try:
                _log = log_callback or print
                _log("[SYSTEM]: Saving glossary before inference...")
                glossary_manager.save()
            except Exception as e:
                _log_err = log_callback or print
                _log_err(f"[SYSTEM]: Glossary save failed: {e}")
        
        try:
            model_id = self.settings.get_model()
            thematic_focus = self.settings.get_thematic_focus()
            scholar_mode = self.settings.get_scholar_mode()
            
            api_key = self.settings.get_api_key()
            
            translation, commentary, metrics = self.router.translate(
                text=text,
                model_id=model_id,
                user_instructions=thematic_focus,
                provide_commentary=scholar_mode,
                log_callback=log_callback,
                cache_control=cache_control,
                api_key=api_key,
                glossary_block=glossary_block,
                vad_settings={
                    "enabled": self.settings.get("vad_enabled", True),
                    "valence_multiplier": self.settings.get("valence_multiplier", 1.0),
                    "arousal_multiplier": self.settings.get("arousal_multiplier", 1.0),
                    "dominance_multiplier": self.settings.get("dominance_multiplier", 1.0),
                },
            )
            
            self.history.add_entry(
                source=text,
                translation=translation,
                model=model_id,
                commentary=commentary or "",
                pdf_path=pdf_path,
            )
            
            return True, translation, commentary, metrics
            
        except Exception as e:
            error_msg = self._friendly_error(e)
            return False, error_msg, None, None

    def _friendly_error(self, e: Exception) -> str:
        """Convert raw exceptions into user-friendly error messages."""
        # Check Anthropic SDK exception types first (more reliable than string matching)
        try:
            import anthropic
            if isinstance(e, anthropic.AuthenticationError):
                return "API key is invalid or expired. Please update it in the sidebar."
            if isinstance(e, anthropic.RateLimitError):
                return "Rate limited by the API. Please wait a moment and try again."
            if isinstance(e, anthropic.APIConnectionError):
                return "No internet connection. Please check your network and try again."
            if isinstance(e, anthropic.APIStatusError) and hasattr(e, 'status_code'):
                if e.status_code in (500, 502, 503):
                    return "The translation service is temporarily unavailable. Try again shortly."
                if e.status_code == 529:
                    return "The API is overloaded. Please try again in a few minutes."
        except ImportError:
            pass

        # Fallback to string matching for non-Anthropic errors
        msg = str(e).lower()
        if "timeout" in msg or "network" in msg:
            return "No internet connection. Please check your network and try again."
        elif "import" in msg or "module" in msg:
            return "Translation engine failed to load. Check the terminal for details."
        else:
            return f"Translation failed: {str(e)}"
    
    def cleanup(self):
        """Cleanup resources"""
        if self.executor:
            self.executor.shutdown(wait=False)