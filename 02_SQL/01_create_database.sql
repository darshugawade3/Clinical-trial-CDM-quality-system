-- =================================================================
-- 01_create_database.sql
-- Clinical Trial Data Quality & Query Management System
-- Oracle SQL / PL-SQL compatible
--
-- Creates the dedicated tablespace and schema user for the CDM
-- project. Run this once as a DBA-privileged user before running
-- 02_create_tables.sql.
-- =================================================================

-- Create a dedicated tablespace for the CDM project data
CREATE TABLESPACE cdm_data
    DATAFILE 'cdm_data01.dbf'
    SIZE 200M
    AUTOEXTEND ON NEXT 50M MAXSIZE 2G;

-- Create the schema owner
CREATE USER cdm_admin IDENTIFIED BY "ChangeMe_2026!"
    DEFAULT TABLESPACE cdm_data
    QUOTA UNLIMITED ON cdm_data;

-- Minimum required privileges for building and querying the schema
GRANT CREATE SESSION TO cdm_admin;
GRANT CREATE TABLE TO cdm_admin;
GRANT CREATE VIEW TO cdm_admin;
GRANT CREATE PROCEDURE TO cdm_admin;
GRANT CREATE SEQUENCE TO cdm_admin;

-- Connect as the new schema owner before running the remaining scripts
-- CONNECT cdm_admin/"ChangeMe_2026!"
