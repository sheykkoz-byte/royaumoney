import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import catalog
from app.config import get_settings
from app.db import init_db, session_scope
from app.health import data_health
from app.scheduler import start_scheduler
from app.store import load_frame, sync_catalog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as s:
        sync_catalog(s)
    scheduler = start_scheduler() if get_settings().scheduler_enabled else None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="RoyauMoney API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["GET"],
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
