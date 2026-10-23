#!/bin/bash
# Airflow's own metadata database (D28): separate database, separate owner role,
# no access to the app's tables. Runs on first start of an empty volume; for an
# existing volume, `make airflow-db` does the same idempotently.
set -euo pipefail
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -v pw="$AIRFLOW_META_PASSWORD" <<'SQL'
CREATE ROLE airflow_meta LOGIN PASSWORD :'pw';
CREATE DATABASE airflow OWNER airflow_meta;
SQL
