"""
entity_resolution — Motor de conciliación híbrido (TF-IDF + candados clínicos SSA).

Adaptado desde cym_datos para el dominio de la Secretaría de Salud de México.

Proporciona dos matchers especializados:

1. **Cie10Matcher** — Reconcilia códigos y descripciones CIE-10 entre versiones
   del catálogo DGIS (años distintos). Aplica candados por capítulo CIE-10
   (letra inicial del código: A=Infecciosas, J=Respiratorio, etc.).

2. **CluesMatcher** — Reconcilia nombres de establecimientos de salud entre
   los microdatos SAEH y el catálogo maestro CLUES. Aplica candados por
   institución (IMSS, ISSSTE, SSA) y entidad federativa.

Uso rápido:

    from platform.shared.entity_resolution import Cie10Matcher, CluesMatcher

    # Reconciliar CIE-10 entre catálogos de años distintos
    matcher = Cie10Matcher().fit(catalogo_2022_df)
    resultados = matcher.match_to_dataframe(catalogo_2023_df)

    # Reconciliar establecimientos SAEH vs catálogo CLUES
    matcher = CluesMatcher().fit(clues_master_df)
    resultados = matcher.match_to_dataframe(saeh_establecimientos_df)
"""

from platform.shared.entity_resolution.matcher import (
    Cie10Matcher,
    CluesMatcher,
    MatchResult,
)
from platform.shared.entity_resolution.standardize import (
    clean_alphanum,
    extract_clinical_numbers,
    get_cie10_chapter,
    remove_accents,
    standardize_cie10_description,
    standardize_clues_name,
    standardize_text,
)

__all__ = [
    # Matchers
    "Cie10Matcher",
    "CluesMatcher",
    "MatchResult",
    # Utilidades de normalización
    "clean_alphanum",
    "extract_clinical_numbers",
    "get_cie10_chapter",
    "remove_accents",
    "standardize_cie10_description",
    "standardize_clues_name",
    "standardize_text",
]
