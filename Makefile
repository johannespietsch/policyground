.PHONY: up down reset seed test psql

up:
	docker compose build -q
	docker compose up -d --wait

down:
	docker compose down

reset:  ## drop the database volume; init scripts re-run on next `make up`
	docker compose down -v

seed:
	uv run python -m policyground.seed

test:
	uv run pytest -q

psql:
	docker compose exec postgres psql -U pgadmin -d policyground
