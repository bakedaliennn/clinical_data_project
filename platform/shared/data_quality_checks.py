"""
data_quality_checks.py
----------------------
Checks reutilizables de calidad de datos para pipelines del repo.

Objetivo:
- evitar que cada proyecto reimplemente las mismas validaciones de PK/FK;
- dejar un formato de resultados consistente para CSV, logs y gates;
- soportar pandas y polars sin forzar al dominio a cambiar de engine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
import polars as pl

DEFAULT_AUDIT_COLUMNS = frozenset(
    {
        "fecha_creacion",
        "fecha_actualizacion",
        "__fecha_procesado",
        "__fuente",
        "_source_file",
        "_report_date",
        "_file_date",
    }
)
STATUS_MARKERS = {
    "OK": "OK",
    "WARN": "!!",
    "FAIL": "XX",
    "INFO": "..",
}
STATUS_ORDER = ("FAIL", "WARN", "INFO", "OK")


@dataclass(frozen=True, slots=True)
class ValidationResult:
    table: str
    check: str
    status: str
    detail: str
    timestamp: str


class ValidationRecorder:
    """Acumula resultados de validacion y opcionalmente los imprime."""

    def __init__(self, *, echo: bool = True):
        self.echo = echo
        self._results: list[ValidationResult] = []

    def record(self, table: str, check: str, status: str, detail: str) -> ValidationResult:
        normalized_status = status.upper()
        if normalized_status not in STATUS_MARKERS:
            raise ValueError(f"Estado de validacion no soportado: {status}")

        result = ValidationResult(
            table=table,
            check=check,
            status=normalized_status,
            detail=detail,
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )
        self._results.append(result)

        if self.echo:
            marker = STATUS_MARKERS[normalized_status]
            print(f"  {marker} [{normalized_status}] {check}: {detail}")

        return result

    def to_frame(self) -> pd.DataFrame:
        if not self._results:
            return pd.DataFrame(columns=["table", "check", "status", "detail", "timestamp"])
        return pd.DataFrame(asdict(result) for result in self._results)

    def write_csv(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_csv(target, index=False, encoding="utf-8-sig")
        return target

    def count(self, status: str) -> int:
        normalized_status = status.upper()
        return sum(result.status == normalized_status for result in self._results)

    def counts_by_status(self) -> dict[str, int]:
        return {status: self.count(status) for status in STATUS_ORDER}

    def has_failures(self) -> bool:
        return self.count("FAIL") > 0


def ensure_pandas(df: pd.DataFrame | pl.DataFrame) -> pd.DataFrame:
    """Convierte Polars a pandas; pandas se devuelve como copia defensiva."""
    if isinstance(df, pd.DataFrame):
        return df.copy()
    if isinstance(df, pl.DataFrame):
        return df.to_pandas()
    raise TypeError(f"Tipo de DataFrame no soportado: {type(df)}")


def load_parquet(
    path: Path | str,
    *,
    recorder: ValidationRecorder | None = None,
    table_label: str | None = None,
) -> pd.DataFrame | None:
    """Carga un parquet y registra FAIL si falta o no puede leerse."""
    parquet_path = Path(path)
    label = table_label or parquet_path.name

    if not parquet_path.exists():
        if recorder is not None:
            recorder.record(label, "existencia_archivo", "FAIL", f"No encontrado: {parquet_path}")
        return None

    try:
        return pd.read_parquet(parquet_path)
    except Exception as exc:
        if recorder is not None:
            recorder.record(label, "lectura_parquet", "FAIL", str(exc))
        return None


def check_pk_unique(
    df: pd.DataFrame | pl.DataFrame,
    table: str,
    pk_cols: Sequence[str],
    recorder: ValidationRecorder,
) -> None:
    """Verifica nulos y duplicados en una clave primaria."""
    frame = ensure_pandas(df)
    missing = [column for column in pk_cols if column not in frame.columns]
    if missing:
        recorder.record(table, "pk_columnas_existen", "FAIL", f"Columnas PK no encontradas: {missing}")
        return

    null_rows = int(frame[list(pk_cols)].isna().any(axis=1).sum())
    if null_rows > 0:
        recorder.record(table, "pk_sin_nulos", "FAIL", f"{null_rows} fila(s) con nulo en PK {list(pk_cols)}")
    else:
        recorder.record(table, "pk_sin_nulos", "OK", f"PK {list(pk_cols)}: 0 nulos")

    duplicated_rows = int(frame.duplicated(subset=list(pk_cols), keep=False).sum())
    if duplicated_rows > 0:
        recorder.record(
            table,
            "pk_unicidad",
            "FAIL",
            f"{duplicated_rows} fila(s) duplicadas en PK {list(pk_cols)}",
        )
    else:
        recorder.record(
            table,
            "pk_unicidad",
            "OK",
            f"PK {list(pk_cols)}: {len(frame):,} filas unicas",
        )


def check_fk_referential(
    fact_df: pd.DataFrame | pl.DataFrame,
    fact_table: str,
    fk_col: str,
    dim_df: pd.DataFrame | pl.DataFrame,
    dim_pk: str,
    recorder: ValidationRecorder,
    *,
    accepted_orphans: int = 0,
    info_null_threshold_pct: float = 50.0,
) -> None:
    """
    Verifica que los valores no nulos de una FK existan en la dimension.

    accepted_orphans:
        Cantidad de valores huerfanos tolerados antes de escalar a FAIL.
    """
    fact = ensure_pandas(fact_df)
    dim = ensure_pandas(dim_df)
    check_name = f"fk_{fk_col}->{dim_pk}"

    if fk_col not in fact.columns:
        recorder.record(fact_table, check_name, "FAIL", f"Columna FK no existe: {fk_col}")
        return
    if dim_pk not in dim.columns:
        recorder.record(fact_table, check_name, "FAIL", f"Columna PK de dimension no existe: {dim_pk}")
        return

    fact_keys = set(fact[fk_col].dropna().unique())
    dim_keys = set(dim[dim_pk].dropna().unique())
    orphans = fact_keys - dim_keys
    null_fk = int(fact[fk_col].isna().sum())
    null_pct = round((null_fk / len(fact)) * 100, 1) if len(fact) > 0 else 0.0

    if orphans:
        sample = sorted(orphans)[:5]
        status = "WARN" if len(orphans) <= accepted_orphans else "FAIL"
        recorder.record(
            fact_table,
            check_name,
            status,
            f"{len(orphans)} valor(es) huerfano(s). Muestra: {sample}",
        )
    else:
        recorder.record(
            fact_table,
            check_name,
            "OK",
            f"0 huerfanos ({len(fact_keys):,} claves validas)",
        )

    if null_pct > 0:
        status = "INFO" if null_pct >= info_null_threshold_pct else "WARN"
        recorder.record(
            fact_table,
            f"fk_{fk_col}_nulos",
            status,
            f"{null_fk:,} nulos ({null_pct}%) en {fk_col}",
        )


def check_critical_nulls(
    df: pd.DataFrame | pl.DataFrame,
    table: str,
    critical_columns: Mapping[str, str | tuple[str, float]],
    recorder: ValidationRecorder,
    *,
    default_tolerance_pct: float = 5.0,
) -> None:
    """Reporta nulos en columnas criticas con tolerancia configurable."""
    frame = ensure_pandas(df)

    for column, spec in critical_columns.items():
        if isinstance(spec, tuple):
            justification, tolerance_pct = spec
        else:
            justification = spec
            tolerance_pct = default_tolerance_pct

        if column not in frame.columns:
            recorder.record(table, f"nulos_{column}", "WARN", "Columna no existe en tabla")
            continue

        null_count = int(frame[column].isna().sum())
        null_pct = round((null_count / len(frame)) * 100, 1) if len(frame) > 0 else 0.0

        if null_count == 0:
            recorder.record(table, f"nulos_{column}", "OK", f"0 nulos - {justification}")
        elif null_pct <= tolerance_pct:
            recorder.record(
                table,
                f"nulos_{column}",
                "WARN",
                f"{null_count:,} nulos ({null_pct}%) - {justification}",
            )
        else:
            recorder.record(
                table,
                f"nulos_{column}",
                "FAIL",
                f"{null_count:,} nulos ({null_pct}%) - {justification}",
            )


def check_numeric_range(
    df: pd.DataFrame | pl.DataFrame,
    table: str,
    column: str,
    recorder: ValidationRecorder,
    *,
    min_val: float | int | None = None,
    max_val: float | int | None = None,
) -> None:
    """Verifica que una columna numerica este dentro de un rango esperado."""
    frame = ensure_pandas(df)
    if column not in frame.columns:
        return

    series = pd.to_numeric(frame[column], errors="coerce").dropna()
    if series.empty:
        return

    out_of_range = 0
    detail_parts: list[str] = []

    if min_val is not None:
        below = int((series < min_val).sum())
        if below > 0:
            out_of_range += below
            detail_parts.append(f"{below} < {min_val}")

    if max_val is not None:
        above = int((series > max_val).sum())
        if above > 0:
            out_of_range += above
            detail_parts.append(f"{above} > {max_val}")

    if out_of_range > 0:
        recorder.record(
            table,
            f"rango_{column}",
            "WARN",
            f"{out_of_range} valor(es) fuera de rango: {'; '.join(detail_parts)}",
        )
    else:
        recorder.record(table, f"rango_{column}", "OK", f"Todos en [{min_val}, {max_val}]")


def check_column_count(
    df: pd.DataFrame | pl.DataFrame,
    table: str,
    recorder: ValidationRecorder,
    *,
    expected: int,
    tolerance: int = 3,
) -> None:
    """Alerta si una tabla tiene muchas mas columnas de las esperadas."""
    frame = ensure_pandas(df)
    actual = len(frame.columns)
    if actual > expected + tolerance:
        recorder.record(
            table,
            "conteo_columnas",
            "WARN",
            f"{actual} columnas (esperado ~{expected}). Posible inflado por joins",
        )
    else:
        recorder.record(table, "conteo_columnas", "OK", f"{actual} columnas (esperado ~{expected})")


def check_empty_business_rows(
    df: pd.DataFrame | pl.DataFrame,
    table: str,
    recorder: ValidationRecorder,
    *,
    audit_columns: set[str] | frozenset[str] = DEFAULT_AUDIT_COLUMNS,
) -> None:
    """Detecta filas donde todos los campos de negocio son nulos."""
    frame = ensure_pandas(df)
    business_columns = [column for column in frame.columns if column not in audit_columns]

    if not business_columns:
        recorder.record(table, "filas_vacias", "WARN", "No hay columnas de negocio para evaluar")
        return

    empty_rows = int(frame[business_columns].isna().all(axis=1).sum())
    if empty_rows > 0:
        recorder.record(
            table,
            "filas_vacias",
            "FAIL",
            f"{empty_rows:,} fila(s) con todos los campos de negocio nulos",
        )
    else:
        recorder.record(table, "filas_vacias", "OK", "0 filas completamente vacias")
