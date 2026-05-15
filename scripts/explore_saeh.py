"""
Exploración rápida del SAEH 2023.
Ejecutar desde la raíz del proyecto con:
    python scripts/explore_saeh.py
"""
import sys
import os

# Evitar colisión de 'platform/' del proyecto con stdlib 'platform'
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path = [p for p in sys.path if p != project_root]

import pandas as pd
import numpy as np

path = os.path.join(project_root, "data_raw", "saeh", "2023", "EGRESOS.txt")
print(f"Cargando {path}...")
df = pd.read_csv(path, encoding="latin-1", dtype=str, sep="|", low_memory=False)

# Quitar BOM
if df.columns[0].startswith("\ufeff"):
    df.rename(columns={df.columns[0]: df.columns[0].lstrip("\ufeff")}, inplace=True)

print(f"Shape: {df.shape}")
print(f"\n{'='*60}")
print(f"COLUMNAS ({len(df.columns)})")
print(f"{'='*60}")
print(list(df.columns))

print(f"\n{'='*60}")
print("DIAGNOSTICO PRINCIPAL (AFECPRIN) — Top 15")
print(f"{'='*60}")
print(df["AFECPRIN"].value_counts().head(15).to_string())

print(f"\n{'='*60}")
print("SEXO")
print(f"{'='*60}")
print(df["SEXO"].value_counts().to_string())

print(f"\n{'='*60}")
print("ENTIDAD — Top 10")
print(f"{'='*60}")
print(df["ENTIDAD"].value_counts().head(10).to_string())

print(f"\n{'='*60}")
print("DIAS_ESTA — Estadísticas")
print(f"{'='*60}")
dias = pd.to_numeric(df["DIAS_ESTA"], errors="coerce")
print(f"  Mean:   {dias.mean():.2f}")
print(f"  Median: {dias.median():.1f}")
print(f"  Max:    {dias.max():.0f}")
print(f"  Zeros:  {(dias == 0).sum():,} ({(dias == 0).sum() / len(dias) * 100:.1f}%)")

print(f"\n{'='*60}")
print("MOTIVO DE EGRESO (MOTEGRE)")
print(f"{'='*60}")
print(df["MOTEGRE"].value_counts().to_string())

print(f"\n{'='*60}")
print("NULOS IMPLÍCITOS SSA")
print(f"{'='*60}")
null_vals = {"NULL", "-1", "8888", "88", "9", "99", "NE", ""}
for col in ["CLUES", "AFECPRIN", "EGRESO", "SEXO", "EDAD", "MOTEGRE", "PROCED", "DIAG_INI"]:
    if col in df.columns:
        n_null = df[col].isin(null_vals).sum()
        pct = n_null / len(df) * 100
        print(f"  {col:18s}  nulls_implicitos={n_null:>8,}  ({pct:.1f}%)")

print(f"\n{'='*60}")
print("FORMATO DE FECHAS (sample)")
print(f"{'='*60}")
for col in ["EGRESO", "INGRE"]:
    sample = df[col].dropna().head(5).tolist()
    print(f"  {col}: {sample}")

print(f"\n{'='*60}")
print("VALORES ÚNICOS POR COLUMNA CLAVE")
print(f"{'='*60}")
for col in ["CLUES", "AFECPRIN", "SEXO", "ENTIDAD", "MOTEGRE", "PROCED", "TIPSERV"]:
    if col in df.columns:
        print(f"  {col:18s}  {df[col].nunique():>6,} valores únicos")

print("\n[OK] Exploración completada.")
