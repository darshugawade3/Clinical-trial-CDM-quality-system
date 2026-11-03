-- =================================================================
-- 03_insert_reference_data.sql
-- Clinical Trial Data Quality & Query Management System
--
-- Loads the CSV extracts produced by 03_Python/01_generate_dataset.py
-- into the tables created in 02_create_tables.sql, and inserts the
-- reference lookup data (approved treatment arms, query status list,
-- query priority list) used by validation/constraint logic.
-- =================================================================

-- ---------------------------------------------------------------
-- REFERENCE LOOKUP TABLES
-- ---------------------------------------------------------------
CREATE TABLE ref_treatment_arms (
    treatment_arm VARCHAR2(30) PRIMARY KEY
);
INSERT INTO ref_treatment_arms VALUES ('Drug A 10mg');
INSERT INTO ref_treatment_arms VALUES ('Drug A 20mg');
INSERT INTO ref_treatment_arms VALUES ('Placebo');

CREATE TABLE ref_query_status (
    query_status VARCHAR2(20) PRIMARY KEY,
    sequence_order NUMBER(2)
);
INSERT INTO ref_query_status VALUES ('OPEN', 1);
INSERT INTO ref_query_status VALUES ('SENT_TO_SITE', 2);
INSERT INTO ref_query_status VALUES ('SITE_RESPONDED', 3);
INSERT INTO ref_query_status VALUES ('UNDER_REVIEW', 4);
INSERT INTO ref_query_status VALUES ('RESOLVED', 5);
INSERT INTO ref_query_status VALUES ('REJECTED', 6);
INSERT INTO ref_query_status VALUES ('REOPENED', 7);
INSERT INTO ref_query_status VALUES ('CLOSED', 8);

CREATE TABLE ref_query_priority (
    priority VARCHAR2(10) PRIMARY KEY,
    weight NUMBER(2)
);
INSERT INTO ref_query_priority VALUES ('LOW', 1);
INSERT INTO ref_query_priority VALUES ('MEDIUM', 2);
INSERT INTO ref_query_priority VALUES ('HIGH', 3);
INSERT INTO ref_query_priority VALUES ('CRITICAL', 4);

COMMIT;

-- ---------------------------------------------------------------
-- LOADING THE GENERATED CSV EXTRACTS (SQL*Loader control-file pattern)
--
-- The Python generator writes these files under 01_Data/raw/ and
-- 01_Data/validation_output/. Each has a matching .ctl example below;
-- adjust the directory path to your environment before running:
--
--   sqlldr cdm_admin/"ChangeMe_2026!" control=sites.ctl log=sites.log
--
-- Example control file (sites.ctl):
--
--   LOAD DATA
--   INFILE '01_Data/raw/sites.csv'
--   INTO TABLE sites
--   FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
--   TRAILING NULLCOLS
--   ( site_id, site_name, country, investigator_id,
--     site_status, activation_date DATE "YYYY-MM-DD" )
--
-- Repeat the same pattern (one .ctl file per table) for:
--   subjects.csv, visits.csv, lab_results.csv, vital_signs.csv,
--   adverse_events.csv, concomitant_medications.csv,
--   protocol_deviations.csv  -> raw source tables
--   data_quality_results.csv, queries.csv -> validation_output tables
--
-- This keeps Python as the single source of truth for the data while
-- SQL demonstrates the production-grade loading pattern used in a
-- real CDM/CRO environment.
-- ---------------------------------------------------------------
