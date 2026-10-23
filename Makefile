.PHONY: airflow-db airflow-init airflow up down reset migrate seed kg ingest ingest-all api eval test psql

up:
	docker compose build -q
	docker compose up -d --wait
	$(MAKE) migrate

down:
	docker compose down

reset:  ## drop the database volume; init scripts re-run on next `make up`
	docker compose down -v

migrate:  ## apply db/migrations in order, as the schema owner (files are idempotent)
	@for f in db/migrations/*.sql; do \
		echo "applying $$f"; \
		docker compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U pgadmin -d policyground < $$f || exit 1; \
	done

seed:
	uv run python -m policyground.seed

kg:  ## load data/<tenant>/kg.json into the KG tables
	uv run python -m policyground.kg

ingest: kg
	uv run python -m policyground.ingest

ingest-all: kg  ## every chunker x embedder, for the M2 comparison
	for c in naive-800 structural-v1; do for e in bge-small-en-v1.5 e5-base-v2; do \
		uv run python -m policyground.ingest --chunker $$c --embedder $$e || exit 1; done; done

api:  ## http://localhost:8000
	uv run uvicorn policyground.api:app --port 8000

GRAPH ?= kg
eval:  ## GRAPH=rag for the M1 baseline
	uv run python -m policyground.eval --graph $(GRAPH)

test:
	uv run pytest -q

psql:
	docker compose exec postgres psql -U pgadmin -d policyground

# ---- Airflow (M3, D28): its own venv, home and metadata database.
# Config is via AIRFLOW__<SECTION>__<KEY> env vars, so nothing in airflow/home needs editing.
AIRFLOW_ENV = AIRFLOW_HOME=$(CURDIR)/airflow/home \
	AIRFLOW__CORE__DAGS_FOLDER=$(CURDIR)/airflow/dags \
	AIRFLOW__CORE__PLUGINS_FOLDER=$(CURDIR)/airflow/plugins \
	AIRFLOW__CORE__LOAD_EXAMPLES=False \
	AIRFLOW__CORE__EXECUTOR=LocalExecutor \
	AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow_meta:airflow_meta@localhost:5433/airflow \
	POLICYGROUND_ROOT=$(CURDIR)
AIRFLOW = $(AIRFLOW_ENV) airflow/.venv/bin/airflow

airflow-db:  ## create the airflow role + database on an existing volume (idempotent)
	docker compose exec -T postgres psql -q -U pgadmin -d postgres -c \
	  "DO \$$\$$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='airflow_meta') THEN CREATE ROLE airflow_meta LOGIN PASSWORD 'airflow_meta'; END IF; END \$$\$$;"
	docker compose exec -T postgres psql -q -U pgadmin -d postgres -tc \
	  "SELECT 1 FROM pg_database WHERE datname='airflow'" | grep -q 1 || \
	  docker compose exec -T postgres psql -q -U pgadmin -d postgres -c "CREATE DATABASE airflow OWNER airflow_meta"

airflow-init: airflow-db  ## create / upgrade Airflow's metadata tables
	$(AIRFLOW) db migrate

airflow:  ## scheduler + dag-processor + triggerer + API server/UI on http://localhost:8080
	$(AIRFLOW) standalone
