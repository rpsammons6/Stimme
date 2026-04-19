"""
Export service for the Stimme UI - bridges frontend and backend export functionality
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the programs directory to the path so we can import export_manager
sys.path.append(str(Path(__file__).parent.parent.parent / "programs"))

from app.contexts.settings import SettingsManager

class ExportService:
    """Service for handling export requests from the UI"""
    
    def __init__(self, settings: SettingsManager):
        self.settings = settings
        self.export_manager = None
        
    def _initialize_export_manager(self):
        """Lazy initialization of the export manager"""
        if self.export_manager is None:
            try:
                from export_manager import ExportManager
                export_dir = self.settings.get_export_directory()
                self.export_manager = ExportManager(export_dir)
            except ImportError as e:
                raise ImportError(f"Failed to import ExportManager: {e}")
    
    def export_single_translation(
        self, 
        translation_data: Dict[str, Any], 
        format_type: str = "txt"
    ) -> tuple[bool, str]:
        """
        Export a single translation
        
        Args:
            translation_data: Translation data dictionary
            format_type: Export format ('txt', 'html', 'markdown')
            
        Returns:
            Tuple of (success, message/filepath)
        """
        try:
            self._initialize_export_manager()
            
            # Update export directory in case it changed
            self.export_manager.set_export_directory(self.settings.get_export_directory())
            
            source_text = translation_data.get('source_full', '')
            translation = translation_data.get('translation', '')
            commentary = translation_data.get('commentary', '')
            metadata = translation_data.get('metrics', {})
            
            if format_type == "txt":
                filepath = self.export_manager.export_translation_txt(
                    source_text, translation, commentary, metadata
                )
            elif format_type == "html":
                filepath = self.export_manager.export_translation_html(
                    source_text, translation, commentary, metadata
                )
            elif format_type == "markdown":
                filepath = self.export_manager.export_translation_markdown(
                    source_text, translation, commentary, metadata
                )
            else:
                return False, f"Unsupported format: {format_type}"
            
            return True, filepath
            
        except Exception as e:
            return False, f"Export failed: {str(e)}"
    
    def export_multiple_translations(
        self, 
        translations: List[Dict[str, Any]], 
        format_type: str = "txt"
    ) -> tuple[bool, str]:
        """
        Export multiple translations to a single file
        
        Args:
            translations: List of translation data dictionaries
            format_type: Export format ('txt', 'html', 'markdown')
            
        Returns:
            Tuple of (success, message/filepath)
        """
        try:
            self._initialize_export_manager()
            
            # Update export directory in case it changed
            self.export_manager.set_export_directory(self.settings.get_export_directory())
            
            filepath = self.export_manager.export_multiple_translations(
                translations, format_type
            )
            
            return True, filepath
            
        except Exception as e:
            return False, f"Export failed: {str(e)}"
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported export formats"""
        try:
            self._initialize_export_manager()
            return self.export_manager.get_supported_formats()
        except:
            return ['txt', 'html', 'markdown']  # Fallback
    
    def get_export_directory(self) -> str:
        """Get current export directory"""
        return self.settings.get_export_directory()
    
    def set_export_directory(self, directory: str):
        """Set export directory"""
        self.settings.set_export_directory(directory)
        if self.export_manager:
            self.export_manager.set_export_directory(directory)