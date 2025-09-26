# Load .env (simple KEY=VALUE lines) and export vars to recipes
# This avoids shell-specific ${VAR:-default} hacks.
include .env
export

# -------- Defaults (override in .env) --------
APP_PORT ?= 8081

# Local psql defaults (override in .env if you want to use your Windows psql)
PGHOST ?= localhost
PGPORT ?= 5432
PGUSER ?= postgres
PGDATABASE ?= marketdata

# Docker Compose shortcut
DC := docker compose

.PHONY: help dev up down reset logs run migrate seed policies fmt lint test \
        psql psql-local psql-docker db-shell status

help:
	@echo "Targets:"
	@echo "  dev         - install project in editable mode (with dev extras if defined)"
	@echo "  up          - docker compose up (build)"
	@echo "  down        - docker compose down (keep volumes)"
	@echo "  reset       - docker compose down -v (NUKES volumes) then up"
	@echo "  logs        - tail docker logs"
	@echo "  run         - start FastAPI dev server on APP_PORT=$(APP_PORT)"
	@echo "  migrate     - run datastore.cli migrate"
	@echo "  seed        - run datastore.cli seed"
	@echo "  policies    - run datastore.cli policies"
	@echo "  fmt         - ruff fix + black format"
	@echo "  lint        - ruff check + black --check"
	@echo "  test        - quick import smoke test"
	@echo "  psql        - open psql inside the DB container (most reliable)"
	@echo "  psql-local  - use local Windows psql via host port (requires psql in PATH)"
	@echo "  db-shell    - sh inside DB container"
	@echo "  status      - docker ps filter for md_postgres"

# ----- Python dev -----
dev:
	python -m pip install -U pip wheel
	-pip install -e ".[dev]" || pip install -e .

# ----- Docker lifecycle -----
up:
	$(DC) up -d --build

down:
	$(DC) down

reset:
	$(DC) down -v
	$(DC) up -d --build

logs:
	$(DC) logs -f --tail=200

status:
	docker ps --filter name=market_data_store-db

# ----- App run (no shell-specific var expansion) -----
run:
	uvicorn datastore.service.app:app --reload --port $(APP_PORT)

# ----- App maintenance -----
migrate:
	python -m datastore.cli migrate

seed:
	python -m datastore.cli seed

policies:
	python -m datastore.cli policies

# ----- Formatting & linting -----
fmt:
	-ruff --version >/dev/null 2>&1 || python -m pip install -q ruff
	-black --version >/dev/null 2>&1 || python -m pip install -q black
	ruff check --fix .
	black .

lint:
	-ruff --version >/dev/null 2>&1 || python -m pip install -q ruff
	-black --version >/dev/null 2>&1 || python -m pip install -q black
	ruff check .
	black --check .

test:
	python -c "import datastore; print('ok')"

# ----- Postgres helpers -----
# Most reliable: use the psql inside the running container (no Windows PATH drama)
psql psql-docker:
	docker exec -it market_data_store-db psql -U $(PGUSER) -d $(PGDATABASE)

# If you WANT to use your Windows psql (you fixed PATH), this hits localhost:5432
psql-local:
	psql -h $(PGHOST) -p $(PGPORT) -U $(PGUSER) -d $(PGDATABASE)

# Open an interactive shell in the DB container (alpine -> use sh)
db-shell:
	docker exec -it market_data_store-db sh
