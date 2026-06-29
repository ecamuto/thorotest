.PHONY: help setup install dev db-reset db-seed demo test test-e2e test-e2e-auth test-e2e-import test-all test-report hooks-install open clean docker-up docker-up-sqlite docker-down docker-logs

PYTHON  := python3
VENV    := venv
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Full setup: venv + deps + Playwright (same as ./install.sh)
	bash install.sh

install: ## Install deps into existing venv (faster re-install)
	$(PIP) install -r requirements.txt
	npm install

dev: ## Start backend dev server on http://localhost:8000
	$(UVICORN) backend.main:app --reload

db-reset: ## Delete DB — re-seeded automatically on next `make dev`
	rm -f testhub.db
	@echo "testhub.db deleted. Run 'make dev' to re-seed."

db-seed: ## Populate DB with demo data (deletes existing DB first)
	rm -f testhub.db
	$(VENV)/bin/python -m backend.seed
	@echo "Done."

demo: db-seed ## Alias: reset DB and load demo data

test: ## Run backend unit tests (pytest)
	$(PYTEST) backend/tests/ -v

test-e2e: ## Run all Playwright e2e tests (requires dev server running)
	npx playwright test

test-e2e-auth: ## Run auth e2e suite only
	npx playwright test e2e/suite1-auth/

test-e2e-import: ## Run import e2e suite only
	npx playwright test e2e/suite17-import/

test-all: ## Full gate: backend pytest + all Playwright e2e (same as CI)
	$(PYTEST) backend/tests/ -q
	npx playwright test

hooks-install: ## Enable the repo's git hooks (pre-push runs test-all)
	git config core.hooksPath .githooks
	@echo "Git hooks enabled. 'git push' now runs 'make test-all' first."

test-report: ## Open last Playwright HTML report
	npx playwright show-report

open: ## Open app in default browser
	open http://localhost:8000

docker-up: ## Start app + Postgres with Docker Compose
	docker compose up --build -d

docker-up-sqlite: ## Start app with SQLite using Docker Compose
	docker compose -f docker-compose.sqlite.yml up --build -d

docker-down: ## Stop and remove Docker containers
	docker compose down

docker-logs: ## Tail Docker container logs
	docker compose logs -f

clean: ## Remove venv, node_modules, DB, test artifacts
	rm -rf $(VENV) node_modules testhub.db playwright-report test-results
