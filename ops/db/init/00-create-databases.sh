#!/bin/bash
# Create auxiliary databases (mlflow) on first boot. Runs as the
# postgres superuser via the official-image entrypoint; CREATE DATABASE
# must run at the top level (never inside a DO block).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE mlflow' WHERE NOT EXISTS (
        SELECT FROM pg_database WHERE datname = 'mlflow')\gexec
    GRANT ALL PRIVILEGES ON DATABASE mlflow TO "$POSTGRES_USER";
EOSQL
