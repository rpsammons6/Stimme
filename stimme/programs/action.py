# test_run.py
import os
import time
from brain import TranslationBrain
from programs.formatter import get_styled_html
from programs.history_manager import HistoryManager

def main():
    # --- 1. CONFIGURATION ---
    COMMENTARY_MODE = True  # Toggle this to False for "Clean Translation Only"
    INPUT_PATH = os.path.join("data", "input_source.txt")
    OUTPUT_HTML = "latest_result.html"
    
    # --- 2. INITIALIZATION ---
    print("Initializing Stimme Engine...")
    brain = TranslationBrain()
    history = HistoryManager()
    
    # Read the source text from the file
    if not os.path.exists(INPUT_PATH):
        print(f"ERROR: Input file '{INPUT_PATH}' not found.")
        print("Please create the file with your German text.")
        return
    
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        source_text = f.read().strip()
    
    if not source_text:
        print("ERROR: Input file is empty.")
        return
    
    print(f"Source text loaded: {len(source_text)} characters")
    
    # --- 3. TRANSLATION ---
    print("Starting translation...")
    start_time = time.time()
    
    try:
        translation, commentary, metrics = brain.translate(
            text=source_text,
            model_id="claude-sonnet-4-6",  # You can change this
            user_instructions="",  # Add any specific instructions
            provide_commentary=COMMENTARY_MODE
        )
        
        end_time = time.time()
        print(f"Translation completed in {end_time - start_time:.2f} seconds")
        
        # A. Save to History
        history.save_entry(source_text, translation, commentary, metrics)
        
        # Handle commentary
        commentary_text = None
        if COMMENTARY_MODE:
            # We'll just grab a mock string for the formatter if the brain 
            # hasn't returned the full JSON yet, or update brain to return both.
            # For now, let's assume brain returns the clean translation.
            commentary_text = commentary

        # B. Generate the Styled HTML
        html_content = get_styled_html(translation, commentary_text)
        with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        print(f"✅ SUCCESS!")
        print(f"📄 Translation saved to: {OUTPUT_HTML}")
        print(f"📊 Metrics: {metrics}")
        
        # C. Display Results
        print("\n" + "="*50)
        print("TRANSLATION RESULT:")
        print("="*50)
        print(translation)
        
        if commentary_text:
            print("\n" + "="*50)
            print("COMMENTARY:")
            print("="*50)
            print(commentary_text)
        
    except Exception as e:
        print(f"❌ Translation failed: {str(e)}")

if __name__ == "__main__":
    main()