import pandas as pd
import numpy as np
from platform.shared.data_cleaning import mask_ssa_nulls, parse_ssa_date, safe_cast_integer

def test_mask_ssa_nulls_converts_garbage():
    df = pd.DataFrame({
        "sexo": ["1", "2", "9", "99", "NE", "SE"],
        "edad": ["10", "45", "99", "120", "NE", ""]
    })
    
    df_clean = mask_ssa_nulls(df, ["sexo", "edad"])
    
    # "sexo" debe tener nulos reales
    assert pd.isna(df_clean.loc[2, "sexo"])  # "9"
    assert pd.isna(df_clean.loc[3, "sexo"])  # "99"
    assert pd.isna(df_clean.loc[4, "sexo"])  # "NE"
    
    # Valores válidos se mantienen (como string)
    assert df_clean.loc[0, "sexo"] == "1"

def test_parse_ssa_date_handles_all_formats():
    dates = pd.Series([
        "2023-01-15",     # ISO
        "15/01/2023",     # DD/MM/YYYY
        "15-01-2023",     # DD-MM-YYYY
        "  /  /    ",     # Espacios crudos DGIS
        "99/99/9999",     # Invalida extrema
        None
    ])
    
    dt_series = parse_ssa_date(dates)
    
    assert pd.api.types.is_datetime64_any_dtype(dt_series)
    assert dt_series.iloc[0].year == 2023
    assert dt_series.iloc[1].month == 1
    assert dt_series.iloc[2].day == 15
    
    # Las basuras se vuelven NaT
    assert pd.isna(dt_series.iloc[3])
    assert pd.isna(dt_series.iloc[4])

def test_safe_cast_integer_with_nans():
    series = pd.Series(["1", "2", "nan", None, "A"])
    cast_series = safe_cast_integer(series, default=-1)
    
    assert cast_series.iloc[0] == 1
    assert cast_series.iloc[2] == -1
    assert cast_series.iloc[4] == -1
