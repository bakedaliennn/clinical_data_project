"""
standardize.py — Normalización semántica para entity resolution clínico (SSA/DGIS).

Adaptado desde cym_datos para el dominio de datos de la Secretaría de Salud de México.

Cambios respecto al original de cym_datos:
  - Se eliminan las abreviaturas y salts farmacológicas (tabletas, cápsulas, etc.)
  - Se añade normalización específica para CIE-10 (grupos, capítulos, descripciones DGIS)
  - Se añade normalización para nombres de establecimientos CLUES
  - Se preservan las funciones genéricas (clean_alphanum, standardize_text, extract_numbers)
    que son agnósticas al dominio.

Funciones puras sin estado. Entrada: string (o NaN); salida: string canónico.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd


# ── Tokens ruidosos comunes en descripciones de la SSA ────────────────────────
# Palabras que tienden a aparecer en nombres de unidades CLUES o descripciones
# CIE-10 pero no aportan valor discriminativo para el matching.
_CLUES_STOPWORDS: frozenset[str] = frozenset({
    "de", "del", "la", "el", "los", "las", "y", "e", "en", "a",
    "con", "sin", "para", "por", "no", "un", "una", "unos", "unas",
    "centro", "unidad", "hospital", "clinica", "clinico", "medico",
    "medica", "salud", "instituto", "jurisdiccion", "servicios",
    "secretaria", "imss", "issste", "ssa", "sedena", "pemex",
})

# Abreviaturas de tipología de unidades que se pueden expandir para mejor matching
_TIPOLOGIA_ABBR: dict[str, str] = {
    "HG": "HOSPITAL GENERAL",
    "HE": "HOSPITAL ESPECIALIDAD",
    "CS": "CENTRO SALUD",
    "UMR": "UNIDAD MEDICINA RURAL",
    "UMAA": "UNIDAD MEDICINA ALTA ESPECIALIDAD",
    "MA": "MODULO ABASTO",
    "PS": "PUNTO SURTIDO",
    "CESSA": "CENTRO SALUD CON SERVICIOS AMPLIADOS",
    "HB": "HOSPITAL BASICO COMUNITARIO",
}


# ── Funciones genéricas (agnósticas al dominio) ───────────────────────────────

def remove_accents(text: str) -> str:
    """Elimina diacríticos Unicode (acentos, diéresis) preservando la base ASCII."""
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", errors="ignore")
        .decode("utf-8")
    )


def clean_alphanum(text) -> str:
    """Retorna solo caracteres alfanuméricos en minúsculas. Útil para claves PK."""
    if pd.isna(text):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def extract_clinical_numbers(text) -> set[int]:
    """Extrae todos los números enteros de una cadena (útil para CIE-10 y CLUES)."""
    if pd.isna(text):
        return set()
    return {int(n) for n in re.findall(r"\d+", str(text))}


def standardize_text(text) -> str:
    """
    Normalización semántica para textos de la SSA (CIE-10, CLUES, establecimientos).

    Pasos aplicados:
    1. NaN → string vacío.
    2. Mayúsculas y remoción de acentos (NFKD).
    3. Expansión de abreviaturas de tipología CLUES.
    4. Eliminación de caracteres no alfanuméricos (salvo espacios).
    5. Colapso de espacios múltiples y trim.
    6. Conversión a minúsculas para TF-IDF.
    """
    if pd.isna(text):
        return ""

    t = str(text).upper()
    t = remove_accents(t)

    # Expandir abreviaturas de tipología
    for abbr, expansion in _TIPOLOGIA_ABBR.items():
        t = re.sub(rf"\b{re.escape(abbr)}\b", expansion, t)

    # Normalizar separadores y puntuación
    t = re.sub(r"[/\-_,;:.]", " ", t)
    t = re.sub(r"[^A-Z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()

    return t.lower()


def standardize_cie10_description(desc) -> str:
    """
    Normaliza específicamente descripciones del catálogo CIE-10 de la SSA.

    Las descripciones DGIS del CIE-10 a veces incluyen paréntesis, calificadores
    de 'no especificado', 'otro especificado', etc. Este normalizador los retira
    para mejorar el matching semántico entre versiones del catálogo.

    Ejemplo:
        'Diarrea y gastroenteritis de presunto origen infeccioso (A09X)'
        → 'diarrea gastroenteritis presunto origen infeccioso'
    """
    if pd.isna(desc):
        return ""

    t = standardize_text(desc)

    # Retirar calificadores que aparecen en casi todos los códigos (bajo valor discriminativo)
    for noise in ["no especificado", "otro especificado", "otros", "otras",
                  "no clasificado en otra parte", "ncoc", "yotp"]:
        t = re.sub(rf"\b{re.escape(noise)}\b", " ", t)

    return re.sub(r"\s+", " ", t).strip()


def standardize_clues_name(name) -> str:
    """
    Normaliza nombres de establecimientos CLUES para matching semántico.

    Retira stopwords institucionales que aparecen en casi todos los nombres
    ('HOSPITAL', 'CENTRO DE SALUD', etc.) cuando se van a usar en TF-IDF,
    ya que dichos tokens tienen IDF ≈ 0 y no aportan discriminación.
    Se usa SOLO para construir el documento TF-IDF, no para display.
    """
    if pd.isna(name):
        return ""

    t = standardize_text(name)
    tokens = [tok for tok in t.split() if tok not in _CLUES_STOPWORDS]
    return " ".join(tokens)


def get_cie10_chapter(codigo: str) -> str:
    """
    Infiere el capítulo CIE-10 desde el código alfanumérico (ej: 'A09X' → 'I').

    El capítulo se determina por la primera letra del código, según la
    clasificación oficial de la OPS/OMS para la CIE-10 en español.
    """
    if not codigo or pd.isna(codigo):
        return "DESCONOCIDO"

    letra = str(codigo).strip().upper()[0]

    CHAPTER_MAP = {
        "A": "I",   "B": "I",                    # Infecciosas y parasitarias
        "C": "II",  "D": "II",                   # Neoplasias
        "E": "IV",                                # Endocrinas, nutricionales
        "F": "V",                                 # Trastornos mentales
        "G": "VI",                                # Enfermedades nerviosas
        "H": "VII",                               # Ojo / oído (H00-H59 VII, H60-H95 VIII)
        "I": "IX",                                # Circulatorio
        "J": "X",                                 # Respiratorio
        "K": "XI",                                # Digestivo
        "L": "XII",                               # Piel y tejido
        "M": "XIII",                              # Osteomuscular
        "N": "XIV",                               # Genitourinario
        "O": "XV",                                # Embarazo, parto, puerperio
        "P": "XVI",                               # Perinatal
        "Q": "XVII",                              # Malformaciones congénitas
        "R": "XVIII",                             # Síntomas y signos no clasificados
        "S": "XIX",  "T": "XIX",                  # Traumatismos y envenenamientos
        "V": "XX",   "W": "XX",  "X": "XX", "Y": "XX",  # Causas externas
        "Z": "XXI",                               # Factores que influyen en salud
        "U": "XXII",                              # Códigos especiales (COVID-19, etc.)
    }
    return CHAPTER_MAP.get(letra, "DESCONOCIDO")
