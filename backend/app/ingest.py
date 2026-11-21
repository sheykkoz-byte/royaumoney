"""Download, verify and store every series in the catalog."""

import logging
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app import catalog, derived
from app.catalog import SeriesDef
from app.config import get_settings
from app.db import Series, session_scope
from app.sources import RawPoint
from app.sources.fred import FredClient
from app.sources.yahoo import download_closes
from app.store import SaveReport, load_frame, save_points, sync_catalog

log = logging.getLogger(__name__)

REVERIFY_AFTER = timedelta(days=7)
# On a routine run, re-download this much history so late revisions are picked up.
INCREMENTAL_LOOKBACK = {"daily": 60, "weekly": 180, "monthly": 3 * 365}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _norm(s: str) -> str:
    return " ".join(s.lower().replace(".", "").split())


def _start(session: Session, sdef: SeriesDef, full: bool) -> date:
    backfill = get_settings().backfill_start
    if full or load_frame(session, sdef.id).empty:
        return backfill
    return max(backfill, date.today() - timedelta(days=INCREMENTAL_LOOKBACK[sdef.frequency]))


# ---- verification ------------------------------------------------------------------------
def verify_fred(session: Session, client: FredClient, ids: list[str] | None = None) -> list[dict]:
    """Check each FRED series exists and still has the unit we expect."""
    sync_catalog(session)
    results = []
    for sdef in catalog.SERIES:
        if sdef.source != "fred" or (ids and sdef.id not in ids):
            continue
        row = session.get(Series, sdef.id)
        try:
            meta = client.metadata(sdef.source_id)
            row.verified_title, row.verified_unit = meta.title, meta.unit
            row.verified_frequency = meta.frequency
            if _norm(meta.unit) != _norm(sdef.source_unit or ""):
                row.verify_error = (
                    f"Unit changed: expected {sdef.source_unit!r}, FRED says {meta.unit!r}"
                )
            else:
                row.verify_error = None
        except Exception as e:
            row.verify_error = f"{type(e).__name__}: {e}"
        row.verified_at = _now()
        results.append({
            "id": sdef.id, "title": row.verified_title, "unit": row.verified_unit,
            "frequency": row.verified_frequency, "expected_unit": sdef.source_unit,
            "stored_unit": sdef.unit, "scale": sdef.scale, "error": row.verify_error,
        })
    session.flush()
    return results


# ---- ingestion ---------------------------------------------------------------------------
def _record(session: Session, sid: str, error: str | None) -> None:
    row = session.get(Series, sid)
    row.last_fetch_at = _now()
    row.last_fetch_error = error


def ingest_fred(session: Session, client: FredClient, full: bool = False) -> dict[str, dict]:
    sync_catalog(session)
    stale = [
        s.id for s in catalog.SERIES
        if s.source == "fred"
        and ((r := session.get(Series, s.id)).verified_at is None
             or _now() - r.verified_at > REVERIFY_AFTER)
    ]
    if stale:
        verify_fred(session, client, stale)

    out = {}
    for sdef in catalog.SERIES:
        if sdef.source != "fred":
            continue
        row = session.get(Series, sdef.id)
        if row.verify_error:
            out[sdef.id] = {"skipped": row.verify_error}
            _record(session, sdef.id, f"Not downloaded: {row.verify_error}")
            continue
        try:
            vintages = sdef.revised and client.has_key
            pts = client.observations(sdef.source_id, _start(session, sdef, full), vintages)
            rep = save_points(session, sdef, pts, "alfred" if vintages else "first_seen")
            out[sdef.id] = asdict(rep) | {"points": len(pts), "vintages": vintages}
            _record(session, sdef.id, None)
        except Exception as e:
            log.exception("FRED %s failed", sdef.id)
            out[sdef.id] = {"error": str(e)}
            _record(session, sdef.id, f"{type(e).__name__}: {e}")
    return out


def ingest_yahoo(session: Session, full: bool = False) -> dict[str, dict]:
    sync_catalog(session)
    defs = [s for s in catalog.SERIES if s.source == "yahoo"]
    start = min(_start(session, s, full) for s in defs)
    out = {}
    try:
        data = download_closes([s.source_id for s in defs], start)
    except Exception as e:
        log.exception("Yahoo download failed")
        for s in defs:
            out[s.id] = {"error": str(e)}
            _record(session, s.id, f"{type(e).__name__}: {e}")
        return out
    for s in defs:
        pts = data.get(s.source_id, [])
        if not pts:
            out[s.id] = {"error": "no data returned"}
            _record(session, s.id, "No data returned by Yahoo")
            continue
        rep = save_points(session, s, pts, "market_close")
        out[s.id] = asdict(rep) | {"points": len(pts)}
        _record(session, s.id, None)
    return out


def _to_points(df: pd.DataFrame) -> list[RawPoint]:
    return [
        RawPoint(d.date(), float(r.value), r.published_at.date())
        for d, r in df.iterrows()
    ]


def compute_derived(session: Session) -> dict[str, dict]:
    sync_catalog(session)
    f = {sid: load_frame(session, sid) for s in catalog.SERIES if s.source == "derived"
         for sid in s.inputs}
    results = {
        "FED_NET_LIQ": derived.fed_net_liquidity(f["WALCL"], f["WTREGEN"], f["RRPONTSYD"]),
        "ECB_ASSETS_USD": derived.convert_with_fx(f["ECBASSETSW"], f["DEXUSEU"], multiply=True),
        "BOJ_ASSETS_USD": derived.convert_with_fx(
            f["JPNASSETS"], f["DEXJPUS"], multiply=False, period_end=True),
        "COPPER_GOLD": derived.ratio(f["COPPER"], f["GOLD"], factor=1000),
        "CYCL_DEF": derived.cyclicals_vs_defensives(
            {k: f[k] for k in ("XLY", "XLI", "XLF", "XLB")},
            {k: f[k] for k in ("XLP", "XLU", "XLV")},
        ),
    }
    out = {}
    for sid, df in results.items():
        sdef = catalog.get(sid)
        if df.empty:
            missing = [i for i in sdef.inputs if f[i].empty]
            msg = f"Missing inputs: {', '.join(missing)}" if missing else "No overlapping data"
            out[sid] = {"error": msg}
            _record(session, sid, msg)
            continue
        rep: SaveReport = save_points(session, sdef, _to_points(df), "derived", scale=1.0)
        out[sid] = asdict(rep) | {"points": len(df)}
        _record(session, sid, None)
    return out


def run_all(full: bool = False, sources: tuple[str, ...] = ("fred", "yahoo")) -> dict:
    settings = get_settings()
    report: dict = {"started_at": _now().isoformat(timespec="seconds"),
                    "fred_mode": "api+alfred" if settings.fred_api_key else "public csv (no key)"}
    if "fred" in sources:
        with session_scope() as s:
            report["fred"] = ingest_fred(s, FredClient(settings.fred_api_key), full)
    if "yahoo" in sources:
        with session_scope() as s:
            report["yahoo"] = ingest_yahoo(s, full)
    with session_scope() as s:
        report["derived"] = compute_derived(s)
    report["finished_at"] = _now().isoformat(timespec="seconds")
    return report
