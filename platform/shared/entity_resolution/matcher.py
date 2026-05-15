"""
matcher.py — Motor de entity resolution para datos clínicos SSA/DGIS.

Adaptado desde cym_datos (motor V7.5 de conciliación farmacológica)
para el dominio de la Secretaría de Salud de México.

Diferencias clave respecto al original:
  - Soporta dos modos de matching: 'cie10' y 'clues'.
  - CIE-10: candados por capítulo (letra inicial) y grupo en lugar de salts/bases.
  - CLUES: candados por institución (IMSS, ISSSTE, SSA) y entidad federativa.
  - Umbral default ajustado a 60 (CIE-10 tiene menos variación textual que farmacología).
  - El 'NLP doc' se construye con standardize_cie10_description / standardize_clues_name.

Estrategia híbrida (heredada):
1. Normalización semántica (standardize.py).
2. Match exacto por concatenado canónico (clave + descripción normalizada).
3. TF-IDF + cosine similarity sobre top-K candidatos.
4. Candados de seguridad clínica por capítulo CIE-10 o institución CLUES.

Uso típico para reconciliar CIE-10 entre años del catálogo DGIS:
    from platform.shared.entity_resolution import Cie10Matcher

    matcher = Cie10Matcher().fit(catalogo_2022_df)
    resultados = matcher.match_to_dataframe(catalogo_2023_df)

Uso típico para cruzar nombres de establecimientos CLUES entre fuentes:
    from platform.shared.entity_resolution import CluesMatcher

    matcher = CluesMatcher().fit(clues_master_df)
    resultados = matcher.match_to_dataframe(saeh_establecimientos_df)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from platform.shared.entity_resolution.standardize import (
    clean_alphanum,
    extract_clinical_numbers,
    get_cie10_chapter,
    standardize_cie10_description,
    standardize_clues_name,
    standardize_text,
)


# ── Resultado canónico de conciliación ───────────────────────────────────────

@dataclass
class MatchResult:
    """Resultado de conciliación para una fila del catálogo de entrada."""

    clave: str               # Código o ID de la fila de entrada
    descripcion: str         # Descripción original de la fila de entrada
    match_clave: str         # Clave del match encontrado en el catálogo maestro
    match_description: str   # Descripción del match encontrado
    score: float             # Puntaje de similitud [0, 100]
    status: str              # 'Exacto' | 'Encontrado' | 'No Encontrado'
    chapter: str             # Capítulo CIE-10 o institución CLUES del match


# ── Motor base (reutilizado por ambos matchers) ───────────────────────────────

@dataclass
class _BaseMatcher:
    """Motor TF-IDF + candados. Clase base — instanciar Cie10Matcher o CluesMatcher."""

    match_threshold: float = 60.0
    top_k_candidates: int = 5
    chapter_mismatch_penalty: float = 40.0   # penalización por capítulo/grupo diferente
    number_mismatch_penalty: float = 20.0    # penalización por números clínicos que divergen
    tfidf_ngram_range: tuple[int, int] = (1, 2)

    # Estado interno — poblado por fit()
    _vectorizer: TfidfVectorizer | None = field(default=None, init=False, repr=False)
    _master_tfidf: Any = field(default=None, init=False, repr=False)
    _master_df: pd.DataFrame | None = field(default=None, init=False, repr=False)
    _exact_map: dict[str, tuple[str, str, str]] = field(default_factory=dict, init=False, repr=False)
    _idx_to_meta: dict[int, dict] = field(default_factory=dict, init=False, repr=False)

    def _build_nlp_doc(self, row: pd.Series) -> str:
        """Override en subclases para construir el documento TF-IDF."""
        raise NotImplementedError

    def _build_full_concat(self, row: pd.Series) -> str:
        """Override en subclases para construir la clave de match exacto."""
        raise NotImplementedError

    def _get_chapter(self, row: pd.Series) -> str:
        """Override en subclases para extraer el grupo/capítulo del item."""
        raise NotImplementedError

    def _chapter_penalty(self, row_chapter: str, cand_chapter: str) -> float:
        """Penalización por mismatch de capítulo/grupo. 0 si coinciden."""
        if row_chapter and cand_chapter and row_chapter != cand_chapter:
            return self.chapter_mismatch_penalty
        return 0.0

    def fit(self, master: pd.DataFrame) -> "_BaseMatcher":
        """Indexa el catálogo maestro para matching posterior."""
        df = master.copy()
        df["_nlp_doc"] = df.apply(self._build_nlp_doc, axis=1)
        df["_full_concat"] = df.apply(self._build_full_concat, axis=1)
        df["_chapter"] = df.apply(self._get_chapter, axis=1)
        df = df.dropna(subset=["_nlp_doc"]).drop_duplicates(subset=["_full_concat"]).reset_index(drop=True)

        self._master_df = df
        self._exact_map = {}
        self._idx_to_meta = {}

        for i, row in df.iterrows():
            self._exact_map[row["_full_concat"]] = (
                str(row.get(self._key_col, "")),
                str(row.get(self._desc_col, "")),
                str(row["_chapter"]),
            )
            self._idx_to_meta[i] = {
                "clave": str(row.get(self._key_col, "")),
                "descripcion": str(row.get(self._desc_col, "")),
                "nlp_doc": row["_nlp_doc"],
                "chapter": row["_chapter"],
            }

        self._vectorizer = TfidfVectorizer(ngram_range=self.tfidf_ngram_range)
        self._master_tfidf = self._vectorizer.fit_transform(df["_nlp_doc"].tolist())
        return self

    def match(self, new: pd.DataFrame) -> list[MatchResult]:
        """Concilia `new` contra el catálogo maestro indexado."""
        if self._vectorizer is None or self._master_df is None:
            raise RuntimeError("Matcher no entrenado — llamar fit() primero.")

        df = new.copy()
        df["_nlp_doc"] = df.apply(self._build_nlp_doc, axis=1)
        df["_full_concat"] = df.apply(self._build_full_concat, axis=1)
        df["_chapter"] = df.apply(self._get_chapter, axis=1)

        new_tfidf = self._vectorizer.transform(df["_nlp_doc"].tolist())
        sim_matrix = cosine_similarity(new_tfidf, self._master_tfidf)

        results: list[MatchResult] = []
        for i, row in df.iterrows():
            results.append(self._match_row(i, row, sim_matrix))
        return results

    def match_to_dataframe(self, new: pd.DataFrame) -> pd.DataFrame:
        """Wrapper que retorna DataFrame con columnas canónicas del reporte."""
        return pd.DataFrame(
            [
                {
                    "CLAVE_ENTRADA": r.clave,
                    "DESCRIPCION_ENTRADA": r.descripcion,
                    "CLAVE_MATCH": r.match_clave,
                    "DESCRIPCION_MATCH": r.match_description,
                    "PUNTAJE_SIMILITUD": round(r.score, 2),
                    "ESTATUS": r.status,
                    "CAPITULO_GRUPO": r.chapter,
                }
                for r in self.match(new)
            ]
        )

    def _match_row(self, i: int, row: pd.Series, sim_matrix) -> MatchResult:
        clave = str(row.get(self._key_col, ""))
        desc = str(row.get(self._desc_col, ""))
        full = row.get("_full_concat", "")
        nlp = row.get("_nlp_doc", "")
        chapter_in = row.get("_chapter", "")

        # 1. Match exacto
        if full and full in self._exact_map:
            mk, md, mch = self._exact_map[full]
            return MatchResult(
                clave=clave, descripcion=desc,
                match_clave=mk, match_description=md,
                score=100.0, status="Exacto", chapter=mch,
            )

        # 2. TF-IDF + candados
        best_score = 0.0
        best_meta: dict = {}
        if nlp:
            nums_in = extract_clinical_numbers(nlp)
            top_indices = np.argsort(sim_matrix[i])[-self.top_k_candidates:][::-1]

            for cand_idx in top_indices:
                score = float(sim_matrix[i][cand_idx]) * 100
                meta = self._idx_to_meta[cand_idx]

                # Candado: capítulo / grupo
                score -= self._chapter_penalty(chapter_in, meta["chapter"])

                # Candado: números clínicos deben ser subset mutuo
                nums_cand = extract_clinical_numbers(meta["nlp_doc"])
                if nums_in and nums_cand:
                    if not (nums_in.issubset(nums_cand) or nums_cand.issubset(nums_in)):
                        score -= self.number_mismatch_penalty

                if score > best_score:
                    best_score = score
                    best_meta = meta

        status = "Encontrado" if best_score >= self.match_threshold else "No Encontrado"
        return MatchResult(
            clave=clave, descripcion=desc,
            match_clave=best_meta.get("clave", "") if best_meta else "",
            match_description=best_meta.get("descripcion", "") if best_meta else "",
            score=best_score,
            status=status,
            chapter=best_meta.get("chapter", "") if best_meta else "",
        )


# ── Matcher especializado: CIE-10 ────────────────────────────────────────────

@dataclass
class Cie10Matcher(_BaseMatcher):
    """
    Concilia códigos y descripciones CIE-10 entre versiones del catálogo DGIS.

    Columnas esperadas en el DataFrame de entrada:
        - `codigo_cie10` : código alfanumérico (e.g., 'A09X', 'J18.9')
        - `descripcion`  : descripción en español del catálogo SSA

    Caso de uso principal:
        Cuando la SSA publica un nuevo catálogo CIE-10 y hay que reconciliar
        los códigos del año anterior con los del año actual para mantener la
        continuidad de los datos históricos de `fact_egresos_hospitalarios`.

    Candado activo: capítulo CIE-10 (letra inicial del código).
    Dos códigos de capítulos distintos reciben penalización de -40 pts.
    """

    match_threshold: float = 60.0
    chapter_mismatch_penalty: float = 40.0

    _key_col: str = field(default="codigo_cie10", init=False, repr=False)
    _desc_col: str = field(default="descripcion", init=False, repr=False)

    def _build_nlp_doc(self, row: pd.Series) -> str:
        desc = standardize_cie10_description(row.get("descripcion", ""))
        grupo = standardize_text(row.get("grupo_cie10", ""))
        return f"{desc} {grupo}".strip()

    def _build_full_concat(self, row: pd.Series) -> str:
        clave = clean_alphanum(row.get("codigo_cie10", ""))
        desc = standardize_cie10_description(row.get("descripcion", ""))
        return f"{clave} {desc}".strip()

    def _get_chapter(self, row: pd.Series) -> str:
        return get_cie10_chapter(str(row.get("codigo_cie10", "")))


# ── Matcher especializado: CLUES ──────────────────────────────────────────────

@dataclass
class CluesMatcher(_BaseMatcher):
    """
    Concilia nombres de establecimientos de salud entre fuentes CLUES y SAEH.

    Columnas esperadas en el DataFrame de entrada:
        - `clues_id`      : clave única del establecimiento (e.g., 'DFSSA000154')
        - `nombre_unidad` : nombre del establecimiento en texto libre
        - `institucion`   : institución (IMSS, ISSSTE, SSA, PEMEX, etc.)
        - `entidad_id`    : código de entidad federativa (2 dígitos)

    Caso de uso principal:
        Los microdatos SAEH registran el establecimiento por CLUES, pero a veces
        llegan con nombres textuales o CLUESs levemente distintas. Este matcher
        permite reconciliar establecimientos cuando la clave exacta no coincide.

    Candado activo: institución + entidad_id.
    Un hospital IMSS en CDMX no puede hacer match con uno SSA en Jalisco.
    """

    match_threshold: float = 65.0
    chapter_mismatch_penalty: float = 35.0  # "chapter" = institución+entidad en este contexto

    _key_col: str = field(default="clues_id", init=False, repr=False)
    _desc_col: str = field(default="nombre_unidad", init=False, repr=False)

    def _build_nlp_doc(self, row: pd.Series) -> str:
        nombre = standardize_clues_name(row.get("nombre_unidad", ""))
        tipologia = standardize_text(row.get("tipologia", ""))
        return f"{nombre} {tipologia}".strip()

    def _build_full_concat(self, row: pd.Series) -> str:
        clave = clean_alphanum(row.get("clues_id", ""))
        nombre = standardize_clues_name(row.get("nombre_unidad", ""))
        entidad = str(row.get("entidad_id", "")).strip().zfill(2)
        return f"{clave} {nombre} {entidad}".strip()

    def _get_chapter(self, row: pd.Series) -> str:
        """El 'capítulo' en CLUES es la combinación institución + entidad_id."""
        institucion = standardize_text(row.get("institucion", ""))
        entidad = str(row.get("entidad_id", "")).strip().zfill(2)
        return f"{institucion}_{entidad}"

    def _chapter_penalty(self, row_chapter: str, cand_chapter: str) -> float:
        """
        Penaliza si la institución es distinta (IMSS vs SSA) o la entidad difiere.
        Permite match dentro de la misma institución aunque la entidad sea adyacente.
        """
        if not row_chapter or not cand_chapter:
            return 0.0
        inst_in, *ent_in = row_chapter.split("_", 1)
        inst_ca, *ent_ca = cand_chapter.split("_", 1)
        # Penalizar si la institución es diferente
        if inst_in and inst_ca and inst_in != inst_ca:
            return self.chapter_mismatch_penalty
        # Penalizar si la entidad federativa es diferente (menor penalización)
        if ent_in and ent_ca and ent_in != ent_ca:
            return self.chapter_mismatch_penalty / 2
        return 0.0
