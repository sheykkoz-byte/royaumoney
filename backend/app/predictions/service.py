"""Registry operations: create, refresh prices, verify, list, track record."""

import hashlib
import json
import logging
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Bar, Prediction, PredictionEvent
from app.predictions.evaluate import evaluate
from app.predictions.spec import PredictionSpec
from app.sources import futures
from app.sources.yahoo import download_ohlc

log = logging.getLogger(__name__)

# Asset → how we price it. Anything else is treated as a Yahoo ticker (stocks, ETFs).
INSTRUMENTS = {
    "XAUUSD": {
        "instrument": "XAUUSD_EST",
        "label": "Spot XAU/USD stimato dai future COMEX (costo di mantenimento)",
    },
}
BAR_LOOKBACK_DAYS = 10


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def instrument_for(asset: str) -> str:
    return INSTRUMENTS.get(asset.upper(), {}).get("instrument") or asset.upper()


def canonical(spec: PredictionSpec) -> str:
    return json.dumps(spec.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


# ---- prices ------------------------------------------------------------------------------
def _upsert_bars(session: Session, instrument: str, df: pd.DataFrame, source: str) -> int:
    """Insert or update bars (the latest bar of the day may be refreshed later)."""
    now = _now()
    existing = {b.date: b for b in session.scalars(
        select(Bar).where(Bar.instrument == instrument))}
    n = 0
    for d, r in df.iterrows():
        day = pd.Timestamp(d).date()
        bar = existing.get(day) or Bar(instrument=instrument, date=day)
        bar.open, bar.high = float(r["open"]), float(r["high"])
        bar.low, bar.close = float(r["low"]), float(r["close"])
        bar.source, bar.fetched_at = source, now
        bar.detail = r.get("detail") if isinstance(r.get("detail"), str) else None
        session.add(bar)
        n += 1
    session.flush()
    return n


def refresh_bars(session: Session, instrument: str, start: date, end: date | None = None) -> int:
    end = end or date.today()
    if instrument == "XAUUSD_EST":
        needed = futures.contracts_needed(start, end)
        raw = download_ohlc([c.symbol for c in needed], start, end)
        df = futures.estimate_spot(raw, start, end)
        return _upsert_bars(session, instrument, df, "yahoo:COMEX GC (stima spot)")
    raw = download_ohlc([instrument], start, end)
    return _upsert_bars(session, instrument, raw.get(instrument, pd.DataFrame()),
                        f"yahoo:{instrument}")


def load_bars(session: Session, instrument: str, start: date | None = None) -> pd.DataFrame:
    q = select(Bar.date, Bar.open, Bar.high, Bar.low, Bar.close).where(
        Bar.instrument == instrument)
    if start:
        q = q.where(Bar.date >= start)
    df = pd.DataFrame(session.execute(q.order_by(Bar.date)).all(),
                      columns=["date", "open", "high", "low", "close"])
    return df.set_index("date")


# ---- create ------------------------------------------------------------------------------
def _next_id(session: Session) -> str:
    """Next free id, also counting ledger files not imported yet."""
    ids = {p for p in session.scalars(select(Prediction.id))}
    d = ledger_dir()
    if d.exists():
        ids |= {f.stem for f in d.glob("P-*.json")}
    n = max((int(i.split("-")[1]) for i in ids), default=0)
    return f"P-{n + 1:04d}"


def create(session: Session, spec: PredictionSpec, context: dict | None = None,
           now: datetime | None = None, ledger: bool = True) -> Prediction:
    """Register a prediction. Its spec is frozen: stored with a SHA-256 fingerprint."""
    now = now or _now()
    instrument = instrument_for(spec.asset)
    created = now.date()
    if spec.targets[0].deadline <= created:
        raise ValueError("the first target's deadline is not in the future")

    offset = 0.0
    ref_close = None
    if spec.align_to_entry:
        refresh_bars(session, instrument, created - timedelta(days=BAR_LOOKBACK_DAYS), created)
        bars = load_bars(session, instrument)
        before = bars[bars.index <= created]
        if before.empty:
            raise ValueError(f"no price for {instrument} before {created}")
        ref_close = float(before["close"].iloc[-1])
        offset = round(spec.entry_price - ref_close, 2)
        if abs(offset) > 0.02 * spec.entry_price:
            raise ValueError(f"entry {spec.entry_price} is {offset:+.2f} from the instrument's "
                             f"last close {ref_close:.2f}: too far to align safely")

    body = canonical(spec)
    p = Prediction(
        id=_next_id(session), created_at=now, author=spec.author, asset=spec.asset.upper(),
        instrument=instrument, direction=spec.direction, entry_price=spec.entry_price,
        probability=spec.probability, horizon_end=spec.horizon_end, title=spec.title,
        scenario=spec.scenario, reasoning=spec.reasoning, spec=body,
        spec_hash=hashlib.sha256(body.encode()).hexdigest(),
        context=json.dumps((context or {}) | {
            "instrument_offset": offset, "instrument_close_at_creation": ref_close,
        }, ensure_ascii=False),
        status="aperta",
    )
    session.add(p)
    session.flush()
    _log(session, p.id, "created", created, "created",
         f"Previsione registrata: {spec.title}.",
         {"spec_hash": p.spec_hash, "offset": offset})
    if ledger:
        export_ledger(p)
    return p


def _log(session: Session, pid: str, key: str, on: date, kind: str, msg: str,
         data: dict | None = None) -> bool:
    exists = session.scalar(select(PredictionEvent.id).where(
        PredictionEvent.prediction_id == pid, PredictionEvent.key == key))
    if exists:
        return False
    session.add(PredictionEvent(prediction_id=pid, key=key, on_date=on, kind=kind, message=msg,
                                data=json.dumps(data or {}, ensure_ascii=False),
                                logged_at=_now()))
    return True


# ---- verify ------------------------------------------------------------------------------
def spec_of(p: Prediction) -> PredictionSpec:
    if hashlib.sha256(p.spec.encode()).hexdigest() != p.spec_hash:
        raise RuntimeError(f"{p.id}: spec does not match its fingerprint")
    return PredictionSpec.model_validate_json(p.spec)


def verify(session: Session, as_of: date | None = None, refresh: bool = True,
           ids: list[str] | None = None) -> list[dict]:
    """Check open predictions against prices and log what changed."""
    as_of = as_of or date.today()
    q = select(Prediction).where(Prediction.status == "aperta")
    if ids:
        q = select(Prediction).where(Prediction.id.in_(ids))
    preds = session.scalars(q).all()
    report = []
    by_instr: dict[str, list[Prediction]] = {}
    for p in preds:
        by_instr.setdefault(p.instrument, []).append(p)

    for instrument, group in by_instr.items():
        start = min(p.created_at.date() for p in group) - timedelta(days=BAR_LOOKBACK_DAYS)
        if refresh:
            try:
                refresh_bars(session, instrument, start, as_of)
            except Exception as e:
                log.exception("Price refresh failed for %s", instrument)
                for p in group:
                    report.append({"id": p.id, "error": f"prezzi non aggiornati: {e}"})
                continue
        bars = load_bars(session, instrument, start)
        for p in group:
            spec = spec_of(p)
            offset = json.loads(p.context or "{}").get("instrument_offset") or 0.0
            res = evaluate(spec, p.created_at.date(), bars, as_of, offset)
            new_events = [e for e in res.events
                          if _log(session, p.id, e.key, e.on_date, e.kind, e.message, e.data)]
            p.status, p.resolved_on = res.status, res.resolved_on
            p.state = json.dumps({"targets": res.targets, "rules": res.rules,
                                  "extremes": res.extremes}, ensure_ascii=False)
            p.checked_at, p.last_bar_date = _now(), res.last_bar
            report.append({"id": p.id, "status": res.status, "last_bar": res.last_bar,
                           "new_events": [e.message for e in new_events]})
    session.flush()
    return report


# ---- read --------------------------------------------------------------------------------
def view(session: Session, p: Prediction, with_events: bool = True) -> dict:
    spec = json.loads(p.spec)
    ctx = json.loads(p.context or "{}")
    state = json.loads(p.state or "{}")
    out = {
        "id": p.id, "title": p.title, "author": p.author, "asset": p.asset,
        "instrument": p.instrument,
        "instrument_label": INSTRUMENTS.get(p.asset, {}).get("label", p.instrument),
        "created_at": p.created_at.isoformat(timespec="seconds"),
        "direction": p.direction, "entry_price": p.entry_price, "probability": p.probability,
        "horizon_end": p.horizon_end.isoformat(), "scenario": p.scenario,
        "reasoning": p.reasoning, "tags": spec.get("tags", []),
        "status": p.status, "resolved_on": p.resolved_on.isoformat() if p.resolved_on else None,
        "targets": state.get("targets") or spec["targets"],
        "invalidations": state.get("rules") or spec["invalidations"],
        "extremes": state.get("extremes"),
        "last_bar_date": p.last_bar_date.isoformat() if p.last_bar_date else None,
        "checked_at": p.checked_at.isoformat(timespec="seconds") if p.checked_at else None,
        "instrument_offset": ctx.get("instrument_offset"),
        "context": {k: v for k, v in ctx.items() if k.startswith("regime") or k == "verdict"},
        "spec_hash": p.spec_hash,
    }
    if with_events:
        out["events"] = [
            {"date": e.on_date.isoformat(), "kind": e.kind, "message": e.message}
            for e in session.scalars(select(PredictionEvent)
                                     .where(PredictionEvent.prediction_id == p.id)
                                     .order_by(PredictionEvent.on_date, PredictionEvent.id))
        ]
    return out


def list_predictions(session: Session, status: str | None = None) -> list[dict]:
    q = select(Prediction).order_by(Prediction.created_at.desc())
    if status:
        q = q.where(Prediction.status == status)
    return [view(session, p, with_events=False) for p in session.scalars(q)]


def analysis_context(session: Session) -> dict:
    """Snapshot of the Phase 2 analysis at creation, to study later which regimes work."""
    from app.analysis.engine import run as run_analysis

    try:
        a = run_analysis(session, with_history=False)
    except Exception as e:  # the registry must work even if the analysis cannot run
        log.warning("Analysis context unavailable: %s", e)
        return {}
    return {
        "regime": a["regime"].get("name"),
        "regime_key": a["regime"].get("key"),
        "verdict": a["verdict"]["text"],
        "regime_scenarios": {s["id"]: s["score"] for s in a["scenarios"]},
    }


# ---- ledger in git -------------------------------------------------------------------------
# Each prediction is also written to registro/<id>.json in the repository. Git history makes
# the ledger tamper-evident, and any fresh database can be rebuilt from it with the
# original creation dates.
def ledger_dir():
    from app.config import BACKEND_DIR

    return BACKEND_DIR.parent / "registro"


def export_ledger(p: Prediction, directory=None) -> None:
    d = directory or ledger_dir()
    d.mkdir(parents=True, exist_ok=True)
    body = {
        "id": p.id,
        "created_at": p.created_at.isoformat(timespec="seconds") + "Z",
        "spec_hash": p.spec_hash,
        "spec": json.loads(p.spec),
        "context": json.loads(p.context or "{}"),
    }
    (d / f"{p.id}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")


def import_ledger(session: Session, directory=None) -> list[str]:
    """Insert ledger entries missing from the database, keeping id and creation date."""
    d = directory or ledger_dir()
    added = []
    for f in sorted(d.glob("P-*.json")) if d.exists() else []:
        body = json.loads(f.read_text(encoding="utf-8"))
        if session.get(Prediction, body["id"]):
            continue
        spec = PredictionSpec.model_validate(body["spec"])
        canon = canonical(spec)
        if hashlib.sha256(canon.encode()).hexdigest() != body["spec_hash"]:
            raise RuntimeError(f"{f.name}: the spec does not match its fingerprint")
        created = datetime.fromisoformat(body["created_at"].rstrip("Z"))
        p = Prediction(
            id=body["id"], created_at=created, author=spec.author, asset=spec.asset.upper(),
            instrument=instrument_for(spec.asset), direction=spec.direction,
            entry_price=spec.entry_price, probability=spec.probability,
            horizon_end=spec.horizon_end, title=spec.title, scenario=spec.scenario,
            reasoning=spec.reasoning, spec=canon, spec_hash=body["spec_hash"],
            context=json.dumps(body.get("context", {}), ensure_ascii=False), status="aperta",
        )
        session.add(p)
        session.flush()
        _log(session, p.id, "created", created.date(), "created",
             f"Previsione registrata: {spec.title}.", {"spec_hash": p.spec_hash,
                                                       "imported_from": f.name})
        added.append(p.id)
    return added
