"""
05_quality_metrics.py
-----------------------
Computes study-level Data Quality KPIs and site-level performance
scores from the cleaned data + validation_output tables. Writes:

    01_Data/validation_output/kpi_summary.csv
    01_Data/validation_output/site_performance.csv
    01_Data/validation_output/database_lock_readiness.csv
"""

import numpy as np
import pandas as pd

from config import CLEANED_DIR, VALIDATION_OUTPUT_DIR

# ---------------------------------------------------------------
# SITE QUALITY SCORE FORMULA (documented exactly, used consistently
# everywhere else in the project — SQL, Excel, Power BI, Word):
#
#   Quality Score = 100
#       - (Missing Data % contributing subjects   * 0.5)
#       - (Open Queries per subject at site        * 8)
#       - (Overdue+Critical Queries per subject     * 12)
#       - (Protocol Deviations per subject          * 10)
#       - (Critical DQ findings per subject         * 15)
#   Floored at 0, capped at 100.
#
# Classification:
#   90-100 = Excellent | 75-89 = Good | 60-74 = Needs Improvement | <60 = High Risk
# ---------------------------------------------------------------

def classify_score(score):
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Good"
    elif score >= 60:
        return "Needs Improvement"
    else:
        return "High Risk"


def main():
    subjects = pd.read_csv(CLEANED_DIR / "subjects.csv").drop_duplicates("SUBJECT_ID")
    visits = pd.read_csv(CLEANED_DIR / "visits.csv")
    deviations = pd.read_csv(CLEANED_DIR / "protocol_deviations.csv")
    dq = pd.read_csv(VALIDATION_OUTPUT_DIR / "data_quality_results.csv")
    queries = pd.read_csv(VALIDATION_OUTPUT_DIR / "queries.csv")

    # ============================================================
    # STUDY-LEVEL KPIs
    # ============================================================
    total_subjects = subjects["SUBJECT_ID"].nunique()
    total_sites = subjects["SITE_ID"].nunique()
    total_visits = len(visits)
    total_records = (len(subjects) + len(visits) +
                      len(pd.read_csv(CLEANED_DIR / "lab_results.csv")) +
                      len(pd.read_csv(CLEANED_DIR / "vital_signs.csv")) +
                      len(pd.read_csv(CLEANED_DIR / "adverse_events.csv")) +
                      len(pd.read_csv(CLEANED_DIR / "concomitant_medications.csv")) +
                      len(deviations))
    total_issues = len(dq)
    total_queries = len(queries)
    closed_statuses = {"CLOSED", "RESOLVED"}
    open_queries = queries[~queries["QUERY_STATUS"].isin(closed_statuses)]
    closed_queries = queries[queries["QUERY_STATUS"].isin(closed_statuses)]

    query_closure_rate = round(len(closed_queries) / total_queries * 100, 2) if total_queries else 0.0

    resolved_with_age = queries[queries["QUERY_STATUS"].isin(closed_statuses) & queries["QUERY_AGE_DAYS"].notna()]
    avg_resolution_days = round(resolved_with_age["QUERY_AGE_DAYS"].mean(), 2) if len(resolved_with_age) else None
    median_resolution_days = round(resolved_with_age["QUERY_AGE_DAYS"].median(), 2) if len(resolved_with_age) else None

    required_fields = ["AGE", "SEX", "WEIGHT_KG", "TREATMENT_ARM"]
    completeness_pct = round(
        (1 - subjects[required_fields].isna().sum().sum() / (len(subjects) * len(required_fields))) * 100, 2
    )

    critical_issues = len(dq[dq["SEVERITY"] == "Critical"])
    overdue_queries = len(queries[queries["AGING_BUCKET"].isin(["Overdue", "Critical"])])
    duplicate_rule_ids = {"D01", "D02", "D03", "D04"}
    duplicate_rate = round(len(dq[dq["RULE_ID"].isin(duplicate_rule_ids)]) / total_issues * 100, 2) if total_issues else 0
    missing_data_rate = round(len(dq[dq["RULE_CATEGORY"] == "Completeness"]) / total_issues * 100, 2) if total_issues else 0
    protocol_deviation_rate = round(len(deviations) / total_subjects * 100, 2)

    # simple accuracy/consistency proxies derived from validation categories
    data_accuracy_pct = round(100 - (len(dq[dq["RULE_CATEGORY"].isin(["Validity", "Range Check"])]) /
                                      max(total_records, 1) * 100), 2)
    data_consistency_pct = round(100 - (len(dq[dq["RULE_CATEGORY"] == "Consistency"]) /
                                         max(total_records, 1) * 100), 2)

    kpi_rows = [
        ("Total Subjects", total_subjects),
        ("Total Sites", total_sites),
        ("Total Visits", total_visits),
        ("Total Records", total_records),
        ("Total Data Issues", total_issues),
        ("Total Queries", total_queries),
        ("Open Queries", len(open_queries)),
        ("Closed Queries", len(closed_queries)),
        ("Query Resolution Rate (%)", query_closure_rate),
        ("Average Query Resolution Time (days)", avg_resolution_days),
        ("Median Query Resolution Time (days)", median_resolution_days),
        ("Data Completeness (%)", completeness_pct),
        ("Data Accuracy (%)", data_accuracy_pct),
        ("Data Consistency (%)", data_consistency_pct),
        ("Protocol Deviation Rate (%)", protocol_deviation_rate),
        ("Duplicate Rate (%)", duplicate_rate),
        ("Missing Data Rate (%)", missing_data_rate),
        ("Critical Issue Count", critical_issues),
        ("Overdue Query Count", overdue_queries),
    ]
    kpi_df = pd.DataFrame(kpi_rows, columns=["KPI", "VALUE"])
    kpi_df.to_csv(VALIDATION_OUTPUT_DIR / "kpi_summary.csv", index=False)

    # ============================================================
    # SITE-LEVEL PERFORMANCE
    # ============================================================
    site_rows = []
    for site_id, grp in subjects.groupby("SITE_ID"):
        n_subj = len(grp)
        site_dq = dq[dq["SITE_ID"] == site_id]
        site_queries = queries[queries["SITE_ID"] == site_id]
        site_open_q = site_queries[~site_queries["QUERY_STATUS"].isin(closed_statuses)]
        site_overdue_q = site_queries[site_queries["AGING_BUCKET"].isin(["Overdue", "Critical"])]
        site_dev = deviations[deviations["SITE_ID"] == site_id]
        site_closed_q = site_queries[site_queries["QUERY_STATUS"].isin(closed_statuses)]
        site_resolution_rate = round(len(site_closed_q) / len(site_queries) * 100, 2) if len(site_queries) else 100.0
        site_avg_resolution = round(
            site_closed_q["QUERY_AGE_DAYS"].mean(), 2
        ) if len(site_closed_q) and site_closed_q["QUERY_AGE_DAYS"].notna().any() else None
        missing_pct = round(grp[required_fields].isna().sum().sum() / (len(grp) * len(required_fields)) * 100, 2)
        critical_dq = len(site_dq[site_dq["SEVERITY"] == "Critical"])

        missing_penalty = missing_pct * 0.5
        open_query_penalty = (len(site_open_q) / n_subj) * 8
        overdue_penalty = (len(site_overdue_q) / n_subj) * 12
        deviation_penalty = (len(site_dev) / n_subj) * 10
        critical_penalty = (critical_dq / n_subj) * 15

        score = 100 - missing_penalty - open_query_penalty - overdue_penalty - deviation_penalty - critical_penalty
        score = round(float(np.clip(score, 0, 100)), 2)

        site_rows.append({
            "SITE_ID": site_id,
            "SUBJECTS": n_subj,
            "DATA_ISSUES": len(site_dq),
            "QUERIES": len(site_queries),
            "OPEN_QUERIES": len(site_open_q),
            "OVERDUE_QUERIES": len(site_overdue_q),
            "QUERY_RESOLUTION_RATE_PCT": site_resolution_rate,
            "AVG_RESOLUTION_TIME_DAYS": site_avg_resolution,
            "PROTOCOL_DEVIATIONS": len(site_dev),
            "MISSING_DATA_PCT": missing_pct,
            "QUALITY_SCORE": score,
            "QUALITY_CLASSIFICATION": classify_score(score),
        })

    site_perf_df = pd.DataFrame(site_rows).sort_values("QUALITY_SCORE", ascending=False)
    site_perf_df.to_csv(VALIDATION_OUTPUT_DIR / "site_performance.csv", index=False)

    # ============================================================
    # DATABASE LOCK READINESS
    # ============================================================
    critical_open_queries = len(queries[(queries["PRIORITY"] == "CRITICAL") &
                                         (~queries["QUERY_STATUS"].isin(closed_statuses))])
    high_open_queries = len(queries[(queries["PRIORITY"] == "HIGH") &
                                     (~queries["QUERY_STATUS"].isin(closed_statuses))])
    missing_data_threshold_pct = 2.0
    unresolved_critical_dq = len(dq[(dq["SEVERITY"] == "Critical") & (dq["STATUS"] == "OPEN")])

    reasons = []
    if critical_open_queries > 0:
        reasons.append(f"{critical_open_queries} CRITICAL-priority queries still open")
    if 100 - completeness_pct > missing_data_threshold_pct:
        reasons.append(f"Missing required data ({100 - completeness_pct:.2f}%) exceeds "
                        f"{missing_data_threshold_pct}% threshold")
    if unresolved_critical_dq > 0:
        reasons.append(f"{unresolved_critical_dq} unresolved critical discrepancies")

    lock_ready = "NO" if reasons else "YES"
    lock_df = pd.DataFrame([{
        "DATABASE_LOCK_READY": lock_ready,
        "CRITICAL_OPEN_QUERIES": critical_open_queries,
        "HIGH_PRIORITY_OPEN_QUERIES": high_open_queries,
        "MISSING_DATA_PCT": round(100 - completeness_pct, 2),
        "MISSING_DATA_THRESHOLD_PCT": missing_data_threshold_pct,
        "UNRESOLVED_CRITICAL_DISCREPANCIES": unresolved_critical_dq,
        "BLOCKING_REASONS": "; ".join(reasons) if reasons else "None",
    }])
    lock_df.to_csv(VALIDATION_OUTPUT_DIR / "database_lock_readiness.csv", index=False)

    print("[Quality Metrics] KPI summary:")
    print(kpi_df.to_string(index=False))
    print("\n[Quality Metrics] Top 5 sites by Quality Score:")
    print(site_perf_df.head(5).to_string(index=False))
    print("\n[Quality Metrics] Database Lock Readiness:", lock_ready)
    if reasons:
        print("  Blocking reasons:", "; ".join(reasons))
    print("\n[Quality Metrics] Output written to 01_Data/validation_output/")


if __name__ == "__main__":
    main()
