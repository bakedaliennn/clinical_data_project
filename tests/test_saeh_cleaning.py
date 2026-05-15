import numpy as np
import pandas as pd
import pytest

from dagster_assets import _mask_ssa_nulls, _parse_ssa_date

def test_mask_ssa_nulls():
    # Setup un dataframe con la basura típica de la SSA
    df = pd.DataFrame({
        "sexo": ["1", "2", "9", "99", "NE", "SE", "8888"],
        "edad": ["10", "45", "99", "120", "None", "", "nan"]
    })
    
    # Ejecutamos
    df_clean = _mask_ssa_nulls(df.copy(), ["sexo", "edad"])
    
    # Validamos
    # En sexo, "9", "99", "NE", "SE", "8888" son nulos implícitos
    assert pd.isna(df_clean.loc[2, "sexo"])
    assert pd.isna(df_clean.loc[3, "sexo"])
    assert pd.isna(df_clean.loc[4, "sexo"])
    
    # En edad
    assert df_clean.loc[0, "edad"] == "10"
    assert df_clean.loc[1, "edad"] == "45"
    assert pd.isna(df_clean.loc[2, "edad"]) # "99" suele ser nulo implícito configurado en SSA_NULLS

def test_parse_ssa_date_variations():
    # Fechas con distintos formatos que escupe la DGIS
    dates = pd.Series([
        "2023-01-15",     # ISO
        "15/01/2023",     # DD/MM/YYYY
        "15-01-2023",     # DD-MM-YYYY
        "  /  /    ",     # Basura literal
        "99/99/9999",     # Invalida extrema
        None
    ])
    
    dt_series = _parse_ssa_date(dates)
    
    # Verificar tipos
    assert pd.api.types.is_datetime64_any_dtype(dt_series)
    
    # Verificar conversiones válidas
    assert dt_series.iloc[0].year == 2023
    assert dt_series.iloc[1].month == 1
    assert dt_series.iloc[2].day == 15
    
    # Verificar manejos de errores -> NaT
    assert pd.isna(dt_series.iloc[3])
    assert pd.isna(dt_series.iloc[4])
    assert pd.isna(dt_series.iloc[5])
