# ══════════════════════════════════════════════════════════════════
#  SDK Management App — Makefile
#  Usage: make <target>
# ══════════════════════════════════════════════════════════════════

COMPOSE = docker compose -f docker/docker-compose.yml
SERVICES = library-data-service scraper-service comparison-service \
           recommendation-service notification-service scheduler-service \
           api-gateway ui-service

.PHONY: help setup migrate build up down restart logs test lint typecheck \
        security-scan scan-images backup-db

# ── Help ──────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "SDK Management App — available commands:"
	@echo ""
	@echo "  setup          Create all .venv per service + install deps"
	@echo "  migrate        Run Alembic migrations against existing DB"
	@echo "  migrate-check  Show pending migrations without applying"
	@echo "  build          Build all Docker images"
	@echo "  up             Start all services (detached)"
	@echo "  down           Stop all services"
	@echo "  restart        Rebuild + restart all services"
	@echo "  logs           Tail logs for all services"
	@echo "  logs-svc SVC=  Tail logs for a specific service"
	@echo "  test           Run all tests across all services"
	@echo "  test-svc SVC=  Run tests for a specific service"
	@echo "  test-coverage  Run tests + HTML coverage report"
	@echo "  lint           Run ruff linter on all services + shared"
	@echo "  typecheck      Run mypy on all services + shared"
	@echo "  security-scan  Run pip-audit on all requirements.txt"
	@echo "  scan-images    Run trivy vulnerability scan on all images"
	@echo "  backup-db      Manually trigger DB backup"
	@echo ""

# ── Dev Setup ─────────────────────────────────────────────────────
setup:
	@echo "==> Setting up Python 3.12 venvs per service..."
	@for svc in $(SERVICES); do \
		echo "  $$svc..."; \
		cd services/$$svc && python3 -m venv .venv && \
		.venv/bin/pip install -q --upgrade pip && \
		.venv/bin/pip install -q -r requirements.txt; \
		cd ../..; \
	done
	@echo "==> Setting up shared dependencies..."
	@pip install -q packaging pydantic-settings aiosqlite sqlalchemy alembic httpx
	@echo "Done."

# ── Database Migrations ───────────────────────────────────────────
migrate:
	@echo "==> Running Alembic migrations..."
	cd .. && python -m alembic -c lib-management-app/migrations/alembic.ini upgrade head

migrate-check:
	@echo "==> Checking pending migrations..."
	cd .. && python -m alembic -c lib-management-app/migrations/alembic.ini current
	cd .. && python -m alembic -c lib-management-app/migrations/alembic.ini history

migrate-down:
	@echo "==> Rolling back last migration..."
	cd .. && python -m alembic -c lib-management-app/migrations/alembic.ini downgrade -1

# ── Docker ────────────────────────────────────────────────────────
build:
	$(COMPOSE) build --no-cache

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart: down build up

logs:
	$(COMPOSE) logs -f

logs-svc:
	$(COMPOSE) logs -f $(SVC)

# ── Testing ───────────────────────────────────────────────────────
test:
	@for svc in $(SERVICES); do \
		echo "==> Testing $$svc..."; \
		cd services/$$svc && .venv/bin/pytest tests/ -v --tb=short; \
		cd ../..; \
	done

test-svc:
	cd services/$(SVC) && .venv/bin/pytest tests/ -v --tb=short

test-coverage:
	@for svc in $(SERVICES); do \
		echo "==> Coverage $$svc..."; \
		cd services/$$svc && .venv/bin/pytest tests/ \
			--cov=src --cov-report=html:htmlcov --cov-report=term-missing; \
		cd ../..; \
	done

# ── Code Quality ──────────────────────────────────────────────────
lint:
	@echo "==> Linting all services + shared..."
	ruff check services/ shared/ --select E,W,F,I,N,UP

typecheck:
	@echo "==> Type checking all services + shared..."
	mypy services/ shared/ --ignore-missing-imports

security-scan:
	@echo "==> Security scanning all requirements.txt..."
	@for svc in $(SERVICES); do \
		echo "  $$svc..."; \
		pip-audit -r services/$$svc/requirements.txt --desc; \
	done

scan-images:
	@echo "==> Scanning Docker images with trivy..."
	@for svc in $(SERVICES); do \
		echo "  Scanning lib-mgmt/$$svc:latest..."; \
		trivy image lib-mgmt/$$svc:latest --exit-code 1 --severity HIGH,CRITICAL; \
	done

# ── DB Backup ─────────────────────────────────────────────────────
backup-db:
	@echo "==> Triggering manual DB backup via scheduler-service..."
	curl -s -X POST http://localhost:8000/api/v1/scheduler/backup \
		-H "Authorization: Bearer $$ADMIN_TOKEN" | python3 -m json.tool
