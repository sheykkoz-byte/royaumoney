.PHONY: setup dev backend frontend verify ingest ingest-full health analisi previsioni previsione previsioni-verifica previsioni-importa track-record test lint

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

previsioni:       ## Prediction registry: list
	$(BACK) $(UV) run python -m app.cli previsioni list

previsione:       ## One prediction with its event log (ID=P-0001)
	$(BACK) $(UV) run python -m app.cli previsioni show $(ID)

previsioni-verifica: ## Check open predictions against prices now
	$(BACK) $(UV) run python -m app.cli previsioni verifica

previsioni-importa: ## Rebuild the registry from registro/*.json (keeps original dates)
	$(BACK) $(UV) run python -m app.cli previsioni importa

track-record:     ## Hit rates, Brier score, calibration
	$(BACK) $(UV) run python -m app.cli track-record

test:
	$(BACK) $(UV) run pytest -q

lint:
	$(BACK) $(UV) run ruff check .
