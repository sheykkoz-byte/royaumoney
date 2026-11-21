.PHONY: setup dev backend frontend verify ingest ingest-full health analisi test lint

UV ?= uv
BACK = cd backend &&

setup:            ## Install backend and frontend dependencies
	$(BACK) $(UV) sync
	cd frontend && npm ci
	@test -f .env || (cp .env.example .env && echo "Created .env — add FRED_API_KEY")

dev:              ## Backend (8000) + frontend (3000)
	$(MAKE) -j2 backend frontend

backend:
	$(BACK) $(UV) run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

verify:           ## Check every FRED ID and unit → docs/serie-verificate.md
	$(BACK) $(UV) run python -m app.cli verify

ingest:           ## Download new data (incremental)
	$(BACK) $(UV) run python -m app.cli ingest

ingest-full:      ## Re-download the whole history
	$(BACK) $(UV) run python -m app.cli ingest --full

health:           ## Data freshness in the terminal
	$(BACK) $(UV) run python -m app.cli health

analisi:          ## Regime, scenarios, convergence (AS_OF=YYYY-MM-DD for a past date)
	$(BACK) $(UV) run python -m app.cli analisi $(if $(AS_OF),--as-of $(AS_OF))

test:
	$(BACK) $(UV) run pytest -q

lint:
	$(BACK) $(UV) run ruff check .
