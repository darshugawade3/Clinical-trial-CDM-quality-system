-- =================================================================
-- 08_final_analysis.sql
-- Clinical Trial Data Quality & Query Management System
--
-- Final study-level analysis: database lock readiness assessment
-- and top-line findings for the closing report.
-- =================================================================

-- ---------------------------------------------------------------
-- DATABASE LOCK READINESS
--   NOT READY if any of the following is true:
--     - Critical-priority open queries > 0
--     - Missing required data % > 2%
--     - Unresolved critical DQ findings > 0
-- ---------------------------------------------------------------
WITH lock_checks AS (
    SELECT
        (SELECT COUNT(*) FROM queries
          WHERE priority = 'CRITICAL' AND query_status NOT IN ('RESOLVED','CLOSED')) AS critical_open_queries,
        (SELECT ROUND(100 - (
             (SUM(CASE WHEN age IS NULL THEN 1 ELSE 0 END) +
              SUM(CASE WHEN sex IS NULL THEN 1 ELSE 0 END) +
              SUM(CASE WHEN weight_kg IS NULL THEN 1 ELSE 0 END) +
              SUM(CASE WHEN treatment_arm IS NULL THEN 1 ELSE 0 END)
             ) / (COUNT(*) * 4) * 100), 2)
         FROM subjects) AS completeness_pct,
        (SELECT COUNT(*) FROM data_quality_results
          WHERE severity = 'Critical' AND status = 'OPEN') AS unresolved_critical_dq
    FROM dual
)
SELECT
    critical_open_queries,
    ROUND(100 - completeness_pct, 2) AS missing_data_pct,
    unresolved_critical_dq,
    CASE
        WHEN critical_open_queries > 0
          OR (100 - completeness_pct) > 2
          OR unresolved_critical_dq > 0
        THEN 'NO'
        ELSE 'YES'
    END AS database_lock_ready
FROM lock_checks;

-- ---------------------------------------------------------------
-- TOP 10 PROBLEMATIC FIELDS (most-frequently-failed rule names)
-- ---------------------------------------------------------------
SELECT rule_name, rule_category, COUNT(*) AS occurrence_count
FROM data_quality_results
GROUP BY rule_name, rule_category
ORDER BY occurrence_count DESC
FETCH FIRST 10 ROWS ONLY;

-- ---------------------------------------------------------------
-- HIGH-RISK SUBJECTS (3+ open data-quality issues) — DENSE_RANK example
-- ---------------------------------------------------------------
SELECT subject_id, site_id, open_issue_count, risk_rank
FROM (
    SELECT subject_id, site_id,
           COUNT(*) AS open_issue_count,
           DENSE_RANK() OVER (ORDER BY COUNT(*) DESC) AS risk_rank
    FROM data_quality_results
    WHERE status = 'OPEN'
    GROUP BY subject_id, site_id
)
WHERE open_issue_count >= 3
ORDER BY risk_rank;

-- ---------------------------------------------------------------
-- MONTHLY QUERY VOLUME TREND
-- ---------------------------------------------------------------
SELECT TO_CHAR(query_date, 'YYYY-MM') AS query_month,
       COUNT(*) AS queries_opened,
       SUM(CASE WHEN query_status IN ('RESOLVED','CLOSED') THEN 1 ELSE 0 END) AS queries_closed
FROM queries
GROUP BY TO_CHAR(query_date, 'YYYY-MM')
ORDER BY query_month;
