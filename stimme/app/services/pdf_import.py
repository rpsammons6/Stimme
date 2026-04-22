import PyPDF2
import sys
import time
import queue
from pathlib import Path

# Add the programs directory to the path so we can import OCR engine
sys.path.append(str(Path(__file__).parent.parent.parent / "programs"))

from app.services.process_worker import WorkerPool, ExtractionMessage


class PDFImportService:
    """Service for importing and extracting text from files"""

    _worker_pool = WorkerPool()

    @classmethod
    def extract_in_process(cls, task_type: str, file_path: str,
                           progress_callback=None, cancel_callback=None,
                           **kwargs) -> str:
        """Submit extraction to a child process. Returns extracted text.

        Polls the worker queue from the calling thread (expected to be a
        daemon thread in HomeTab) and forwards progress messages, handles
        timeouts, and detects worker crashes.
        """
        result_queue = cls._worker_pool.submit(task_type, file_path, **kwargs)
        last_message_time = time.monotonic()
        TIMEOUT_SECONDS = 30

        while True:
            # --- crash detection (8.5) ---
            process = cls._worker_pool._active_process
            if process is not None and not process.is_alive():
                # Process died — drain any remaining messages first
                try:
                    msg = result_queue.get_nowait()
                except queue.Empty:
                    cls._worker_pool._cleanup()
                    raise RuntimeError(
                        "Extraction worker process crashed unexpectedly"
                    )
                else:
                    # Got a message from the dead process — handle it below
                    pass
            else:
                # --- poll queue with short timeout ---
                try:
                    msg = result_queue.get(timeout=0.1)
                except queue.Empty:
                    # --- timeout detection (8.4) ---
                    if time.monotonic() - last_message_time > TIMEOUT_SECONDS:
                        cls._worker_pool.cancel()
                        raise RuntimeError(
                            "Extraction worker timed out (no message for 30 seconds)"
                        )
                    continue

            # We have a message — reset the timeout clock
            last_message_time = time.monotonic()

            if msg.msg_type == ExtractionMessage.PROGRESS:
                if progress_callback:
                    progress_callback(
                        msg.data.get("message", ""),
                        msg.data.get("progress", 0),
                    )

            elif msg.msg_type == ExtractionMessage.RESULT:
                cls._worker_pool._cleanup()
                return msg.data.get("text", "")

            elif msg.msg_type == ExtractionMessage.ERROR:
                cls._worker_pool._cleanup()
                raise RuntimeError(msg.data.get("error", "Unknown extraction error"))
    
    @staticmethod
    def extract_pdf_text(file_path: str, use_ocr: bool = True, progress_callback=None, cancel_callback=None) -> str:
        """
        Extract text from PDF file with OCR fallback
        
        Args:
            file_path: Path to PDF file
            use_ocr: Whether to use OCR if digital extraction fails
            progress_callback: Optional callback for progress updates (message, progress)
            cancel_callback: Optional callback to check if processing should be cancelled
        
        Returns:
            Extracted text
        """
        print(f" PDF_IMPORT: Starting PDF text extraction from: {file_path}")  # Debug
        
        # Check for cancellation
        if cancel_callback and cancel_callback():
            raise Exception("PDF processing cancelled")
        
        if progress_callback:
            progress_callback("Starting PDF text extraction...", 5)
        
        try:
            # First try digital extraction with PyPDF2
            text_parts = []
            with open(file_path, 'rb') as file:
                print(f" PDF_IMPORT: File opened successfully")  # Debug
                pdf_reader = PyPDF2.PdfReader(file)
                
                # Check for encryption
                if pdf_reader.is_encrypted:
                    try:
                        # Try empty password (some PDFs are "encrypted" with no password)
                        pdf_reader.decrypt("")
                    except Exception:
                        raise Exception("This PDF is password-protected. Please provide an unencrypted version.")
                
                num_pages = len(pdf_reader.pages)
                print(f" PDF_IMPORT: PDF reader created, pages: {num_pages}")  # Debug
                
                if num_pages == 0:
                    raise Exception("This PDF has no pages.")
                
                if progress_callback:
                    progress_callback("Attempting digital text extraction...", 10)
                
                for i, page in enumerate(pdf_reader.pages):
                    # Check for cancellation
                    if cancel_callback and cancel_callback():
                        raise Exception("PDF processing cancelled")
                    
                    print(f" PDF_IMPORT: Processing page {i+1}")  # Debug
                    text = page.extract_text()
                    print(f" PDF_IMPORT: Page {i+1} text length: {len(text) if text else 0}")  # Debug
                    if text and text.strip():
                        text_parts.append(text)
                    
                    # Update progress for digital extraction
                    if progress_callback and len(pdf_reader.pages) > 0:
                        digital_progress = 10 + (i + 1) / len(pdf_reader.pages) * 20  # 10-30%
                        progress_callback(f"Processing page {i+1} of {len(pdf_reader.pages)}...", digital_progress)
            
            digital_text = "\n\n".join(text_parts).strip()
            print(f"✅ PDF_IMPORT: Digital extraction - text length: {len(digital_text)}")  # Debug
            
            # If we got substantial digital text, return it
            if len(digital_text) > 100:  # Reasonable threshold
                print("✅ PDF_IMPORT: Using digital text extraction")
                return digital_text
            
            # If digital extraction failed or insufficient, try OCR
            if use_ocr:
                print(" PDF_IMPORT: Digital extraction insufficient, trying OCR...")
                if progress_callback:
                    progress_callback("Digital extraction insufficient, starting OCR...", 35)
                return PDFImportService._extract_with_ocr(file_path, progress_callback, cancel_callback)
            else:
                print("  PDF_IMPORT: OCR disabled, returning digital text")
                return digital_text
            
        except Exception as e:
            err_str = str(e)
            print(f" PDF_IMPORT: Exception during extraction: {err_str}")
            
            # If it's a clear user-facing error, don't try OCR fallback
            if "password-protected" in err_str.lower() or "no pages" in err_str.lower():
                raise
            
            # If digital extraction completely failed, try OCR as last resort
            if use_ocr:
                print(" PDF_IMPORT: Digital extraction failed, trying OCR as fallback...")
                if progress_callback:
                    progress_callback("Digital extraction failed, starting OCR...", 35)
                try:
                    return PDFImportService._extract_with_ocr(file_path, progress_callback, cancel_callback)
                except Exception as ocr_e:
                    ocr_str = str(ocr_e)
                    print(f" PDF_IMPORT: OCR also failed: {ocr_str}")
                    # Give a friendlier message
                    if "poppler" in ocr_str.lower():
                        raise Exception("PDF text extraction failed and OCR requires Poppler. Please ensure Poppler is installed.")
                    elif "tesseract" in ocr_str.lower():
                        raise Exception("PDF text extraction failed and OCR requires Tesseract. Please ensure Tesseract is installed.")
                    else:
                        raise Exception(f"Could not extract text from this PDF. Digital extraction and OCR both failed.")
            else:
                raise Exception(f"Error extracting PDF: {err_str}")
    
    @staticmethod
    def _extract_with_ocr(file_path: str, progress_callback=None, cancel_callback=None) -> str:
        """Extract text using OCR engine"""
        try:
            from ocr_engine import OCREngine
            
            ocr = OCREngine()
            
            # Check if OCR is available
            if not ocr.is_available():
                raise Exception("OCR is not properly configured. Please install Tesseract and Poppler using the provided installation script.")
            
            print(" PDF_IMPORT: Starting OCR extraction...")
            if progress_callback:
                progress_callback("Starting OCR processing...", 40)
            
            # Create a wrapper progress callback that adjusts the range
            def ocr_progress_callback(message, progress):
                if progress_callback:
                    # Map OCR progress (0-100) to our range (40-95)
                    adjusted_progress = 40 + (progress * 0.55)  # 40% to 95%
                    progress_callback(message, adjusted_progress)
            
            # Create a wrapper cancel callback
            def ocr_cancel_callback():
                return cancel_callback() if cancel_callback else False
            
            text = ocr.process_file(file_path, language='deu', 
                                 progress_callback=ocr_progress_callback,
                                 cancel_callback=ocr_cancel_callback)
            print(f"✅ PDF_IMPORT: OCR extraction completed - text length: {len(text)}")
            
            if progress_callback:
                progress_callback("OCR processing complete!", 100)
            
            if not text.strip():
                raise Exception("OCR extraction returned no text")
            
            return text
            
        except ImportError as e:
            raise Exception(f"OCR engine not available: {str(e)}")
        except Exception as e:
            if "cancelled" in str(e).lower():
                raise e
            raise Exception(f"OCR extraction failed: {str(e)}")
    
    @staticmethod
    def test_ocr_availability() -> dict:
        """Test if OCR is available and properly configured"""
        try:
            from ocr_engine import OCREngine
            ocr = OCREngine()
            return ocr.test_ocr()
        except ImportError:
            return {
                "tesseract_available": False,
                "poppler_available": False,
                "languages": [],
                "errors": ["OCR engine not available"]
            }
        except Exception as e:
            return {
                "tesseract_available": False,
                "poppler_available": False,
                "languages": [],
                "errors": [f"OCR test failed: {str(e)}"]
            }
    
    @staticmethod
    def extract_image_text(file_path: str, progress_callback=None, cancel_callback=None) -> str:
        """
        Extract text from image file using OCR
        
        Args:
            file_path: Path to image file
            progress_callback: Optional callback for progress updates
            cancel_callback: Optional callback to check if processing should be cancelled
        
        Returns:
            Extracted text
        """
        try:
            from ocr_engine import OCREngine
            
            # Check for cancellation
            if cancel_callback and cancel_callback():
                raise Exception("Image processing cancelled")
            
            ocr = OCREngine()
            
            if not ocr.is_available():
                raise Exception("OCR is not properly configured. Please install Tesseract and Poppler.")
            
            print(f"  PDF_IMPORT: Starting image OCR extraction from: {file_path}")
            
            if progress_callback:
                progress_callback("Processing image with OCR...", 20)
            
            # Create a wrapper progress callback
            def ocr_progress_callback(message, progress):
                if progress_callback:
                    # Map OCR progress (0-100) to our range (20-95)
                    adjusted_progress = 20 + (progress * 0.75)  # 20% to 95%
                    progress_callback(message, adjusted_progress)
            
            # Create a wrapper cancel callback
            def ocr_cancel_callback():
                return cancel_callback() if cancel_callback else False
            
            text = ocr.process_file(file_path, language='deu',
                                 progress_callback=ocr_progress_callback,
                                 cancel_callback=ocr_cancel_callback)
            print(f"✅ PDF_IMPORT: Image OCR completed - text length: {len(text)}")
            
            if progress_callback:
                progress_callback("Image processing complete!", 100)
            
            return text
            
        except ImportError as e:
            raise Exception(f"OCR engine not available: {str(e)}")
        except Exception as e:
            if "cancelled" in str(e).lower():
                raise e
            raise Exception(f"Image OCR failed: {str(e)}")
    
    @staticmethod
    def read_text_file(file_path: str) -> str:
        """
        Read text from .txt or .md file.
        Tries UTF-8 first, falls back to Latin-1 (which never fails).
        
        Args:
            file_path: Path to text file
        
        Returns:
            File contents
        """
        # Try UTF-8 first (most common)
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            pass
        
        # Fallback: try UTF-8 with BOM
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as file:
                return file.read()
        except UnicodeDecodeError:
            pass
        
        # Fallback: Latin-1 (Windows-1252 superset, never raises UnicodeDecodeError)
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                return file.read()
        except Exception as e:
            raise Exception(f"Error reading file: {str(e)}")
    
    @staticmethod
    def get_file_extension(file_path: str) -> str:
        """Get file extension"""
        return file_path.lower().split('.')[-1] if '.' in file_path else ""
    
    @staticmethod
    def is_supported_file(file_path: str) -> bool:
        """Check if file type is supported"""
        ext = PDFImportService.get_file_extension(file_path)
        return ext in ['pdf', 'txt', 'md', 'png', 'jpg', 'jpeg', 'tiff', 'bmp']