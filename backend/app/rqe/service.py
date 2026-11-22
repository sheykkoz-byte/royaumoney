"""Regime & Quality Engine orchestration: cached regime history, today's snapshot,
allocation, backtest, alerts; written to frontend/public/rqe/rqe.json for the dashboard."""

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.rqe import allocation, assets, backtest, macro
from app.rqe import config as C
from app.store import load_frame, load_versions

HISTORY_CACHE = BACKEND_DIR / "data" / "cache" / "rqe_regime_history.csv"
OUT = BACKEND_DIR.parent / "frontend" / "public" / "rqe" / "rqe.json"
HISTORY_START = "1999-12-31"


def _series_ids() -> set[str]:
    return {c.series for c in C.GROWTH + C.INFLATION}


def regime_history(session: Session, today: date | None = None,
                   cache: Path = HISTORY_CACHE) -> pd.DataFrame:
    """Month-end regime history. A past month's view never changes (it only uses data
    published by then), so cached months are kept and only new month-ends are computed."""
    today = today or date.today()
    dates = pd.date_range(HISTORY_START, today, freq="ME")
    cached = pd.DataFrame()
    if cache.exists():
        cached = pd.read_csv(cache, index_col=0, parse_dates=True)
        # the last cached month may have been computed before that month ended
        cached = cached[cached.index < cached.index.max()] if len(cached) else cached
    todo = dates[~dates.isin(cached.index)] if len(cached) else dates
    if len(todo):
        versions = {sid: load_versions(session, sid) for sid in _series_ids()}
        new = macro.history(versions, pd.DatetimeIndex(todo))
        cached = pd.concat([cached, new]).sort_index()
        cached = cached[~cached.index.duplicated(keep="last")]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cached.to_csv(cache)
    return cached


def snapshot(session: Session, today: date | None = None) -> dict:
    today = today or date.today()
    as_of = pd.Timestamp(today)
    frames = {sid: load_frame(session, sid, as_of=today, availability="first")
              for sid in _series_ids()}
    now = macro.current(frames, as_of)
    hist = regime_history(session, today)
    rets = assets.returns(session)
    base = allocation.risk_parity(rets)
    probs = now.get("probabilita") or {}
    tilted = allocation.tilt(base, probs) if probs else {}
    bt = backtest.run(rets, hist)
    changes = macro.regime_changes(hist)
    return {
        "generato": datetime.now().isoformat(timespec="minutes"),
        "as_of": today.isoformat(),
        "regime": now,
        "quadranti": C.QUADRANTS,
        "storico": [
            {"data": d.date().isoformat(), "crescita": round(r.crescita, 3),
             "inflazione": round(r.inflazione, 3), "dominante": r.dominante,
             **{q: round(float(r[q]), 3) for q in C.QUADRANTS}}
            for d, r in hist.iterrows()
        ],
        "allocazione": {
            "base": {a: round(w, 4) for a, w in base.items()},
            "consigliata": {a: round(w, 4) for a, w in tilted.items()},
            "righe": allocation.explain(base, tilted, probs) if probs else [],
            "limiti": {"scostamento_massimo": C.MAX_DEVIATION, "forza_tilt": C.TILT_STRENGTH},
            "rendimenti_fino_al": rets.index[-1].date().isoformat() if len(rets) else None,
        },
        "backtest": {
            "strategie": backtest.STRATEGIES,
            "statistiche": bt["stats"],
            "per_regime": bt["by_regime"],
            "curve": backtest.curves(bt["returns"]),
            "costi_bps": C.COST_BPS,
            "note": [
                "Prima della nascita degli ETF i rendimenti sono ricostruiti: obbligazioni e "
                "TIPS da rendimenti FRED (carry − duration × variazione), oro e materie prime "
                "dai future. I TIPS entrano nel 2003.",
                "Il regime di ogni mese usa solo i dati pubblicati entro quel mese, "
                "revisioni comprese.",
                "Ribilanciamento mensile, costo di 10 punti base per unità di turnover. "
                "Allocazione modello a scopo di ricerca, non consulenza personalizzata.",
            ],
        },
        "alert": {"cambi_di_regime": changes[-12:], "soglia": C.ALERT_MIN_PROB},
    }


def export(session: Session, out: Path = OUT, today: date | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot(session, today), ensure_ascii=False,
                              separators=(",", ":"), default=str), encoding="utf-8")
    return out
