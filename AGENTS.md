# AGENTS — SaludMX Analytics Pipeline

## Propósito del Proyecto

Pipeline E2E de datos clínicos sobre fuentes abiertas de la Secretaría de Salud de México
(SAEH, CLUES, Recursos Físicos y Humanos). El objetivo es modelar la carga hospitalaria,
calcular el ALOS (Average Length of Stay) y entrenar un modelo predictivo de estancia.

## Stack

- **Orquestación:** Dagster (`platform/orchestration/dagster/`)
- **Base de Datos:** PostgreSQL 16 — Star Schema en `schema.sql`, migraciones en `db/migrations/`
- **Cómputo:** Python 3.11 (Pandas, Polars, Scikit-learn, LightGBM)
- **Entorno:** Docker Compose (`platform/orchestration/docker-compose.yml`)
- **Visualización:** Power BI Desktop conectado a PostgreSQL

## Orden de arranque de sesión para agentes de IA

Antes de cualquier tarea, ejecutar en este orden:

1. Leer este `AGENTS.md` para entender el stack y convenciones.
2. Revisar `README.md` para el diagrama de arquitectura y guía de levantamiento.
3. Inspeccionar `dagster_assets.py` si la tarea involucra el pipeline.
4. Revisar `schema.sql` si la tarea involucra la base de datos.

## Agentes disponibles

Los agentes en `.github/agents/` están especializados por rol:

| Agente | Cuándo usarlo |
|--------|--------------|
| `data-engineer.agent.md` | Modificar el pipeline ETL, assets de Dagster, transformaciones |
| `healthcare-logistics-executive.agent.md` | Preguntas de dominio clínico/salud, KPIs de ALOS, interpretación de datos |
| `power-bi-engineer.agent.md` | Modelado en Power BI, medidas DAX, diseño del dashboard |
| `technical-writer.agent.md` | Documentar assets, actualizar README, escribir runbooks |

## Convenciones del proyecto

### Encodings SSA
- Todos los CSV/XLS de la DGIS se leen con `encoding="latin-1"` y `dtype=str`.
- Los textos se normalizan a NFKD → ASCII → mayúsculas antes de insertar a Postgres.

### Códigos geográficos
- `entidad_id`: siempre 2 dígitos (`zfill(2)`).
- `municipio_id`: siempre 3 dígitos (`zfill(3)`).
- `clues_id`: preservar formato original (alfanumérico mayúscula, e.g. `DFSSA000154`).

### Nulos implícitos de la SSA
- Códigos `'99'`, `'9'`, `'NE'`, `'  /  /    '` son nulos implícitos — convertir a `NaN`.

### Archivos permitidos por rol
- **Pipeline:** `dagster_assets.py`, `platform/shared/`, `platform/orchestration/`
- **Schema:** `schema.sql`, `db/migrations/`, `db/ddl/`
- **Documentación:** `README.md`, `AGENTS.md`

## Coordinación multiagente

- Un solo agente escribe por archivo en cada ciclo; los demás revisan y proponen.
- Separar siempre: evidencia directa del código vs. inferencias vs. decisiones pendientes.
- No crear worktrees — Antigravity no es compatible con esta configuración.
- Antes de proponer cambios amplios, verificar que el schema.sql y dagster_assets.py sean consistentes.

## Notas de infraestructura

- El `prepare_local.ps1` es el punto de entrada para levantar el entorno desde cero.
- El `docker-compose.yml` expone Dagster en `:3000`, PgAdmin en `:5050` y Postgres en `:5432`.
- Los datos de Postgres persisten en el volumen `saludmx_postgres_data` — no se borran con `docker compose down`.
