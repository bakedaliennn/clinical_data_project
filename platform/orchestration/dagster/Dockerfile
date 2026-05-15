FROM python:3.11-slim

# Dependencias del sistema para Polars (libgomp), compilación (gcc/g++) y psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DAGSTER_HOME=/opt/dagster/dagster_home

WORKDIR /opt/dagster/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "import pydantic_core"
RUN python -c "from pydantic import BaseModel, TypeAdapter"

# Copiar estructura del proyecto (excluye data_raw y logs via .dockerignore)
COPY alembic.ini ./alembic.ini
COPY platform ./platform
COPY dagster_assets.py ./dagster_assets.py
COPY schema.sql ./schema.sql
COPY .env.example ./.env.example

RUN mkdir -p /opt/dagster/dagster_home/storage
COPY platform/orchestration/dagster/dagster_home/dagster.yaml /opt/dagster/dagster_home/dagster.yaml
