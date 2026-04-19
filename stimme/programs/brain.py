import os
import json
import lancedb
import anthropic
import unicodedata
import re
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from transformers import pipeline

load_dotenv()

import os
import json
import lancedb
import anthropic
import unicodedata
import re
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from transformers import pipeline

load_dotenv()

class TranslationBrain:
    def __init__(self):
        # Set up cross-platform paths
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.vectors_path = os.path.join(self.base_dir, "lancedb_vectors")
        
        # Initialize models
        self.embed_model = SentenceTransformer('intfloat/multilingual-e5-small')
        
        # Connect to vector database with cross-platform path
        try:
            self.db = lancedb.connect(self.vectors_path)
            print(f"✅ BRAIN: Connected to vector database at {self.vectors_path}")
        except Exception as e:
            print(f"⚠️  BRAIN: Vector database not found at {self.vectors_path}")
            print("  BRAIN: Translation will work without RAG context")
            self.db = None
        
        # Initialize the active plugins list (CRITICAL FIX)
        self.active_plugins = ["idioms", "corpus"] 
        
        # Local Sentiment
        self.sentiment_pipe = pipeline(
            "sentiment-analysis", 
            model="oliverguhr/german-sentiment-bert"
        )
        
        self.client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
        
        self.system_instructions = """
        You are a world-class Philologist and Translator. 
        You specialize in historical, academic, and philosophical German.
        
        RULES:
        1. OUTPUT ONLY MARKDOWN or JSON as requested.
        2. DO NOT include conversational filler.
        3. Prioritize the register and vocabulary found in the 'SPECIALIZED CONTEXT'.
        4. If the researcher provides a 'THEMATIC FOCUS', prioritize that interpretation.
        5. If providing a technical 'terminus technicus', provide the English followed by German in [].
        6. IGNORE obvious OCR noise, page numbers, margin artifacts, or line numbers. Focus only on the semantic German text.
        7. If you encounter text fragments like "124/b" or similar artifacts mixed with German text, ignore them and translate only the meaningful German content.
        """
    
    def sanitize_text(self, text):
        """
        Sanitize input text to handle encoding issues and normalize Unicode.
        
        Fixes:
        - ISO-8859-1 encoding issues (GroÃŸe -> Große)
        - Unicode normalization (NFKC)
        - OCR noise cleanup
        
        Args:
            text: Raw input text that may have encoding issues
            
        Returns:
            Clean, normalized UTF-8 text
        """
        if not text:
            return text
        
        # Step 1: Handle common ISO-8859-1 -> UTF-8 encoding issues
        # Common patterns: ÃŸ -> ß, Ã¤ -> ä, Ã¶ -> ö, Ã¼ -> ü, Ã„ -> Ä, Ã– -> Ö, Ãœ -> Ü
        encoding_fixes = {
            'ÃŸ': 'ß',
            'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü',
            'Ã„': 'Ä', 'Ã–': 'Ö', 'Ãœ': 'Ü',
            'Ã¡': 'á', 'Ã©': 'é', 'Ã­': 'í', 'Ã³': 'ó', 'Ãº': 'ú',
            'Ã ': 'à', 'Ã¨': 'è', 'Ã¬': 'ì', 'Ã²': 'ò', 'Ã¹': 'ù',
            'Ã¢': 'â', 'Ãª': 'ê', 'Ã®': 'î', 'Ã´': 'ô', 'Ã»': 'û',
            'Ã§': 'ç', 'Ã±': 'ñ'
        }
        
        # Apply encoding fixes
        for broken, fixed in encoding_fixes.items():
            text = text.replace(broken, fixed)
        
        # Step 2: Try to detect and fix double-encoded UTF-8
        try:
            # If text was incorrectly decoded as latin-1, re-encode and decode as UTF-8
            if any(char in text for char in ['Ã', 'â', 'Â']):
                # Attempt to fix double-encoding
                try:
                    fixed_text = text.encode('latin-1').decode('utf-8')
                    text = fixed_text
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass  # Keep original if fix fails
        except:
            pass  # Keep original if any error occurs
        
        # Step 3: Unicode normalization (NFKC - Canonical Decomposition + Canonical Composition)
        # This handles composed vs decomposed characters (e.g., ü vs u + ¨)
        text = unicodedata.normalize('NFKC', text)
        
        # Step 4: Clean up OCR noise patterns
        # Remove obvious page numbers and margin artifacts
        text = re.sub(r'\b\d+/[a-z]\b', '', text)  # Remove patterns like "124/b"
        text = re.sub(r'\b\d+\.\d+\.\d+\b', '', text)  # Remove version numbers
        text = re.sub(r'\b[A-Z]{2,}\s*\d+\b', '', text)  # Remove reference codes like "ABC 123"
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text

    def detect_multi_column_pdf(self, text):
        """
        Detect if text might be from a multi-column PDF based on line length inconsistencies.
        
        Args:
            text: Input text to analyze
            
        Returns:
            bool: True if multi-column layout is suspected
        """
        if not text or len(text) < 200:
            return False
        
        lines = text.split('\n')
        if len(lines) < 10:
            return False
        
        # Calculate line lengths (excluding very short lines which might be headers)
        line_lengths = [len(line.strip()) for line in lines if len(line.strip()) > 10]
        
        if len(line_lengths) < 5:
            return False
        
        # Calculate coefficient of variation (std dev / mean)
        import statistics
        mean_length = statistics.mean(line_lengths)
        if mean_length == 0:
            return False
        
        std_dev = statistics.stdev(line_lengths)
        coefficient_of_variation = std_dev / mean_length
        
        # Additional checks for multi-column indicators
        very_short_lines = sum(1 for length in line_lengths if length < mean_length * 0.4)
        very_long_lines = sum(1 for length in line_lengths if length > mean_length * 1.6)
        
        # Check for abrupt line breaks (common in multi-column OCR)
        abrupt_breaks = 0
        for line in lines:
            stripped = line.strip()
            if len(stripped) > 20 and not stripped.endswith(('.', '!', '?', ':', ';')):
                # Line ends abruptly without punctuation
                abrupt_breaks += 1
        
        abrupt_break_ratio = abrupt_breaks / len(lines) if lines else 0
        
        # Multi-column detection criteria:
        # 1. High coefficient of variation (CV > 0.5)
        # 2. Many very short and very long lines
        # 3. High ratio of abrupt line breaks
        
        if coefficient_of_variation > 0.5:
            return True
        
        if (very_short_lines + very_long_lines) / len(line_lengths) > 0.3:
            return True
        
        if abrupt_break_ratio > 0.4:
            return True
        
        return False
        try:
            self.db.open_table(table_name)
            if table_name not in self.active_plugins:
                self.active_plugins.append(table_name)
            return True
        except:
            return False

    def remove_plugin(self, table_name):
        if table_name in self.active_plugins:
            self.active_plugins.remove(table_name)

    def add_plugin(self, table_name):
        if self.db is None:
            print(f"⚠️  BRAIN: Cannot add plugin '{table_name}' - no vector database available")
            return False
        
        try:
            self.db.open_table(table_name)
            if table_name not in self.active_plugins:
                self.active_plugins.append(table_name)
            return True
        except Exception as e:
            print(f"⚠️  BRAIN: Failed to add plugin '{table_name}': {e}")
            return False

    def remove_plugin(self, table_name):
        if table_name in self.active_plugins:
            self.active_plugins.remove(table_name)

    def get_context(self, german_text, max_examples_per_plugin=3):
        """
        Get contextual examples from active plugins with distance scoring and context budgeting.
        
        Args:
            german_text: The German text to find context for
            max_examples_per_plugin: Maximum examples per plugin (for context budgeting)
            
        Returns:
            Tuple of (context_string, has_relevant_context)
        """
        if self.db is None:
            return "\n--- NOTE ---\nNo vector database available. Translation will use general knowledge only.\n", False
        
        query_vector = self.embed_model.encode(german_text)
        context_str = ""
        has_relevant_context = False
        
        # Context budgeting: reduce examples if input text is long
        input_length = len(german_text)
        if input_length > 3000:  # Long text
            max_examples_per_plugin = 2
        elif input_length > 1500:  # Medium text
            max_examples_per_plugin = 2
        # Short text keeps default (3)

        for table_name in self.active_plugins:
            try:
                table = self.db.open_table(table_name)
                matches = table.search(query_vector).limit(max_examples_per_plugin).to_list()
                
                # Check if we have relevant matches (distance score < 1.5)
                relevant_matches = []
                for m in matches:
                    # LanceDB uses L2 distance, lower is better
                    # Typical good matches are < 1.0, questionable matches > 1.5
                    distance = m.get('_distance', 0)
                    if distance < 1.5:  # Only include relevant matches
                        relevant_matches.append(m)
                        has_relevant_context = True
                
                if relevant_matches:
                    context_str += f"\n--- SPECIALIZED CONTEXT: {table_name.upper()} ---\n"
                    for m in relevant_matches:
                        if table_name == "idioms":
                            context_str += f"DE Idiom: {m['german']} | Meaning: {m['meaning']} | Target: {m['english']}\n"
                        else:
                            context_str += f"DE: {m.get('de', m.get('german'))} | EN: {m.get('en', m.get('english'))} | Sentiment: {m.get('sentiment', 'N/A')}\n"
            except Exception as e:
                print(f"⚠️  BRAIN: Error accessing table '{table_name}': {e}")
                continue 
        
        if not has_relevant_context:
            context_str += "\n--- NOTE ---\nNo relevant scholarly context found in active libraries. Translation will use general knowledge.\n"
        
        return context_str, has_relevant_context

    def translate(self, text, model_id="claude-sonnet-4-6", user_instructions="", provide_commentary=True):
        """
        The main pipeline with comprehensive text sanitization and context management.
        
        Args:
            text: German text to translate
            model_id: Claude model ID (claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5-20251001)
            user_instructions: Thematic focus from the user
            provide_commentary: Whether to include philological commentary
            
        Returns:
            Tuple of (translation, commentary, metrics)
        """
        # Step 1: Sanitize input text
        print("🧹 BRAIN: Sanitizing input text...")
        original_text = text
        text = self.sanitize_text(text)
        
        if text != original_text:
            print("✅ BRAIN: Text sanitization applied (encoding/Unicode fixes)")
        
        # Step 2: Check for multi-column PDF issues
        if self.detect_multi_column_pdf(text):
            print("⚠️  BRAIN: Multi-column PDF layout detected - translation quality may be affected")
            # Add warning to commentary if enabled
            multi_column_warning = "\n\n**Note**: Multi-column PDF layout detected. If translation seems fragmented, consider cropping the PDF to single columns."
        else:
            multi_column_warning = ""
        
        # Step 3: Analysis with sanitized text
        try:
            sentiment_res = self.sentiment_pipe(text)[0]
            sentiment_label = sentiment_res['label']
        except Exception as e:
            print(f"⚠️  BRAIN: Sentiment analysis failed (possibly due to text encoding): {e}")
            sentiment_label = "NEUTRAL"  # Fallback
        
        # Step 4: Get context with distance scoring
        context_str, has_relevant_context = self.get_context(text)
        
        if not has_relevant_context:
            context_str += "\n--- NOTE ---\nNo relevant scholarly context found in active libraries. Translation will use general knowledge.\n"
            print("ℹ️  BRAIN: No relevant context found in libraries (distance scores too high)")

        # Step 5: Mission Mode Logic
        if provide_commentary:
            mode_instruction = (
                "Return response in RAW JSON format only. Do not use markdown blocks. "
                "Format: {'translation': '...', 'commentary': '...'}. "
            )
        else:
            mode_instruction = "OUTPUT ONLY THE RAW TRANSLATION STRING. No JSON."

        # Step 6: Call Claude with the USER-SELECTED model
        # Calculate appropriate max_tokens based on input length
        estimated_input_tokens = len(text) // 4 + len(context_str) // 4 + 500  # +500 for system/instructions
        
        # Set max_tokens based on model and input size
        if "opus-4" in model_id:
            max_output_tokens = min(8000, 200000 - estimated_input_tokens)  # Opus has 200k context
        elif "sonnet-4" in model_id:
            max_output_tokens = min(8000, 200000 - estimated_input_tokens)  # Sonnet has 200k context
        elif "haiku-4" in model_id:
            max_output_tokens = min(4000, 200000 - estimated_input_tokens)  # Haiku has 200k context
        else:
            max_output_tokens = min(4000, 100000 - estimated_input_tokens)  # Conservative fallback
        
        # Ensure we have at least 1000 tokens for output
        max_output_tokens = max(1000, max_output_tokens)
        
        response = self.client.messages.create(
            model=model_id, 
            max_tokens=max_output_tokens,
            system=self.system_instructions + "\n\n" + mode_instruction,
            messages=[{
                "role": "user", 
                "content": f"SENTIMENT: {sentiment_label}\nFOCUS: {user_instructions}\nCONTEXT:\n{context_str}\nTEXT:\n{text}"
            }]
        )

        # Step 7: Extract Data & Tokens
        raw_output = response.content[0].text
        in_t = response.usage.input_tokens
        out_t = response.usage.output_tokens
        
        # Calculate cost based on model type (Updated pricing for Claude 4 models)
        if "opus-4" in model_id:
            cost = (in_t * (15.0/1000000)) + (out_t * (75.0/1000000))
        elif "sonnet-4" in model_id:
            cost = (in_t * (3.0/1000000)) + (out_t * (15.0/1000000))
        elif "haiku-4" in model_id:
            cost = (in_t * (0.25/1000000)) + (out_t * (1.25/1000000))
        else:
            cost = 0.0

        metrics = {
            "input_tokens": in_t,
            "output_tokens": out_t,
            "estimated_cost": round(cost, 5),
            "model_used": model_id,
            "text_sanitized": text != original_text,
            "relevant_context_found": has_relevant_context
        }

        # Step 8: Handling JSON and Commentary
        if provide_commentary:
            try:
                clean_json = raw_output.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json)
                translation = data.get('translation', "")
                commentary = data.get('commentary', "") + multi_column_warning
                return translation, commentary, metrics
            except:
                return raw_output, multi_column_warning, metrics
        else:
            return raw_output, None, metrics