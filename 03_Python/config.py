"""
config.py
---------
Shared configuration, relative paths and constants for the
Clinical Trial Data Quality & Query Management System.

All other scripts import from here so that paths, seeds and
study-level constants stay consistent across the whole project.
"""

from pathlib import Path
from datetime import date

# ---------------------------------------------------------------
# BASE PATHS (relative — works after copying the project anywhere)
# ---------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # project root
DATA_DIR = BASE_DIR / "01_Data"
RAW_DIR = DATA_DIR / "raw"
CLEANED_DIR = DATA_DIR / "cleaned"
VALIDATION_OUTPUT_DIR = DATA_DIR / "validation_output"
DICTIONARIES_DIR = DATA_DIR / "dictionaries"
EXCEL_DIR = BASE_DIR / "04_Excel"
REPORTS_DIR = BASE_DIR / "09_Reports"
SQL_DIR = BASE_DIR / "02_SQL"

for _d in (RAW_DIR, CLEANED_DIR, VALIDATION_OUTPUT_DIR, DICTIONARIES_DIR,
           EXCEL_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------
# REPRODUCIBILITY
# ---------------------------------------------------------------
RANDOM_SEED = 20260822  # fixed seed -> dataset is fully reproducible

# ---------------------------------------------------------------
# STUDY-LEVEL CONSTANTS
# ---------------------------------------------------------------
N_SUBJECTS = 5000
N_SITES = 25
STUDY_START_DATE = date(2023, 1, 15)          # first site activation
STUDY_DATA_CUTOFF = date(2025, 6, 30)         # snapshot / analysis date
TREATMENT_ARMS = ["Drug A 10mg", "Drug A 20mg", "Placebo"]
COUNTRIES = ["India", "USA", "Germany", "Brazil", "Philippines",
             "South Africa", "Poland", "Mexico"]

VISIT_SCHEDULE = [
    ("Screening", -14, 7),
    ("Baseline", 0, 3),
    ("Week 2", 14, 3),
    ("Week 4", 28, 5),
    ("Week 8", 56, 5),
    ("Week 12", 84, 7),
    ("Week 24", 168, 7),
    ("End of Study", 180, 7),
]  # (visit_name, nominal_day_from_randomization, allowed_window_days)

LAB_TESTS = {
    # test_name: (unit, lower_limit, upper_limit, mean, sd)
    "Hemoglobin":        ("g/dL",   12.0, 17.5, 14.2, 1.4),
    "WBC Count":         ("10^3/uL", 4.0, 11.0,  7.0, 1.6),
    "Platelet Count":    ("10^3/uL", 150, 450,  270, 55),
    "ALT":               ("U/L",     7,  56,   28,  12),
    "AST":               ("U/L",     8,  48,   26,  11),
    "Creatinine":        ("mg/dL",  0.6, 1.3,  0.9, 0.18),
    "Fasting Glucose":   ("mg/dL",  70, 100,   85,   8),
    "Total Cholesterol": ("mg/dL", 125, 200,  162,  20),
}

AE_TERMS = [
    "Headache", "Nausea", "Fatigue", "Dizziness", "Diarrhea",
    "Upper Respiratory Tract Infection", "Back Pain", "Insomnia",
    "Injection Site Reaction", "Hypertension", "Rash", "Vomiting",
    "Myalgia", "Cough", "Abdominal Pain", "Anxiety", "Constipation",
    "Decreased Appetite", "Pyrexia", "Arthralgia",
]

CONMED_NAMES = [
    "Paracetamol", "Ibuprofen", "Omeprazole", "Metformin", "Atorvastatin",
    "Amlodipine", "Cetirizine", "Aspirin", "Levothyroxine", "Metoprolol",
    "Multivitamin", "Vitamin D3", "Loratadine", "Pantoprazole",
]

DEVIATION_TYPES = [
    "Missed Visit Window", "Informed Consent Timing", "Dosing Error",
    "Inclusion/Exclusion Criteria Deviation", "Prohibited Medication Use",
    "Lab Sample Mishandling", "Missed Assessment",
]
