import pytesseract
from pdf2image import convert_from_path
import pdfplumber
from PIL import Image
import os
import platform
import subprocess
import threading
import time

class OCREngine:
    def __init__(self):
        """Initialize OCR engine with proper paths for the current OS"""
        self.setup_tesseract_path()
        self.setup_poppler_path()
        self._cancel_flag = threading.Event()
        self._current_process = None
        
    def cancel_processing(self):
        """Cancel any ongoing OCR processing"""
        print(" OCR: Cancellation requested")
        self._cancel_flag.set()
        if self._current_process:
            try:
                self._current_process.terminate()
                print("✅ OCR: Process terminated")
            except:
                pass
    
    def reset_cancel_flag(self):
        """Reset the cancellation flag for new processing"""
        self._cancel_flag.clear()
        
    def setup_tesseract_path(self):
        """Setup Tesseract path based on OS"""
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # Try common Homebrew installation paths
            possible_paths = [
                "/opt/homebrew/bin/tesseract",  # Apple Silicon Macs
                "/usr/local/bin/tesseract",     # Intel Macs
                "/usr/bin/tesseract"            # System installation
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    print(f"✅ OCR: Found Tesseract at {path}")
                    return
            
            # Try to find via which command
            try:
                result = subprocess.run(['which', 'tesseract'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    path = result.stdout.strip()
                    pytesseract.pytesseract.tesseract_cmd = path
                    print(f"✅ OCR: Found Tesseract via which: {path}")
                    return
            except:
                pass
                
            print("  OCR: Tesseract not found. Please install with: brew install tesseract tesseract-lang")
            
        elif system == "Windows":
            # Windows paths
            possible_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME', ''))
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    print(f"✅ OCR: Found Tesseract at {path}")
                    return
                    
            print("  OCR: Tesseract not found on Windows")
            
        else:  # Linux
            # Usually in PATH on Linux
            try:
                result = subprocess.run(['which', 'tesseract'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    path = result.stdout.strip()
                    pytesseract.pytesseract.tesseract_cmd = path
                    print(f"✅ OCR: Found Tesseract via which: {path}")
                    return
            except:
                pass
                
            print("  OCR: Tesseract not found on Linux")
    
    def setup_poppler_path(self):
        """Setup Poppler path based on OS"""
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # Try common Homebrew installation paths
            possible_paths = [
                "/opt/homebrew/bin",      # Apple Silicon Macs
                "/usr/local/bin",         # Intel Macs
                "/usr/bin"                # System installation
            ]
            
            for path in possible_paths:
                if os.path.exists(os.path.join(path, "pdftoppm")):
                    self.poppler_path = path
                    print(f"✅ OCR: Found Poppler at {path}")
                    return
                    
            # Try to find via which command
            try:
                result = subprocess.run(['which', 'pdftoppm'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    path = os.path.dirname(result.stdout.strip())
                    self.poppler_path = path
                    print(f"✅ OCR: Found Poppler via which: {path}")
                    return
            except:
                pass
                
            print("  OCR: Poppler not found. Please install with: brew install poppler")
            self.poppler_path = None
            
        elif system == "Windows":
            # Windows paths
            possible_paths = [
                r'C:\Program Files\poppler\Library\bin',
                r'C:\Program Files\poppler\bin',
                r'C:\poppler\bin',
                r'C:\poppler-25.12.0\Library\bin',
            ]
            
            # Also search C:\ for any poppler-* directories
            try:
                import glob
                for match in glob.glob(r'C:\poppler*\Library\bin'):
                    if match not in possible_paths:
                        possible_paths.append(match)
                for match in glob.glob(r'C:\poppler*\bin'):
                    if match not in possible_paths:
                        possible_paths.append(match)
            except Exception:
                pass

            for path in possible_paths:
                if os.path.exists(path):
                    self.poppler_path = path
                    print(f"✅ OCR: Found Poppler at {path}")
                    return
                    
            print("  OCR: Poppler not found on Windows")
            self.poppler_path = None
            
        else:  # Linux
            # Usually in PATH on Linux
            self.poppler_path = None  # pdf2image will find it automatically
            print("✅ OCR: Using system Poppler on Linux")

    def is_available(self) -> bool:
        """Check if OCR is available and properly configured"""
        try:
            # Test Tesseract
            pytesseract.get_tesseract_version()
            print("✅ OCR: Tesseract is available")
            
            # Test Poppler (try to import and use pdf2image)
            from pdf2image import convert_from_path
            print("✅ OCR: Poppler is available")
            
            return True
        except Exception as e:
            print(f"❌ OCR: Not available - {e}")
            return False
    
    def get_installation_instructions(self) -> dict:
        """Get OS-specific installation instructions for OCR dependencies"""
        import platform
        system = platform.system()
        
        instructions = {
            "system": system,
            "tesseract_missing": False,
            "poppler_missing": False,
            "instructions": []
        }
        
        # Check Tesseract
        try:
            pytesseract.get_tesseract_version()
        except:
            instructions["tesseract_missing"] = True
            if system == "Darwin":  # macOS
                instructions["instructions"].append({
                    "component": "Tesseract",
                    "command": "brew install tesseract tesseract-lang",
                    "description": "Install Tesseract OCR engine via Homebrew"
                })
            elif system == "Windows":
                instructions["instructions"].append({
                    "component": "Tesseract",
                    "url": "https://github.com/UB-Mannheim/tesseract/wiki",
                    "description": "Download and install Tesseract from the official Windows installer"
                })
            else:  # Linux
                instructions["instructions"].append({
                    "component": "Tesseract",
                    "command": "sudo apt-get install tesseract-ocr tesseract-ocr-deu",
                    "description": "Install Tesseract OCR engine via package manager"
                })
        
        # Check Poppler
        try:
            from pdf2image import convert_from_path
            # Try a minimal test
            import tempfile
            import os
            # This will fail if poppler is not available
        except:
            instructions["poppler_missing"] = True
            if system == "Darwin":  # macOS
                instructions["instructions"].append({
                    "component": "Poppler",
                    "command": "brew install poppler",
                    "description": "Install Poppler PDF utilities via Homebrew"
                })
            elif system == "Windows":
                instructions["instructions"].append({
                    "component": "Poppler",
                    "url": "https://blog.alivate.com.au/poppler-windows/",
                    "description": "Download and install Poppler for Windows"
                })
            else:  # Linux
                instructions["instructions"].append({
                    "component": "Poppler",
                    "command": "sudo apt-get install poppler-utils",
                    "description": "Install Poppler PDF utilities via package manager"
                })
        
        return instructions
    
    def get_available_languages(self) -> list:
        """Get list of available OCR languages"""
        try:
            langs = pytesseract.get_languages(config='')
            return langs
        except:
            return ['eng']  # Fallback to English
    
    def process_file(self, file_path: str, language: str = 'deu', progress_callback=None, cancel_callback=None) -> str:
        """
        Process file with OCR and detect potential multi-column issues
        
        Args:
            file_path: Path to file
            language: OCR language code (default: 'deu' for German)
            progress_callback: Optional callback for progress updates
            cancel_callback: Optional callback to check if processing should be cancelled
            
        Returns:
            Extracted text
        """
        if not self.is_available():
            raise Exception("OCR is not properly configured. Please install Tesseract and Poppler.")
        
        # Reset cancellation flag
        self.reset_cancel_flag()
        
        ext = file_path.lower()
        
        # --- CASE 1: PDF FILE ---
        if ext.endswith('.pdf'):
            print(" OCR: Processing PDF file...")
            
            # Try digital extraction first (faster)
            try:
                with pdfplumber.open(file_path) as pdf:
                    text_parts = []
                    for page in pdf.pages:
                        if self._cancel_flag.is_set() or (cancel_callback and cancel_callback()):
                            raise Exception("OCR processing cancelled")
                        text = page.extract_text()
                        if text and text.strip():
                            text_parts.append(text)
                    
                    if text_parts:
                        digital_text = "\n\n".join(text_parts).strip()
                        if len(digital_text) > 100:  # Reasonable amount of text
                            print("✅ OCR: Found digital text in PDF")
                            # Check for multi-column issues
                            if self._detect_multi_column_issues(digital_text):
                                print("⚠️  OCR: Multi-column layout detected in digital text")
                            return digital_text
            except Exception as e:
                if "cancelled" in str(e):
                    raise e
                print(f"  OCR: Digital extraction failed: {e}")
            
            # If digital fails or insufficient text, use OCR
            print(" OCR: Digital extraction insufficient, using OCR...")
            ocr_text = self._ocr_pdf(file_path, language, progress_callback, cancel_callback)
            
            # Check OCR text for multi-column issues
            if self._detect_multi_column_issues(ocr_text):
                print("⚠️  OCR: Multi-column layout detected in OCR text")
            
            return ocr_text
        
        # --- CASE 2: IMAGE FILE ---
        elif ext.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
            print("  OCR: Processing image file...")
            ocr_text = self._ocr_image(file_path, language, cancel_callback)
            
            # Check for multi-column issues
            if self._detect_multi_column_issues(ocr_text):
                print("⚠️  OCR: Multi-column layout detected in image text")
            
            return ocr_text
        
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    
    def _detect_multi_column_issues(self, text: str) -> bool:
        """
        Detect potential multi-column layout issues in OCR text.
        
        Args:
            text: Extracted text to analyze
            
        Returns:
            bool: True if multi-column issues are suspected
        """
        if not text or len(text) < 200:
            return False
        
        lines = text.split('\n')
        if len(lines) < 10:
            return False
        
        # Filter out very short lines (likely headers/footers)
        content_lines = [line.strip() for line in lines if len(line.strip()) > 10]
        
        if len(content_lines) < 5:
            return False
        
        # Calculate line length statistics
        line_lengths = [len(line) for line in content_lines]
        
        try:
            import statistics
            mean_length = statistics.mean(line_lengths)
            if mean_length == 0:
                return False
            
            std_dev = statistics.stdev(line_lengths)
            coefficient_of_variation = std_dev / mean_length
            
            # Count very short and very long lines
            very_short_lines = sum(1 for length in line_lengths if length < mean_length * 0.4)
            very_long_lines = sum(1 for length in line_lengths if length > mean_length * 1.6)
            
            # Check for abrupt line breaks (common in multi-column OCR)
            abrupt_breaks = 0
            for line in content_lines:
                if len(line) > 20 and not line.endswith(('.', '!', '?', ':', ';', '-')):
                    abrupt_breaks += 1
            
            abrupt_break_ratio = abrupt_breaks / len(content_lines) if content_lines else 0
            
            # Multi-column detection criteria
            if coefficient_of_variation > 0.5:
                return True
            
            if (very_short_lines + very_long_lines) / len(line_lengths) > 0.3:
                return True
            
            if abrupt_break_ratio > 0.4:
                return True
            
        except:
            pass  # If statistics fail, continue without detection
        
        return False
    
    def _ocr_pdf(self, file_path: str, language: str, progress_callback=None, cancel_callback=None) -> str:
        """OCR a PDF file by converting to images first"""
        try:
            if self._cancel_flag.is_set() or (cancel_callback and cancel_callback()):
                raise Exception("OCR processing cancelled")
            
            # Convert PDF to images
            if progress_callback:
                progress_callback("Converting PDF to images...", 0)
            
            if self.poppler_path:
                images = convert_from_path(file_path, poppler_path=self.poppler_path)
            else:
                images = convert_from_path(file_path)
            
            if self._cancel_flag.is_set() or (cancel_callback and cancel_callback()):
                raise Exception("OCR processing cancelled")
            
            print(f" OCR: Converted PDF to {len(images)} images")
            
            # OCR each page
            text_parts = []
            total_pages = len(images)
            
            for i, image in enumerate(images):
                if self._cancel_flag.is_set() or (cancel_callback and cancel_callback()):
                    raise Exception("OCR processing cancelled")
                
                print(f" OCR: Processing page {i+1}/{total_pages}")
                
                if progress_callback:
                    progress = int((i / total_pages) * 100)
                    progress_callback(f"Processing page {i+1} of {total_pages}...", progress)
                
                # Use appropriate language settings for German
                if language == 'deu':
                    # Try German Fraktur + modern German
                    try:
                        text = pytesseract.image_to_string(image, lang='deu_frak+deu')
                    except:
                        # Fallback to just modern German
                        text = pytesseract.image_to_string(image, lang='deu')
                else:
                    text = pytesseract.image_to_string(image, lang=language)
                
                if text.strip():
                    text_parts.append(text.strip())
            
            if self._cancel_flag.is_set() or (cancel_callback and cancel_callback()):
                raise Exception("OCR processing cancelled")
            
            result = "\n\n".join(text_parts)
            print(f"✅ OCR: Extracted {len(result)} characters from PDF")
            
            if progress_callback:
                progress_callback("OCR processing complete!", 100)
            
            return result
            
        except Exception as e:
            if "cancelled" in str(e):
                print(" OCR: Processing was cancelled")
                raise e
            raise Exception(f"OCR processing failed: {str(e)}")
    
    def _ocr_image(self, file_path: str, language: str, cancel_callback=None) -> str:
        """OCR an image file"""
        try:
            if cancel_callback and cancel_callback():
                raise Exception("OCR processing cancelled")
            
            image = Image.open(file_path)
            
            # Handle multi-frame images (e.g. multi-page TIFF) — only first frame
            if hasattr(image, 'n_frames') and image.n_frames > 1:
                print(f"⚠️  OCR: Multi-frame image detected ({image.n_frames} frames). Processing first frame only.")
            
            # Convert RGBA/P to RGB (transparency causes OCR issues)
            if image.mode in ('RGBA', 'P', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if 'A' in image.mode else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Use appropriate language settings for German
            if language == 'deu':
                # Try German Fraktur + modern German
                try:
                    text = pytesseract.image_to_string(image, lang='deu_frak+deu')
                except Exception:
                    # Fallback to just modern German
                    text = pytesseract.image_to_string(image, lang='deu')
            else:
                text = pytesseract.image_to_string(image, lang=language)
            
            print(f"✅ OCR: Extracted {len(text)} characters from image")
            return text.strip()
            
        except Exception as e:
            if "cancelled" in str(e):
                raise e
            raise Exception(f"Image OCR failed: {str(e)}")
    
    def test_ocr(self) -> dict:
        """Test OCR functionality and return status"""
        status = {
            "tesseract_available": False,
            "poppler_available": False,
            "languages": [],
            "errors": []
        }
        
        try:
            # Test Tesseract
            version = pytesseract.get_tesseract_version()
            status["tesseract_available"] = True
            status["tesseract_version"] = str(version)
            
            # Get languages
            status["languages"] = self.get_available_languages()
            
        except Exception as e:
            status["errors"].append(f"Tesseract error: {e}")
        
        try:
            # Test Poppler
            from pdf2image import convert_from_path
            status["poppler_available"] = True
            
        except Exception as e:
            status["errors"].append(f"Poppler error: {e}")
        
        return status