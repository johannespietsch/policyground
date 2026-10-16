#!/bin/bash
# Runs once, on first start of an empty volume. Trust boundaries (PLAN §4):
#   - the admin role owns the schema and runs migrations; no app process uses it
#   - ingest_rw: the Kafka consumer and the Airflow DAG (read + write data)
#   - api_ro:    the API and the MCP server (read only)
set -euo pipefail

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v ingest_pw="$INGEST_RW_PASSWORD" -v api_pw="$API_RO_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;

CREATE ROLE ingest_rw LOGIN PASSWORD :'ingest_pw';
CREATE ROLE api_ro    LOGIN PASSWORD :'api_pw';

-- Nobody but the owner creates objects in public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO ingest_rw, api_ro;

-- Tables the admin creates later inherit these grants automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ingest_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ingest_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO api_ro;
SQL
