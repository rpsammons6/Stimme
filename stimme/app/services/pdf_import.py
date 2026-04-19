import PyPDF2
import sys
import os
from pathlib import Path
from typing import Optional

# Add the programs directory to the path so we can import OCR engine
sys.path.append(str(Path(__file__).parent.parent.parent / "programs"))

class PDFImportService:
    """Service for importing and extracting text from files"""
    
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
                print(f" PDF_IMPORT: PDF reader created, pages: {len(pdf_reader.pages)}")  # Debug
                
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
            print(f" PDF_IMPORT: Exception during extraction: {e}")  # Debug
            
            # If digital extraction completely failed, try OCR as last resort
            if use_ocr:
                print(" PDF_IMPORT: Digital extraction failed, trying OCR as fallback...")
                if progress_callback:
                    progress_callback("Digital extraction failed, starting OCR...", 35)
                try:
                    return PDFImportService._extract_with_ocr(file_path, progress_callback, cancel_callback)
                except Exception as ocr_e:
                    print(f" PDF_IMPORT: OCR also failed: {ocr_e}")
                    raise Exception(f"Both digital extraction and OCR failed. Digital: {str(e)}, OCR: {str(ocr_e)}")
            else:
                raise Exception(f"Error extracting PDF: {str(e)}")
    
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
        Read text from .txt or .md file
        
        Args:
            file_path: Path to text file
        
        Returns:
            File contents
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
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