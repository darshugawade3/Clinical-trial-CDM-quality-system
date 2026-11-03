-- =================================================================
-- 05_query_generation.sql
-- Clinical Trial Data Quality & Query Management System
--
-- Demonstrates generating a QUERIES record directly from a
-- DATA_QUALITY_RESULTS finding using a stored procedure — this is
-- the SQL equivalent of 03_Python/04_query_engine.py.
-- =================================================================

CREATE SEQUENCE seq_query_id START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE PROCEDURE generate_query_from_dq (
    p_dq_id IN VARCHAR2
) IS
    v_query_id       VARCHAR2(12);
    v_subject_id     data_quality_results.subject_id%TYPE;
    v_site_id        data_quality_results.site_id%TYPE;
    v_rule_category  data_quality_results.rule_category%TYPE;
    v_rule_name      data_quality_results.rule_name%TYPE;
    v_description    data_quality_results.description%TYPE;
    v_severity       data_quality_results.severity%TYPE;
    v_query_type     VARCHAR2(30);
    v_priority       VARCHAR2(10);
BEGIN
    SELECT subject_id, site_id, rule_category, rule_name, description, severity
    INTO v_subject_id, v_site_id, v_rule_category, v_rule_name, v_description, v_severity
    FROM data_quality_results
    WHERE dq_id = p_dq_id;

    v_query_type := CASE v_rule_category
        WHEN 'Completeness' THEN 'MISSING_DATA'
        WHEN 'Validity'     THEN 'CODING_ISSUE'
        WHEN 'Range Check'  THEN 'RANGE_ERROR'
        WHEN 'Consistency'  THEN 'DATE_DISCREPANCY'
        WHEN 'Cross-form'   THEN 'CROSS_FORM_MISMATCH'
        WHEN 'Duplicate'    THEN 'DUPLICATE'
        ELSE 'OTHER'
    END;

    v_priority := CASE v_severity
        WHEN 'Critical' THEN 'CRITICAL'
        WHEN 'Major'    THEN 'HIGH'
        WHEN 'Minor'    THEN 'MEDIUM'
        ELSE 'LOW'
    END;

    v_query_id := 'QRY-' || LPAD(seq_query_id.NEXTVAL, 6, '0');

    INSERT INTO queries (
        query_id, subject_id, site_id, form_name, field_name,
        query_type, query_description, query_date, query_status,
        priority, source_dq_id
    ) VALUES (
        v_query_id, v_subject_id, v_site_id, v_rule_category, v_rule_name,
        v_query_type, v_description, SYSDATE, 'OPEN',
        v_priority, p_dq_id
    );

    COMMIT;
END generate_query_from_dq;
/

-- Generate a query for every currently-open, not-yet-queried DQ finding
BEGIN
    FOR r IN (
        SELECT dq_id FROM data_quality_results
        WHERE status = 'OPEN'
          AND dq_id NOT IN (SELECT source_dq_id FROM queries WHERE source_dq_id IS NOT NULL)
    ) LOOP
        generate_query_from_dq(r.dq_id);
    END LOOP;
END;
/
