"""Calibration of the regime tilt, with protection against fitting the past.

Parameters are *chosen* on the train period only (2000-2012) and *judged* on the test period
(2013 onwards), which the choice never sees. Candidates are few and meaningful:
- theoretical preferences with different strengths (0 = pure risk parity);
- regime probabilities smoothed over 3 or 6 months (fewer flip-flops);
- a different σ (how quickly a reading becomes "sure");
- preferences *learned* walk-forward: each month they are estimated only from earlier
  months (expanding window, shrunk toward zero), so even the learning never sees the future;
- longer horizons (3, 6, 12 months): the decision is held h months (overlapping portfolios)
  and learning uses h-month returns from windows already completed; optionally only the
  part of the preference that changes with the regime ("solo_regime").
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
HORIZONS = (1, 3, 6, 12)  # months a regime decision is held (and learned over)


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


def _month_cache(returns: pd.DataFrame, s, nxt, cache: dict):
    """Month ``nxt``'s asset returns and the risk-parity return (weights decided at ``s``).
    They never change, so they are computed once per month and shared by all candidates."""
    if s not in cache:
        w = allocation.risk_parity(returns.loc[:s])
        if len(w) < 3:
            cache[s] = None
        else:
            r = returns.loc[nxt]
            cache[s] = {"r": {a: r[a] for a in C.ASSETS},
                        "rp": sum(w[a] * r[a] for a in w if pd.notna(r[a]))}
    return cache[s]


def learned_preferences(returns: pd.DataFrame, probs: pd.DataFrame, t,
                        cache: dict | None = None, horizon: int = 1,
                        demean: bool = False) -> dict[str, dict[str, float]] | None:
    """Preferences estimated from windows that ended strictly before ``t``.

    For each quadrant q and asset a: probability-weighted mean, over decision months s, of
    the asset's return over the ``horizon`` months after s minus the risk-parity return over
    the same months; scaled to [-1, 1] by its cross-asset spread and shrunk by
    n/(n + LEARN_SHRINK). Only windows completed before t are used (s + horizon < t).
    ``demean``: remove each asset's average across quadrants, keeping only what *changes*
    with the regime (no static over/underweight).
    """
    cache = {} if cache is None else cache
    past = returns.index[returns.index < t]
    if len(past) < LEARN_MIN_MONTHS + horizon:
        return None
    rows, ws = [], []
    for i in range(len(past) - horizon):
        s = past[i]
        if s not in probs.index:
            continue
        months = [_month_cache(returns, past[i + k], past[i + k + 1], cache)
                  for k in range(horizon)]
        if any(m is None for m in months):
            continue
        rp = float(np.prod([1 + m["rp"] for m in months]) - 1)
        ex = {}
        for a in C.ASSETS:
            ra = [m["r"][a] for m in months]
            ex[a] = float(np.prod([1 + x for x in ra]) - 1 - rp) if all(pd.notna(ra)) \
                else np.nan
        rows.append(ex)
        ws.append({q: probs.loc[s, q] for q in C.QUADRANTS})
    if not rows:
        return None
    ex, wq = pd.DataFrame(rows), pd.DataFrame(ws)
    means = {q: {a: np.nansum(wq[q] * ex[a]) / max(wq[q][ex[a].notna()].sum(), 1e-9)
                 for a in C.ASSETS} for q in C.QUADRANTS}
    if demean:
        common = {a: float(np.mean([means[q][a] for q in C.QUADRANTS])) for a in C.ASSETS}
        means = {q: {a: means[q][a] - common[a] for a in C.ASSETS} for q in C.QUADRANTS}
    prefs = {}
    for q in C.QUADRANTS:
        m = means[q]
        spread = np.nanstd(list(m.values())) or 1.0
        n = float(wq[q].sum())
        prefs[q] = {a: float(np.clip(m[a] / spread, -1, 1) * n / (n + LEARN_SHRINK))
                    for a in C.ASSETS}
    return prefs


def learned(probs: pd.DataFrame, strength: float = C.TILT_STRENGTH,
            max_dev: float = C.MAX_DEVIATION, horizon: int = 1, demean: bool = False,
            cache: dict | None = None):
    """Walk-forward tilt: at each t, preferences learned from windows completed before t."""
    cache = {} if cache is None else cache

    def fn(base, p, t, hist):
        prefs = learned_preferences(hist, probs, t, cache, horizon, demean)
        if prefs is None:
            return dict(base) | {"cash": 0.0}
        return allocation.tilt(base, p, strength=strength, max_dev=max_dev, tilts=prefs)
    return fn


def hold(fn, horizon: int):
    """A decision made at t is kept for ``horizon`` months: the weights are today's risk
    parity plus the average of the last ``horizon`` tilt deviations (overlapping
    portfolios). Each deviation sums to zero and stays within ±max_dev, so their average
    does too. Stateful: use a fresh one for every backtest run."""
    if horizon <= 1:
        return fn
    devs: list[dict[str, float]] = []

    def held(base, p, t, hist):
        w = fn(base, p, t, hist)
        devs.append({a: w.get(a, 0.0) - base.get(a, 0.0) for a in set(w) | set(base)})
        del devs[:-horizon]
        keys = set(base) | {"cash"} | {a for d in devs for a in d}
        out = {a: max(0.0, base.get(a, 0.0) + sum(d.get(a, 0.0) for d in devs) / len(devs))
               for a in keys}
        tot = sum(out.values())
        return {a: v / tot for a, v in out.items()} if tot > 0 else dict(base)
    return held


def _period_stats(r: pd.Series, cash: pd.Series, start=None, end=None) -> dict:
    return backtest.stats(r.loc[start:end], cash)


def candidate_fn(c: dict, probs: pd.DataFrame, cache: dict | None = None):
    """The tilt function of a candidate (fresh state every call)."""
    h = c.get("orizzonte", 1)
    if c["tipo"] == "teorico":
        fn = theoretical(c["forza"])
    else:
        fn = learned(probs, c["forza"], horizon=h, demean=c.get("solo_regime", False),
                     cache=cache)
    return hold(fn, h)


def evaluate(returns: pd.DataFrame, hist: pd.DataFrame, cost_bps: float = C.COST_BPS) -> list:
    """Run every candidate; return their train and test statistics."""
    cash = returns["cash"]
    candidates = []
    for sigma, smooth, strength in itertools.product((0.4, 0.6, 1.0), (1, 3, 6),
                                                     (0.0, 0.25, 0.5, 1.0)):
        if strength == 0 and (sigma, smooth) != (0.6, 1):
            continue  # pure risk parity does not depend on σ or smoothing
        candidates.append({"tipo": "teorico", "sigma": sigma, "media_mesi": smooth,
                           "forza": strength, "orizzonte": 1})
    for smooth in (1, 3, 6):
        candidates.append({"tipo": "imparato", "sigma": 0.6, "media_mesi": smooth,
                           "forza": 0.5, "orizzonte": 1})
    # Longer horizons: the decision is held h months, learning uses h-month returns
    for h, strength in itertools.product(HORIZONS[1:], (0.5, 1.0)):
        candidates.append({"tipo": "teorico", "sigma": 0.6, "media_mesi": 3,
                           "forza": strength, "orizzonte": h})
        for demean in (False, True):
            candidates.append({"tipo": "imparato", "sigma": 0.6, "media_mesi": 3,
                               "forza": strength, "orizzonte": h, "solo_regime": demean})
    cache: dict = {}
    out = []
    for c in candidates:
        c.setdefault("solo_regime", False)
        probs = probs_from_scores(hist, c["sigma"], c["media_mesi"])
        bt = backtest.run(returns, probs, cost_bps, tilt_fn=candidate_fn(c, probs, cache))
        r = bt["returns"]["rp_tilt"]
        out.append(c | {
            "train": _period_stats(r, cash, end=TRAIN_END),
            "test": _period_stats(r, cash, start=TEST_START),
            "rp_train": _period_stats(bt["returns"]["rp"], cash, end=TRAIN_END),
            "rp_test": _period_stats(bt["returns"]["rp"], cash, start=TEST_START),
            "t_test": significance(r, bt["returns"]["rp"], start=TEST_START)["t"],
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
