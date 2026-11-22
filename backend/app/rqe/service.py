"""Regime & Quality Engine orchestration: cached regime history, today's snapshot,
allocation, backtest, alerts; written to frontend/public/rqe/rqe.json for the dashboard."""

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.rqe import allocation, assets, backtest, calibrate, macro
from app.rqe import config as C
from app.store import load_frame, load_versions

HISTORY_CACHE = BACKEND_DIR / "data" / "cache" / "rqe_regime_history.csv"
CALIBRATION = BACKEND_DIR.parent / "docs" / "rqe-taratura.json"
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

    # Probabilities used by the tilt: scores averaged over SMOOTH_MONTHS (today + history)
    probs_hist = calibrate.probs_from_scores(hist, C.SIGMA, C.SMOOTH_MONTHS)
    probs = now.get("probabilita") or {}
    if probs:
        recent = pd.concat([hist[["crescita", "inflazione"]],
                            pd.DataFrame({"crescita": [now["crescita"]["punteggio"]],
                                          "inflazione": [now["inflazione"]["punteggio"]]},
                                         index=[as_of])])
        smoothed = calibrate.probs_from_scores(recent, C.SIGMA, C.SMOOTH_MONTHS).iloc[-1]
        probs_tilt = {q: float(smoothed[q]) for q in C.QUADRANTS}
    else:
        probs_tilt = {}
    if C.TILT_MODE == "imparato":
        prefs = calibrate.learned_preferences(rets, probs_hist, as_of + pd.offsets.MonthEnd(1))
        tilt_fn = calibrate.learned(probs_hist)
    else:
        prefs, tilt_fn = C.TILTS, None
    tilted = allocation.tilt(base, probs_tilt, tilts=prefs) if probs_tilt and prefs else {}
    bt = backtest.run(rets, probs_hist, tilt_fn=tilt_fn)
    changes = macro.regime_changes(hist)
    calib = json.loads(CALIBRATION.read_text(encoding="utf-8")) if CALIBRATION.exists() else None
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
            "righe": allocation.explain(base, tilted, probs_tilt, prefs) if tilted else [],
            "limiti": {"scostamento_massimo": C.MAX_DEVIATION, "forza_tilt": C.TILT_STRENGTH},
            "tilt": {"modo": C.TILT_MODE, "media_mesi": C.SMOOTH_MONTHS,
                     "probabilita_usate": {q: round(p, 3) for q, p in probs_tilt.items()},
                     "preferenze": {q: {a: round(v, 2) for a, v in d.items()}
                                    for q, d in (prefs or {}).items()},
                     "preferenze_teoriche": C.TILTS},
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
        "taratura": calib,
    }


def export(session: Session, out: Path = OUT, today: date | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot(session, today), ensure_ascii=False,
                              separators=(",", ":"), default=str), encoding="utf-8")
    return out


def calibrate_and_save(session: Session, out: Path = CALIBRATION) -> dict:
    """Run the calibration grid and save a summary (train/test, choice, significance)."""
    hist = regime_history(session)
    rets = assets.returns(session)
    res = calibrate.evaluate(rets, hist)
    best = calibrate.choose(res)
    probs = calibrate.probs_from_scores(hist, best["sigma"], best["media_mesi"])
    fn = calibrate.learned(probs, best["forza"]) if best["tipo"] == "imparato" else \
        calibrate.theoretical(best["forza"])
    r = backtest.run(rets, probs, tilt_fn=fn)["returns"]
    summary = {
        "generata": datetime.now().isoformat(timespec="minutes"),
        "periodi": {"taratura": f"2000 – {calibrate.TRAIN_END[:4]}",
                    "verifica": f"{calibrate.TEST_START[:4]} – oggi"},
        "scelto": {k: best[k] for k in ("tipo", "sigma", "media_mesi", "forza")},
        "risk_parity": {"train": best["rp_train"], "test": best["rp_test"]},
        "scelto_stats": {"train": best["train"], "test": best["test"]},
        "significativita_test": calibrate.significance(r["rp_tilt"], r["rp"],
                                                       start=calibrate.TEST_START),
        "candidati": [{k: c[k] for k in ("tipo", "sigma", "media_mesi", "forza")}
                      | {"sharpe_train": c["train"]["sharpe"], "sharpe_test": c["test"]["sharpe"],
                         "dd_test": c["test"]["max_drawdown"]}
                      for c in sorted(res, key=lambda x: -x["train"]["sharpe"])],
    }
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str) + "\n",
                   encoding="utf-8")
    return summary
