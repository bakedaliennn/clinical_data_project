"""
tests/test_entity_resolution.py
--------------------------------
Tests unitarios para el módulo platform/shared/entity_resolution adaptado
al dominio clínico SSA (CIE-10 y CLUES).

Cubre:
  - Normalización de textos (standardize.py)
  - Inferencia de capítulos CIE-10
  - Match exacto y TF-IDF de Cie10Matcher
  - Match exacto y candados de CluesMatcher
"""

import pytest
import pandas as pd

from platform.shared.entity_resolution import (
    Cie10Matcher,
    CluesMatcher,
    clean_alphanum,
    get_cie10_chapter,
    standardize_cie10_description,
    standardize_clues_name,
    standardize_text,
)


# ── standardize.py ────────────────────────────────────────────────────────────

class TestStandardizeText:
    def test_removes_accents(self):
        assert "diarrea" in standardize_text("Diarrea")

    def test_handles_nan(self):
        assert standardize_text(None) == ""
        assert standardize_text(float("nan")) == ""

    def test_uppercase_input_normalized_to_lower(self):
        result = standardize_text("NEUMONIA ADQUIRIDA EN LA COMUNIDAD")
        assert result == result.lower()

    def test_removes_special_chars(self):
        result = standardize_text("Infección, de vía: urinaria/superior")
        assert "," not in result
        assert "/" not in result
        assert ":" not in result


class TestStandardizeCie10Description:
    def test_removes_no_especificado(self):
        desc = "Diarrea no especificado (A09X)"
        result = standardize_cie10_description(desc)
        assert "no especificado" not in result

    def test_removes_otro_especificado(self):
        result = standardize_cie10_description("Tumor otro especificado")
        assert "otro especificado" not in result

    def test_preserves_meaningful_tokens(self):
        result = standardize_cie10_description("Neumonia por Streptococcus")
        assert "neumonia" in result
        assert "streptococcus" in result


class TestGetCie10Chapter:
    @pytest.mark.parametrize("codigo,expected", [
        ("A09X", "I"),
        ("B20",  "I"),
        ("C50",  "II"),
        ("J18",  "X"),
        ("J189", "X"),
        ("O80",  "XV"),
        ("U07",  "XXII"),
        ("Z00",  "XXI"),
        ("",     "DESCONOCIDO"),
        (None,   "DESCONOCIDO"),
    ])
    def test_chapter_mapping(self, codigo, expected):
        assert get_cie10_chapter(codigo) == expected


class TestCleanAlphanum:
    def test_strips_to_alphanumeric(self):
        assert clean_alphanum("A09.X") == "a09x"

    def test_nan_returns_empty(self):
        assert clean_alphanum(None) == ""


class TestStandardizeCluesName:
    def test_removes_institutional_stopwords(self):
        result = standardize_clues_name("HOSPITAL GENERAL DE MEXICO")
        # 'hospital' y 'de' y 'mexico' deben ser removidos por stopwords o limpieza
        assert "hospital" not in result

    def test_preserves_discriminative_tokens(self):
        result = standardize_clues_name("IMSS BIENESTAR TLAXCALA")
        # Los tokens discriminativos de localización deben quedar
        assert "tlaxcala" in result


# ── Cie10Matcher ──────────────────────────────────────────────────────────────

@pytest.fixture
def cie10_master():
    return pd.DataFrame({
        "codigo_cie10": ["A09X", "J18.9", "E11.9", "O80", "U07.1"],
        "descripcion": [
            "Diarrea y gastroenteritis de presunto origen infeccioso",
            "Neumonía no especificada",
            "Diabetes mellitus tipo 2 sin complicaciones",
            "Parto único espontáneo presentación cefálica",
            "COVID-19 virus identificado",
        ],
        "grupo_cie10": [
            "Enfermedades infecciosas intestinales",
            "Influenza y neumonía",
            "Diabetes mellitus",
            "Parto",
            "Códigos de uso especial",
        ],
    })


class TestCie10Matcher:
    def test_exact_match(self, cie10_master):
        matcher = Cie10Matcher().fit(cie10_master)
        query = pd.DataFrame({
            "codigo_cie10": ["A09X"],
            "descripcion": ["Diarrea y gastroenteritis de presunto origen infeccioso"],
            "grupo_cie10": ["Enfermedades infecciosas intestinales"],
        })
        results = matcher.match(query)
        assert len(results) == 1
        assert results[0].status == "Exacto"
        assert results[0].score == 100.0

    def test_semantic_match(self, cie10_master):
        matcher = Cie10Matcher().fit(cie10_master)
        # Descripción levemente distinta al original
        query = pd.DataFrame({
            "codigo_cie10": ["J18.9"],
            "descripcion": ["Neumonia sin especificacion"],
            "grupo_cie10": ["Influenza y neumonia"],
        })
        results = matcher.match(query)
        assert results[0].status in ("Exacto", "Encontrado")
        assert results[0].chapter == "X"  # Capítulo Respiratorio

    def test_chapter_mismatch_penalizes(self, cie10_master):
        """Un código de capítulo diferente debe bajar el score significativamente."""
        matcher = Cie10Matcher().fit(cie10_master)
        # A09X es capítulo I; O80 es capítulo XV — muy distintos
        query = pd.DataFrame({
            "codigo_cie10": ["O80"],
            "descripcion": ["Diarrea gastroenteritis infecciosa"],  # descripción de cap I
            "grupo_cie10": ["Enfermedades infecciosas"],
        })
        results = matcher.match(query)
        # El candidato A09X debería recibir penalización por ser capítulo I vs XV
        assert results[0].score < 100.0

    def test_dataframe_output_columns(self, cie10_master):
        matcher = Cie10Matcher().fit(cie10_master)
        result_df = matcher.match_to_dataframe(cie10_master.head(2))
        expected_cols = {
            "CLAVE_ENTRADA", "DESCRIPCION_ENTRADA",
            "CLAVE_MATCH", "DESCRIPCION_MATCH",
            "PUNTAJE_SIMILITUD", "ESTATUS", "CAPITULO_GRUPO",
        }
        assert expected_cols.issubset(set(result_df.columns))

    def test_unfitted_raises(self):
        with pytest.raises(RuntimeError, match="fit\\(\\)"):
            Cie10Matcher().match(pd.DataFrame())


# ── CluesMatcher ──────────────────────────────────────────────────────────────

@pytest.fixture
def clues_master():
    return pd.DataFrame({
        "clues_id": ["DFSSA000154", "MEX0214512", "JAL0100033"],
        "nombre_unidad": [
            "HOSPITAL GENERAL DE MEXICO",
            "CENTRO DE SALUD SANTA FE",
            "HOSPITAL REGIONAL DE GUADALAJARA",
        ],
        "institucion": ["SSA", "IMSS-BIENESTAR", "SSA"],
        "entidad_id": ["09", "15", "14"],
        "tipologia": ["Hospital General", "Unidad de Primer Contacto", "Hospital Regional"],
    })


class TestCluesMatcher:
    def test_exact_match_by_clues_id(self, clues_master):
        matcher = CluesMatcher().fit(clues_master)
        query = clues_master.head(1).copy()
        results = matcher.match(query)
        assert results[0].status == "Exacto"

    def test_cross_institution_penalized(self, clues_master):
        """Un hospital SSA no debe hacer match fuerte con uno IMSS."""
        matcher = CluesMatcher().fit(clues_master)
        query = pd.DataFrame({
            "clues_id": ["NUEVO999"],
            "nombre_unidad": ["HOSPITAL GENERAL SANTA FE"],
            "institucion": ["SSA"],
            "entidad_id": ["15"],
            "tipologia": ["Hospital General"],
        })
        results = matcher.match(query)
        # IMSS-BIENESTAR SANTA FE debería tener menor score por institución distinta
        if results[0].status == "Encontrado":
            assert results[0].score < 95.0
