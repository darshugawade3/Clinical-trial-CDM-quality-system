-- =================================================================
-- 07_quality_metrics.sql
-- Clinical Trial Data Quality & Query Management System
--
-- Study-level KPI calculation and site-level quality scoring in
-- pure SQL, matching 03_Python/05_quality_metrics.py.
-- =================================================================

-- ---------------------------------------------------------------
-- STUDY-LEVEL KPI SUMMARY
-- ---------------------------------------------------------------
SELECT
    (SELECT COUNT(DISTINCT subject_id) FROM subjects)              AS total_subjects,
    (SELECT COUNT(DISTINCT site_id) FROM sites)                    AS total_sites,
    (SELECT COUNT(*) FROM visits)                                  AS total_visits,
    (SELECT COUNT(*) FROM data_quality_results)                    AS total_data_issues,
    (SELECT COUNT(*) FROM queries)                                 AS total_queries,
    (SELECT COUNT(*) FROM queries WHERE query_status NOT IN ('RESOLVED','CLOSED')) AS open_queries,
    (SELECT COUNT(*) FROM queries WHERE query_status IN ('RESOLVED','CLOSED'))     AS closed_queries,
    (SELECT ROUND(COUNT(CASE WHEN query_status IN ('RESOLVED','CLOSED') THEN 1 END)
            / NULLIF(COUNT(*),0) * 100, 2) FROM queries)           AS query_closure_rate_pct,
    (SELECT COUNT(*) FROM data_quality_results WHERE severity = 'Critical') AS critical_issue_count
FROM dual;

-- ---------------------------------------------------------------
-- AVERAGE / MEDIAN QUERY RESOLUTION TIME
-- ---------------------------------------------------------------
SELECT
    ROUND(AVG(resolution_date - query_date), 2) AS avg_resolution_days,
    ROUND(MEDIAN(resolution_date - query_date), 2) AS median_resolution_days
FROM queries
WHERE resolution_date IS NOT NULL;

-- ---------------------------------------------------------------
-- DATA COMPLETENESS % (required subject fields)
-- ---------------------------------------------------------------
SELECT
    ROUND(100 - (
        (SUM(CASE WHEN age IS NULL THEN 1 ELSE 0 END) +
         SUM(CASE WHEN sex IS NULL THEN 1 ELSE 0 END) +
         SUM(CASE WHEN weight_kg IS NULL THEN 1 ELSE 0 END) +
         SUM(CASE WHEN treatment_arm IS NULL THEN 1 ELSE 0 END)
        ) / (COUNT(*) * 4) * 100
    ), 2) AS data_completeness_pct
FROM subjects;

-- ---------------------------------------------------------------
-- SITE QUALITY SCORE
-- Formula (identical across Python / SQL / Excel / Power BI):
--   100 - (missing_data_pct * 0.5)
--       - (open_queries_per_subject * 8)
--       - (overdue_queries_per_subject * 12)
--       - (deviations_per_subject * 10)
--       - (critical_dq_per_subject * 15)
-- ---------------------------------------------------------------
WITH site_subject_counts AS (
    SELECT site_id, COUNT(*) AS n_subjects
    FROM subjects
    GROUP BY site_id
),
site_missing AS (
    SELECT site_id,
           ROUND(SUM(CASE WHEN age IS NULL OR sex IS NULL
                           OR weight_kg IS NULL OR treatment_arm IS NULL
                      THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) AS missing_pct
    FROM subjects
    GROUP BY site_id
),
site_queries AS (
    SELECT site_id,
           COUNT(CASE WHEN query_status NOT IN ('RESOLVED','CLOSED') THEN 1 END) AS open_q,
           COUNT(CASE WHEN (NVL(resolution_date, SYSDATE) - query_date) > 14
                       AND query_status NOT IN ('RESOLVED','CLOSED') THEN 1 END) AS overdue_q
    FROM queries
    GROUP BY site_id
),
site_deviations AS (
    SELECT site_id, COUNT(*) AS n_deviations
    FROM protocol_deviations
    GROUP BY site_id
),
site_critical_dq AS (
    SELECT site_id, COUNT(*) AS n_critical
    FROM data_quality_results
    WHERE severity = 'Critical'
    GROUP BY site_id
)
SELECT
    sc.site_id,
    sc.n_subjects,
    NVL(sm.missing_pct, 0) AS missing_pct,
    NVL(sq.open_q, 0) AS open_queries,
    NVL(sq.overdue_q, 0) AS overdue_queries,
    NVL(sd.n_deviations, 0) AS protocol_deviations,
    NVL(sdq.n_critical, 0) AS critical_dq,
    ROUND(GREATEST(0, LEAST(100,
        100
        - (NVL(sm.missing_pct, 0) * 0.5)
        - (NVL(sq.open_q, 0) / sc.n_subjects * 8)
        - (NVL(sq.overdue_q, 0) / sc.n_subjects * 12)
        - (NVL(sd.n_deviations, 0) / sc.n_subjects * 10)
        - (NVL(sdq.n_critical, 0) / sc.n_subjects * 15)
    )), 2) AS quality_score
FROM site_subject_counts sc
LEFT JOIN site_missing sm ON sm.site_id = sc.site_id
LEFT JOIN site_queries sq ON sq.site_id = sc.site_id
LEFT JOIN site_deviations sd ON sd.site_id = sc.site_id
LEFT JOIN site_critical_dq sdq ON sdq.site_id = sc.site_id
ORDER BY quality_score DESC;
