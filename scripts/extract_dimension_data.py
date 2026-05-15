"""
scripts/extract_dimension_data.py
Lee los catálogos DGIS descargados y los imprime de forma estructurada
para mapear directamente a las dim_* del Star Schema.
"""
import sys, os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path = [p for p in sys.path if p != project_root]
import pandas as pd

CAT_DIR = os.path.join(project_root, "data_raw", "saeh", "2023")
# Encontrar carpeta de catalogos (nombre puede tener acentos)
for d in os.listdir(CAT_DIR):
    if d.lower().startswith("cat") and os.path.isdir(os.path.join(CAT_DIR, d)):
        CAT_DIR = os.path.join(CAT_DIR, d)
        break

def read_cat(name):
    path = os.path.join(CAT_DIR, name)
    for enc in ["latin-1", "utf-8", "cp1252"]:
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except Exception:
            continue
    return None

print("=" * 70)
print("DIMENSION MAPS FROM DGIS OFFICIAL CATALOGS")
print("=" * 70)

# 1. SEXO -> dim_sexo
print("\n--- CATSEXO.csv -> dim_sexo ---")
df = read_cat("CATSEXO.csv")
if df is not None:
    print(df.to_string(index=False))

# 2. MOTIVO EGRESO -> dim_motivo_egreso
print("\n--- CATMOTEGRESO.csv -> dim_motivo_egreso ---")
df = read_cat("CATMOTEGRESO.csv")
if df is not None:
    print(df.to_string(index=False))

# 3. PROCEDENCIA -> dim_procedencia
print("\n--- CATPROCEDENCIA.csv -> dim_procedencia ---")
df = read_cat("CATPROCEDENCIA.csv")
if df is not None:
    print(df.to_string(index=False))

# 4. TIPO SERVICIO -> dim_tipo_ingreso
print("\n--- CATTIPOSERV.csv -> dim_tipo_ingreso ---")
df = read_cat("CATTIPOSERV.csv")
if df is not None:
    print(df.to_string(index=False))

# 5. TIPO ATENCION
print("\n--- CATTIPOATEN.csv ---")
df = read_cat("CATTIPOATEN.csv")
if df is not None:
    print(df.to_string(index=False))

# 6. DERECHOHABIENTE
print("\n--- CATDEREC.csv ---")
df = read_cat("CATDEREC.csv")
if df is not None:
    print(df.to_string(index=False))

# 7. ENTIDAD -> dim_geografia (parcial)
print("\n--- CATENTIDADRES.csv -> dim_geografia (entidades) ---")
df = read_cat("CATENTIDADRES.csv")
if df is not None:
    print(df.to_string(index=False))

# 8. VEZ (primera vez vs subsecuente)
print("\n--- CATVEZ.csv ---")
df = read_cat("CATVEZ.csv")
if df is not None:
    print(df.to_string(index=False))

# 9. TIPO EDAD
print("\n--- CATTIPOEDAD.csv ---")
df = read_cat("CATTIPOEDAD.csv")
if df is not None:
    print(df.to_string(index=False))

# 10. CIE-10 (primeras 20 filas)
print("\n--- CAT_CIE_10_2021.csv -> dim_cie10 (top 20) ---")
df = read_cat("CAT_CIE_10_2021.csv")
if df is not None:
    print(f"Columnas: {list(df.columns)}")
    print(f"Total: {len(df)} codigos")
    print(df.head(20).to_string(index=False))

# 11. CLUES (estructura)
print("\n--- CATCLUES.csv -> dim_clues (estructura, top 5) ---")
df = read_cat("CATCLUES.csv")
if df is not None:
    print(f"Columnas ({len(df.columns)}): {list(df.columns)}")
    print(f"Total: {len(df)} establecimientos")
    print(df.head(5).to_string(index=False))

# 12. SERVICIOS
print("\n--- CATSERVICIOS.csv ---")
df = read_cat("CATSERVICIOS.csv")
if df is not None:
    print(df.to_string(index=False))

# 13. PLAN FAMILIAR
print("\n--- CATPLANFAM.csv ---")
df = read_cat("CATPLANFAM.csv")
if df is not None:
    print(df.to_string(index=False))

print("\n[OK] Dimension data extracted.")
