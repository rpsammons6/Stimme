# test_run.py
from brain import TranslationBrain
import time

def run_test():
    print("--- STIMME: Translation Engine Initialization ---")
    brain = TranslationBrain()
    
    # This sentence is designed to trigger your PRIORITY IDIOM table
    test_sentence = "Einst warf auch Zarathustra seinen Wahn jenseits des Menschen, gleich allen Hinterweltlern. Eines leidenden und zerquälten Gottes Werk schien mir da die Welt. Traum schien mir da die Welt und Dichtung eines Gottes; farbiger Rauch vor den Augen eines göttlich Unzufriednen. Gut und böse und Lust und Leid und Ich und Du—farbiger Rauch dünkte mich’s vor schöpferischen Augen. Wegsehn wollte der Schöpfer von sich,—da schuf er die Welt."
    
    print(f"\n[1] INPUT GERMAN: {test_sentence}")
    print("[2] ANALYZING SENTIMENT & CONTEXT...")
    
    start_time = time.time()
    
    # Run the translation
    try:
        translation = brain.translate(test_sentence)
        end_time = time.time()
        
        print(f"\n[3] CLAUDE'S SCHOLARLY OUTPUT (Markdown):\n")
        print("--------------------------------------------------")
        print(translation)
        print("--------------------------------------------------")
        
        print(f"\n[4] METRICS:")
        print(f"Total Time: {round(end_time - start_time, 2)} seconds")
        print("Check your Anthropic Dashboard for Cache Hit status!")

    except Exception as e:
        print(f"\n[ERROR]: {e}")

if __name__ == "__main__":
    run_test()