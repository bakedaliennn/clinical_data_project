"""Definitions de Dagster para SaludMX Analytics Pipeline."""
from __future__ import annotations

import os

from dagster import (
    AssetSelection,
    Definitions,
    define_asset_job,
    load_assets_from_modules,
)

import dagster_assets as assets_module
import sys
sys.path.append(os.path.dirname(__file__))
from resources import (
    SaludMxPathsResource,
    SaludMxPostgresResource,
)

# ── Jobs ──────────────────────────────────────────────────────────────────────

all_assets = load_assets_from_modules([assets_module])

ingest_job = define_asset_job(
    name="ingest_job",
    description="Extrae los archivos crudos de la SSA (SAEH + CLUES) a DataFrames.",
    selection=AssetSelection.groups("ingest"),
)

clean_job = define_asset_job(
    name="clean_job",
    description="Limpia y normaliza microdatos SAEH y catálogo CLUES.",
    selection=AssetSelection.groups("clean"),
)

full_etl_job = define_asset_job(
    name="full_etl_job",
    description="Pipeline E2E: Ingesta → Limpieza → Carga al Data Warehouse.",
    selection=AssetSelection.all(),
)

# ── Definitions ───────────────────────────────────────────────────────────────

defs = Definitions(
    assets=all_assets,
    jobs=[ingest_job, clean_job, full_etl_job],
    resources={
        "postgres": SaludMxPostgresResource(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://saludmx_user:saludmx_pass@localhost:5432/saludmx_dw",
            )
        ),
        "paths": SaludMxPathsResource(
            ssa_data_dir=os.getenv("SSA_DATA_DIR", "./data_raw"),
            pipeline_logs_dir=os.getenv("PIPELINE_LOGS_DIR", "./logs"),
        ),
    },
)
