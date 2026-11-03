-- =================================================================
-- 06_query_management.sql
-- Clinical Trial Data Quality & Query Management System
--
-- Query lifecycle transitions, aging calculation, and priority-based
-- monitoring views.
-- =================================================================

-- ---------------------------------------------------------------
-- QUERY AGE + AGING BUCKET (view — always reflects current date)
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW vw_query_aging AS
SELECT
    q.query_id,
    q.subject_id,
    q.site_id,
    q.query_type,
    q.priority,
    q.query_status,
    q.query_date,
    q.resolution_date,
    (NVL(q.resolution_date, SYSDATE) - q.query_date) AS query_age_days,
    CASE
        WHEN (NVL(q.resolution_date, SYSDATE) - q.query_date) <= 7  THEN 'Normal'
        WHEN (NVL(q.resolution_date, SYSDATE) - q.query_date) <= 14 THEN 'Attention'
        WHEN (NVL(q.resolution_date, SYSDATE) - q.query_date) <= 30 THEN 'Overdue'
        ELSE 'Critical'
    END AS aging_bucket
FROM queries q;

-- ---------------------------------------------------------------
-- ADVANCE A QUERY TO ITS NEXT LIFECYCLE STATE
-- ---------------------------------------------------------------
CREATE OR REPLACE PROCEDURE advance_query_status (
    p_query_id     IN VARCHAR2,
    p_new_status   IN VARCHAR2
) IS
    v_current_status queries.query_status%TYPE;
BEGIN
    SELECT query_status INTO v_current_status
    FROM queries WHERE query_id = p_query_id;

    IF p_new_status NOT IN
        ('OPEN','SENT_TO_SITE','SITE_RESPONDED','UNDER_REVIEW',
         'RESOLVED','REJECTED','REOPENED','CLOSED')
    THEN
        RAISE_APPLICATION_ERROR(-20001, 'Invalid query status: ' || p_new_status);
    END IF;

    UPDATE queries
    SET query_status = p_new_status,
        response_date = CASE WHEN p_new_status = 'SITE_RESPONDED'
                              THEN SYSDATE ELSE response_date END,
        resolution_date = CASE WHEN p_new_status IN ('RESOLVED', 'CLOSED')
                                THEN SYSDATE ELSE resolution_date END
    WHERE query_id = p_query_id;

    COMMIT;
END advance_query_status;
/

-- ---------------------------------------------------------------
-- OVERDUE / CRITICAL-AGING OPEN QUERIES REQUIRING ESCALATION
-- ---------------------------------------------------------------
SELECT query_id, subject_id, site_id, priority, query_age_days, aging_bucket
FROM vw_query_aging
WHERE query_status NOT IN ('RESOLVED', 'CLOSED', 'REJECTED')
  AND aging_bucket IN ('Overdue', 'Critical')
ORDER BY query_age_days DESC;

-- ---------------------------------------------------------------
-- QUERY VOLUME AND STATUS MIX BY SITE (CTE + aggregate)
-- ---------------------------------------------------------------
WITH site_query_counts AS (
    SELECT site_id,
           COUNT(*) AS total_queries,
           SUM(CASE WHEN query_status IN ('RESOLVED','CLOSED') THEN 1 ELSE 0 END) AS closed_queries,
           SUM(CASE WHEN query_status NOT IN ('RESOLVED','CLOSED') THEN 1 ELSE 0 END) AS open_queries
    FROM queries
    GROUP BY site_id
)
SELECT site_id, total_queries, closed_queries, open_queries,
       ROUND(closed_queries / total_queries * 100, 2) AS closure_rate_pct,
       RANK() OVER (ORDER BY closed_queries / total_queries DESC) AS closure_rank
FROM site_query_counts
ORDER BY closure_rate_pct DESC;
