import pandas as pd
import lancedb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# Load the embedding model (This stays local on your machine)
model = SentenceTransformer('intfloat/multilingual-e5-small')
db = lancedb.connect("./lancedb_vectors")

def build_idiom_table():
    print("Building Idiom Table...")
    # Load with low_memory=False to prevent type-guessing issues
    df = pd.read_csv("data/idioms_dict.csv", low_memory=False)
    df.columns = df.columns.str.strip()

    data = []
    for _, row in tqdm(df.iterrows(), total=len(df)):
        # 1. Encode the German text
        # We use str() here to make sure even if the cell is empty/numeric, it doesn't crash
        german_text = str(row['Matching German Idiom']) if pd.notna(row['Matching German Idiom']) else ""
        vector = model.encode(german_text)
        
        # 2. Construct the row, explicitly casting everything to string
        # This tells PyArrow: "Don't guess, these are all TEXT."
        data.append({
            "vector": vector, # This remains a list of floats (must be)
            "german": german_text,
            "english": str(row['Idiom']) if pd.notna(row['Idiom']) else "",
            "meaning": str(row['Meaning(s)']) if pd.notna(row['Meaning(s)']) else "",
            "literal": str(row['Literal Translation of Matching German Idiom']) if pd.notna(row['Literal Translation of Matching German Idiom']) else "",
            "familiarity_sem": str(row['Unnamed: 10']) if pd.notna(row['Unnamed: 10']) else "0",
            "notes": str(row['False Friends/Other Notes']) if pd.notna(row['False Friends/Other Notes']) else ""
        })
        
    db.create_table("idioms", data=data, mode="overwrite")
    print("Idiom table complete!")
    
    # Create ANN index for fast vector search
    try:
        table = db.open_table("idioms")
        table.create_index(num_partitions=256, num_sub_vectors=96)
        print("✅ ANN index created for idioms table")
    except Exception as e:
        print(f"⚠️  Could not create ANN index for idioms: {e}")


def build_corpus_table_sample():
    print("Building Corpus Table (Sample for testing)...")
    # USE YOUR JUNK 5M CSV HERE
    df = pd.read_csv("data/processed_corpus.csv")
    data = []
    for _, row in tqdm(df.iterrows(), total=len(df)):
        vector = model.encode(str(row['de']))
        data.append({
            "vector": vector,
            "de": str(row['de']),
            "en": str(row['en']),
            "sentiment": str(row['sentiment'])
        })
    db.create_table("corpus", data=data, mode="overwrite")
    
    # Create ANN index for fast vector search
    try:
        table = db.open_table("corpus")
        table.create_index(num_partitions=256, num_sub_vectors=96)
        print("✅ ANN index created for corpus table")
    except Exception as e:
        print(f"⚠️  Could not create ANN index for corpus: {e}")

if __name__ == "__main__":
    build_idiom_table()
    build_corpus_table_sample()