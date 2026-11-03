-- =================================================================
-- database_schema.sql
-- Clinical Trial Data Quality & Query Management System
-- Consolidated schema + ERD description (see also 02_SQL/02_create_tables.sql,
-- which is the authoritative, run-in-order version of this DDL).
-- =================================================================

-- ERD RELATIONSHIP SUMMARY
-- SITES (1) ----< SUBJECTS (many)
-- SUBJECTS (1) ----< VISITS (many)
-- SUBJECTS (1) ----< LAB_RESULTS, VITAL_SIGNS, ADVERSE_EVENTS,
--                     CONCOMITANT_MEDICATIONS, PROTOCOL_DEVIATIONS (many)
-- VISITS (1) ----< LAB_RESULTS, VITAL_SIGNS (many)
-- SUBJECTS/SITES ----< DATA_QUALITY_RESULTS (many)
-- DATA_QUALITY_RESULTS (1) ----< QUERIES (many, via source_dq_id)
--
-- All child tables carry SUBJECT_ID (and SITE_ID where relevant) as a
-- foreign key back to SUBJECTS/SITES, enforcing referential integrity.
-- Indexes are created on every foreign key and on frequently filtered
-- columns (query_status, query_date, rule_id) to support the KPI and
-- site-performance queries in 07_quality_metrics.sql.

See 02_SQL/02_create_tables.sql for the full executable DDL.
