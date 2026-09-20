.PHONY: install lint format typecheck test audit compose-config build up down migrate logs validate

install:
	python -m pip install -e '.[dev]'
lint:
	ruff check .
format:
	ruff format .
typecheck:
	mypy
test:
	pytest tests/unit
audit:
	pip-audit
compose-config:
	docker compose config --quiet
build:
	docker compose build
up:
	docker compose up -d --wait
down:
	docker compose down
migrate:
	docker compose run --rm migrate
logs:
	docker compose logs --tail=200
validate: lint typecheck test audit compose-config
