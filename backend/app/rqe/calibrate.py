"""Calibration of the regime tilt, with protection against fitting the past.

Parameters are *chosen* on the train period only (2000-2012) and *judged* on the test period
(2013 onwards), which the choice never sees. Candidates are few and meaningful:
- theoretical preferences with different strengths (0 = pure risk parity);
- regime probabilities smoothed over 3 or 6 months (fewer flip-flops);
- a different σ (how quickly a reading becomes "sure");
- preferences *learned* walk-forward: each month they are estimated only from earlier
  months (expanding window, shrunk toward zero), so even the learning never sees the future.
"""

import itertools
import math

import numpy as np
import pandas as pd

from app.rqe import allocation, backtest
from app.rqe import config as C

TRAIN_END = "2012-12-31"
TEST_START = "2013-01-01"
LEARN_MIN_MONTHS = 60  # learned tilts start after 5 years of history
LEARN_SHRINK = 36  # pref × n / (n + 36): little data → small tilt


def probs_from_scores(hist: pd.DataFrame, sigma: float, smooth: int) -> pd.DataFrame:
    """Quadrant probabilities from the growth/inflation scores with another σ and an
    optional moving average of the scores (``smooth`` months, trailing: no look-ahead)."""
    g = hist["crescita"].rolling(smooth, min_periods=1).mean()
    i = hist["inflazione"].rolling(smooth, min_periods=1).mean()
    phi = lambda x: 0.5 * (1 + math.erf(x / sigma / math.sqrt(2)))  # noqa: E731
    pg, pi = g.map(phi), i.map(phi)
    out = pd.DataFrame(index=hist.index)
    for q, d in C.QUADRANTS.items():
        out[q] = (pg if d["growth"] else 1 - pg) * (pi if d["inflation"] else 1 - pi)
    out["dominante"] = out[list(C.QUADRANTS)].idxmax(axis=1)
    return out


def theoretical(strength: float, max_dev: float = C.MAX_DEVIATION):
    def fn(base, p, t, hist):
        return allocation.tilt(base, p, strength=strength, max_dev=max_dev) if strength else \
            dict(base) | {"cash": 0.0}
    return fn


def learned_preferences(returns: pd.DataFrame, probs: pd.DataFrame, t,
                         cache: dict | None = None) -> dict[str, dict[str, float]] | None:
    """Preferences estimated from the months strictly before ``t``.

    For each quadrant q and asset a: probability-weighted mean of the asset's next-month
    return minus the risk-parity return, scaled to [-1, 1] by its cross-asset spread and
    shrunk by n/(n + LEARN_SHRINK). ``cache`` keeps each month's excess returns (they never
    change), so a walk-forward run costs one risk-parity computation per month.
    """
    cache = {} if cache is None else cache
    past = returns.index[returns.index < t]
    if len(past) < LEARN_MIN_MONTHS + 1:
        return None
    rows, ws = [], []
    for s, nxt in zip(past[:-1], past[1:], strict=False):
        if s not in probs.index:
            continue
        if s not in cache:
            w = allocation.risk_parity(returns.loc[:s])
            if len(w) < 3:
                cache[s] = None
            else:
                r = returns.loc[nxt]
                rp = sum(w[a] * r[a] for a in w if pd.notna(r[a]))
                cache[s] = {a: (r[a] - rp) if pd.notna(r[a]) else np.nan for a in C.ASSETS}
        if cache[s] is None:
            continue
        rows.append(cache[s])
        ws.append({q: probs.loc[s, q] for q in C.QUADRANTS})
    if not rows:
        return None
    ex, wq = pd.DataFrame(rows), pd.DataFrame(ws)
    prefs = {}
    for q in C.QUADRANTS:
        m = {a: np.nansum(wq[q] * ex[a]) / max(wq[q][ex[a].notna()].sum(), 1e-9)
             for a in C.ASSETS}
        spread = np.nanstd(list(m.values())) or 1.0
        n = float(wq[q].sum())
        prefs[q] = {a: float(np.clip(m[a] / spread, -1, 1) * n / (n + LEARN_SHRINK))
                    for a in C.ASSETS}
    return prefs


def learned(probs: pd.DataFrame, strength: float = C.TILT_STRENGTH,
            max_dev: float = C.MAX_DEVIATION):
    """Walk-forward tilt: at each t, preferences learned from months before t only."""
    cache: dict = {}

    def fn(base, p, t, hist):
        prefs = learned_preferences(hist, probs, t, cache)
        if prefs is None:
            return dict(base) | {"cash": 0.0}
        return allocation.tilt(base, p, strength=strength, max_dev=max_dev, tilts=prefs)
    return fn


def _period_stats(r: pd.Series, cash: pd.Series, start=None, end=None) -> dict:
    return backtest.stats(r.loc[start:end], cash)


def evaluate(returns: pd.DataFrame, hist: pd.DataFrame, cost_bps: float = C.COST_BPS) -> list:
    """Run every candidate; return their train and test statistics."""
    cash = returns["cash"]
    candidates = []
    for sigma, smooth, strength in itertools.product((0.4, 0.6, 1.0), (1, 3, 6),
                                                     (0.0, 0.25, 0.5, 1.0)):
        if strength == 0 and (sigma, smooth) != (0.6, 1):
            continue  # pure risk parity does not depend on σ or smoothing
        candidates.append({"tipo": "teorico", "sigma": sigma, "media_mesi": smooth,
                           "forza": strength})
    for smooth in (1, 3, 6):
        candidates.append({"tipo": "imparato", "sigma": 0.6, "media_mesi": smooth,
                           "forza": 0.5})
    out = []
    for c in candidates:
        probs = probs_from_scores(hist, c["sigma"], c["media_mesi"])
        fn = theoretical(c["forza"]) if c["tipo"] == "teorico" else learned(probs, c["forza"])
        bt = backtest.run(returns, probs, cost_bps, tilt_fn=fn)
        r = bt["returns"]["rp_tilt"]
        out.append(c | {
            "train": _period_stats(r, cash, end=TRAIN_END),
            "test": _period_stats(r, cash, start=TEST_START),
            "rp_train": _period_stats(bt["returns"]["rp"], cash, end=TRAIN_END),
            "rp_test": _period_stats(bt["returns"]["rp"], cash, start=TEST_START),
        })
    return out


def significance(tilt: pd.Series, base: pd.Series, start=None, end=None) -> dict:
    """Is the tilt's extra return distinguishable from noise? Mean monthly difference,
    its t-statistic (|t| > 2 ≈ significant) and the Sharpe standard error over the period."""
    d = (tilt - base).loc[start:end].dropna()
    t = float(d.mean() / (d.std() / math.sqrt(len(d)))) if d.std() > 0 else 0.0
    years = len(d) / 12
    return {"differenza_mensile": round(float(d.mean()), 5), "t": round(t, 2),
            "errore_sharpe": round(1 / math.sqrt(years), 2) if years else None,
            "mesi": int(len(d))}


def choose(results: list) -> dict:
    """Best candidate by train Sharpe only (ties: smaller tilt)."""
    return max(results, key=lambda x: (x["train"]["sharpe"], -x["forza"]))
