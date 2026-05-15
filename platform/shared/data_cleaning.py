import pandas as pd
import numpy as np

# Nulos explícitos utilizados por la DGIS en sus catálogos
SSA_NULLS_CATEGORICAL = {"9", "99", "999", "NE", "SE"}
SSA_NULLS_DATES = {"  /  /    ", "nan", "None", "", "NULL"}

def mask_ssa_nulls(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Convierte nulos implícitos de la Secretaría de Salud en np.nan puros.
    """
    df_clean = df.copy()
    for col in columns:
        if col in df_clean.columns:
            # Asegurar tipo string antes del replace estricto
            df_clean[col] = df_clean[col].astype(str).str.strip()
            df_clean[col] = df_clean[col].replace(list(SSA_NULLS_CATEGORICAL), np.nan)
    return df_clean

def parse_ssa_date(series: pd.Series) -> pd.Series:
    """
    Lógica blindada para parsear columnas de fechas con formatos mixtos, nulos e invertidos.
    """
    # 1. Strip y null coercion de la serie
    cleaned = series.astype(str).str.strip()
    cleaned = cleaned.replace([r'^\s*/\s*/\s*$', r'^nan$', r'^None$', r'^\s*$'], np.nan, regex=True)
    cleaned = cleaned.replace(list(SSA_NULLS_DATES), np.nan)
    
    # 2. To datetime (mixed types supported in pandas 2.x)
    parsed = pd.to_datetime(cleaned, errors='coerce', format='mixed')
    return parsed

def safe_cast_integer(series: pd.Series, default: int = 0) -> pd.Series:
    """
    Cast seguro de strings con nulos a enteros (útil para keys foráneas).
    """
    return pd.to_numeric(series, errors='coerce').fillna(default).astype(int)
