.DEFAULT_GOAL := help
SHELL := /bin/bash

UV ?= uv
NPM ?= npm

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- setup -----------------------------------------------------------------

.PHONY: install
install: ## Install API + dev deps and the frontend (no torch)
	$(UV) sync --group api --group dev
	cd web && $(NPM) install

.PHONY: install-worker
install-worker: ## Add the worker deps (torch, transformers, pyannote) -- several GB
	$(UV) sync --group api --group worker --group dev

# --- run -------------------------------------------------------------------

.PHONY: api
api: ## Run the API with reload
	$(UV) run uvicorn sarai.api.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: worker
worker: ## Run the worker
	$(UV) run python -m sarai.worker.main

.PHONY: web
web: ## Run the Vite dev server
	cd web && $(NPM) run dev

.PHONY: dev
dev: ## Run API + worker + web together (Ctrl-C stops all three)
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) api & \
	$(MAKE) worker & \
	$(MAKE) web & \
	wait

# --- codegen and checks ----------------------------------------------------

.PHONY: types
types: ## Regenerate web/src/types.ts from the Pydantic models
	$(UV) run python scripts/gen_types.py

.PHONY: types-check
types-check: ## Fail if web/src/types.ts has drifted (CI)
	$(UV) run python scripts/gen_types.py --check

.PHONY: test
test: ## Run the pytest suite
	$(UV) run pytest -q

.PHONY: lint
lint: ## ruff + mypy --strict
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy

.PHONY: fmt
fmt: ## Autoformat
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

.PHONY: typecheck-web
typecheck-web: ## TypeScript strict check
	cd web && $(NPM) run typecheck

.PHONY: check
check: lint types-check test typecheck-web ## Everything CI runs

# --- docker ----------------------------------------------------------------

.PHONY: up
up: ## docker compose up --build
	docker compose up --build

.PHONY: down
down: ## docker compose down
	docker compose down

.PHONY: clean
clean: ## Remove caches and build output
	rm -rf .pytest_cache .mypy_cache .ruff_cache web/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
