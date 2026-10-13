# MLflow tracking server for the Ticketward ml profile.
# Postgres-backed store; artifacts on a Docker volume (dev) or object store (prod).
#
#   docker compose --profile ml up -d --build

FROM python:3.12-slim

RUN groupadd -r mlflow && useradd -r -g mlflow -d /home/mlflow -m mlflow \
    && pip install --no-cache-dir \
       mlflow==3.16.0 \
       "psycopg[binary]>=3.2,<4" \
    && mkdir -p /mlflow/artifacts \
    && chown mlflow:mlflow /mlflow/artifacts

USER mlflow
EXPOSE 5000
