import pandas as pd

# 1. Load the Excel (make sure you have 'openpyxl' installed: pip install openpyxl)
file_path = "English_Idioms_Database_Website2017.xlsx"
df = pd.read_excel(file_path)

# 2. Rename the columns based on your screenshot's structure
# Note: Check your Excel file to see which column indices match!
# Based on the image, it looks like:
# Col B: English Idiom
# Col C: Meaning
# Col D: German Idiom
# Col E: Literal Translation

print(f"beginning cleaning!")

print(df.head())

# We will create a clean version with just the essentials
clean_df = pd.DataFrame()
clean_df['idiom_id'] = df.iloc[:, 0]
clean_df['german'] = df.iloc[:, 3]   # The 'ein Fisch auf dem Trockenen' column
clean_df['english'] = df.iloc[:, 1]  # The 'a fish out of water' column
clean_df['meaning'] = df.iloc[:, 2]  # The 'awkward because...' column
clean_df['literal'] = df.iloc[:, 4]  # The 'a fish on the dry' column

#false friends are important for the AI to watch out for
clean_df['false_friends'] = df.iloc[:, 7]

#SEMs
clean_df['familiarity'] = df.iloc[:, 14]
clean_df['meaningfulness'] = df.iloc[:, 12]

# 3. Basic Cleaning
# Remove any rows where German or English is missing
clean_df = clean_df.dropna(subset=['german', 'english'])

# Remove leading/trailing whitespace
clean_df = clean_df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

# 4. Save to your project's data folder
clean_df.to_csv("data/priority_idioms.csv", index=False)

print(f"Cleaned {len(clean_df)} idioms. Saved to data/priority_idioms.csv")