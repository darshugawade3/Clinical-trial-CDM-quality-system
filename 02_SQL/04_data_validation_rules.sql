-- =================================================================
-- 04_data_validation_rules.sql
-- Clinical Trial Data Quality & Query Management System
--
-- SQL implementations of the core validation-rule categories (the
-- authoritative, full 27-rule engine runs in Python —
-- 03_Python/03_validation_engine.py — this file demonstrates the
-- same logic in pure SQL for the tables loaded via SQL*Loader).
-- =================================================================

-- ---------------------------------------------------------------
-- COMPLETENESS: required subject fields missing
-- ---------------------------------------------------------------
SELECT subject_id, site_id,
       CASE WHEN age IS NULL THEN 'AGE' END AS missing_field
FROM subjects
WHERE age IS NULL OR sex IS NULL OR weight_kg IS NULL OR treatment_arm IS NULL;

-- ---------------------------------------------------------------
-- VALIDITY: treatment arm not in the approved reference list
-- ---------------------------------------------------------------
SELECT s.subject_id, s.site_id, s.treatment_arm
FROM subjects s
WHERE s.treatment_arm IS NOT NULL
  AND NOT EXISTS (
        SELECT 1 FROM ref_treatment_arms r
        WHERE r.treatment_arm = s.treatment_arm
  );

-- ---------------------------------------------------------------
-- RANGE CHECK: implausible age / BMI
-- ---------------------------------------------------------------
SELECT subject_id, site_id, age, bmi
FROM subjects
WHERE (age IS NOT NULL AND (age < 18 OR age > 90))
   OR (bmi IS NOT NULL AND (bmi < 12 OR bmi > 60));

-- ---------------------------------------------------------------
-- RANGE CHECK: lab results implausibly outside reference range
-- (mild out-of-range = normal clinical variation, already captured
--  by abnormal_flag; only >30% beyond limit is treated as a DQ issue)
-- ---------------------------------------------------------------
SELECT lab_id, subject_id, lab_test, result_value, lower_limit, upper_limit
FROM lab_results
WHERE result_value IS NOT NULL
  AND (result_value < lower_limit * 0.7 OR result_value > upper_limit * 1.3);

-- ---------------------------------------------------------------
-- CONSISTENCY: randomization before screening
-- ---------------------------------------------------------------
SELECT subject_id, site_id, screening_date, randomization_date
FROM subjects
WHERE randomization_date IS NOT NULL
  AND screening_date IS NOT NULL
  AND randomization_date < screening_date;

-- ---------------------------------------------------------------
-- CONSISTENCY: visit outside its allowed protocol window
-- ---------------------------------------------------------------
SELECT visit_id, subject_id, visit_name,
       ABS(actual_date - planned_date) AS drift_days,
       window_days
FROM visits
WHERE actual_date IS NOT NULL
  AND ABS(actual_date - planned_date) > window_days;

-- ---------------------------------------------------------------
-- CONSISTENCY: AE start date before subject randomization date
-- ---------------------------------------------------------------
SELECT ae.ae_id, ae.subject_id, ae.start_date, s.randomization_date
FROM adverse_events ae
JOIN subjects s ON s.subject_id = ae.subject_id
WHERE ae.start_date IS NOT NULL
  AND s.randomization_date IS NOT NULL
  AND ae.start_date < s.randomization_date;

-- ---------------------------------------------------------------
-- CROSS-FORM: medication or AE recorded for a subject never randomized
-- ---------------------------------------------------------------
SELECT 'MEDICATION' AS source_form, m.medication_id AS record_id, m.subject_id
FROM concomitant_medications m
JOIN subjects s ON s.subject_id = m.subject_id
WHERE s.randomization_date IS NULL
UNION ALL
SELECT 'ADVERSE_EVENT', ae.ae_id, ae.subject_id
FROM adverse_events ae
JOIN subjects s ON s.subject_id = ae.subject_id
WHERE s.randomization_date IS NULL;

-- ---------------------------------------------------------------
-- CROSS-FORM: lab record referencing a visit_id that does not exist
-- ---------------------------------------------------------------
SELECT l.lab_id, l.subject_id, l.visit_id
FROM lab_results l
WHERE NOT EXISTS (SELECT 1 FROM visits v WHERE v.visit_id = l.visit_id);

-- ---------------------------------------------------------------
-- DUPLICATE CHECKS: duplicate subject / lab / AE records
-- (ROW_NUMBER analytic function — flags every row beyond the first)
-- ---------------------------------------------------------------
SELECT subject_id, dup_rank
FROM (
    SELECT subject_id,
           ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY subject_id) AS dup_rank
    FROM subjects
) t
WHERE dup_rank > 1;

SELECT lab_id, subject_id, visit_id, lab_test, dup_rank
FROM (
    SELECT lab_id, subject_id, visit_id, lab_test, result_value,
           ROW_NUMBER() OVER (
               PARTITION BY subject_id, visit_id, lab_test, result_value
               ORDER BY lab_id
           ) AS dup_rank
    FROM lab_results
) t
WHERE dup_rank > 1;
