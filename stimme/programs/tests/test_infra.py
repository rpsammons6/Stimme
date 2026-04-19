# test_infra.py
import os
import sys

# Ensure the root directory is in the path so we can import from the 'programs' folder
sys.path.append(os.getcwd())

from ocr_engine import OCREngine
from formatter import get_styled_html  # Using the updated function name
from history_manager import HistoryManager

def test_all():
    print("--- STIMME: Infrastructure Integration Test ---")
    print(f"Working Directory: {os.getcwd()}")

    # 1. TEST OCR ENGINE
    print("\n[1/3] Testing OCR Engine...")
    ocr = OCREngine()
    
    data_dir = "data"
    test_file = None

    # SMART SEARCH: Find any image in the data folder
    if os.path.exists(data_dir):
        files_in_data = os.listdir(data_dir)
        # Look for the first file ending in .png, .jpg, or .jpeg
        images = [f for f in files_in_data if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        if images:
            test_file = os.path.join(data_dir, images[0])
            print(f"Found image: {test_file}")
        else:
            print(f"No images found in {data_dir}. Found these files instead: {files_in_data}")
    else:
        print(f"CRITICAL: The '{data_dir}' folder does not exist at {os.getcwd()}")

    # RUN THE TEST IF A FILE WAS FOUND
    if test_file and os.path.exists(test_file):
        try:
            extracted_text = ocr.process_file(test_file)
            print(f"SUCCESS: Extracted {len(extracted_text)} characters.")
            print(f"Sample: {extracted_text[:70].strip()}...")
        except Exception as e:
            print(f"FAILED OCR: {e}")
    else:
        print("SKIP OCR: No valid test image found.")

    # 2. TEST FORMATTER
    print("\n[2/3] Testing HTML Formatter...")
    mock_trans = "# Scholarly Translation\nThis is a *test* of the 'Stimme' system."
    mock_comm = "## Philological Notes\n- **Register**: Academic\n- **Source**: 19th Century"
    
    try:
        html_result = get_styled_html(mock_trans, mock_comm)
        
        # Save it to the root to check da vibes
        output_path = "test_view.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_result)
        print(f"SUCCESS: HTML generated. Open '{output_path}' in your browser.")
    except Exception as e:
        print(f"FAILED FORMATTER: {e}")

    # 3. TEST HISTORY MANAGER
    print("\n[3/3] Testing History Manager...")
    # HistoryManager now defaults to creating a /history folder in the current directory
    history = HistoryManager()
    try:
        history.save_entry(
            source="Einst warf auch Zarathustra seinen Wahn...",
            translation="Once Zarathustra also cast his fancy...",
            commentary="Initial test for history serialization."
        )
        print(f"SUCCESS: JSON log created in the '{history.history_dir}' folder.")
    except Exception as e:
        print(f"FAILED HISTORY: {e}")

if __name__ == "__main__":
    test_all()