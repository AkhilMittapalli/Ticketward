#!/usr/bin/env bash
# Creates the MLflow tracking database and role (ml profile, P2.17).
# Sourced by the Postgres Docker entrypoint during first initialization.
# The password is read from the Docker secret (hex-only, no quoting risk).

MLFLOW_PW="$(cat /run/secrets/tw_mlflow_db_password)"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE USER mlflow WITH PASSWORD '${MLFLOW_PW}';
CREATE DATABASE mlflow OWNER mlflow;
EOSQL
