"""Macro regime (plan 4.2): liquidity axis × growth/inflation quadrant, and how assets
behaved historically in each regime."""

import numpy as np
import pandas as pd

from app.analysis import config as C
from app.analysis.indicators import on_dates
from app.analysis.scoring import clip, weighted_mean


def axis_score(signals: list[C.Signal], values: dict[tuple[str, str], float | None]):
    """Weighted mean of sign × scaled change. ``values`` maps (indicator, field) → number."""
    items = [(None if (v := values.get((s.indicator, s.field))) is None else s.sign * v, s.weight)
             for s in signals]
    return weighted_mean(items)


def classify(liquidity: float, growth: float, inflation: float) -> dict:
    qid, qname, qdesc = C.QUADRANTS[(growth > 0, inflation > 0)]
    liq_up = liquidity > 0
    return {
        "key": f"{'liq_up' if liq_up else 'liq_down'}_{qid}",
        "name": f"Liquidità in {'espansione' if liq_up else 'contrazione'} · {qname}",
        "liquidity": "espansione" if liq_up else "contrazione",
        "quadrant": qname,
        "description": f"Liquidità in {'espansione' if liq_up else 'contrazione'}; {qdesc}.",
    }


def history(ind_frames: dict[str, pd.DataFrame], dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Axis scores and regime on each date, using only data published by that date."""
    out = pd.DataFrame(index=dates)
    for axis, signals in C.REGIME_AXES.items():
        num = pd.Series(0.0, index=dates)
        den = pd.Series(0.0, index=dates)
        for s in signals:
            v = on_dates(ind_frames.get(s.indicator, pd.DataFrame()), s.field, dates)
            v = (s.sign * v).clip(-C.Z_CLIP, C.Z_CLIP)
            ok = v.notna()
            num[ok] += v[ok] * s.weight
            den[ok] += s.weight
        out[axis] = (num / den).where(den > 0)
    out = out.dropna()
    out["regime"] = [
        classify(r.liquidity, r.growth, r.inflation)["key"] for r in out.itertuples()
    ]
    return out


def month_ends(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq="ME")


def forward_returns(price: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.Series:
    """% return from each date to the next date in ``dates`` (last price on or before)."""
    if price.empty:
        return pd.Series(np.nan, index=dates)
    p = price["value"].reindex(price.index.union(dates)).ffill().reindex(dates)
    # Only use prices that existed: a date before the first price stays NaN
    p[dates < price.index[0]] = np.nan
    return (p.shift(-1) / p - 1) * 100


def performance(
    hist: pd.DataFrame,
    asset_frames: dict[str, pd.DataFrame],
    as_of: pd.Timestamp,
) -> dict:
    """Average next-month return of each asset in each regime, versus all months."""
    if hist.empty:
        return {"months": 0, "regimes": {}}
    dates = hist.index
    rets = pd.DataFrame({sid: forward_returns(asset_frames.get(sid, pd.DataFrame()), dates)
                         for sid, _ in C.REGIME_ASSETS})
    # The last month's forward return is not known yet on as_of
    rets = rets[rets.index + pd.offsets.MonthEnd(1) <= as_of]
    labels = dict(C.REGIME_ASSETS)
    overall = rets.mean()
    regimes = {}
    for key, idx in hist.loc[rets.index].groupby("regime").groups.items():
        r = rets.loc[idx]
        assets = []
        for sid in rets.columns:
            col = r[sid].dropna()
            if len(col) < 3:
                continue
            assets.append({
                "id": sid,
                "name": labels[sid],
                "months": int(len(col)),
                "avg_month_pct": round(float(col.mean()), 2),
                "vs_all_months_pct": round(float(col.mean() - overall[sid]), 2),
                "hit_rate": round(float((col > 0).mean()), 2),
            })
        assets.sort(key=lambda a: a["vs_all_months_pct"], reverse=True)
        regimes[key] = {"months": int(len(idx)), "assets": assets}
    return {
        "from": rets.index[0].date().isoformat() if len(rets) else None,
        "to": rets.index[-1].date().isoformat() if len(rets) else None,
        "months": int(len(rets)),
        "regimes": regimes,
    }


def current(ind_rows: dict[str, pd.Series | None]) -> dict:
    """Regime today, with each axis's components explained."""
    axes = {}
    for axis, signals in C.REGIME_AXES.items():
        values = {}
        comps = []
        for s in signals:
            row = ind_rows.get(s.indicator)
            v = None if row is None or pd.isna(row.get(s.field)) else float(row[s.field])
            raw = None if row is None or pd.isna(row.get(C.FIELD_RAW[s.field])) \
                else float(row[C.FIELD_RAW[s.field]])
            values[(s.indicator, s.field)] = v
            ind = C.INDICATOR_BY_ID[s.indicator]
            comps.append({
                "indicator": s.indicator,
                "label": ind.label,
                "measure": C.FIELD_LABELS[s.field],
                "change": None if raw is None else round(raw, 3),
                "change_unit": C.change_unit(ind),
                "scaled": None if v is None else round(v, 2),
                "weight": s.weight,
                "contribution": None if v is None else round(s.sign * clip(v) * s.weight, 3),
            })
        score, coverage = axis_score(signals, values)
        axes[axis] = {
            "label": C.AXIS_LABELS[axis],
            "score": None if score is None else round(score, 2),
            "direction": None if score is None else ("su" if score > 0 else "giù"),
            "borderline": score is not None and abs(score) < C.BORDERLINE,
            "coverage": round(coverage, 2),
            "components": comps,
        }
    scores = [axes[a]["score"] for a in ("liquidity", "growth", "inflation")]
    if any(s is None for s in scores):
        return {"available": False, "axes": axes}
    out = classify(*scores) | {"available": True, "axes": axes}
    out["borderline_axes"] = [axes[a]["label"] for a in axes if axes[a]["borderline"]]
    return out
