class WorkspaceManager:
    """Manages workspace state including tabs and active translations"""
    
    def __init__(self):
        self.translation_tabs = []  # List of translation results
        self.active_translation_index = -1  # -1 means no translation active (show home)
        self.input_text = ""
    
    def set_input_text(self, text: str):
        """Set input text"""
        self.input_text = text
    
    def get_input_text(self) -> str:
        """Get input text"""
        return self.input_text
    
    def add_translation(self, source_text: str, translation: str, commentary: str = None, metrics: dict = None):
        """Add a new translation result and return its index"""
        translation_data = {
            "id": len(self.translation_tabs),
            "source_preview": source_text[:50] + "..." if len(source_text) > 50 else source_text,
            "source_full": source_text,
            "translation": translation,
            "commentary": commentary,
            "metrics": metrics,
            "timestamp": __import__('datetime').datetime.now()
        }
        
        self.translation_tabs.append(translation_data)
        self.active_translation_index = len(self.translation_tabs) - 1
        return self.active_translation_index
    
    def get_active_translation(self):
        """Get the currently active translation"""
        if 0 <= self.active_translation_index < len(self.translation_tabs):
            return self.translation_tabs[self.active_translation_index]
        return None
    
    def set_active_translation(self, index: int):
        """Set active translation by index"""
        if -1 <= index < len(self.translation_tabs):
            self.active_translation_index = index
    
    def close_translation_tab(self, index: int):
        """Close a translation tab"""
        if 0 <= index < len(self.translation_tabs):
            self.translation_tabs.pop(index)
            # Adjust active index
            if self.active_translation_index >= len(self.translation_tabs):
                self.active_translation_index = len(self.translation_tabs) - 1
            elif self.active_translation_index > index:
                self.active_translation_index -= 1
    
    def has_translations(self) -> bool:
        """Check if there are any translations"""
        return len(self.translation_tabs) > 0
    
    def has_unsaved_content(self, pdf_file=None) -> bool:
        """Check if there's unsaved content (input text or loaded PDF)"""
        # Check if there's text in the input
        if self.input_text and self.input_text.strip():
            return True
        
        # Check if there's a PDF loaded
        if pdf_file:
            return True
            
        return False
    
    def get_translation_count(self) -> int:
        """Get number of translations"""
        return len(self.translation_tabs)
