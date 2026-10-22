.PHONY: up down reset migrate seed kg ingest ingest-all api eval test psql

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
