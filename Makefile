UV ?= uv
NPM ?= npm

.PHONY: check backend-check frontend-check contracts-check api-generate

check: backend-check contracts-check frontend-check

backend-check:
	cd backend && $(UV) run --locked ruff check .
	cd backend && $(UV) run --locked ruff format --check .
	cd backend && $(UV) run --locked pytest -q

frontend-check:
	cd frontend && $(NPM) run lint
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) test
	cd frontend && $(NPM) run build

contracts-check:
	cd backend && $(UV) run --locked python scripts/export_openapi.py --check
	cd frontend && $(NPM) run api:check

api-generate:
	cd backend && $(UV) run --locked python scripts/export_openapi.py
	cd frontend && $(NPM) run api:generate
