-- ============================================================================
-- SQL DDL - SaludMX Analytics Pipeline
-- Data Warehouse Star Schema definition for PostgreSQL 15+
-- ============================================================================

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS core;

-- Set search path to avoid prefixing
SET search_path TO core, public;

-- ============================================================================
-- 1. DIMENSION TABLES (A-Z)
-- ============================================================================

-- 1.1 DIMENSION GEOGRAFIA (Entity & Municipality Catalog)
CREATE TABLE IF NOT EXISTS dim_geografia (
    entidad_id VARCHAR(2) NOT NULL,
    municipio_id VARCHAR(3) NOT NULL,
    nombre_entidad VARCHAR(100) NOT NULL,
    nombre_municipio VARCHAR(150) NOT NULL,
    region_ssa VARCHAR(100) NULL,
    CONSTRAINT pk_dim_geografia PRIMARY KEY (entidad_id, municipio_id)
);

-- Index for geographical filtering (highly used in BI reports)
CREATE INDEX IF NOT EXISTS idx_dim_geografia_entidad ON dim_geografia(entidad_id);

-- 1.2 DIMENSION SEXO
CREATE TABLE IF NOT EXISTS dim_sexo (
    sexo_id INT PRIMARY KEY,
    descripcion_sexo VARCHAR(50) NOT NULL
);

-- 1.3 DIMENSION PROCEDENCIA (Origin of admission: Emergency, Outpatient, etc.)
CREATE TABLE IF NOT EXISTS dim_procedencia (
    procedencia_id INT PRIMARY KEY,
    descripcion_procedencia VARCHAR(150) NOT NULL
);

-- 1.4 DIMENSION TIPO INGRESO (Admission type: Scheduled, Emergency, etc.)
CREATE TABLE IF NOT EXISTS dim_tipo_ingreso (
    tipo_ingreso_id INT PRIMARY KEY,
    descripcion_tipo_ingreso VARCHAR(150) NOT NULL
);

-- 1.5 DIMENSION TIPO EGRESO (Discharge type: Cure, Improvement, Death, Transfer, etc.)
CREATE TABLE IF NOT EXISTS dim_tipo_egreso (
    tipo_egreso_id INT PRIMARY KEY,
    descripcion_tipo_egreso VARCHAR(150) NOT NULL
);

-- 1.6 DIMENSION MOTIVO EGRESO
CREATE TABLE IF NOT EXISTS dim_motivo_egreso (
    motivo_egreso_id INT PRIMARY KEY,
    descripcion_motivo VARCHAR(150) NOT NULL
);

-- 1.7 DIMENSION CIE10 (ICD-10 Diagnostic Codes)
CREATE TABLE IF NOT EXISTS dim_cie10 (
    codigo_cie10 VARCHAR(10) PRIMARY KEY,
    descripcion TEXT NOT NULL,
    grupo_cie10 VARCHAR(250) NULL,
    capitulo_cie10 VARCHAR(250) NULL
);

CREATE INDEX IF NOT EXISTS idx_dim_cie10_grupo ON dim_cie10(grupo_cie10);

-- 1.8 DIMENSION FECHA (Time dimension for advanced BI time intelligence)
CREATE TABLE IF NOT EXISTS dim_fecha (
    fecha_id INT PRIMARY KEY, -- format: YYYYMMDD
    fecha DATE NOT NULL UNIQUE,
    anio INT NOT NULL,
    mes INT NOT NULL,
    mes_nombre VARCHAR(30) NOT NULL,
    dia INT NOT NULL,
    dia_semana INT NOT NULL,
    dia_semana_nombre VARCHAR(30) NOT NULL,
    trimestre INT NOT NULL,
    es_fin_semana BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dim_fecha_date ON dim_fecha(fecha);

-- 1.9 DIMENSION CLUES (Master Health Facilities Catalog)
-- Note: Includes integrated physical and human resources snapshot attributes to avoid wide-join performance hits in BI
CREATE TABLE IF NOT EXISTS dim_clues (
    clues_id VARCHAR(20) PRIMARY KEY, -- unique CLUES alphanumeric key (e.g. DFSSA000154)
    nombre_unidad VARCHAR(250) NOT NULL,
    entidad_id VARCHAR(2) NOT NULL,
    municipio_id VARCHAR(3) NOT NULL,
    localidad VARCHAR(250) NULL,
    jurisdiccion VARCHAR(150) NULL,
    institucion VARCHAR(100) NOT NULL, -- e.g. IMSS, ISSSTE, SSA, PEMEX
    tipologia VARCHAR(150) NULL, -- General Hospital, Clinic, Specialty Center
    estado_operacion VARCHAR(50) NOT NULL, -- Active, Inactive, etc.
    
    -- Capacity/Physical Resources snapshot
    camas_sensibles INT DEFAULT 0,
    camas_no_sensibles INT DEFAULT 0,
    consultorios INT DEFAULT 0,
    quirofanos INT DEFAULT 0,
    
    -- Human Resources snapshot
    total_medicos INT DEFAULT 0,
    total_enfermeras INT DEFAULT 0,
    
    CONSTRAINT fk_dim_clues_geografia FOREIGN KEY (entidad_id, municipio_id) 
        REFERENCES dim_geografia(entidad_id, municipio_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_dim_clues_institucion ON dim_clues(institucion);
CREATE INDEX IF NOT EXISTS idx_dim_clues_geo ON dim_clues(entidad_id, municipio_id);

-- ============================================================================
-- 2. FACT TABLE
-- ============================================================================

-- 2.1 FACT EGRESOS HOSPITALARIOS (Hospital Discharges microdata)
CREATE TABLE IF NOT EXISTS fact_egresos_hospitalarios (
    id_egreso UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    
    -- Dimension Foreign Keys
    clues_establecimiento_id VARCHAR(20) NOT NULL,
    diagnostico_principal_cie10 VARCHAR(10) NOT NULL,
    fecha_ingreso_id INT NOT NULL,
    fecha_egreso_id INT NOT NULL,
    sexo_id INT NOT NULL,
    procedencia_id INT NOT NULL,
    tipo_ingreso_id INT NOT NULL,
    tipo_egreso_id INT NOT NULL,
    motivo_egreso_id INT NOT NULL,
    
    -- Degenerate Dimensions & Demographics
    edad_anios INT NOT NULL,
    
    -- Metrics / Numerical measures
    dias_estancia INT NOT NULL, -- ALOS (Average Length of Stay) numerator
    horas_estancia INT NULL,
    costo_estimado NUMERIC(12,2) NULL,
    
    -- Flags
    esta_complicado BOOLEAN DEFAULT FALSE,
    
    -- Data Quality Check Constraints (Capa 3: Database Integrity)
    CONSTRAINT chk_edad_valida CHECK (edad_anios >= 0 AND edad_anios <= 120),
    CONSTRAINT chk_dias_estancia_valida CHECK (dias_estancia >= 0),
    CONSTRAINT chk_fechas_consistentes CHECK (fecha_egreso_id >= fecha_ingreso_id),
    
    -- Foreign Key Constraints
    CONSTRAINT fk_fact_egresos_clues FOREIGN KEY (clues_establecimiento_id)
        REFERENCES dim_clues(clues_id) ON DELETE RESTRICT,
        
    CONSTRAINT fk_fact_egresos_cie10 FOREIGN KEY (diagnostico_principal_cie10)
        REFERENCES dim_cie10(codigo_cie10) ON DELETE RESTRICT,
        
    CONSTRAINT fk_fact_egresos_fecha_ingreso FOREIGN KEY (fecha_ingreso_id)
        REFERENCES dim_fecha(fecha_id) ON DELETE RESTRICT,
        
    CONSTRAINT fk_fact_egresos_fecha_egreso FOREIGN KEY (fecha_egreso_id)
        REFERENCES dim_fecha(fecha_id) ON DELETE RESTRICT,
        
    CONSTRAINT fk_fact_egresos_sexo FOREIGN KEY (sexo_id)
        REFERENCES dim_sexo(sexo_id) ON DELETE RESTRICT,
        
    CONSTRAINT fk_fact_egresos_procedencia FOREIGN KEY (procedencia_id)
        REFERENCES dim_procedencia(procedencia_id) ON DELETE RESTRICT,
        
    CONSTRAINT fk_fact_egresos_tipo_ingreso FOREIGN KEY (tipo_ingreso_id)
        REFERENCES dim_tipo_ingreso(tipo_ingreso_id) ON DELETE RESTRICT,
        
    CONSTRAINT fk_fact_egresos_tipo_egreso FOREIGN KEY (tipo_egreso_id)
        REFERENCES dim_tipo_egreso(tipo_egreso_id) ON DELETE RESTRICT,
        
    CONSTRAINT fk_fact_egresos_motivo_egreso FOREIGN KEY (motivo_egreso_id)
        REFERENCES dim_motivo_egreso(motivo_egreso_id) ON DELETE RESTRICT
);

-- ============================================================================
-- 3. INDEXES & OPTIMIZATIONS
-- ============================================================================

-- B-Tree indexes on crucial foreign keys for star query joins
CREATE INDEX IF NOT EXISTS idx_fact_egresos_clues ON fact_egresos_hospitalarios(clues_establecimiento_id);
CREATE INDEX IF NOT EXISTS idx_fact_egresos_cie10 ON fact_egresos_hospitalarios(diagnostico_principal_cie10);
CREATE INDEX IF NOT EXISTS idx_fact_egresos_fecha_ingreso ON fact_egresos_hospitalarios(fecha_ingreso_id);
CREATE INDEX IF NOT EXISTS idx_fact_egresos_fecha_egreso ON fact_egresos_hospitalarios(fecha_egreso_id);
CREATE INDEX IF NOT EXISTS idx_fact_egresos_sexo ON fact_egresos_hospitalarios(sexo_id);

-- Multi-column index for common group-by slices in BI reports
CREATE INDEX IF NOT EXISTS idx_fact_egresos_composite_report 
ON fact_egresos_hospitalarios(fecha_egreso_id, clues_establecimiento_id, diagnostico_principal_cie10);

-- ============================================================================
-- 4. STAGING TABLES (STG - TRUNCATE AND LOAD INTERMEDIARY LAYER)
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS staging;

-- Raw SAEH Ingestion Staging
CREATE TABLE IF NOT EXISTS staging.stg_saeh (
    clues VARCHAR(100),
    fecha_ingreso VARCHAR(50),
    fecha_egreso VARCHAR(50),
    diagnostico VARCHAR(20),
    edad VARCHAR(10),
    sexo VARCHAR(10),
    procedencia VARCHAR(10),
    tipo_ingreso VARCHAR(10),
    tipo_egreso VARCHAR(10),
    motivo_egreso VARCHAR(10),
    dias_estancia VARCHAR(10),
    horas_estancia VARCHAR(10),
    complicacion VARCHAR(10)
);

-- Raw CLUES Ingestion Staging
CREATE TABLE IF NOT EXISTS staging.stg_clues (
    clues_id VARCHAR(50),
    nombre_unidad VARCHAR(300),
    entidad_id VARCHAR(10),
    municipio_id VARCHAR(10),
    localidad VARCHAR(300),
    jurisdiccion VARCHAR(200),
    institucion VARCHAR(200),
    tipologia VARCHAR(200),
    estado_operacion VARCHAR(100),
    camas_sensibles VARCHAR(10),
    camas_no_sensibles VARCHAR(10),
    consultorios VARCHAR(10),
    quirofanos VARCHAR(10),
    total_medicos VARCHAR(10),
    total_enfermeras VARCHAR(10)
);
