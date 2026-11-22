"""Monthly backtest from 2000: risk parity, risk parity + regime tilt, and a 60/40.

At each month-end t the weights use only returns up to t and the regime probabilities
known at t (point in time); they earn the returns of month t+1. Rebalancing every month
costs COST_BPS per unit of turnover.
"""

import math

import numpy as np
import pandas as pd

from app.rqe import allocation
from app.rqe import config as C

STRATEGIES = {"rp": "Risk parity (All Weather)", "rp_tilt": "Risk parity + regime",
              "bench": "60/40 (azioni/Treasury intermedi)"}


def run(returns: pd.DataFrame, probs: pd.DataFrame, cost_bps: float = C.COST_BPS,
        tilt_fn=None) -> dict:
    """``returns``: monthly returns per asset; ``probs``: columns A-D (+ dominante).

    ``tilt_fn(base, probs_at_t, t, returns_up_to_t) -> weights`` replaces the default tilt
    (used by the calibration to try variants); it must only use information up to t.
    """
    tilt_fn = tilt_fn or (lambda base, p, t, hist: allocation.tilt(base, p))
    dates = returns.index
    weights: dict[str, dict] = {k: {} for k in STRATEGIES}
    rets: dict[str, list] = {k: [] for k in STRATEGIES}
    regime_at: list = []
    out_dates = []
    prev: dict[str, dict[str, float]] = {k: {} for k in STRATEGIES}
    for i in range(len(dates) - 1):
        t, nxt = dates[i], dates[i + 1]
        hist = returns.loc[:t]
        base = allocation.risk_parity(hist)
        if len(base) < 3 or t not in probs.index:
            continue
        p = {q: float(probs.loc[t, q]) for q in C.QUADRANTS}
        ws = {"rp": base, "rp_tilt": tilt_fn(base, p, t, hist),
              "bench": {"equity": 0.6, "int_tsy": 0.4}}
        r_next = returns.loc[nxt]
        for k, w in ws.items():
            gross = sum(w[a] * (0.0 if pd.isna(r_next.get(a)) else r_next[a]) for a in w)
            turnover = sum(abs(w.get(a, 0) - prev[k].get(a, 0)) for a in set(w) | set(prev[k]))
            rets[k].append(gross - turnover * cost_bps / 10_000)
            prev[k] = w
            weights[k][nxt] = w
        regime_at.append(probs.loc[t, "dominante"])
        out_dates.append(nxt)
    idx = pd.DatetimeIndex(out_dates)
    r = pd.DataFrame(rets, index=idx)
    cash = returns["cash"].reindex(idx).fillna(0)
    return {
        "returns": r,
        "regime": pd.Series(regime_at, index=idx),
        "stats": {k: stats(r[k], cash) for k in STRATEGIES},
        "by_regime": by_regime(r, pd.Series(regime_at, index=idx), returns),
        "last_weights": {k: (weights[k][idx[-1]] if len(idx) else {}) for k in STRATEGIES},
    }


def max_drawdown(r: pd.Series) -> float:
    curve = (1 + r).cumprod()
    return float((curve / curve.cummax() - 1).min())


def stats(r: pd.Series, cash: pd.Series) -> dict:
    r = r.dropna()
    if r.empty:
        return {}
    years = len(r) / 12
    cagr = float((1 + r).prod() ** (1 / years) - 1)
    vol = float(r.std() * math.sqrt(12))
    excess = r - cash.reindex(r.index).fillna(0)
    sharpe = float(excess.mean() / excess.std() * math.sqrt(12)) if excess.std() > 0 else None
    return {"cagr": round(cagr, 4), "volatilita": round(vol, 4),
            "sharpe": None if sharpe is None else round(sharpe, 2),
            "max_drawdown": round(max_drawdown(r), 4),
            "mesi": int(len(r)), "dal": r.index[0].date().isoformat(),
            "al": r.index[-1].date().isoformat()}


def by_regime(strat: pd.DataFrame, regime: pd.Series, assets: pd.DataFrame) -> dict:
    """Average monthly return of each strategy and asset by the regime expected at t."""
    out = {}
    a = assets.reindex(strat.index)
    for q in C.QUADRANTS:
        mask = regime == q
        if not mask.any():
            continue
        out[q] = {
            "mesi": int(mask.sum()),
            "strategie": {k: round(float(strat.loc[mask, k].mean()), 4) for k in strat},
            "asset": {k: (None if np.isnan(v := float(a.loc[mask, k].mean())) else round(v, 4))
                      for k in C.ASSETS},
        }
    return out


def curves(r: pd.DataFrame) -> list[dict]:
    """Growth of 100 for each strategy, one point per month."""
    c = (1 + r).cumprod() * 100
    return [{"data": d.date().isoformat(), **{k: round(float(v), 2) for k, v in row.items()}}
            for d, row in c.iterrows()]
