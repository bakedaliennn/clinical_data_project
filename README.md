# SaludMX Analytics Pipeline 📊🏥

## 🌟 Ecosistema End-to-End de Datos Clínicos (Secretaría de Salud de México)

Un ecosistema avanzado de ingeniería de datos, modelado analítico y ciencia de datos diseñado para analizar la **carga hospitalaria**, estimar el **tiempo promedio de estancia (ALOS)** y correlacionar la **disponibilidad de recursos físicos, materiales y humanos** con la eficiencia operativa en los establecimientos de salud de México.

---

## 🏗️ 1. Arquitectura de Datos E2E

El pipeline está diseñado bajo los principios de **DataOps** y **Modern Data Stack**, utilizando Dagster para la orquestación, Docker para el aislamiento, PostgreSQL como Data Warehouse dimensional, y Power BI junto con Scikit-learn para la analítica avanzada.

```mermaid
graph TD
    %% Fuentes de Datos
    subgraph Fuentes de Datos (DGIS / SSA)
        Raw_SAEH[SAEH CSV <br> Microdatos de Egresos]
        Raw_CLUES[CLUES CSV/XLS <br> Catálogo Maestro]
        Raw_Rec_Fis[Recursos Físicos CSV <br> Camas, Quirofanos...]
        Raw_Rec_Hum[Recursos Humanos CSV <br> Médicos, Enfermeras...]
    end

    %% Capa de Orquestación y ETL
    subgraph Orquestación con Dagster (Capa de Cómputo)
        Asset_Ingest[Asset: Ingesta RAW] --> Asset_Clean[Asset: Limpieza & Normalización]
        Asset_Clean --> Asset_Transform[Asset: Transformación Dimensional]
    end

    %% Base de Datos
    subgraph PostgreSQL Data Warehouse (Docker)
        Staging_Tables[(Tablas de Staging <br> s_saeh, s_clues, s_recursos)]
        Star_Schema[("Modelo Dimensional (Star Schema)" <br> fact_egresos_hospitalarios <br> dim_clues, dim_cie10, dim_fecha...)]
        Staging_Tables -->|ETL de Inserción| Star_Schema
    end

    %% Consumo y Modelado
    subgraph Capa de Consumo (Analítica & Ciencia de Datos)
        PBI_Dashboard[Power BI Desktop <br> Métricas de ALOS & Suministros]
        DS_Model[Modelo de Machine Learning <br> Estimación de Estancia (Regresión)]
    end

    %% Conexiones entre componentes
    Raw_SAEH -->|Lectura con Encodings| Asset_Ingest
    Raw_CLUES -->|Lectura con Encodings| Asset_Ingest
    Raw_Rec_Fis -->|Lectura con Encodings| Asset_Ingest
    Raw_Rec_Hum -->|Lectura con Encodings| Asset_Ingest

    Asset_Transform -->|Carga de Staging| Staging_Tables
    Star_Schema -->|DirectQuery / Import| PBI_Dashboard
    Star_Schema -->|Dataset de Entrenamiento| DS_Model
```

---

## 🗄️ 2. Diseño del Modelo Dimensional (Star Schema)

Para garantizar la máxima velocidad de consulta en Power BI y simplificar la extracción de características para el modelo de Machine Learning, implementamos un **Esquema de Estrella** robusto en PostgreSQL.

```mermaid
erDiagram
    fact_egresos_hospitalarios {
        UUID id_egreso PK
        VARCHAR clues_establecimiento_id FK "dim_clues.clues_id"
        VARCHAR diagnostico_principal_cie10 FK "dim_cie10.codigo_cie10"
        INTEGER fecha_ingreso_id FK "dim_fecha.fecha_id"
        INTEGER fecha_egreso_id FK "dim_fecha.fecha_id"
        INTEGER sexo_id FK "dim_sexo.sexo_id"
        INTEGER procedencia_id FK "dim_procedencia.procedencia_id"
        INTEGER tipo_ingreso_id FK "dim_tipo_ingreso.tipo_ingreso_id"
        INTEGER tipo_egreso_id FK "dim_tipo_egreso.tipo_egreso_id"
        INTEGER motivo_egreso_id FK "dim_motivo_egreso.motivo_egreso_id"
        INTEGER edad_anios
        INTEGER dias_estancia "Métrica ALOS"
        INTEGER horas_estancia
        BOOLEAN esta_complicado
        NUMERIC costo_estimado
    }

    dim_clues {
        VARCHAR clues_id PK
        VARCHAR nombre_unidad
        INTEGER entidad_id FK "dim_geografia.entidad_id"
        INTEGER municipio_id FK "dim_geografia.municipio_id"
        VARCHAR localidad
        VARCHAR jurisdiccion
        VARCHAR institucion
        VARCHAR tipologia
        VARCHAR estado_operacion
        INTEGER camas_sensibles "Recurso Físico"
        INTEGER camas_no_sensibles "Recurso Físico"
        INTEGER consultorios "Recurso Físico"
        INTEGER quirofanos "Recurso Físico"
        INTEGER total_medicos "Recurso Humano"
        INTEGER total_enfermeras "Recurso Humano"
    }

    dim_cie10 {
        VARCHAR codigo_cie10 PK
        VARCHAR descripcion
        VARCHAR grupo_cie10
        VARCHAR capitulo_cie10
    }

    dim_fecha {
        INTEGER fecha_id PK
        DATE fecha
        INTEGER anio
        INTEGER mes
        VARCHAR mes_nombre
        INTEGER dia
        INTEGER dia_semana
        VARCHAR dia_semana_nombre
        INTEGER trimestre
        BOOLEAN es_fin_semana
    }

    dim_geografia {
        INTEGER entidad_id PK
        INTEGER municipio_id PK
        VARCHAR nombre_entidad
        VARCHAR nombre_municipio
        VARCHAR region
    }

    dim_sexo {
        INTEGER sexo_id PK
        VARCHAR descripcion_sexo
    }

    dim_procedencia {
        INTEGER procedencia_id PK
        VARCHAR descripcion_procedencia
    }

    dim_tipo_ingreso {
        INTEGER tipo_ingreso_id PK
        VARCHAR descripcion_tipo_ingreso
    }

    dim_tipo_egreso {
        INTEGER tipo_egreso_id PK
        VARCHAR descripcion_tipo_egreso
    }

    dim_motivo_egreso {
        INTEGER motivo_egreso_id PK
        VARCHAR descripcion_motivo
    }

    %% Relaciones
    dim_clues ||--o{ fact_egresos_hospitalarios : "registra"
    dim_cie10 ||--o{ fact_egresos_hospitalarios : "diagnostica"
    dim_fecha ||--o{ fact_egresos_hospitalarios : "fecha_ingreso"
    dim_fecha ||--o{ fact_egresos_hospitalarios : "fecha_egreso"
    dim_sexo ||--o{ fact_egresos_hospitalarios : "clasifica_sexo"
    dim_procedencia ||--o{ fact_egresos_hospitalarios : "proviene_de"
    dim_tipo_ingreso ||--o{ fact_egresos_hospitalarios : "tipo_ingreso"
    dim_tipo_egreso ||--o{ fact_egresos_hospitalarios : "tipo_egreso"
    dim_motivo_egreso ||--o{ fact_egresos_hospitalarios : "motivo"
    dim_geografia ||--o{ dim_clues : "localiza"
```

---

## 🛠️ 3. Retos de Ingesta y Limpieza de Datos (DGIS SSA)

Los microdatos de la Secretaría de Salud de México presentan desafíos técnicos sistemáticos. El pipeline de Dagster resolverá de manera canónica los siguientes puntos:

### 🧩 Encodings Latinoamericanos
*   **Problema:** Los archivos de egresos y catálogos de la SSA suelen exportarse con codificaciones heredadas como `ISO-8859-1`, `latin-1` o `cp1252`. Forzar la lectura en `utf-8` provoca un fallo de detención de ejecución o caracteres rotos (e.g., `MÃ©xico` por `México`).
*   **Solución:** Detección dinámica y especificación explícita del encoding en Pandas:
    ```python
    df = pd.read_csv("archivo.csv", encoding="latin-1", low_memory=False)
    ```
*   **Normalización:** Todas las columnas de texto se limpian de acentos, caracteres especiales y se convierten a mayúsculas para unificar uniones en SQL:
    ```python
    df['municipio'] = df['municipio'].str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8').str.upper()
    ```

### 📅 Inconsistencia de Fechas
*   **Problema:** Campos como fecha de ingreso o egreso varían de formato año con año (e.g., `DD/MM/YYYY`, `YYYY-MM-DD`, enteros como `20231225`, o nulos codificados como `"  /  /    "`).
*   **Solución:** Lógica de análisis multi-formato coercitivo:
    ```python
    def clean_ssa_dates(series):
        # Reemplazar nulos textuales por NaN reales
        series = series.astype(str).replace(r'^\s*/\s*/\s*$', np.nan, regex=True)
        # Intentar parser automático coercitivo
        return pd.to_datetime(series, errors='coerce', format='mixed')
    ```

### 🔢 Preservación de Ceros a la Izquierda (Padding)
*   **Problema:** Los códigos de entidades federativas (01 a 32) y de municipios (e.g. 001, 015) son cargados por Pandas por defecto como flotantes o enteros, eliminando los ceros (e.g., `9` en lugar de `09` para la CDMX). Esto destruye las uniones espaciales y con catálogos.
*   **Solución:** Configuración estricta de tipos de datos en la lectura y padding artificial en el cleaning:
    ```python
    dtype_dict = {'entidad_id': str, 'municipio_id': str, 'clues_id': str}
    df = pd.read_csv("archivo.csv", dtype=dtype_dict)
    # En caso de necesitar padding:
    df['entidad_id'] = df['entidad_id'].str.strip().str.zfill(2)
    df['municipio_id'] = df['municipio_id'].str.strip().str.zfill(3)
    ```

---

## 🐳 4. Guía de Levantamiento de Entorno Docker

El entorno está completamente contenedorizado para garantizar portabilidad. Incluye una base de datos PostgreSQL 15, un servidor PgAdmin 4 para exploración rápida, y la interfaz web de Dagster daemon.

### Requisitos Previos
*   Docker Desktop instalado.
*   Al menos 4GB de RAM asignados al motor de Docker.

### Estructura de Contenedores (`docker-compose.yml`)

El archivo `docker-compose.yml` (que se creará en el repositorio) define tres servicios clave:

1.  **`postgres`**: Instancia de base de datos Postgres 15 con persistencia de volumen para el Data Warehouse.
2.  **`pgadmin`**: Interfaz de administración web para Postgres.
3.  **`dagster`**: Contenedor para orquestación que expone la interfaz Dagster Webserver en el puerto `3000`.

### Comandos de Levantamiento

```bash
# 1. Clonar el repositorio y moverse a la carpeta
cd clinical_data_project

# 2. Construir e iniciar los servicios en segundo plano
docker compose up -d --build

# 3. Validar que todos los contenedores estén corriendo
docker compose ps
```

*   **Dagster Webserver:** Acceda a [http://localhost:3000](http://localhost:3000) para ver y lanzar los assets.
*   **PgAdmin 4:** Acceda a [http://localhost:5050](http://localhost:5050) (Credenciales: `admin@saludmx.org` / `adminpass`).
*   **PostgreSQL:** Host: `localhost`, Puerto: `5432`, DB: `saludmx_dw`, User: `postgres_user`, Pass: `postgres_pass`.

---

## 📈 5. Plan de Hitos (Project Milestones Roadmap)

Para mayor visibilidad, las tareas se estructuran en 4 hitos secuenciales descritos en detalle en [project_backlog.json](file:///c:/VSCode/clinical_data_project/project_backlog.json):

```
🏁 MILESTONE 1: Ingesta y Aislamiento Docker (Estatus: Pendiente)
├── Configuración de Docker Compose (Postgres + Dagster)
└── Extracción robusta de archivos crudos de SSA (SAEH, CLUES) respetando encodings.

🏁 MILESTONE 2: Limpieza y Normalización Canónica (Estatus: Pendiente)
├── Normalización de Encodings e imputación de nulos estructurados.
└── Corrección de fechas multi-formato y empaquetado de códigos geográficos (zfill).

🏁 MILESTONE 3: Modelado Dimensional y Carga (Estatus: Pendiente)
├── Ejecución del script schema.sql para generar el Star Schema.
└── Pipeline Dagster para la transformación y carga final a tablas dimensionales (Staging -> Core).

🏁 MILESTONE 4: Analítica y Modelado Predictivo (Estatus: Pendiente)
├── Conexión de Power BI Desktop y creación del modelo de datos de estancia (ALOS).
└── Entrenamiento y serialización del modelo Scikit-learn para predecir estancia por CIE-10/Demografía.
```

---

> [!NOTE]
> Este repositorio se encuentra bajo desarrollo activo. El archivo [schema.sql](file:///c:/VSCode/clinical_data_project/schema.sql) contiene las definiciones DDL necesarias para iniciar la base de datos, mientras que la estructura lógica de los assets orquestados se encuentra en [dagster_assets.py](file:///c:/VSCode/clinical_data_project/dagster_assets.py).
