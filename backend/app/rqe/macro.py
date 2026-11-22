"""Dalio's growth and inflation signals and the probability of each of the four regimes.

Each component is a series transformed (e.g. year-on-year) whose 3- and 6-month change is
compared with its own last five years (robust z-score): a positive value means "above
trend". The composite of the growth components and the composite of the inflation
components give P(growth rising) = Φ(score/σ) and P(inflation rising); the four quadrant
probabilities are the products. Everything is point-in-time: on each date only data
already published is used.
"""

import math

import pandas as pd

from app.analysis.indicators import Indicator, build, latest, on_dates  # noqa: F401
from app.rqe import config as C


def _indicator(c: C.Component) -> Indicator:
    return Indicator(c.series, c.label, "macro", (c.series,), c.transform, "diff", "")


def component_frames(frames: dict[str, pd.DataFrame], comps: list[C.Component]) -> dict:
    return {c.series: build(_indicator(c), frames) for c in comps}


def _component_value(c: C.Component, row_or_values) -> float | None:
    vals = [row_or_values.get(f) for f in c.fields]
    vals = [float(v) for v in vals if v is not None and not pd.isna(v)]
    if not vals:
        return None
    return c.sign * max(-C.Z_CLIP, min(C.Z_CLIP, sum(vals) / len(vals)))


def composite_now(ind: dict[str, pd.DataFrame], comps: list[C.Component],
                  as_of: pd.Timestamp) -> dict:
    parts, num, den = [], 0.0, 0.0
    for c in comps:
        row = latest(ind[c.series], as_of) if not ind[c.series].empty else None
        v = None if row is None else _component_value(c, row)
        if v is not None:
            num += v * c.weight
            den += c.weight
        parts.append({
            "serie": c.series, "nome": c.label, "peso": c.weight,
            "segnale": None if v is None else round(v, 2),
            "valore": None if row is None else round(float(row["value"]), 3),
            "data": None if row is None else row.name.date().isoformat(),
        })
    return {"punteggio": None if den == 0 else round(num / den, 3), "componenti": parts,
            "copertura": round(den / sum(c.weight for c in comps), 2)}


def composite_history(ind: dict[str, pd.DataFrame], comps: list[C.Component],
                      dates: pd.DatetimeIndex) -> pd.Series:
    num = pd.Series(0.0, index=dates)
    den = pd.Series(0.0, index=dates)
    for c in comps:
        cols = [on_dates(ind[c.series], f, dates) for f in c.fields]
        v = pd.concat(cols, axis=1).mean(axis=1, skipna=True)
        v = (c.sign * v).clip(-C.Z_CLIP, C.Z_CLIP)
        ok = v.notna()
        num[ok] += v[ok] * c.weight
        den[ok] += c.weight
    return (num / den).where(den > 0)


def p_rising(score: float | None) -> float | None:
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return None
    return 0.5 * (1 + math.erf(score / C.SIGMA / math.sqrt(2)))


def quadrant_probs(p_growth: float, p_infl: float) -> dict[str, float]:
    out = {}
    for q, d in C.QUADRANTS.items():
        pg = p_growth if d["growth"] else 1 - p_growth
        pi = p_infl if d["inflation"] else 1 - p_infl
        out[q] = pg * pi
    return out


def history(versions: dict[str, pd.DataFrame], dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Monthly scores, probabilities and the most likely quadrant, truly point in time:
    on each date every series is rebuilt as it was known that day (revisions included).

    ``versions``: series id → every stored version (``store.load_versions``).
    """
    from app.store import as_known_on

    comps = C.GROWTH + C.INFLATION
    revised = {sid for sid, v in versions.items() if v.duplicated("ref_date").any()}
    # Series never revised: one build serves every date
    fixed = {c.series: build(_indicator(c), {c.series: as_known_on(versions[c.series],
                                                                    dates[-1])})
             for c in comps if c.series not in revised}
    rows = []
    for d in dates:
        vals = {}
        for c in comps:
            if c.series in fixed:
                df = fixed[c.series]
            else:
                frame = as_known_on(versions[c.series], d)
                df = build(_indicator(c), {c.series: frame}) if not frame.empty else frame
            row = latest(df, d) if not df.empty else None
            vals[c.series] = None if row is None else _component_value(c, row)
        rec = {"data": d}
        for name, group in (("crescita", C.GROWTH), ("inflazione", C.INFLATION)):
            num = sum(vals[c.series] * c.weight for c in group if vals[c.series] is not None)
            den = sum(c.weight for c in group if vals[c.series] is not None)
            rec[name] = num / den if den else None
        rows.append(rec)
    df = pd.DataFrame(rows).set_index("data").dropna()
    pg = df["crescita"].map(p_rising)
    pi = df["inflazione"].map(p_rising)
    for q, d in C.QUADRANTS.items():
        df[q] = (pg if d["growth"] else 1 - pg) * (pi if d["inflation"] else 1 - pi)
    df["dominante"] = df[list(C.QUADRANTS)].idxmax(axis=1)
    return df


def current(frames: dict[str, pd.DataFrame], as_of: pd.Timestamp) -> dict:
    g = composite_now(component_frames(frames, C.GROWTH), C.GROWTH, as_of)
    i = composite_now(component_frames(frames, C.INFLATION), C.INFLATION, as_of)
    if g["punteggio"] is None or i["punteggio"] is None:
        return {"disponibile": False, "crescita": g, "inflazione": i}
    pg, pi = p_rising(g["punteggio"]), p_rising(i["punteggio"])
    probs = quadrant_probs(pg, pi)
    dom = max(probs, key=probs.get)
    return {
        "disponibile": True,
        "crescita": g | {"p_su": round(pg, 3)},
        "inflazione": i | {"p_su": round(pi, 3)},
        "probabilita": {q: round(p, 3) for q, p in probs.items()},
        "dominante": dom,
        "nome": C.QUADRANTS[dom]["name"],
        "descrizione": C.QUADRANTS[dom]["desc"],
        "sicurezza": round(probs[dom], 3),
    }


def regime_changes(hist: pd.DataFrame, min_prob: float = C.ALERT_MIN_PROB) -> list[dict]:
    """Dates on which the most likely regime changed (with hysteresis)."""
    events, cur = [], None
    for d, r in hist.iterrows():
        dom = r["dominante"]
        if cur is None:
            cur = dom
            continue
        if dom != cur and r[dom] >= min_prob:
            events.append({"data": d.date().isoformat(), "da": cur, "a": dom,
                           "probabilita": round(float(r[dom]), 3)})
            cur = dom
    return events
