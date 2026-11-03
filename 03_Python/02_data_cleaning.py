"""
02_data_cleaning.py
--------------------
Loads raw CDM extracts, standardizes data types/formats, and writes
cleaned versions to 01_Data/cleaned/. This step does NOT remove or
"fix" data-quality problems — those are intentionally preserved so
the validation engine (03_validation_engine.py) has real issues to
detect. Cleaning here means: consistent date parsing, consistent
dtypes, whitespace trimming, consistent ID formatting.
"""

import pandas as pd
from config import RAW_DIR, CLEANED_DIR

DATE_COLUMNS = {
    "subjects.csv": ["SCREENING_DATE", "RANDOMIZATION_DATE"],
    "sites.csv": ["ACTIVATION_DATE"],
    "visits.csv": ["PLANNED_DATE", "ACTUAL_DATE"],
    "lab_results.csv": ["COLLECTION_DATE"],
    "vital_signs.csv": ["MEASUREMENT_DATE"],
    "adverse_events.csv": ["START_DATE", "END_DATE"],
    "concomitant_medications.csv": ["START_DATE", "END_DATE"],
    "protocol_deviations.csv": ["DEVIATION_DATE"],
}


def clean_file(filename):
    df = pd.read_csv(RAW_DIR / filename)

    # trim whitespace on all string/object columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})

    # parse dates consistently (invalid parsing kept as NaT, not silently dropped)
    for col in DATE_COLUMNS.get(filename, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    return df


def main():
    files = [
        "sites.csv", "subjects.csv", "visits.csv", "lab_results.csv",
        "vital_signs.csv", "adverse_events.csv",
        "concomitant_medications.csv", "protocol_deviations.csv",
    ]

    print("[Data Cleaning] Standardizing data types and formats...")
    for f in files:
        cleaned = clean_file(f)
        cleaned.to_csv(CLEANED_DIR / f, index=False)
        print(f"  -> {f}: {len(cleaned)} rows cleaned")

    print("[Data Cleaning] Complete. Cleaned files written to 01_Data/cleaned/")


if __name__ == "__main__":
    main()
