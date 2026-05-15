"""Bootstrap mínimo para asegurar la base de metadata de Dagster."""
from __future__ import annotations

import os

import psycopg
from psycopg import errors
from psycopg.rows import dict_row


def ensure_dagster_database() -> None:
    """Crea la base de metadata de Dagster si aún no existe."""
    host = os.getenv("DAGSTER_POSTGRES_HOST", "postgres")
    user = os.getenv("POSTGRES_USER", "saludmx_user")
    password = os.getenv("POSTGRES_PASSWORD", "saludmx_pass")
    target_db = os.getenv("DAGSTER_POSTGRES_DB", "saludmx_dagster")
    admin_db = os.getenv("DAGSTER_POSTGRES_ADMIN_DB", "postgres")

    admin_dsn = (
        f"host={host} port=5432 dbname={admin_db} "
        f"user={user} password={password}"
    )

    with psycopg.connect(admin_dsn, autocommit=True, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if cur.fetchone():
                print(f"[dagster_bootstrap] Base {target_db} ya existe.")
                return

            try:
                cur.execute(f'CREATE DATABASE "{target_db}"')
                print(f"[dagster_bootstrap] Base {target_db} creada.")
            except errors.DuplicateDatabase:
                print(f"[dagster_bootstrap] Base {target_db} ya fue creada en paralelo.")


def main() -> int:
    ensure_dagster_database()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
