import os
import re
import numpy as np
import pandas as pd
from dagster import (
    AssetExecutionContext,
    MetadataValue,
    asset,
    asset_check,
    AssetCheckResult
)

# ============================================================================
# HEALTH CHECK & CONSTANTS
# ============================================================================
DATA_DIR = os.getenv("SSA_DATA_DIR", "./data_raw")
DB_CONN_STRING = os.getenv("DATABASE_URL", "postgresql://postgres_user:postgres_pass@localhost:5432/saludmx_dw")
_docker_host = os.getenv("DAGSTER_POSTGRES_HOST")
if _docker_host:
    DB_CONN_STRING = DB_CONN_STRING.replace("localhost", _docker_host).replace("127.0.0.1", _docker_host)

# ============================================================================
# 1. INGESTION ASSETS (Raw Extraction Layer)
# ============================================================================

@asset(
    group_name="ingest",
    description="Loads raw SAEH (Discharges) CSV file, resolving LATIN-1 / ISO-8859-1 encodings and returning a clean Pandas DataFrame structure.",
)
def raw_saeh_data(context: AssetExecutionContext) -> pd.DataFrame:
    """
    Ingesta cruda de los microdatos del Subsistema de Egresos Hospitalarios (SAEH).
    Desafío Técnico Resuelto: Encodings heredados y detección de tipos crudos.
    """
    file_path = os.path.join(DATA_DIR, "saeh_raw_current.csv")
    
    # Simulación/Fallback para demostración estructural si el archivo no existe
    if not os.path.exists(file_path):
        context.log.warning(f"File {file_path} not found. Generating structurally correct Mock Data for initial build validation.")
        mock_data = pd.DataFrame({
            "clues": ["DFSSA000154", "MEX0214512", "  /  /  ", "DFSSA000154"],
            "fecha_ingreso": ["2023-12-25", "25/12/2023", "20231225", "  /  /    "],
            "fecha_egreso": ["2023-12-30", "30/12/2023", "20231230", "30/12/2023"],
            "diagnostico": ["A09X", "J189", "U071", "A09X"],
            "edad": ["45", "72", "NE", "15"],
            "sexo": ["1", "2", "9", "1"],
            "procedencia": ["1", "2", "9", "1"],
            "tipo_ingreso": ["1", "2", "9", "1"],
            "tipo_egreso": ["1", "2", "9", "1"],
            "motivo_egreso": ["1", "2", "9", "1"],
            "dias_estancia": ["5", "7", "  ", "3"],
            "horas_estancia": ["120", "168", "0", "72"],
            "complicacion": ["0", "1", "9", "0"]
        })
        context.add_output_metadata(
            metadata={
                "row_count": len(mock_data),
                "encoding_fallback": "mock_generation",
                "preview": MetadataValue.md(mock_data.head(2).to_markdown())
            }
        )
        return mock_data

    # Carga de archivo real con enconding tradicional de la Secretaría de Salud
    # low_memory=False previene alertas de tipo mixto
    df = pd.read_csv(file_path, encoding="latin-1", dtype=str, low_memory=False)
    
    context.log.info(f"Successfully loaded {len(df)} rows with Latin-1 encoding.")
    context.add_output_metadata(
        metadata={
            "row_count": len(df),
            "columns": list(df.columns),
            "encoding_used": "latin-1"
        }
    )
    return df


@asset(
    group_name="ingest",
    description="Loads Clave Única de Establecimientos de Salud (CLUES) master catalog, dealing with Latin-1 encoding and trimmings.",
)
def raw_clues_catalog(context: AssetExecutionContext) -> pd.DataFrame:
    """
    Ingesta del catálogo nacional maestro de CLUES.
    Contiene la tipología, institución y recursos reportados.
    """
    file_path = os.path.join(DATA_DIR, "clues_master.csv")
    
    if not os.path.exists(file_path):
        context.log.warning(f"File {file_path} not found. Generating structurally correct Mock Data.")
        mock_data = pd.DataFrame({
            "clues_id": ["DFSSA000154", "MEX0214512"],
            "nombre_unidad": ["HOSPITAL GENERAL DE MÉXICO", "CENTRO DE SALUD SANTA FE"],
            "entidad_id": ["9", "15"], # Ceros perdidos a propósito para la prueba de limpieza
            "municipio_id": ["15", "1"],
            "localidad": ["Cuauhtémoc", "Alvaro Obregón"],
            "jurisdiccion": ["Jurisdicción I", "Jurisdicción III"],
            "institucion": ["SSA", "IMSS-BIENESTAR"],
            "tipologia": ["Hospital General", "Unidad de Primer Contacto"],
            "estado_operacion": ["ACTIVO", "ACTIVO"],
            "camas_sensibles": ["120", "0"],
            "camas_no_sensibles": ["40", "5"],
            "consultorios": ["30", "4"],
            "quirofanos": ["6", "0"],
            "total_medicos": ["150", "3"],
            "total_enfermeras": ["280", "5"]
        })
        return mock_data

    df = pd.read_csv(file_path, encoding="latin-1", dtype=str, low_memory=False)
    return df


# ============================================================================
# 2. TRANSFORM & CLEANING ASSETS (Business Logic & Standardization)
# ============================================================================

@asset(
    group_name="clean",
    description="Performs severe cleaning on SAEH: Multi-format Date parsing, numeric padding, custom NULL representation coercion.",
)
def clean_saeh_discharges(context: AssetExecutionContext, raw_saeh_data: pd.DataFrame) -> pd.DataFrame:
    """
    Normalización del microdato SAEH.
    Aplica lógica robusta para:
    1. Parseo coercitivo de fechas (DD/MM/YYYY, YYYY-MM-DD, e ints YYYYMMDD).
    2. Manejo de valores nulos ocultos ('99', 'NE', '  /  /    ').
    3. Conversión de campos numéricos con seguridad en tipos de datos.
    """
    df = raw_saeh_data.copy()
    context.log.info("Starting normalization of SAEH data...")

    # A. Función local para normalizar fechas con formatos mixtos e inconsistentes
    def parse_ssa_date(series):
        # 1. Limpieza de espacios en blanco y strings nulos habituales de la SSA
        cleaned = series.astype(str).str.strip()
        cleaned = cleaned.replace([r'^\s*/\s*/\s*$', r'^nan$', r'^None$', r'^\s*$'], np.nan, regex=True)
        
        # 2. Intento de parsear múltiples formatos comunes
        # format='mixed' disponible en Pandas 2.0+
        parsed = pd.to_datetime(cleaned, errors='coerce', format='mixed')
        return parsed

    # Aplicar transformación a fechas
    df['fecha_ingreso'] = parse_ssa_date(df['fecha_ingreso'])
    df['fecha_egreso'] = parse_ssa_date(df['fecha_egreso'])

    # B. Limpieza de strings textuales y encodings que hayan pasado
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
        # Normalizar caracteres con acentos o diéresis a formato estándar ASCII (e.g. MÉXICO -> MEXICO)
        df[col] = df[col].str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8').str.upper()

    # C. Manejo de Nulos Numéricos y Códigos por Defecto ('99', 'NE', '9')
    # Reemplazamos códigos que SSA usa para 'No Especificado' por NaN reales para el DW
    null_mappings = {
        'sexo': {'9': np.nan, 'NE': np.nan},
        'procedencia': {'9': np.nan, 'NE': np.nan},
        'tipo_ingreso': {'9': np.nan, 'NE': np.nan},
        'tipo_egreso': {'9': np.nan, 'NE': np.nan},
        'motivo_egreso': {'9': np.nan, 'NE': np.nan},
        'edad': {'NE': np.nan, '999': np.nan},
        'dias_estancia': {'': np.nan, ' ': np.nan, 'NE': np.nan}
    }
    
    for col, mapping in null_mappings.items():
        if col in df.columns:
            df[col] = df[col].replace(mapping)

    # D. Conversión Segura de Tipos de Datos (Coerce integers)
    numeric_cols = ['edad', 'dias_estancia', 'horas_estancia']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    # E. Derivación de Bandera Analítica (esta_complicado)
    # Por ejemplo, si complicacion == 1 o dias de estancia superan 14 (indicador de complejidad)
    if 'complicacion' in df.columns:
        df['esta_complicado'] = (df['complicacion'] == '1') | (df['dias_estancia'] > 14)
    else:
        df['esta_complicado'] = df['dias_estancia'] > 14

    # F. Eliminación de renglones inviables (e.g. sin CLUES válido o sin fecha de egreso)
    # Un CLUES válido debe contener al menos caracteres alfanuméricos (excluye "/  /", espacios, etc.)
    df = df.dropna(subset=['clues', 'fecha_egreso'])
    df = df[df['clues'].str.contains(r'[A-Z0-9]{5,}', na=False)]

    # F2. Rellenar IDs categóricos nulos con 9 (código SSA para "No Especificado")
    # El fact table tiene constraints NOT NULL, y 9 ya está en las dim tables de semilla
    cat_id_cols = ['sexo', 'procedencia', 'tipo_ingreso', 'tipo_egreso', 'motivo_egreso']
    for col in cat_id_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(9).astype(int)

    # G. Generación de claves de fechas en formato YYYYMMDD para modelo estrella
    df['fecha_ingreso_id'] = df['fecha_ingreso'].dt.strftime('%Y%m%d').fillna('0').astype(int)
    df['fecha_egreso_id'] = df['fecha_egreso'].dt.strftime('%Y%m%d').fillna('0').astype(int)

    # H. Renombrado para empalmar con el esquema de staging y el data warehouse
    df = df.rename(columns={
        'clues': 'clues_establecimiento_id',
        'diagnostico': 'diagnostico_principal_cie10',
        'sexo': 'sexo_id',
        'procedencia': 'procedencia_id',
        'tipo_ingreso': 'tipo_ingreso_id',
        'tipo_egreso': 'tipo_egreso_id',
        'motivo_egreso': 'motivo_egreso_id',
        'edad': 'edad_anios'
    })

    context.log.info(f"Finished cleaning. {len(df)} records are valid for dimensional modeling.")
    context.add_output_metadata(
        metadata={
            "valid_records": len(df),
            "invalid_records_dropped": len(raw_saeh_data) - len(df),
            "mean_length_of_stay": float(df['dias_estancia'].mean()) if 'dias_estancia' in df.columns else 0.0
        }
    )
    return df


@asset_check(asset=clean_saeh_discharges, description="Valida la integridad relacional y lógica de los datos de egresos.")
def check_saeh_data_quality(clean_saeh_discharges: pd.DataFrame) -> AssetCheckResult:
    """Verifica reglas de calidad de datos en los egresos hospitalarios limpios (Capa 2 DQ)."""
    
    # 1. No debe haber IDs de CLUES nulos
    clues_nulos = int(clean_saeh_discharges["clues_establecimiento_id"].isna().sum())
    
    # 2. Las estancias no pueden ser negativas
    estancias_negativas = int((clean_saeh_discharges.get("dias_estancia", pd.Series([0])) < 0).sum())
    
    # 3. La fecha de ingreso no puede ser posterior a la de egreso
    if "fecha_ingreso" in clean_saeh_discharges.columns and "fecha_egreso" in clean_saeh_discharges.columns:
        fechas_invertidas = int((clean_saeh_discharges["fecha_ingreso"] > clean_saeh_discharges["fecha_egreso"]).sum())
    else:
        fechas_invertidas = 0
        
    success = (clues_nulos == 0) and (estancias_negativas == 0) and (fechas_invertidas == 0)
    
    return AssetCheckResult(
        passed=bool(success),
        metadata={
            "clues_nulos": clues_nulos,
            "estancias_negativas": estancias_negativas,
            "fechas_invertidas": fechas_invertidas
        }
    )


@asset(
    group_name="clean",
    description="Cleans CLUES catalog ensuring padding of geography IDs",
)
def clean_clues_catalog(context: AssetExecutionContext, raw_clues_catalog: pd.DataFrame) -> pd.DataFrame:
    """
    Lógica de limpieza del catálogo de CLUES.
    Punto crítico resuelto: Preservación de ceros a la izquierda en entidades y municipios
    (e.g., '9' -> '09' y '15' -> '015').
    """
    df = raw_clues_catalog.copy()

    # 1. Enforzar mayúsculas y remover espacios de la PK canónica CLUES
    df['clues_id'] = df['clues_id'].astype(str).str.strip().str.upper()

    # 2. Rescate crítico de códigos geográficos (zfill de longitud estándar de INEGI / DGIS)
    # Entidad federativa siempre tiene 2 dígitos (01 a 32)
    # Municipio siempre tiene 3 dígitos (001 a 570+)
    df['entidad_id'] = df['entidad_id'].astype(str).str.strip().replace(r'\.0$', '', regex=True).str.zfill(2)
    df['municipio_id'] = df['municipio_id'].astype(str).str.strip().replace(r'\.0$', '', regex=True).str.zfill(3)

    # 3. Limpieza de campos de texto
    text_cols = ['nombre_unidad', 'localidad', 'jurisdiccion', 'institucion', 'tipologia', 'estado_operacion']
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8').str.upper()

    # 4. Sanitización de métricas de recursos
    resource_cols = [
        'camas_sensibles', 'camas_no_sensibles', 'consultorios', 
        'quirofanos', 'total_medicos', 'total_enfermeras'
    ]
    for col in resource_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    context.log.info(f"Finished normalising CLUES catalog. Total active units: {len(df)}")
    return df


# ============================================================================
# 3. MODELING & DATA WAREHOUSE LOADING ASSETS (Postgres Layer)
# ============================================================================

@asset(
    group_name="load",
    description="Loads sanitized staging tables into Postgres and executes transactional upsert routines to update the Star Schema.",
)
def load_data_warehouse(context: AssetExecutionContext, clean_saeh_discharges: pd.DataFrame, clean_clues_catalog: pd.DataFrame):
    clean_saeh = clean_saeh_discharges.copy()
    clean_clues = clean_clues_catalog.copy()
    from sqlalchemy import create_engine, text
    context.log.info("Connecting to Postgres Data Warehouse...")

    # Coerce categorical string IDs to nullable integers before writing to staging.
    # This ensures Postgres receives proper int columns, not text.
    int_id_cols = ['sexo_id', 'procedencia_id', 'tipo_ingreso_id', 'tipo_egreso_id', 'motivo_egreso_id']
    for col in int_id_cols:
        if col in clean_saeh.columns:
            clean_saeh[col] = pd.to_numeric(clean_saeh[col], errors='coerce').astype('Int64')

    engine = create_engine(DB_CONN_STRING)
    
    with engine.begin() as conn:
        conn.execute(text("SET search_path TO core, public;"))
        context.log.info("1. Loading raw DataFrames to Staging schema...")
        clean_clues.to_sql('stg_clues', con=conn, schema='staging', if_exists='replace', index=False)
        clean_saeh.to_sql('stg_saeh', con=conn, schema='staging', if_exists='replace', index=False)
        
        context.log.info("2. Seeding static dimensions & inferring missing dimensions...")
        
        # Seed small static dimensions (SSA catalog codes)
        conn.execute(text("""
            INSERT INTO dim_sexo (sexo_id, descripcion_sexo) VALUES
                (1, 'MASCULINO'), (2, 'FEMENINO'), (9, 'NO ESPECIFICADO')
            ON CONFLICT (sexo_id) DO NOTHING;
        """))
        conn.execute(text("""
            INSERT INTO dim_procedencia (procedencia_id, descripcion_procedencia) VALUES
                (1, 'URGENCIAS'), (2, 'CONSULTA EXTERNA'), (3, 'OTRO HOSPITAL'), (9, 'NO ESPECIFICADO')
            ON CONFLICT (procedencia_id) DO NOTHING;
        """))
        conn.execute(text("""
            INSERT INTO dim_tipo_ingreso (tipo_ingreso_id, descripcion_tipo_ingreso) VALUES
                (1, 'PROGRAMADO'), (2, 'URGENCIA'), (3, 'OTRO'), (9, 'NO ESPECIFICADO')
            ON CONFLICT (tipo_ingreso_id) DO NOTHING;
        """))
        conn.execute(text("""
            INSERT INTO dim_tipo_egreso (tipo_egreso_id, descripcion_tipo_egreso) VALUES
                (1, 'CURACION'), (2, 'MEJORIA'), (3, 'VOLUNTARIO'), (4, 'PASE A OTRO HOSPITAL'),
                (5, 'DEFUNCION'), (6, 'OTRO'), (9, 'NO ESPECIFICADO')
            ON CONFLICT (tipo_egreso_id) DO NOTHING;
        """))
        conn.execute(text("""
            INSERT INTO dim_motivo_egreso (motivo_egreso_id, descripcion_motivo) VALUES
                (1, 'CURACION'), (2, 'MEJORIA'), (3, 'VOLUNTARIO'), (4, 'PASE A OTRO HOSPITAL'),
                (5, 'DEFUNCION'), (6, 'OTRO'), (9, 'NO ESPECIFICADO')
            ON CONFLICT (motivo_egreso_id) DO NOTHING;
        """))

        # Infer Geography
        conn.execute(text("""
            INSERT INTO dim_geografia (entidad_id, municipio_id, nombre_entidad, nombre_municipio)
            SELECT DISTINCT entidad_id, municipio_id, 'Desconocido', 'Desconocido'
            FROM staging.stg_clues
            ON CONFLICT (entidad_id, municipio_id) DO NOTHING;
        """))
        
        # Infer CIE-10
        conn.execute(text("""
            INSERT INTO dim_cie10 (codigo_cie10, descripcion)
            SELECT DISTINCT diagnostico_principal_cie10, 'Inferred/Desconocido'
            FROM staging.stg_saeh
            ON CONFLICT (codigo_cie10) DO NOTHING;
        """))
        
        # Infer Dates
        conn.execute(text("""
            INSERT INTO dim_fecha (fecha_id, fecha, anio, mes, mes_nombre, dia, dia_semana, dia_semana_nombre, trimestre, es_fin_semana)
            SELECT DISTINCT 
                fecha_ingreso_id, 
                TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD'),
                EXTRACT(YEAR FROM TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD')),
                EXTRACT(MONTH FROM TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD')),
                'Mes ' || EXTRACT(MONTH FROM TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD')),
                EXTRACT(DAY FROM TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD')),
                EXTRACT(ISODOW FROM TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD')),
                'Dia ' || EXTRACT(ISODOW FROM TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD')),
                EXTRACT(QUARTER FROM TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD')),
                EXTRACT(ISODOW FROM TO_DATE(fecha_ingreso_id::text, 'YYYYMMDD')) IN (6,7)
            FROM staging.stg_saeh
            WHERE fecha_ingreso_id > 0
            ON CONFLICT (fecha_id) DO NOTHING;
        """))
        conn.execute(text("""
            INSERT INTO dim_fecha (fecha_id, fecha, anio, mes, mes_nombre, dia, dia_semana, dia_semana_nombre, trimestre, es_fin_semana)
            SELECT DISTINCT 
                fecha_egreso_id, 
                TO_DATE(fecha_egreso_id::text, 'YYYYMMDD'),
                EXTRACT(YEAR FROM TO_DATE(fecha_egreso_id::text, 'YYYYMMDD')),
                EXTRACT(MONTH FROM TO_DATE(fecha_egreso_id::text, 'YYYYMMDD')),
                'Mes ' || EXTRACT(MONTH FROM TO_DATE(fecha_egreso_id::text, 'YYYYMMDD')),
                EXTRACT(DAY FROM TO_DATE(fecha_egreso_id::text, 'YYYYMMDD')),
                EXTRACT(ISODOW FROM TO_DATE(fecha_egreso_id::text, 'YYYYMMDD')),
                'Dia ' || EXTRACT(ISODOW FROM TO_DATE(fecha_egreso_id::text, 'YYYYMMDD')),
                EXTRACT(QUARTER FROM TO_DATE(fecha_egreso_id::text, 'YYYYMMDD')),
                EXTRACT(ISODOW FROM TO_DATE(fecha_egreso_id::text, 'YYYYMMDD')) IN (6,7)
            FROM staging.stg_saeh
            WHERE fecha_egreso_id > 0
            ON CONFLICT (fecha_id) DO NOTHING;
        """))
        
        context.log.info("3. Upserting Dimensions (CLUES)...")
        conn.execute(text("""
            INSERT INTO dim_clues (
                clues_id, nombre_unidad, entidad_id, municipio_id, localidad,
                jurisdiccion, institucion, tipologia, estado_operacion,
                camas_sensibles, camas_no_sensibles, consultorios, quirofanos,
                total_medicos, total_enfermeras
            )
            SELECT 
                clues_id, nombre_unidad, entidad_id, municipio_id, localidad,
                jurisdiccion, institucion, tipologia, estado_operacion,
                camas_sensibles, camas_no_sensibles, consultorios, quirofanos,
                total_medicos, total_enfermeras
            FROM staging.stg_clues
            ON CONFLICT (clues_id) DO UPDATE SET
                nombre_unidad = EXCLUDED.nombre_unidad,
                estado_operacion = EXCLUDED.estado_operacion,
                camas_sensibles = EXCLUDED.camas_sensibles,
                total_medicos = EXCLUDED.total_medicos,
                total_enfermeras = EXCLUDED.total_enfermeras;
        """))
        
        context.log.info("4. Inserting Facts (Egresos)...")
        conn.execute(text("""
            INSERT INTO fact_egresos_hospitalarios (
                clues_establecimiento_id, diagnostico_principal_cie10,
                fecha_ingreso_id, fecha_egreso_id,
                sexo_id, procedencia_id, tipo_ingreso_id, tipo_egreso_id,
                motivo_egreso_id,
                edad_anios, dias_estancia, horas_estancia, esta_complicado
            )
            SELECT 
                s.clues_establecimiento_id, s.diagnostico_principal_cie10,
                s.fecha_ingreso_id, s.fecha_egreso_id,
                s.sexo_id, s.procedencia_id, s.tipo_ingreso_id, s.tipo_egreso_id,
                s.motivo_egreso_id,
                s.edad_anios, s.dias_estancia, s.horas_estancia, s.esta_complicado
            FROM staging.stg_saeh s
            WHERE s.fecha_ingreso_id > 0 AND s.fecha_egreso_id > 0
        """))
        
    context.add_output_metadata(
        metadata={
            "staging_saeh_rows_inserted": len(clean_saeh),
            "staging_clues_rows_inserted": len(clean_clues),
            "status": "SUCCESFULLY_LOADED_TO_POSTGRES"
        }
    )
    return True
