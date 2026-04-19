"""
Translation service that bridges the frontend and backend.
Handles the actual translation calls to the brain.py backend.
"""

import sys
import os
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, Optional, Dict, Any

# Add the programs directory to the path so we can import brain
sys.path.append(str(Path(__file__).parent.parent.parent / "programs"))

from app.constants import ERROR_NO_API_KEY, ERROR_TRANSLATION_FAILED, LOADING_MESSAGES
from app.contexts.settings import SettingsManager
from app.services.history import HistoryManager

class TranslationService:
    """Service for handling translation requests"""
    
    def __init__(self, settings: SettingsManager):
        self.settings = settings
        self.brain = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.history = HistoryManager()  # Add history manager
        
    def _initialize_brain(self):
        """Lazy initialization of the brain to avoid import issues"""
        if self.brain is None:
            try:
                from brain import TranslationBrain
                self.brain = TranslationBrain()
            except ImportError as e:
                raise ImportError(f"Failed to import TranslationBrain: {e}")
    
    async def translate_async(
        self, 
        text: str, 
        progress_callback: Optional[callable] = None
    ) -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
        """
        Translate text asynchronously.
        
        Args:
            text: German text to translate
            progress_callback: Optional callback for progress updates
            
        Returns:
            Tuple of (success, translation, commentary, metrics)
        """
        # Validate inputs
        if not text or not text.strip():
            return False, "Please enter some German text to translate.", None, None
            
        if not self.settings.has_api_key():
            return False, ERROR_NO_API_KEY, None, None
        
        try:
            # Initialize brain if needed
            self._initialize_brain()
            
            # Get settings
            model_id = self.settings.get_model()
            thematic_focus = self.settings.get_thematic_focus()
            scholar_mode = self.settings.get_scholar_mode()
            
            # Progress updates
            if progress_callback:
                await progress_callback("Initializing translation…")
            
            # Run translation in thread pool to avoid blocking UI
            loop = asyncio.get_event_loop()
            
            def _translate():
                return self.brain.translate(
                    text=text,
                    model_id=model_id,
                    user_instructions=thematic_focus,
                    provide_commentary=scholar_mode
                )
            
            if progress_callback:
                await progress_callback("Consulting the library…")
            
            # Execute translation
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
                commentary=commentary or ""
            )
            
            return True, translation, commentary, metrics
            
        except Exception as e:
            error_msg = f"{ERROR_TRANSLATION_FAILED}: {str(e)}"
            return False, error_msg, None, None
    
    def translate_sync(
        self, 
        text: str
    ) -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
        """
        Synchronous translation for simple use cases.
        
        Args:
            text: German text to translate
            
        Returns:
            Tuple of (success, translation, commentary, metrics)
        """
        # Validate inputs
        if not text or not text.strip():
            return False, "Please enter some German text to translate.", None, None
            
        if not self.settings.has_api_key():
            return False, ERROR_NO_API_KEY, None, None
        
        # Check text length (rough token estimation: 1 token ≈ 4 characters)
        estimated_tokens = len(text) // 4
        max_input_tokens = 150000  # Conservative limit for Claude models
        
        if estimated_tokens > max_input_tokens:
            return False, f"Text is too long ({estimated_tokens:,} estimated tokens). Maximum supported: {max_input_tokens:,} tokens. Please split your text into smaller sections.", None, None
        
        try:
            # Initialize brain if needed
            self._initialize_brain()
            
            # Get settings
            model_id = self.settings.get_model()
            thematic_focus = self.settings.get_thematic_focus()
            scholar_mode = self.settings.get_scholar_mode()
            
            # Execute translation
            translation, commentary, metrics = self.brain.translate(
                text=text,
                model_id=model_id,
                user_instructions=thematic_focus,
                provide_commentary=scholar_mode
            )
            
            # Save to history
            self.history.add_entry(
                source=text,
                translation=translation,
                model=model_id,
                commentary=commentary or ""
            )
            
            return True, translation, commentary, metrics
            
        except Exception as e:
            error_msg = f"{ERROR_TRANSLATION_FAILED}: {str(e)}"
            return False, error_msg, None, None
    
    def get_loading_message(self, step: int = 0) -> str:
        """Get a loading message for the given step"""
        if step < len(LOADING_MESSAGES):
            return LOADING_MESSAGES[step]
        return LOADING_MESSAGES[-1]
    
    def cleanup(self):
        """Cleanup resources"""
        if self.executor:
            self.executor.shutdown(wait=False)