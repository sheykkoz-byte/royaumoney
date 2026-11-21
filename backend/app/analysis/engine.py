"""Daily analysis (plan phase 2): indicators → regime → scenarios → convergence/divergence.

``analyze`` is pure (frames in, dict out) so it can be tested and back-tested; ``run`` loads
the frames from the database as they were known on ``as_of``.
"""

from datetime import date

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import catalog
from app.analysis import config as C
from app.analysis import regime, scoring
from app.analysis.indicators import build, latest, on_dates
from app.db import Observation
from app.store import load_frame

HISTORY_START = pd.Timestamp("2000-01-31")
TIMELINE_MONTHS = 24


def required_series() -> set[str]:
    ids = {s for i in C.INDICATORS for s in i.series}
    return ids | {sid for sid, _ in C.REGIME_ASSETS}


def _num(x, nd: int = 3):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def _indicator_view(ind, row: pd.Series | None) -> dict:
    base = {"id": ind.id, "label": ind.label, "voice": ind.voice, "unit": ind.unit,
            "change_unit": C.change_unit(ind),
            "series": list(ind.series), "z_window_years": ind.z_years, "note": ind.note or None}
    if row is None:
        return base | {"available": False}
    return base | {
        "available": True,
        "date": row.name.date().isoformat(),
        "published_at": row["available"].date().isoformat(),
        "value": _num(row["value"]),
        "chg_1m": _num(row["chg1"]), "chg_3m": _num(row["chg3"]), "chg_6m": _num(row["chg6"]),
        "z": _num(row["z"], 2),
        "z_chg_3m": _num(row["z_chg3"], 2),
    }


def scenario_history(ind_frames: dict[str, pd.DataFrame], dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Macro and market voice of every scenario on each date (data known at that date).

    Columns: ``<scenario>_macro`` and ``<scenario>_market``.
    """
    out = {}
    for sc in C.SCENARIOS:
        acc = {v: (pd.Series(0.0, index=dates), pd.Series(0.0, index=dates))
               for v in ("macro", "market")}
        for s in sc.signals:
            voice = C.INDICATOR_BY_ID[s.indicator].voice
            v = (s.sign * on_dates(ind_frames[s.indicator], s.field, dates)).clip(
                -C.Z_CLIP, C.Z_CLIP)
            ok = v.notna()
            num, den = acc[voice]
            num[ok] += v[ok] * s.weight
            den[ok] += s.weight
        for voice, (num, den) in acc.items():
            out[f"{sc.id}_{voice}"] = (num / den).where(den > 0)
    return pd.DataFrame(out, index=dates)


def _scenario(sc: C.Scenario, rows: dict[str, pd.Series | None],
              past_gaps: list[float]) -> dict:
    voices: dict[str, list] = {"macro": [], "market": []}
    evidence = []
    for s in sc.signals:
        ind = C.INDICATOR_BY_ID[s.indicator]
        row = rows.get(s.indicator)
        z = None if row is None or pd.isna(row.get(s.field)) else float(row[s.field])
        aligned = None if z is None else s.sign * z
        voices[ind.voice].append((aligned, s.weight))
        raw_field = C.FIELD_RAW[s.field]
        evidence.append({
            "indicator": s.indicator,
            "label": ind.label,
            "voice": ind.voice,
            "measure": C.FIELD_LABELS[s.field],
            "expected": "alto" if s.sign > 0 else "basso",
            "value": None if row is None else _num(row.get(raw_field)),
            "unit": ind.unit if raw_field == "value" else C.change_unit(ind),
            "z": _num(z, 2),
            "aligned_z": _num(aligned, 2),
            "weight": s.weight,
            "stance": scoring.stance(aligned),
            "date": None if row is None else row.name.date().isoformat(),
        })
    macro, macro_cov = scoring.weighted_mean(voices["macro"])
    market, market_cov = scoring.weighted_mean(voices["market"])

    threshold, basis = scoring.divergence_threshold(past_gaps)
    gap = None if macro is None or market is None else market - macro
    div = scoring.divergence(macro, market, threshold)
    pct = None if gap is None else scoring.gap_percentile(gap, past_gaps)
    if div:
        div["percentile"] = None if pct is None else round(pct, 2)
        if div["leader"] == "mercato":
            div["text"] = (f"Il mercato prezza «{sc.name}» più di quanto dicano i dati macro: "
                           "possibile cambiamento in arrivo non ancora visibile nei dati.")
        else:
            div["text"] = (f"I dati macro vanno verso «{sc.name}», ma il mercato non ci crede "
                           "(ancora).")

    by_strength = sorted(evidence, key=lambda e: -abs(e["aligned_z"] or 0) * e["weight"])
    return {
        "id": sc.id,
        "name": sc.name,
        "description": sc.description,
        "score": scoring.scenario_score(macro, market),
        "macro_voice": _num(macro, 2),
        "market_voice": _num(market, 2),
        "coverage": {"macro": round(macro_cov, 2), "market": round(market_cov, 2)},
        "convergence": scoring.convergence(macro, market),
        "gap": _num(gap, 2),
        "gap_percentile": None if pct is None else round(pct, 2),
        "divergence_threshold": {"value": round(threshold, 2), "basis": basis},
        "divergence_alarm": div,
        "supports": [e for e in by_strength if e["stance"] == "sostiene"],
        "contradicts": [e for e in by_strength if e["stance"] == "contraddice"],
        "neutral": [e for e in by_strength if e["stance"] in ("neutro", "mancante")],
    }


def _verdict(scenarios: list[dict]) -> dict:
    """Dominant scenario, or an explicit statement that the data are mixed."""
    scored = [s for s in scenarios if s["score"] is not None]
    if not scored:
        return {"scenario": None, "mixed": True, "text": "Dati insufficienti per un giudizio."}
    top = scored[0]
    second = scored[1]["score"] if len(scored) > 1 else -100
    if top["score"] < C.DOMINANT_MIN_SCORE or top["score"] - second < C.DOMINANT_MIN_LEAD:
        close = [s["name"] for s in scored if top["score"] - s["score"] < C.DOMINANT_MIN_LEAD]
        return {
            "scenario": None, "mixed": True,
            "text": ("Nessuno scenario prevale: i dati sono contrastanti"
                     + (f" ({' e '.join(close)} quasi alla pari)" if len(close) > 1 else "")
                     + f". Il più forte ha punteggio {top['score']}."),
        }
    return {"scenario": top["id"], "mixed": False,
            "text": f"Scenario dominante: {top['name']} (punteggio {top['score']})."}


def analyze(frames: dict[str, pd.DataFrame], as_of: pd.Timestamp,
            notes: list[str] | None = None, with_history: bool = True) -> dict:
    ind_frames = {i.id: build(i, frames) for i in C.INDICATORS}
    rows = {i.id: latest(ind_frames[i.id], as_of) for i in C.INDICATORS}
    reg = regime.current(rows)

    voice_hist = pd.DataFrame()
    if with_history:
        dates = regime.month_ends(HISTORY_START, as_of)
        hist = regime.history(ind_frames, dates)
        perf = regime.performance(hist, frames, as_of)
        reg["history"] = {
            "from": perf.get("from"), "to": perf.get("to"), "months": perf["months"],
            "current": perf["regimes"].get(reg.get("key")) if reg.get("available") else None,
            "all": {k: {"months": v["months"]} for k, v in perf["regimes"].items()},
            "note": ("Rendimento medio del mese successivo in ciascun regime, rispetto alla media "
                     "di tutti i mesi. Il regime di ogni mese usa solo i dati già pubblicati "
                     "a fine mese."),
        }
        reg["timeline"] = [
            {"date": d.date().isoformat(), "regime": r.regime,
             "liquidity": round(r.liquidity, 2), "growth": round(r.growth, 2),
             "inflation": round(r.inflation, 2)}
            for d, r in hist.tail(TIMELINE_MONTHS).iterrows()
        ]
        # Month-ends strictly before as_of: today's own gap is not part of its benchmark
        voice_hist = scenario_history(ind_frames, dates[dates < as_of])

    scenarios = []
    for sc in C.SCENARIOS:
        past = []
        if not voice_hist.empty:
            past = (voice_hist[f"{sc.id}_market"] - voice_hist[f"{sc.id}_macro"]).dropna()
            past = past.tolist()
        out = _scenario(sc, rows, past)
        if not voice_hist.empty:
            tl = voice_hist[[f"{sc.id}_macro", f"{sc.id}_market"]].dropna().tail(TIMELINE_MONTHS)
            out["timeline"] = [
                {"date": d.date().isoformat(), "macro": round(m, 2), "market": round(k, 2),
                 "convergence": scoring.convergence(m, k)}
                for d, (m, k) in tl.iterrows()
            ]
        scenarios.append(out)
    scenarios.sort(key=lambda s: -(s["score"] if s["score"] is not None else -999))

    divergences = [
        {"scenario": s["id"], "name": s["name"], **s["divergence_alarm"],
         "macro_voice": s["macro_voice"], "market_voice": s["market_voice"]}
        for s in scenarios if s["divergence_alarm"]
    ]
    verdict = _verdict(scenarios)
    return {
        "as_of": as_of.date().isoformat(),
        "regime": reg,
        "scenarios": scenarios,
        "dominant_scenario": verdict["scenario"],
        "verdict": verdict,
        "divergences": divergences,
        "indicators": [_indicator_view(i, rows[i.id]) for i in C.INDICATORS],
        "notes": notes or [],
        "method": {
            "z_score": "z-score su 5 anni (3 anni per gli spread ICE), limitato a ±3.",
            "voices": "Voce = media pesata degli z-score allineati al segno atteso dallo scenario.",
            "convergence": ("100·m·k/max(m²,k²): +100 voci identiche, −100 opposte, "
                            "0 una voce muta."),
            "divergence_alarm": (
                f"Distanza tra le voci più ampia del {C.DIVERGENCE_PERCENTILE:.0%} dei mesi "
                f"precedenti (soglia fissa {C.DIVERGENCE_FALLBACK}σ se lo storico è corto)."),
            "score": f"Media delle due voci; {C.SCORE_FULL_SCALE}σ = 100.",
            "regime": "Assi = media pesata delle variazioni scalate (segno = direzione).",
        },
    }


def data_notes(session: Session, has_fred_key: bool) -> list[str]:
    notes = []
    revised = [s.id for s in catalog.SERIES if s.revised]
    rows = session.execute(
        select(Observation.series_id, func.count())
        .where(Observation.series_id.in_(revised), Observation.pub_method == "estimated_lag")
        .group_by(Observation.series_id)).all()
    n_alfred = session.scalar(select(func.count()).select_from(Observation)
                              .where(Observation.pub_method == "alfred"))
    if not n_alfred:
        notes.append(
            "Le date di pubblicazione dello storico FRED sono stimate"
            + (" (manca la chiave FRED)" if not has_fred_key else
               ": rilancia `make ingest-full` per scaricare le date esatte da ALFRED")
            + ". Il regime storico può anticipare di qualche giorno i dati reali e ignora "
              "le revisioni.")
    elif rows:
        ids = ", ".join(sorted(sid for sid, _ in rows))
        notes.append(
            "Date di pubblicazione esatte (ALFRED) con revisioni. Per alcune osservazioni "
            f"vecchie ALFRED non ha la prima versione ({ids}, per lo più prima del 2009): "
            "lì la data è stimata.")
    notes.append("Spread high yield e investment grade: storico di soli 3 anni su FRED "
                 "(licenza ICE), z-score calcolato su 3 anni. Lo spread Baa ha storico lungo.")
    return notes


def run(session: Session, as_of: date | None = None, has_fred_key: bool = False,
        with_history: bool = True) -> dict:
    as_of_ts = pd.Timestamp(as_of or date.today())
    frames = {sid: load_frame(session, sid, as_of=as_of_ts.date())
              for sid in required_series()}
    return analyze(frames, as_of_ts, data_notes(session, has_fred_key), with_history)
