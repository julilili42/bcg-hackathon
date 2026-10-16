# Reach — common tasks. `make help` lists them.
UV ?= uv
PORT ?= 7071
export PYTHONPATH := api

.PHONY: help setup dev web build-web check lint format type test web-check smoke seed seed-live secrets rehearse schema clean

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## install Python 3.12 + deps (uv) and web deps (npm)
	$(UV) sync
	cd web && npm install

dev: ## run the API locally on :$(PORT) (uvicorn, SQLite, Twilio signature check off unless TWILIO_VALIDATE is set)
	TWILIO_VALIDATE=$${TWILIO_VALIDATE:-0} $(UV) run uvicorn reach.app:create_app --factory --reload --port $(PORT)

web: ## run the web map dev server on :5173 (proxies /api to :$(PORT))
	cd web && npm run dev

build-web: ## build web/dist, served by the API at /
	cd web && npm run build

lint: ## ruff format check + lint
	$(UV) run ruff format --check api
	$(UV) run ruff check api

format: ## apply ruff formatting and safe fixes
	$(UV) run ruff format api
	$(UV) run ruff check --fix api

type: ## mypy --strict over the package
	$(UV) run mypy

test: ## pytest with coverage gate
	$(UV) run pytest --cov=reach --cov-report=term-missing --cov-fail-under=80

web-check: ## eslint + tsc + vite build
	cd web && npm run lint && npm run typecheck && npm run build

check: lint type test web-check ## everything CI runs

smoke: ## replay Twilio-shaped requests against a running host (make dev + make seed first)
	scripts/smoke.sh http://localhost:$(PORT)

seed: ## reset the local DB and load the Kisarawe snapshot, clinics, and demo overlay
	$(UV) run python -m reach.ingest.seed --reset

seed-live: ## same, but fetch water points from the WPDx API
	$(UV) run python -m reach.ingest.seed --reset --live

secrets: ## scan the repo history for leaked secrets
	gitleaks detect --no-banner --redact

rehearse: ## run the demo script end to end against a running host and print PASS/FAIL per step
	$(UV) run python scripts/rehearse.py http://localhost:$(PORT)

schema: ## regenerate api/reach/storage/schema.sql from the SQLAlchemy metadata (SQLite dialect)
	$(UV) run python scripts/dump_schema.py > api/reach/storage/schema.sql

clean: ## remove caches, local db, audio cache
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis htmlcov coverage.xml .coverage data/local.db audio web/dist
