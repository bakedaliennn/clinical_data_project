"""Recursos de Dagster para el pipeline SaludMX Analytics."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from dagster import ConfigurableResource
from pydantic import PrivateAttr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


class SaludMxPostgresResource(ConfigurableResource):
    """Recurso ligero de PostgreSQL para validaciones y cargas del DW."""

    database_url: str

    _engine: Engine | None = PrivateAttr(default=None)

    def setup_for_execution(self, _context) -> None:
        self._engine = create_engine(self.database_url, future=True)

    def teardown_after_execution(self, _context) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(self.database_url, future=True)
        return self._engine

    def scalar(self, sql: str, params: Mapping[str, Any] | None = None) -> int:
        """Ejecuta una consulta escalar y devuelve el resultado como entero."""
        with self.engine.connect() as connection:
            result = connection.execute(text(sql), params or {})
            value = result.scalar_one()
        return int(value or 0)


class SaludMxPathsResource(ConfigurableResource):
    """Rutas compartidas entre assets y sensores del pipeline SSA."""

    ssa_data_dir: str
    pipeline_logs_dir: str

    @property
    def ssa_data_dir_path(self) -> Path:
        return Path(self.ssa_data_dir)

    @property
    def saeh_dir(self) -> Path:
        return self.ssa_data_dir_path / "saeh"

    @property
    def clues_dir(self) -> Path:
        return self.ssa_data_dir_path / "clues"

    @property
    def recursos_fisicos_dir(self) -> Path:
        return self.ssa_data_dir_path / "recursos_fisicos"

    @property
    def recursos_humanos_dir(self) -> Path:
        return self.ssa_data_dir_path / "recursos_humanos"

    @property
    def pipeline_logs_dir_path(self) -> Path:
        return Path(self.pipeline_logs_dir)
