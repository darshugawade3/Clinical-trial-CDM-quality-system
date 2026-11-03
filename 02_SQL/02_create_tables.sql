-- =================================================================
-- 02_create_tables.sql
-- Clinical Trial Data Quality & Query Management System
-- Oracle SQL / PL-SQL compatible
--
-- Creates all core tables, primary keys, foreign keys and indexes.
-- Run as cdm_admin after 01_create_database.sql.
-- =================================================================

-- ---------------------------------------------------------------
-- SITES
-- ---------------------------------------------------------------
CREATE TABLE sites (
    site_id           VARCHAR2(10)  NOT NULL,
    site_name         VARCHAR2(100) NOT NULL,
    country           VARCHAR2(50)  NOT NULL,
    investigator_id   VARCHAR2(10)  NOT NULL,
    site_status       VARCHAR2(20)  NOT NULL,
    activation_date   DATE          NOT NULL,
    CONSTRAINT pk_sites PRIMARY KEY (site_id),
    CONSTRAINT ck_site_status CHECK (site_status IN ('Active', 'Closed'))
);

-- ---------------------------------------------------------------
-- SUBJECTS
-- ---------------------------------------------------------------
CREATE TABLE subjects (
    subject_id           VARCHAR2(12) NOT NULL,
    site_id              VARCHAR2(10) NOT NULL,
    screening_date       DATE,
    randomization_date   DATE,
    age                  NUMBER(3),
    sex                  VARCHAR2(1),
    height_cm            NUMBER(5,1),
    weight_kg            NUMBER(5,1),
    bmi                  NUMBER(5,1),
    treatment_arm        VARCHAR2(30),
    subject_status       VARCHAR2(20),
    CONSTRAINT pk_subjects PRIMARY KEY (subject_id),
    CONSTRAINT fk_subjects_site FOREIGN KEY (site_id) REFERENCES sites(site_id),
    CONSTRAINT ck_subject_sex CHECK (sex IN ('M', 'F'))
);

-- ---------------------------------------------------------------
-- VISITS
-- ---------------------------------------------------------------
CREATE TABLE visits (
    visit_id       VARCHAR2(12) NOT NULL,
    subject_id     VARCHAR2(12) NOT NULL,
    visit_name     VARCHAR2(30) NOT NULL,
    planned_date   DATE,
    actual_date    DATE,
    visit_status   VARCHAR2(20),
    window_days    NUMBER(3),
    CONSTRAINT pk_visits PRIMARY KEY (visit_id),
    CONSTRAINT fk_visits_subject FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

-- ---------------------------------------------------------------
-- LAB_RESULTS
-- ---------------------------------------------------------------
CREATE TABLE lab_results (
    lab_id            VARCHAR2(12) NOT NULL,
    subject_id        VARCHAR2(12) NOT NULL,
    visit_id          VARCHAR2(12) NOT NULL,
    lab_test          VARCHAR2(50) NOT NULL,
    result_value      NUMBER(10,2),
    unit              VARCHAR2(20),
    lower_limit       NUMBER(10,2),
    upper_limit       NUMBER(10,2),
    abnormal_flag     VARCHAR2(1),
    collection_date   DATE,
    CONSTRAINT pk_lab_results PRIMARY KEY (lab_id),
    CONSTRAINT fk_lab_subject FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
    CONSTRAINT ck_abnormal_flag CHECK (abnormal_flag IN ('Y', 'N'))
);

-- ---------------------------------------------------------------
-- VITAL_SIGNS
-- ---------------------------------------------------------------
CREATE TABLE vital_signs (
    vital_id           VARCHAR2(12) NOT NULL,
    subject_id         VARCHAR2(12) NOT NULL,
    visit_id           VARCHAR2(12) NOT NULL,
    systolic_bp        NUMBER(3),
    diastolic_bp       NUMBER(3),
    heart_rate         NUMBER(3),
    temperature        NUMBER(4,1),
    weight             NUMBER(5,1),
    measurement_date   DATE,
    CONSTRAINT pk_vital_signs PRIMARY KEY (vital_id),
    CONSTRAINT fk_vitals_subject FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

-- ---------------------------------------------------------------
-- ADVERSE_EVENTS
-- ---------------------------------------------------------------
CREATE TABLE adverse_events (
    ae_id                    VARCHAR2(12) NOT NULL,
    subject_id               VARCHAR2(12) NOT NULL,
    ae_term                  VARCHAR2(100),
    start_date               DATE,
    end_date                 DATE,
    severity                 VARCHAR2(20),
    seriousness              VARCHAR2(20),
    action_taken             VARCHAR2(30),
    outcome                  VARCHAR2(30),
    related_to_study_drug    VARCHAR2(20),
    CONSTRAINT pk_adverse_events PRIMARY KEY (ae_id),
    CONSTRAINT fk_ae_subject FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

-- ---------------------------------------------------------------
-- CONCOMITANT_MEDICATIONS
-- ---------------------------------------------------------------
CREATE TABLE concomitant_medications (
    medication_id     VARCHAR2(12) NOT NULL,
    subject_id        VARCHAR2(12) NOT NULL,
    medication_name   VARCHAR2(100),
    start_date        DATE,
    end_date          DATE,
    dose              VARCHAR2(20),
    route             VARCHAR2(20),
    frequency         VARCHAR2(30),
    CONSTRAINT pk_conmeds PRIMARY KEY (medication_id),
    CONSTRAINT fk_conmed_subject FOREIGN KEY (subject_id) REFERENCES subjects(subject_id)
);

-- ---------------------------------------------------------------
-- PROTOCOL_DEVIATIONS
-- ---------------------------------------------------------------
CREATE TABLE protocol_deviations (
    deviation_id      VARCHAR2(12) NOT NULL,
    subject_id        VARCHAR2(12) NOT NULL,
    site_id           VARCHAR2(10) NOT NULL,
    deviation_type    VARCHAR2(60),
    deviation_date    DATE,
    severity          VARCHAR2(20),
    description       VARCHAR2(500),
    status            VARCHAR2(20),
    CONSTRAINT pk_deviations PRIMARY KEY (deviation_id),
    CONSTRAINT fk_dev_subject FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
    CONSTRAINT fk_dev_site FOREIGN KEY (site_id) REFERENCES sites(site_id)
);

-- ---------------------------------------------------------------
-- DATA_QUALITY_RESULTS
-- ---------------------------------------------------------------
CREATE TABLE data_quality_results (
    dq_id            VARCHAR2(12) NOT NULL,
    subject_id       VARCHAR2(12),
    site_id          VARCHAR2(10),
    rule_id          VARCHAR2(10) NOT NULL,
    rule_name        VARCHAR2(100),
    rule_category    VARCHAR2(30),
    severity         VARCHAR2(20),
    description      VARCHAR2(500),
    current_value    VARCHAR2(200),
    expected_value   VARCHAR2(200),
    status           VARCHAR2(20),
    detected_date    DATE,
    CONSTRAINT pk_dq_results PRIMARY KEY (dq_id),
    CONSTRAINT ck_dq_severity CHECK (severity IN ('Critical', 'Major', 'Minor'))
);

-- ---------------------------------------------------------------
-- QUERIES
-- ---------------------------------------------------------------
CREATE TABLE queries (
    query_id            VARCHAR2(12) NOT NULL,
    subject_id          VARCHAR2(12),
    site_id             VARCHAR2(10),
    form_name           VARCHAR2(50),
    field_name          VARCHAR2(100),
    query_type          VARCHAR2(30),
    query_description   VARCHAR2(500),
    query_date          DATE,
    query_status        VARCHAR2(20),
    priority            VARCHAR2(10),
    response_date       DATE,
    resolution_date     DATE,
    source_dq_id        VARCHAR2(12),
    CONSTRAINT pk_queries PRIMARY KEY (query_id),
    CONSTRAINT fk_query_dq FOREIGN KEY (source_dq_id) REFERENCES data_quality_results(dq_id),
    CONSTRAINT ck_query_status CHECK (query_status IN
        ('OPEN','SENT_TO_SITE','SITE_RESPONDED','UNDER_REVIEW',
         'RESOLVED','REJECTED','REOPENED','CLOSED')),
    CONSTRAINT ck_query_priority CHECK (priority IN ('LOW','MEDIUM','HIGH','CRITICAL'))
);

-- ---------------------------------------------------------------
-- INDEXES (performance for common query patterns)
-- ---------------------------------------------------------------
CREATE INDEX ix_subjects_site       ON subjects(site_id);
CREATE INDEX ix_visits_subject      ON visits(subject_id);
CREATE INDEX ix_lab_subject         ON lab_results(subject_id);
CREATE INDEX ix_lab_visit           ON lab_results(visit_id);
CREATE INDEX ix_vitals_subject      ON vital_signs(subject_id);
CREATE INDEX ix_ae_subject          ON adverse_events(subject_id);
CREATE INDEX ix_conmed_subject      ON concomitant_medications(subject_id);
CREATE INDEX ix_deviation_site      ON protocol_deviations(site_id);
CREATE INDEX ix_dq_site             ON data_quality_results(site_id);
CREATE INDEX ix_dq_rule             ON data_quality_results(rule_id);
CREATE INDEX ix_queries_site        ON queries(site_id);
CREATE INDEX ix_queries_status      ON queries(query_status);
CREATE INDEX ix_queries_date        ON queries(query_date);
