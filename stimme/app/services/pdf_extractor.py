import PyPDF2

class PDFExtractor:
    """Service for extracting text from PDF files"""
    
    @staticmethod
    def extract_text(file_path: str) -> str:
        """
        Extract text from PDF file
        
        Args:
            file_path: Path to PDF file
        
        Returns:
            Extracted text
        """
        try:
            text = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text()
            return text
        except Exception as e:
            raise Exception(f"Error extracting PDF: {str(e)}")
    
    @staticmethod
    def extract_text_file(file_path: str) -> str:
        """
        Extract text from .txt or .md file
        
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
