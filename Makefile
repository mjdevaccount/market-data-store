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
PGDATABASE ?= market_data   # matches .env (underscore)

# Docker Compose shortcut
DC := docker compose

.PHONY: help dev up down reset logs run migrate seed policies fmt lint test \
        psql psql-local psql-docker db-shell status db-ready init-db

help:
	@echo "Targets:"
	@echo "  dev         - install project in editable mode (with dev extras if defined)"
	@echo "  up          - docker compose up (build)"
	@echo "  down        - docker compose down (keep volumes)"
	@echo "  reset       - docker compose down -v (NUKES volumes) then up"
	@echo "  logs        - tail docker logs"
	@echo "  run         - start FastAPI dev server on APP_PORT=$(APP_PORT)"
	@echo "  migrate     - run datastore.cli migrate (waits for DB)"
	@echo "  seed        - run datastore.cli seed (waits for DB)"
	@echo "  policies    - run datastore.cli policies"
	@echo "  fmt         - ruff fix + black format"
	@echo "  lint        - ruff check + black --check"
	@echo "  test        - quick import smoke test"
	@echo "  psql        - open psql inside the DB container (most reliable)"
	@echo "  psql-local  - use local Windows psql via host port (requires psql in PATH)"
	@echo "  db-shell    - sh inside DB container"
	@echo "  db-ready    - wait until Postgres is healthy"
	@echo "  init-db     - db-ready -> migrate -> seed -> policies"
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
	docker ps --filter name=md_postgres

# ----- App run (no shell-specific var expansion) -----
run:
	uvicorn datastore.service.app:app --reload --port $(APP_PORT)

# ----- App maintenance -----
# Make these safe: they will wait for DB before running
migrate: db-ready
	python -m datastore.cli migrate

seed: db-ready
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
	docker exec -it md_postgres psql -U $(PGUSER) -d $(PGDATABASE)

# If you WANT to use your Windows psql (you fixed PATH), this hits localhost:5432
psql-local:
	psql -h $(PGHOST) -p $(PGPORT) -U $(PGUSER) -d $(PGDATABASE)

# Open an interactive shell in the DB container (alpine -> use sh)
db-shell:
	docker exec -it md_postgres sh

# Wait until Postgres is healthy before running migrations/seed
db-ready:
	@powershell -NoProfile -Command "while (-not (docker exec md_postgres pg_isready -U $(PGUSER) -d $(PGDATABASE) | Select-String 'accepting connections' -Quiet)) { Start-Sleep -Seconds 1; Write-Host 'Still waiting...'; }; Write-Host 'Postgres is ready!'"

# Chain everything for a single-shot DB init
init-db:
	$(MAKE) db-ready
	$(MAKE) migrate
	$(MAKE) seed
	$(MAKE) policies
	@echo "DB initialization complete."
