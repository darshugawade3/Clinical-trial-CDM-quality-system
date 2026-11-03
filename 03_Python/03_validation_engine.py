"""
03_validation_engine.py
-------------------------
Runs 27 data-validation rules across 6 categories (Completeness,
Validity, Range Checks, Consistency, Cross-form, Duplicates) against
the cleaned CDM extracts and produces DATA_QUALITY_RESULTS records.

Output: 01_Data/validation_output/data_quality_results.csv
        01_Data/validation_output/validation_rule_catalog.csv
"""

from datetime import date, timedelta

import pandas as pd

from config import CLEANED_DIR, VALIDATION_OUTPUT_DIR, STUDY_DATA_CUTOFF

dq_records = []
dq_counter = 1

RULE_CATALOG = []  # (RULE_ID, RULE_NAME, RULE_CATEGORY, SEVERITY, DESCRIPTION)


def register_rule(rule_id, name, category, severity, description):
    RULE_CATALOG.append({
        "RULE_ID": rule_id, "RULE_NAME": name, "RULE_CATEGORY": category,
        "SEVERITY": severity, "DESCRIPTION": description,
    })


def add_dq(subject_id, site_id, rule_id, rule_name, category, severity,
           description, current_value, expected_value, detected_date=None):
    global dq_counter
    dq_records.append({
        "DQ_ID": f"DQ-{dq_counter:06d}",
        "SUBJECT_ID": subject_id,
        "SITE_ID": site_id,
        "RULE_ID": rule_id,
        "RULE_NAME": rule_name,
        "RULE_CATEGORY": category,
        "SEVERITY": severity,
        "DESCRIPTION": description,
        "CURRENT_VALUE": current_value,
        "EXPECTED_VALUE": expected_value,
        "STATUS": "OPEN",
        "DETECTED_DATE": detected_date or STUDY_DATA_CUTOFF,
    })
    dq_counter += 1


def main():
    subjects = pd.read_csv(CLEANED_DIR / "subjects.csv")
    visits = pd.read_csv(CLEANED_DIR / "visits.csv")
    labs = pd.read_csv(CLEANED_DIR / "lab_results.csv")
    vitals = pd.read_csv(CLEANED_DIR / "vital_signs.csv")
    aes = pd.read_csv(CLEANED_DIR / "adverse_events.csv")
    conmeds = pd.read_csv(CLEANED_DIR / "concomitant_medications.csv")
    deviations = pd.read_csv(CLEANED_DIR / "protocol_deviations.csv")

    site_lookup = subjects.drop_duplicates("SUBJECT_ID").set_index("SUBJECT_ID")["SITE_ID"].to_dict()

    def site_of(subj_id):
        return site_lookup.get(subj_id, "UNKNOWN")

    # ============================================================
    # CATEGORY 1: COMPLETENESS (rules C01-C05)
    # ============================================================
    register_rule("C01", "Missing Required Subject Field", "Completeness", "Major",
                   "A required demographic field is null")
    for col in ["AGE", "SEX", "WEIGHT_KG", "TREATMENT_ARM"]:
        missing = subjects[subjects[col].isna()]
        for _, r in missing.iterrows():
            add_dq(r["SUBJECT_ID"], r["SITE_ID"], "C01", "Missing Required Subject Field",
                   "Completeness", "Major", f"Required field {col} is missing",
                   "NULL", "Non-null value")

    register_rule("C02", "Missing Visit Date on Completed Visit", "Completeness", "Major",
                   "Visit marked Completed but ACTUAL_DATE is null")
    missing_visit_date = visits[(visits["VISIT_STATUS"] == "Completed") & (visits["ACTUAL_DATE"].isna())]
    for _, r in missing_visit_date.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "C02", "Missing Visit Date on Completed Visit",
               "Completeness", "Major", f"{r['VISIT_NAME']} marked Completed with no actual date",
               "NULL", "Valid date")

    register_rule("C03", "Missing Lab Result Value", "Completeness", "Critical",
                   "Lab record present but RESULT_VALUE is null")
    missing_lab = labs[labs["RESULT_VALUE"].isna()]
    for _, r in missing_lab.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "C03", "Missing Lab Result Value",
               "Completeness", "Critical", f"{r['LAB_TEST']} result value missing",
               "NULL", "Numeric result")

    register_rule("C04", "Missing AE End Date (Serious)", "Completeness", "Critical",
                   "Serious AE missing required END_DATE")
    missing_ae_end = aes[(aes["SERIOUSNESS"] == "Serious") & (aes["END_DATE"].isna())]
    for _, r in missing_ae_end.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "C04", "Missing AE End Date (Serious)",
               "Completeness", "Critical", f"Serious AE '{r['AE_TERM']}' missing end date",
               "NULL", "Valid date")

    register_rule("C05", "Missing Protocol Deviation Date", "Completeness", "Major",
                   "Protocol deviation record missing DEVIATION_DATE")
    missing_dev_date = deviations[deviations["DEVIATION_DATE"].isna()]
    for _, r in missing_dev_date.iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "C05", "Missing Protocol Deviation Date",
               "Completeness", "Major", "Deviation date missing", "NULL", "Valid date")

    # ============================================================
    # CATEGORY 2: VALIDITY (rules V01-V04)
    # ============================================================
    register_rule("V01", "Invalid Sex Value", "Validity", "Major",
                   "SEX not in {M, F}")
    invalid_sex = subjects[~subjects["SEX"].isin(["M", "F"]) & subjects["SEX"].notna()]
    for _, r in invalid_sex.iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "V01", "Invalid Sex Value", "Validity", "Major",
               f"SEX = {r['SEX']}", r["SEX"], "M or F")

    register_rule("V02", "Invalid Treatment Arm", "Validity", "Critical",
                   "TREATMENT_ARM not in approved randomization list")
    allowed_arms = {"Drug A 10mg", "Drug A 20mg", "Placebo"}
    invalid_arm = subjects[~subjects["TREATMENT_ARM"].isin(allowed_arms) & subjects["TREATMENT_ARM"].notna()]
    for _, r in invalid_arm.iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "V02", "Invalid Treatment Arm", "Validity", "Critical",
               f"TREATMENT_ARM = {r['TREATMENT_ARM']}", r["TREATMENT_ARM"], "|".join(allowed_arms))

    register_rule("V03", "Invalid Subject Status", "Validity", "Minor",
                   "SUBJECT_STATUS not in approved status list")
    allowed_status = {"Completed", "Ongoing", "Withdrawn", "Discontinued", "Screen Failure"}
    invalid_status = subjects[~subjects["SUBJECT_STATUS"].isin(allowed_status)]
    for _, r in invalid_status.iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "V03", "Invalid Subject Status", "Validity", "Minor",
               f"STATUS = {r['SUBJECT_STATUS']}", r["SUBJECT_STATUS"], "|".join(allowed_status))

    register_rule("V04", "Invalid Abnormal Flag", "Validity", "Minor",
                   "ABNORMAL_FLAG not in {Y, N}")
    invalid_flag = labs[~labs["ABNORMAL_FLAG"].isin(["Y", "N"])]
    for _, r in invalid_flag.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "V04", "Invalid Abnormal Flag",
               "Validity", "Minor", f"FLAG = {r['ABNORMAL_FLAG']}", r["ABNORMAL_FLAG"], "Y or N")

    # ============================================================
    # CATEGORY 3: RANGE CHECKS (rules R01-R07)
    # ============================================================
    register_rule("R01", "Age Out of Plausible Range", "Range Check", "Critical",
                   "AGE not within 18-90 years")
    bad_age = subjects[(subjects["AGE"].notna()) & ((subjects["AGE"] < 18) | (subjects["AGE"] > 90))]
    for _, r in bad_age.iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "R01", "Age Out of Plausible Range", "Range Check",
               "Critical", f"AGE = {r['AGE']}", r["AGE"], "18-90")

    register_rule("R02", "BMI Out of Plausible Range", "Range Check", "Major",
                   "BMI not within 12-60")
    bad_bmi = subjects[(subjects["BMI"].notna()) & ((subjects["BMI"] < 12) | (subjects["BMI"] > 60))]
    for _, r in bad_bmi.iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "R02", "BMI Out of Plausible Range", "Range Check",
               "Major", f"BMI = {r['BMI']}", r["BMI"], "12-60")

    register_rule("R03", "Systolic BP Out of Range", "Range Check", "Major",
                   "SYSTOLIC_BP not within 80-220 mmHg")
    bad_sbp = vitals[(vitals["SYSTOLIC_BP"] < 80) | (vitals["SYSTOLIC_BP"] > 220)]
    for _, r in bad_sbp.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "R03", "Systolic BP Out of Range",
               "Range Check", "Major", f"SBP = {r['SYSTOLIC_BP']}", r["SYSTOLIC_BP"], "80-220")

    register_rule("R04", "Diastolic BP Out of Range", "Range Check", "Major",
                   "DIASTOLIC_BP not within 40-140 mmHg")
    bad_dbp = vitals[(vitals["DIASTOLIC_BP"] < 40) | (vitals["DIASTOLIC_BP"] > 140)]
    for _, r in bad_dbp.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "R04", "Diastolic BP Out of Range",
               "Range Check", "Major", f"DBP = {r['DIASTOLIC_BP']}", r["DIASTOLIC_BP"], "40-140")

    register_rule("R05", "Heart Rate Out of Range", "Range Check", "Major",
                   "HEART_RATE not within 35-180 bpm")
    bad_hr = vitals[(vitals["HEART_RATE"] < 35) | (vitals["HEART_RATE"] > 180)]
    for _, r in bad_hr.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "R05", "Heart Rate Out of Range",
               "Range Check", "Major", f"HR = {r['HEART_RATE']}", r["HEART_RATE"], "35-180")

    register_rule("R06", "Temperature Out of Range", "Range Check", "Minor",
                   "TEMPERATURE not within 34.5-42.0 C")
    bad_temp = vitals[(vitals["TEMPERATURE"] < 34.5) | (vitals["TEMPERATURE"] > 42.0)]
    for _, r in bad_temp.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "R06", "Temperature Out of Range",
               "Range Check", "Minor", f"TEMP = {r['TEMPERATURE']}", r["TEMPERATURE"], "34.5-42.0")

    # NOTE: a result that is mildly outside [LOWER_LIMIT, UPPER_LIMIT] is normal
    # clinical variation (already captured by ABNORMAL_FLAG) and is NOT on its
    # own a data-quality problem. This rule flags results that are so far
    # outside range that they are clinically implausible / likely data errors
    # (beyond 30% past the limit) — these warrant a query, not just medical review.
    register_rule("R07", "Lab Result Implausibly Outside Reference Range", "Range Check", "Major",
                   "RESULT_VALUE more than 30% beyond [LOWER_LIMIT, UPPER_LIMIT] — likely data error")
    labs_valid = labs[labs["RESULT_VALUE"].notna()]
    lower_thresh = labs_valid["LOWER_LIMIT"] * 0.7
    upper_thresh = labs_valid["UPPER_LIMIT"] * 1.3
    bad_lab = labs_valid[(labs_valid["RESULT_VALUE"] < lower_thresh) |
                          (labs_valid["RESULT_VALUE"] > upper_thresh)]
    for _, r in bad_lab.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "R07", "Lab Result Outside Reference Range",
               "Range Check", "Major", f"{r['LAB_TEST']} = {r['RESULT_VALUE']} {r['UNIT']}",
               r["RESULT_VALUE"], f"{r['LOWER_LIMIT']}-{r['UPPER_LIMIT']}")

    # ============================================================
    # CATEGORY 4: CONSISTENCY (rules N01-N04)
    # ============================================================
    register_rule("N01", "Randomization Before Screening", "Consistency", "Critical",
                   "RANDOMIZATION_DATE earlier than SCREENING_DATE")
    subj_dates = subjects.copy()
    subj_dates["SCREENING_DATE"] = pd.to_datetime(subj_dates["SCREENING_DATE"], errors="coerce")
    subj_dates["RANDOMIZATION_DATE"] = pd.to_datetime(subj_dates["RANDOMIZATION_DATE"], errors="coerce")
    bad_seq = subj_dates[subj_dates["RANDOMIZATION_DATE"] < subj_dates["SCREENING_DATE"]]
    for _, r in bad_seq.iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "N01", "Randomization Before Screening",
               "Consistency", "Critical",
               f"RAND={r['RANDOMIZATION_DATE'].date()} SCREEN={r['SCREENING_DATE'].date()}",
               "RAND < SCREEN", "RAND >= SCREEN")

    register_rule("N02", "Visit Outside Protocol Window", "Consistency", "Major",
                   "ACTUAL_DATE deviates from PLANNED_DATE by more than WINDOW_DAYS")
    v = visits.copy()
    v["PLANNED_DATE"] = pd.to_datetime(v["PLANNED_DATE"], errors="coerce")
    v["ACTUAL_DATE"] = pd.to_datetime(v["ACTUAL_DATE"], errors="coerce")
    v = v[v["ACTUAL_DATE"].notna()]
    v["DRIFT"] = (v["ACTUAL_DATE"] - v["PLANNED_DATE"]).dt.days.abs()
    bad_window = v[v["DRIFT"] > v["WINDOW_DAYS"]]
    for _, r in bad_window.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "N02", "Visit Outside Protocol Window",
               "Consistency", "Major", f"{r['VISIT_NAME']} drift = {int(r['DRIFT'])} days",
               int(r["DRIFT"]), f"<= {r['WINDOW_DAYS']} days")

    register_rule("N03", "AE Start Date Before Randomization", "Consistency", "Critical",
                   "AE START_DATE earlier than subject's RANDOMIZATION_DATE")
    ae_check = aes.merge(subjects[["SUBJECT_ID", "RANDOMIZATION_DATE", "SITE_ID"]].drop_duplicates("SUBJECT_ID"),
                          on="SUBJECT_ID", how="left")
    ae_check["START_DATE"] = pd.to_datetime(ae_check["START_DATE"], errors="coerce")
    ae_check["RANDOMIZATION_DATE"] = pd.to_datetime(ae_check["RANDOMIZATION_DATE"], errors="coerce")
    bad_ae_date = ae_check[ae_check["START_DATE"] < ae_check["RANDOMIZATION_DATE"]]
    for _, r in bad_ae_date.iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "N03", "AE Start Date Before Randomization",
               "Consistency", "Critical", f"AE START={r['START_DATE'].date()}",
               "START < RAND_DATE", "START >= RAND_DATE")

    register_rule("N04", "Medication Date Inconsistent with Study Timeline", "Consistency", "Major",
                   "Medication START_DATE falls after the study data cutoff")
    cm = conmeds.copy()
    cm["START_DATE"] = pd.to_datetime(cm["START_DATE"], errors="coerce")
    bad_cm_date = cm[cm["START_DATE"] > pd.Timestamp(STUDY_DATA_CUTOFF)]
    for _, r in bad_cm_date.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "N04",
               "Medication Date Inconsistent with Study Timeline", "Consistency", "Major",
               f"START={r['START_DATE'].date()}", "START > cutoff", "START <= cutoff")

    # ============================================================
    # CATEGORY 5: CROSS-FORM (rules X01-X04)
    # ============================================================
    register_rule("X01", "AE Exists Without Randomization Data", "Cross-form", "Major",
                   "Subject has an AE record but no RANDOMIZATION_DATE")
    unrand_ids = set(subjects[subjects["RANDOMIZATION_DATE"].isna()]["SUBJECT_ID"])
    ae_no_rand = aes[aes["SUBJECT_ID"].isin(unrand_ids)]
    for _, r in ae_no_rand.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "X01", "AE Exists Without Randomization Data",
               "Cross-form", "Major", "AE present, RANDOMIZATION_DATE null", "NULL", "Valid date")

    register_rule("X02", "Medication Exists but Subject Not Randomized", "Cross-form", "Major",
                   "Concomitant medication recorded for an unrandomized subject")
    cm_no_rand = conmeds[conmeds["SUBJECT_ID"].isin(unrand_ids)]
    for _, r in cm_no_rand.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "X02",
               "Medication Exists but Subject Not Randomized", "Cross-form", "Major",
               "Medication present, RANDOMIZATION_DATE null", "NULL", "Valid date")

    register_rule("X03", "Protocol Deviation Without Date (Cross-check)", "Cross-form", "Major",
                   "Deviation record present but DEVIATION_DATE missing (validated against source)")
    dev_no_date = deviations[deviations["DEVIATION_DATE"].isna()]
    for _, r in dev_no_date.drop_duplicates("DEVIATION_ID").iterrows():
        pass  # already captured under C05 — avoid double count; kept in catalog for documentation completeness

    register_rule("X04", "Lab Record Without Corresponding Visit", "Cross-form", "Critical",
                   "LAB_RESULTS.VISIT_ID does not exist in VISITS table")
    valid_visit_ids = set(visits["VISIT_ID"])
    orphan_labs = labs[~labs["VISIT_ID"].isin(valid_visit_ids)]
    for _, r in orphan_labs.iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "X04", "Lab Record Without Corresponding Visit",
               "Cross-form", "Critical", f"VISIT_ID={r['VISIT_ID']}", r["VISIT_ID"], "Existing VISIT_ID")

    # ============================================================
    # CATEGORY 6: DUPLICATE CHECKS (rules D01-D04)
    # ============================================================
    register_rule("D01", "Duplicate Subject Record", "Duplicate", "Critical",
                   "SUBJECT_ID appears more than once in SUBJECTS")
    dup_subjects = subjects[subjects.duplicated("SUBJECT_ID", keep=False)]
    for _, r in dup_subjects.drop_duplicates("SUBJECT_ID").iterrows():
        add_dq(r["SUBJECT_ID"], r["SITE_ID"], "D01", "Duplicate Subject Record", "Duplicate",
               "Critical", "SUBJECT_ID duplicated", "2+", "1")

    register_rule("D02", "Duplicate Lab Record", "Duplicate", "Major",
                   "Identical SUBJECT_ID+VISIT_ID+LAB_TEST+RESULT_VALUE appears more than once")
    dup_labs = labs[labs.duplicated(["SUBJECT_ID", "VISIT_ID", "LAB_TEST", "RESULT_VALUE"], keep=False)]
    for _, r in dup_labs.drop_duplicates(["SUBJECT_ID", "VISIT_ID", "LAB_TEST", "RESULT_VALUE"]).iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "D02", "Duplicate Lab Record", "Duplicate",
               "Major", f"{r['LAB_TEST']} duplicated for same visit", "2+", "1")

    register_rule("D03", "Duplicate AE Record", "Duplicate", "Minor",
                   "Identical SUBJECT_ID+AE_TERM+START_DATE appears more than once")
    dup_ae = aes[aes.duplicated(["SUBJECT_ID", "AE_TERM", "START_DATE"], keep=False)]
    for _, r in dup_ae.drop_duplicates(["SUBJECT_ID", "AE_TERM", "START_DATE"]).iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "D03", "Duplicate AE Record", "Duplicate",
               "Minor", f"{r['AE_TERM']} duplicated", "2+", "1")

    register_rule("D04", "Duplicate Visit Record", "Duplicate", "Minor",
                   "Identical SUBJECT_ID+VISIT_NAME appears more than once")
    dup_visits = visits[visits.duplicated(["SUBJECT_ID", "VISIT_NAME"], keep=False)]
    for _, r in dup_visits.drop_duplicates(["SUBJECT_ID", "VISIT_NAME"]).iterrows():
        add_dq(r["SUBJECT_ID"], site_of(r["SUBJECT_ID"]), "D04", "Duplicate Visit Record", "Duplicate",
               "Minor", f"{r['VISIT_NAME']} duplicated", "2+", "1")

    # ============================================================
    # WRITE OUTPUT
    # ============================================================
    dq_df = pd.DataFrame(dq_records)
    dq_df.to_csv(VALIDATION_OUTPUT_DIR / "data_quality_results.csv", index=False)

    catalog_df = pd.DataFrame(RULE_CATALOG)
    catalog_df.to_csv(VALIDATION_OUTPUT_DIR / "validation_rule_catalog.csv", index=False)

    print(f"[Validation Engine] {len(catalog_df)} rules registered across "
          f"{catalog_df['RULE_CATEGORY'].nunique()} categories")
    print(f"[Validation Engine] {len(dq_df)} data quality issues detected")
    print(dq_df.groupby("SEVERITY").size().to_string() if len(dq_df) else "No issues found")
    print("[Validation Engine] Output written to 01_Data/validation_output/")


if __name__ == "__main__":
    main()
