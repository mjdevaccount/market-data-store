.PHONY: dev up down logs fmt lint test run migrate seed policies

dev:
	python -m pip install -U pip wheel
	pip install -e .

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

run:
	uvicorn datastore.service.app:app --reload --port $${APP_PORT:-8081}

migrate:
	python -m datastore.cli migrate

seed:
	python -m datastore.cli seed

policies:
	python -m datastore.cli policies

fmt:
	python -m pip install ruff black
	ruff check --fix .
	black .

lint:
	python -m pip install ruff black
	ruff check .
	black --check .

test:
	python -c "import datastore; print('ok')"
