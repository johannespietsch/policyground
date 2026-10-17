.PHONY: up down reset migrate seed ingest test psql

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

ingest:
	uv run python -m policyground.ingest

test:
	uv run pytest -q

psql:
	docker compose exec postgres psql -U pgadmin -d policyground
