"""
scripts/explore_catalogs.py
Explora los catálogos DGIS descargados y extrae la estructura para poblar las dim_* del DW.
"""
import sys, os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path = [p for p in sys.path if p != project_root]

import pandas as pd

CAT_DIR = os.path.join(project_root, "data_raw", "saeh", "2023", "Catálogos")

# Fallback si el encoding de la carpeta no coincide
if not os.path.exists(CAT_DIR):
    # Buscar la carpeta real
    parent = os.path.join(project_root, "data_raw", "saeh", "2023")
    for d in os.listdir(parent):
        if d.lower().startswith("cat"):
            CAT_DIR = os.path.join(parent, d)
            break

print(f"Directorio de catálogos: {CAT_DIR}")
print(f"{'='*70}")

# Explorar cada catálogo
catalogs = sorted(os.listdir(CAT_DIR))
for fname in catalogs:
    fpath = os.path.join(CAT_DIR, fname)
    if not fname.endswith(".csv"):
        continue

    try:
        df = pd.read_csv(fpath, encoding="latin-1", dtype=str, nrows=50)
    except Exception:
        try:
            df = pd.read_csv(fpath, encoding="utf-8", dtype=str, nrows=50)
        except Exception as e:
            print(f"\n[ERROR] {fname}: {e}")
            continue

    print(f"\n{'='*70}")
    print(f"[CAT] {fname}  ({len(df)} filas cargadas, cols: {list(df.columns)})")
    print(f"{'='*70}")

    if len(df) <= 20:
        print(df.to_string(index=False))
    else:
        print(df.head(10).to_string(index=False))
        print(f"  ... ({len(df)} filas total en preview)")

# Explorar el descriptor Excel
print(f"\n{'='*70}")
print("[CAT] DESCRIPTOR (Layout)")
print(f"{'='*70}")
desc_path = os.path.join(project_root, "data_raw", "saeh", "2023",
                          "ssa_Descriptores_Bases_de_Datos_EGRESOS_2023_2025.xlsx")
if os.path.exists(desc_path):
    xls = pd.ExcelFile(desc_path, engine="openpyxl")
    print(f"Hojas: {xls.sheet_names}")
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        print(f"\n--- Hoja: {sheet} ({df.shape}) ---")
        print(f"Columnas: {list(df.columns)}")
        print(df.head(15).to_string(index=False))
else:
    print(f"[WARN] No encontrado: {desc_path}")

print("\n[OK] Exploración de catálogos completada.")
