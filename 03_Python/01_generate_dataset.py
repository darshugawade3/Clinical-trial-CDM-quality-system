"""
01_generate_dataset.py
-----------------------
Generates a fully synthetic, de-identified clinical-trial dataset
for the Clinical Trial Data Quality & Query Management System.

IMPORTANT: This dataset is 100% synthetically generated using
realistic clinical-trial distributions. It does NOT contain any
real patient, hospital, or investigator information. It is built
solely for educational / portfolio purposes.

Output (written to 01_Data/raw/):
    subjects.csv
    sites.csv
    visits.csv
    lab_results.csv
    vital_signs.csv
    adverse_events.csv
    concomitant_medications.csv
    protocol_deviations.csv
    error_injection_log.csv   <- exact log of every intentional error injected
"""

import random
from datetime import timedelta

import numpy as np
import pandas as pd

from config import (
    RANDOM_SEED, N_SUBJECTS, N_SITES, STUDY_START_DATE, STUDY_DATA_CUTOFF,
    TREATMENT_ARMS, COUNTRIES, VISIT_SCHEDULE, LAB_TESTS, AE_TERMS,
    CONMED_NAMES, DEVIATION_TYPES, RAW_DIR,
)

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

error_log = []  # every intentionally injected error is appended here


def log_error(table, record_id, error_type, description):
    error_log.append({
        "TABLE": table,
        "RECORD_ID": record_id,
        "ERROR_TYPE": error_type,
        "DESCRIPTION": description,
    })


# =================================================================
# 1. SITES
# =================================================================
def generate_sites():
    rows = []
    for i in range(1, N_SITES + 1):
        site_id = f"SITE-{i:03d}"
        activation_date = STUDY_START_DATE + timedelta(days=int(np.random.randint(0, 90)))
        rows.append({
            "SITE_ID": site_id,
            "SITE_NAME": f"Research Center {i}",
            "COUNTRY": random.choice(COUNTRIES),
            "INVESTIGATOR_ID": f"INV-{i:03d}",
            "SITE_STATUS": np.random.choice(
                ["Active", "Active", "Active", "Closed"], p=[0.6, 0.2, 0.15, 0.05]
            ),
            "ACTIVATION_DATE": activation_date,
        })
    return pd.DataFrame(rows)


# =================================================================
# 2. SUBJECTS
# =================================================================
def generate_subjects(sites_df):
    rows = []
    site_ids = sites_df["SITE_ID"].tolist()
    # weight enrollment unevenly across sites (realistic — some sites recruit faster)
    site_weights = np.random.dirichlet(np.ones(len(site_ids)) * 2)

    duplicate_target = random.sample(range(1, N_SUBJECTS + 1), k=8)  # error type 4
    impossible_age_target = random.sample(range(1, N_SUBJECTS + 1), k=15)  # error type 7
    invalid_treatment_target = random.sample(range(1, N_SUBJECTS + 1), k=6)  # error type 11
    missing_required_target = random.sample(range(1, N_SUBJECTS + 1), k=40)  # error type 1
    rand_before_screen_target = random.sample(range(1, N_SUBJECTS + 1), k=10)

    for i in range(1, N_SUBJECTS + 1):
        subject_id = f"SUBJ-{i:05d}"
        site_id = np.random.choice(site_ids, p=site_weights)

        screening_date = STUDY_START_DATE + timedelta(days=int(np.random.randint(30, 850)))
        randomization_date = screening_date + timedelta(days=int(np.random.randint(3, 21)))

        if i in rand_before_screen_target:
            randomization_date = screening_date - timedelta(days=int(np.random.randint(1, 5)))
            log_error("SUBJECTS", subject_id, "Error Type: Consistency",
                      "Randomization date recorded before screening date")

        age = int(np.clip(np.random.normal(52, 14), 18, 85))
        if i in impossible_age_target:
            age = random.choice([3, 7, 129, 145, -5])
            log_error("SUBJECTS", subject_id, "Error Type 7: Impossible Age",
                      f"Age recorded as {age}, outside plausible human range")

        sex = np.random.choice(["M", "F"], p=[0.48, 0.52])
        height_cm = round(np.random.normal(165 if sex == "F" else 175, 8), 1)
        weight_kg = round(np.random.normal(68 if sex == "F" else 78, 13), 1)
        bmi = round(weight_kg / ((height_cm / 100) ** 2), 1)

        treatment_arm = random.choice(TREATMENT_ARMS)
        if i in invalid_treatment_target:
            treatment_arm = "Drug A 999mg"  # error type 11
            log_error("SUBJECTS", subject_id, "Error Type 11: Invalid Treatment Assignment",
                      "Treatment arm value not in approved randomization list")

        subject_status = np.random.choice(
            ["Completed", "Ongoing", "Withdrawn", "Discontinued", "Screen Failure"],
            p=[0.55, 0.20, 0.10, 0.08, 0.07],
        )

        record = {
            "SUBJECT_ID": subject_id,
            "SITE_ID": site_id,
            "SCREENING_DATE": screening_date,
            "RANDOMIZATION_DATE": randomization_date,
            "AGE": age,
            "SEX": sex,
            "HEIGHT_CM": height_cm,
            "WEIGHT_KG": weight_kg,
            "BMI": bmi,
            "TREATMENT_ARM": treatment_arm,
            "SUBJECT_STATUS": subject_status,
        }

        if i in missing_required_target:
            field = random.choice(["AGE", "SEX", "WEIGHT_KG", "TREATMENT_ARM"])
            record[field] = None
            log_error("SUBJECTS", subject_id, "Error Type 1: Missing Required Value",
                      f"Required field {field} left null")

        rows.append(record)

    df = pd.DataFrame(rows)

    # inject duplicate subject rows (error type 4)
    dup_rows = df[df["SUBJECT_ID"].isin([f"SUBJ-{i:05d}" for i in duplicate_target])].copy()
    for _, r in dup_rows.iterrows():
        log_error("SUBJECTS", r["SUBJECT_ID"], "Error Type 4: Duplicate Subject",
                  "Subject record duplicated in source data")
    df = pd.concat([df, dup_rows], ignore_index=True)

    return df


# =================================================================
# 3. VISITS
# =================================================================
def generate_visits(subjects_df):
    rows = []
    visit_id_counter = 1
    outside_window_target = set(random.sample(range(1, N_SUBJECTS + 1), k=60))

    for _, subj in subjects_df.drop_duplicates("SUBJECT_ID").iterrows():
        rand_date = subj["RANDOMIZATION_DATE"]
        if pd.isna(rand_date):
            continue
        subj_num = int(subj["SUBJECT_ID"].split("-")[1])

        for visit_name, nominal_day, window in VISIT_SCHEDULE:
            planned_date = rand_date + timedelta(days=nominal_day)
            if planned_date > STUDY_DATA_CUTOFF:
                continue  # visit hasn't occurred yet in this snapshot

            drift = int(np.random.normal(0, window / 2))
            actual_date = planned_date + timedelta(days=drift)

            visit_status = np.random.choice(
                ["Completed", "Completed", "Missed", "Rescheduled"], p=[0.82, 0.10, 0.05, 0.03]
            )

            if subj_num in outside_window_target and visit_name in ("Week 4", "Week 8"):
                actual_date = planned_date + timedelta(days=window + random.randint(5, 20))
                log_error("VISITS", f"{subj['SUBJECT_ID']}-{visit_name}",
                          "Error Type 3: Visit Outside Allowed Window",
                          f"Actual visit date exceeds +/-{window} day protocol window")

            rows.append({
                "VISIT_ID": f"VIS-{visit_id_counter:06d}",
                "SUBJECT_ID": subj["SUBJECT_ID"],
                "VISIT_NAME": visit_name,
                "PLANNED_DATE": planned_date,
                "ACTUAL_DATE": actual_date if visit_status != "Missed" else None,
                "VISIT_STATUS": visit_status,
                "WINDOW_DAYS": window,
            })
            visit_id_counter += 1

    return pd.DataFrame(rows)


# =================================================================
# 4. LAB RESULTS
# =================================================================
def generate_lab_results(visits_df):
    rows = []
    lab_id_counter = 1
    out_of_range_target = set(random.sample(range(len(visits_df)), k=min(150, len(visits_df))))

    completed_visits = visits_df[visits_df["VISIT_STATUS"] == "Completed"].reset_index(drop=True)

    for idx, visit in completed_visits.iterrows():
        n_tests = random.randint(4, len(LAB_TESTS))
        chosen_tests = random.sample(list(LAB_TESTS.items()), k=n_tests)
        for test_name, (unit, low, high, mean, sd) in chosen_tests:
            value = round(np.random.normal(mean, sd), 2)

            if idx in out_of_range_target:
                value = round(high * random.uniform(1.3, 2.0), 2)
                log_error("LAB_RESULTS", f"{visit['SUBJECT_ID']}-{test_name}",
                          "Error Type 6: Lab Result Outside Reference Range",
                          f"{test_name} recorded far outside [{low}, {high}] {unit}")

            abnormal_flag = "Y" if (value < low or value > high) else "N"
            collection_date = visit["ACTUAL_DATE"]

            rows.append({
                "LAB_ID": f"LAB-{lab_id_counter:07d}",
                "SUBJECT_ID": visit["SUBJECT_ID"],
                "VISIT_ID": visit["VISIT_ID"],
                "LAB_TEST": test_name,
                "RESULT_VALUE": value,
                "UNIT": unit,
                "LOWER_LIMIT": low,
                "UPPER_LIMIT": high,
                "ABNORMAL_FLAG": abnormal_flag,
                "COLLECTION_DATE": collection_date,
            })
            lab_id_counter += 1

    df = pd.DataFrame(rows)

    # duplicate lab records (error type: duplicate)
    dup_sample = df.sample(n=min(25, len(df)), random_state=RANDOM_SEED)
    for _, r in dup_sample.iterrows():
        log_error("LAB_RESULTS", r["LAB_ID"], "Duplicate Check: Duplicate Lab Record",
                  "Lab result duplicated in source extract")
    df = pd.concat([df, dup_sample], ignore_index=True)

    return df


# =================================================================
# 5. VITAL SIGNS
# =================================================================
def generate_vital_signs(visits_df):
    rows = []
    vital_id_counter = 1
    completed_visits = visits_df[visits_df["VISIT_STATUS"] == "Completed"]

    for _, visit in completed_visits.iterrows():
        systolic = int(np.clip(np.random.normal(124, 14), 85, 210))
        diastolic = int(np.clip(np.random.normal(79, 9), 50, 130))
        heart_rate = int(np.clip(np.random.normal(74, 10), 40, 160))
        temperature = round(np.random.normal(36.8, 0.4), 1)
        weight = round(np.random.normal(74, 14), 1)

        rows.append({
            "VITAL_ID": f"VIT-{vital_id_counter:07d}",
            "SUBJECT_ID": visit["SUBJECT_ID"],
            "VISIT_ID": visit["VISIT_ID"],
            "SYSTOLIC_BP": systolic,
            "DIASTOLIC_BP": diastolic,
            "HEART_RATE": heart_rate,
            "TEMPERATURE": temperature,
            "WEIGHT": weight,
            "MEASUREMENT_DATE": visit["ACTUAL_DATE"],
        })
        vital_id_counter += 1

    return pd.DataFrame(rows)


# =================================================================
# 6. ADVERSE EVENTS
# =================================================================
def generate_adverse_events(subjects_df):
    rows = []
    ae_id_counter = 1
    unique_subjects = subjects_df.drop_duplicates("SUBJECT_ID")
    ae_subjects = unique_subjects.sample(frac=0.55, random_state=RANDOM_SEED)

    missing_end_date_target = set(random.sample(range(len(ae_subjects) * 2), k=20))
    ae_before_rand_target = set(random.sample(range(len(ae_subjects) * 2), k=12))
    running_idx = 0

    for _, subj in ae_subjects.iterrows():
        n_aes = np.random.choice([1, 2, 3], p=[0.6, 0.3, 0.1])
        rand_date = subj["RANDOMIZATION_DATE"]
        for _ in range(n_aes):
            if pd.isna(rand_date):
                continue
            start_date = rand_date + timedelta(days=int(np.random.randint(1, 150)))
            severity = np.random.choice(["Mild", "Moderate", "Severe"], p=[0.6, 0.3, 0.1])
            seriousness = np.random.choice(["Non-serious", "Serious"], p=[0.93, 0.07])
            duration = int(np.random.randint(1, 21))
            end_date = start_date + timedelta(days=duration)

            if running_idx in ae_before_rand_target:
                start_date = rand_date - timedelta(days=random.randint(1, 10))
                log_error("ADVERSE_EVENTS", f"AE-{ae_id_counter:06d}",
                          "Error Type 5: AE Date Before Randomization",
                          "Adverse event start date precedes subject randomization date")

            record = {
                "AE_ID": f"AE-{ae_id_counter:06d}",
                "SUBJECT_ID": subj["SUBJECT_ID"],
                "AE_TERM": random.choice(AE_TERMS),
                "START_DATE": start_date,
                "END_DATE": end_date,
                "SEVERITY": severity,
                "SERIOUSNESS": seriousness,
                "ACTION_TAKEN": np.random.choice(
                    ["None", "Dose Reduced", "Drug Interrupted", "Drug Withdrawn"],
                    p=[0.6, 0.2, 0.15, 0.05],
                ),
                "OUTCOME": np.random.choice(
                    ["Recovered", "Recovering", "Not Recovered", "Recovered with Sequelae"],
                    p=[0.7, 0.15, 0.1, 0.05],
                ),
                "RELATED_TO_STUDY_DRUG": np.random.choice(
                    ["Not Related", "Unlikely", "Possible", "Probable", "Definite"],
                    p=[0.35, 0.25, 0.2, 0.15, 0.05],
                ),
            }

            if running_idx in missing_end_date_target and seriousness == "Serious":
                record["END_DATE"] = None
                log_error("ADVERSE_EVENTS", record["AE_ID"],
                          "Error Type 8: Missing AE End Date",
                          "Serious AE missing required end date")

            rows.append(record)
            ae_id_counter += 1
            running_idx += 1

    return pd.DataFrame(rows)


# =================================================================
# 7. CONCOMITANT MEDICATIONS
# =================================================================
def generate_conmeds(subjects_df):
    rows = []
    med_id_counter = 1
    unique_subjects = subjects_df.drop_duplicates("SUBJECT_ID")
    conmed_subjects = unique_subjects.sample(frac=0.4, random_state=RANDOM_SEED + 1)

    inconsistent_target = set(random.sample(range(len(conmed_subjects)), k=15))

    for pos, (_, subj) in enumerate(conmed_subjects.iterrows()):
        rand_date = subj["RANDOMIZATION_DATE"]
        if pd.isna(rand_date):
            continue
        n_meds = np.random.choice([1, 2, 3], p=[0.5, 0.35, 0.15])
        for _ in range(n_meds):
            start_date = rand_date - timedelta(days=int(np.random.randint(0, 60)))
            duration = int(np.random.randint(5, 120))
            end_date = start_date + timedelta(days=duration)

            if pos in inconsistent_target:
                start_date = STUDY_DATA_CUTOFF + timedelta(days=random.randint(30, 90))
                log_error("CONCOMITANT_MEDICATIONS", f"MED-{med_id_counter:06d}",
                          "Error Type 9: Medication Date Inconsistent with Study Timeline",
                          "Medication start date recorded after study data cutoff")

            rows.append({
                "MEDICATION_ID": f"MED-{med_id_counter:06d}",
                "SUBJECT_ID": subj["SUBJECT_ID"],
                "MEDICATION_NAME": random.choice(CONMED_NAMES),
                "START_DATE": start_date,
                "END_DATE": end_date,
                "DOSE": f"{random.choice([5, 10, 20, 25, 50, 100])} mg",
                "ROUTE": np.random.choice(["Oral", "Topical", "Intravenous"], p=[0.85, 0.1, 0.05]),
                "FREQUENCY": random.choice(["Once Daily", "Twice Daily", "As Needed", "Three Times Daily"]),
            })
            med_id_counter += 1

    df = pd.DataFrame(rows)

    # medication exists but subject not randomized -> cross-form error
    unrandomized = unique_subjects[unique_subjects["RANDOMIZATION_DATE"].isna()]
    if len(unrandomized) > 0:
        for _, subj in unrandomized.sample(n=min(5, len(unrandomized)), random_state=RANDOM_SEED).iterrows():
            new_id = f"MED-{med_id_counter:06d}"
            df = pd.concat([df, pd.DataFrame([{
                "MEDICATION_ID": new_id,
                "SUBJECT_ID": subj["SUBJECT_ID"],
                "MEDICATION_NAME": random.choice(CONMED_NAMES),
                "START_DATE": STUDY_START_DATE,
                "END_DATE": STUDY_START_DATE + timedelta(days=30),
                "DOSE": "10 mg",
                "ROUTE": "Oral",
                "FREQUENCY": "Once Daily",
            }])], ignore_index=True)
            log_error("CONCOMITANT_MEDICATIONS", new_id,
                      "Cross-form Check: Medication Without Randomization",
                      "Concomitant medication recorded for a subject with no randomization date")
            med_id_counter += 1

    return df


# =================================================================
# 8. PROTOCOL DEVIATIONS
# =================================================================
def generate_protocol_deviations(subjects_df):
    rows = []
    dev_id_counter = 1
    unique_subjects = subjects_df.drop_duplicates("SUBJECT_ID")
    dev_subjects = unique_subjects.sample(frac=0.08, random_state=RANDOM_SEED + 2)

    missing_date_target = set(random.sample(range(len(dev_subjects)), k=8))

    for pos, (_, subj) in enumerate(dev_subjects.iterrows()):
        rand_date = subj["RANDOMIZATION_DATE"]
        deviation_date = (rand_date if not pd.isna(rand_date) else STUDY_START_DATE) + \
            timedelta(days=int(np.random.randint(1, 200)))

        record = {
            "DEVIATION_ID": f"DEV-{dev_id_counter:05d}",
            "SUBJECT_ID": subj["SUBJECT_ID"],
            "SITE_ID": subj["SITE_ID"],
            "DEVIATION_TYPE": random.choice(DEVIATION_TYPES),
            "DEVIATION_DATE": deviation_date,
            "SEVERITY": np.random.choice(["Minor", "Major", "Critical"], p=[0.65, 0.28, 0.07]),
            "DESCRIPTION": "Deviation identified during routine monitoring visit review.",
            "STATUS": np.random.choice(["Open", "Under Review", "Closed"], p=[0.25, 0.15, 0.6]),
        }

        if pos in missing_date_target:
            record["DEVIATION_DATE"] = None
            log_error("PROTOCOL_DEVIATIONS", record["DEVIATION_ID"],
                      "Cross-form Check: Protocol Deviation Without Date",
                      "Protocol deviation record missing required deviation date")

        rows.append(record)
        dev_id_counter += 1

    return pd.DataFrame(rows)


# =================================================================
# MAIN
# =================================================================
def main():
    print("[Data Generator] Generating SITES...")
    sites_df = generate_sites()

    print("[Data Generator] Generating SUBJECTS...")
    subjects_df = generate_subjects(sites_df)

    print("[Data Generator] Generating VISITS...")
    visits_df = generate_visits(subjects_df)

    print("[Data Generator] Generating LAB_RESULTS...")
    lab_df = generate_lab_results(visits_df)

    print("[Data Generator] Generating VITAL_SIGNS...")
    vitals_df = generate_vital_signs(visits_df)

    print("[Data Generator] Generating ADVERSE_EVENTS...")
    ae_df = generate_adverse_events(subjects_df)

    print("[Data Generator] Generating CONCOMITANT_MEDICATIONS...")
    conmed_df = generate_conmeds(subjects_df)

    print("[Data Generator] Generating PROTOCOL_DEVIATIONS...")
    deviation_df = generate_protocol_deviations(subjects_df)

    # write outputs
    sites_df.to_csv(RAW_DIR / "sites.csv", index=False)
    subjects_df.to_csv(RAW_DIR / "subjects.csv", index=False)
    visits_df.to_csv(RAW_DIR / "visits.csv", index=False)
    lab_df.to_csv(RAW_DIR / "lab_results.csv", index=False)
    vitals_df.to_csv(RAW_DIR / "vital_signs.csv", index=False)
    ae_df.to_csv(RAW_DIR / "adverse_events.csv", index=False)
    conmed_df.to_csv(RAW_DIR / "concomitant_medications.csv", index=False)
    deviation_df.to_csv(RAW_DIR / "protocol_deviations.csv", index=False)

    error_df = pd.DataFrame(error_log)
    error_df.to_csv(RAW_DIR / "error_injection_log.csv", index=False)

    print("\n=== DATASET GENERATION SUMMARY ===")
    print(f"Sites:                      {len(sites_df)}")
    print(f"Subjects (incl. duplicates):{len(subjects_df)}")
    print(f"Visits:                     {len(visits_df)}")
    print(f"Lab Results:                {len(lab_df)}")
    print(f"Vital Signs:                {len(vitals_df)}")
    print(f"Adverse Events:             {len(ae_df)}")
    print(f"Concomitant Medications:    {len(conmed_df)}")
    print(f"Protocol Deviations:        {len(deviation_df)}")
    print(f"Intentional Errors Injected:{len(error_df)}")
    print("===================================\n")
    print("All files written to 01_Data/raw/")


if __name__ == "__main__":
    main()
