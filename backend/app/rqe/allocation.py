"""All Weather-style allocation: risk parity base, then a tactical tilt by regime.

Base: weights inversely proportional to each asset's volatility (last 12 monthly returns),
so each asset class contributes similar risk. Cash is not part of the base.
Tilt: weight × (1 + strength × Σ_q P(q) × preference[q][asset]), renormalised, every
weight kept within ±MAX_DEVIATION of its base; cash can rise up to MAX_DEVIATION when the
regimes that like it (stagflation, recession) are likely.
"""

import numpy as np
import pandas as pd

from app.rqe import config as C


def risk_parity(returns: pd.DataFrame, months: int = C.VOL_MONTHS,
                min_months: int = C.VOL_MIN_MONTHS) -> dict[str, float]:
    """Inverse-volatility weights of the risky assets with enough history."""
    window = returns[[a for a in C.RISKY if a in returns]].tail(months)
    vols = {}
    for a in window.columns:
        r = window[a].dropna()
        if len(r) >= min_months and r.std() > 0:
            vols[a] = float(r.std())
    if not vols:
        return {}
    inv = {a: 1 / v for a, v in vols.items()}
    tot = sum(inv.values())
    return {a: inv[a] / tot for a in inv}


def expected_preference(probs: dict[str, float], asset: str,
                        tilts: dict[str, dict[str, float]] | None = None) -> float:
    tilts = tilts or C.TILTS
    return sum(p * tilts[q].get(asset, 0.0) for q, p in probs.items())


def tilt(base: dict[str, float], probs: dict[str, float],
         strength: float = C.TILT_STRENGTH, max_dev: float = C.MAX_DEVIATION,
         tilts: dict[str, dict[str, float]] | None = None) -> dict[str, float]:
    """Tilted weights (sum 1, each within ±max_dev of base; cash base is 0).

    ``tilts``: preferences per quadrant and asset (default: the theoretical ones).
    """
    if not base:
        return {}
    cash = max(0.0, min(max_dev, max_dev * expected_preference(probs, "cash", tilts)))
    raw = {a: w * max(0.0, 1 + strength * expected_preference(probs, a, tilts))
           for a, w in base.items()}
    lo = {a: max(0.0, base[a] - max_dev) for a in base}
    hi = {a: base[a] + max_dev for a in base}
    # Scale to (1 − cash), clip to the bands, repeat until stable
    w = dict(raw)
    for _ in range(50):
        tot = sum(w.values())
        w = {a: v * (1 - cash) / tot for a, v in w.items()} if tot > 0 else dict(base)
        clipped = {a: min(hi[a], max(lo[a], v)) for a, v in w.items()}
        if all(abs(clipped[a] - w[a]) < 1e-12 for a in w):
            break
        # Spread what clipping added/removed over the assets that are not at a bound
        excess = sum(w.values()) - sum(clipped.values())
        free = [a for a in w if lo[a] < clipped[a] < hi[a]]
        w = clipped
        if free and abs(excess) > 1e-12:
            share = sum(w[a] for a in free)
            for a in free:
                w[a] += excess * (w[a] / share if share else 1 / len(free))
    out = {a: float(np.clip(v, lo[a], hi[a])) for a, v in w.items()}
    out["cash"] = cash
    tot = sum(out.values())
    return {a: v / tot for a, v in out.items()}


def explain(base: dict[str, float], tilted: dict[str, float], probs: dict[str, float],
            tilts: dict[str, dict[str, float]] | None = None) -> list:
    """One line per asset: base, tilted, change and why."""
    rows = []
    for a in C.ASSETS:
        b, t = base.get(a, 0.0), tilted.get(a, 0.0)
        pref = expected_preference(probs, a, tilts)
        if abs(t - b) < 0.005:
            why = "Peso di base: il regime atteso non lo favorisce né lo penalizza."
        elif t > b:
            why = "Sovrappeso: lo favoriscono i regimi più probabili."
        else:
            why = "Sottopeso: i regimi più probabili lo penalizzano."
        rows.append({"asset": a, "nome": C.ASSETS[a], "base": round(b, 4),
                     "consigliato": round(t, 4), "scostamento": round(t - b, 4),
                     "preferenza": round(pref, 3), "motivo": why})
    return rows
