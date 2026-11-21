import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import catalog
from app.analysis.engine import run as run_analysis
from app.config import get_settings
from app.db import Prediction, init_db, session_scope
from app.health import data_health
from app.predictions import service as predictions
from app.predictions.spec import PredictionSpec
from app.predictions.stats import track_record
from app.scheduler import start_scheduler
from app.store import load_frame, sync_catalog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as s:
        sync_catalog(s)
        predictions.import_ledger(s)  # a fresh database picks up the git ledger
    scheduler = start_scheduler() if get_settings().scheduler_enabled else None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="RoyauMoney API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/data")
def health_data() -> dict:
    with session_scope() as s:
        return data_health(s)


@app.get("/series")
def list_series() -> list[dict]:
    return [
        {"id": d.id, "name": d.name, "category": d.category, "source": d.source,
         "source_id": d.source_id, "unit": d.unit, "frequency": d.frequency, "notes": d.notes}
        for d in catalog.SERIES
    ]


@app.get("/series/{series_id}")
def get_series(
    series_id: str,
    start: date | None = None,
    as_of: date | None = Query(None, description="Only values published on or before this date"),
) -> dict:
    try:
        sdef = catalog.get(series_id)
    except KeyError:
        raise HTTPException(404, f"Unknown series {series_id}") from None
    with session_scope() as s:
        df = load_frame(s, series_id, as_of=as_of, start=start)
    return {
        "id": sdef.id, "name": sdef.name, "unit": sdef.unit, "source": sdef.source,
        "as_of": as_of.isoformat() if as_of else None,
        "points": [
            {"date": d.date().isoformat(), "value": r.value,
             "published_at": r.published_at.date().isoformat()}
            for d, r in df.iterrows()
        ],
    }


@app.get("/analisi/oggi")
def analisi_oggi(
    as_of: date | None = Query(
        None, description="Analysis as it would have been on this date (point in time)"),
    history: bool = Query(True, description="Include regime history and voice timelines"),
) -> dict:
    """Regime, scenarios, convergence and divergences, with the data behind each one."""
    if as_of and as_of > date.today():
        raise HTTPException(400, "as_of cannot be in the future")
    with session_scope() as s:
        return run_analysis(s, as_of, has_fred_key=bool(get_settings().fred_api_key),
                            with_history=history)


# ---- Phase 3: prediction registry --------------------------------------------------------
@app.get("/previsioni")
def list_previsioni(status: str | None = None) -> list[dict]:
    with session_scope() as s:
        return predictions.list_predictions(s, status)


@app.get("/previsioni/{pid}")
def get_previsione(pid: str) -> dict:
    with session_scope() as s:
        p = s.get(Prediction, pid)
        if p is None:
            raise HTTPException(404, f"Previsione {pid} non trovata")
        return predictions.view(s, p)


@app.post("/previsioni", status_code=201)
def create_previsione(spec: PredictionSpec) -> dict:
    """Register a prediction (frozen after creation) and verify it immediately."""
    with session_scope() as s:
        try:
            p = predictions.create(s, spec, predictions.analysis_context(s))
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        predictions.verify(s, ids=[p.id])
        return predictions.view(s, p)


@app.get("/track-record")
def get_track_record() -> dict:
    with session_scope() as s:
        return track_record(s)
