import os
from anthropic import Anthropic

class TranslationService:
    """Service for handling Claude API translations"""
    
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
    
    def translate(self, text: str, model: str, instructions: str = "", include_commentary: bool = False) -> dict:
        """
        Translate German text to English
        
        Args:
            text: German text to translate
            model: Claude model to use
            instructions: Optional user instructions
            include_commentary: Whether to include commentary
        
        Returns:
            Dictionary with translation and optional commentary
        """
        prompt = f"Translate the following German text to English:\n\n{text}"
        
        if instructions:
            prompt += f"\n\nAdditional instructions: {instructions}"
        
        if include_commentary:
            prompt += "\n\nPlease also provide a brief commentary on the translation."
        
        try:
            message = self.client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = message.content[0].text
            
            result = {
                "translation": response_text,
                "model": model,
                "success": True
            }
            
            return result
        
        except Exception as e:
            return {
                "translation": "",
                "error": str(e),
                "success": False
            }
