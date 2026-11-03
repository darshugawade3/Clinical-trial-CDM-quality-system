"""
04_query_engine.py
--------------------
Converts DATA_QUALITY_RESULTS into a realistic query lifecycle:

    Data Issue Detected -> Query Generated -> Query Assigned ->
    Site Response -> CDM Review -> Resolved/Rejected/Reopened -> Closed

Assigns QUERY_TYPE, PRIORITY, and simulates a realistic distribution
of query ages/statuses as of the study data cutoff, then computes
query-aging classification.

Output: 01_Data/validation_output/queries.csv
"""

import random
from datetime import timedelta

import numpy as np
import pandas as pd

from config import RANDOM_SEED, VALIDATION_OUTPUT_DIR, STUDY_DATA_CUTOFF

random.seed(RANDOM_SEED + 10)
np.random.seed(RANDOM_SEED + 10)

STUDY_DATA_CUTOFF = pd.Timestamp(STUDY_DATA_CUTOFF)  # normalize to Timestamp for date arithmetic

RULE_CATEGORY_TO_QUERY_TYPE = {
    "Completeness": "MISSING_DATA",
    "Validity": "CODING_ISSUE",
    "Range Check": "RANGE_ERROR",
    "Consistency": "DATE_DISCREPANCY",
    "Cross-form": "CROSS_FORM_MISMATCH",
    "Duplicate": "DUPLICATE",
}

SEVERITY_TO_PRIORITY = {
    "Critical": "CRITICAL",
    "Major": "HIGH",
    "Minor": "MEDIUM",
}

STATUS_FLOW = ["OPEN", "SENT_TO_SITE", "SITE_RESPONDED", "UNDER_REVIEW",
               "RESOLVED", "REJECTED", "REOPENED", "CLOSED"]


def assign_status_and_dates(query_date):
    """
    Simulate where in its lifecycle a query currently sits, and derive
    consistent RESPONSE_DATE / RESOLUTION_DATE from that status.
    """
    days_since_query = (STUDY_DATA_CUTOFF - query_date).days
    days_since_query = max(days_since_query, 0)

    # older queries are more likely to have progressed further in the lifecycle
    if days_since_query < 5:
        status = np.random.choice(["OPEN", "SENT_TO_SITE"], p=[0.5, 0.5])
    elif days_since_query < 15:
        status = np.random.choice(
            ["SENT_TO_SITE", "SITE_RESPONDED", "UNDER_REVIEW", "RESOLVED"],
            p=[0.25, 0.30, 0.25, 0.20])
    elif days_since_query < 30:
        status = np.random.choice(
            ["SITE_RESPONDED", "UNDER_REVIEW", "RESOLVED", "CLOSED", "REOPENED"],
            p=[0.10, 0.15, 0.30, 0.35, 0.10])
    else:
        status = np.random.choice(
            ["RESOLVED", "CLOSED", "REJECTED", "REOPENED"],
            p=[0.20, 0.60, 0.10, 0.10])

    response_date = None
    resolution_date = None

    if status in ("SITE_RESPONDED", "UNDER_REVIEW", "RESOLVED", "CLOSED", "REJECTED", "REOPENED"):
        response_lag = int(np.clip(np.random.exponential(6), 1, days_since_query))
        response_date = query_date + timedelta(days=response_lag)

    if status in ("RESOLVED", "CLOSED", "REJECTED"):
        remaining = max((STUDY_DATA_CUTOFF - (response_date or query_date)).days, 1)
        resolution_lag = int(np.clip(np.random.exponential(5), 1, remaining))
        resolution_date = (response_date or query_date) + timedelta(days=resolution_lag)

    return status, response_date, resolution_date


def classify_aging(query_date, resolution_date):
    end_point = resolution_date if pd.notna(resolution_date) else STUDY_DATA_CUTOFF
    age_days = (end_point - query_date).days if pd.notna(query_date) else None
    if age_days is None:
        return None, None
    if age_days <= 7:
        bucket = "Normal"
    elif age_days <= 14:
        bucket = "Attention"
    elif age_days <= 30:
        bucket = "Overdue"
    else:
        bucket = "Critical"
    return age_days, bucket


def main():
    dq = pd.read_csv(VALIDATION_OUTPUT_DIR / "data_quality_results.csv")
    dq["DETECTED_DATE"] = pd.to_datetime(dq["DETECTED_DATE"], errors="coerce")

    rows = []
    query_counter = 1
    duplicate_query_target = set(random.sample(range(len(dq)), k=min(15, len(dq))))

    for idx, r in dq.reset_index(drop=True).iterrows():
        # spread query detection dates back over ~9 months before cutoff so
        # aging / status distributions look realistic rather than everything
        # clustered on one day
        backdate_days = int(np.random.randint(1, 270))
        query_date = STUDY_DATA_CUTOFF - timedelta(days=backdate_days)

        query_type = RULE_CATEGORY_TO_QUERY_TYPE.get(r["RULE_CATEGORY"], "OTHER")
        priority = SEVERITY_TO_PRIORITY.get(r["SEVERITY"], "MEDIUM")

        status, response_date, resolution_date = assign_status_and_dates(query_date)

        query_id = f"QRY-{query_counter:06d}"
        rows.append({
            "QUERY_ID": query_id,
            "SUBJECT_ID": r["SUBJECT_ID"],
            "SITE_ID": r["SITE_ID"],
            "FORM_NAME": r["RULE_CATEGORY"],
            "FIELD_NAME": r["RULE_NAME"],
            "QUERY_TYPE": query_type,
            "QUERY_DESCRIPTION": r["DESCRIPTION"],
            "QUERY_DATE": query_date.date(),
            "QUERY_STATUS": status,
            "PRIORITY": priority,
            "RESPONSE_DATE": response_date.date() if response_date is not None else None,
            "RESOLUTION_DATE": resolution_date.date() if resolution_date is not None else None,
            "SOURCE_DQ_ID": r["DQ_ID"],
        })
        query_counter += 1

        if idx in duplicate_query_target:
            dup_id = f"QRY-{query_counter:06d}"
            dup_row = rows[-1].copy()
            dup_row["QUERY_ID"] = dup_id
            rows.append(dup_row)
            query_counter += 1

    queries = pd.DataFrame(rows)
    queries["QUERY_DATE"] = pd.to_datetime(queries["QUERY_DATE"])
    queries["RESOLUTION_DATE"] = pd.to_datetime(queries["RESOLUTION_DATE"])

    ages, buckets = [], []
    for _, r in queries.iterrows():
        age, bucket = classify_aging(r["QUERY_DATE"], r["RESOLUTION_DATE"])
        ages.append(age)
        buckets.append(bucket)
    queries["QUERY_AGE_DAYS"] = ages
    queries["AGING_BUCKET"] = buckets

    queries.to_csv(VALIDATION_OUTPUT_DIR / "queries.csv", index=False)

    print(f"[Query Engine] {len(queries)} queries generated from {len(dq)} data-quality findings")
    print(queries["QUERY_STATUS"].value_counts().to_string())
    print("\nAging distribution:")
    print(queries["AGING_BUCKET"].value_counts().to_string())
    print("\n[Query Engine] Output written to 01_Data/validation_output/queries.csv")


if __name__ == "__main__":
    main()
