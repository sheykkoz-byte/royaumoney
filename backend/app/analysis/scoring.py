"""Pure scoring maths for the convergence engine (plan 4.3). No pandas, easy to test."""

import math

from app.analysis import config as C


def clip(x: float, limit: float = C.Z_CLIP) -> float:
    return max(-limit, min(limit, x))


def weighted_mean(items: list[tuple[float | None, float]]) -> tuple[float | None, float]:
    """Weighted mean of (value, weight), skipping missing values.

    Returns (mean or None, coverage) where coverage = weight available / weight total.
    """
    total = sum(w for _, w in items)
    avail = [(clip(v), w) for v, w in items if v is not None and not math.isnan(v)]
    w_avail = sum(w for _, w in avail)
    if not avail or w_avail == 0:
        return None, 0.0
    return sum(v * w for v, w in avail) / w_avail, (w_avail / total if total else 0.0)


def convergence(macro: float | None, market: float | None) -> int | None:
    """How much the two voices agree, from −100 (opposite) to +100 (identical).

    100 · m·k / max(m², k²): equals +100 when the voices say the same thing with the same
    strength, −100 when they say opposite things with the same strength, and tends to 0 when
    one voice is silent. If both are weaker than the dead zone there is nothing to compare.
    """
    if macro is None or market is None:
        return None
    big = max(abs(macro), abs(market))
    if big < C.CONVERGENCE_DEADZONE:
        return 0
    return round(100 * macro * market / big**2)


def scenario_score(macro: float | None, market: float | None) -> int | None:
    """Overall support for a scenario, −100..+100: mean of the two voices, 2σ = 100."""
    voices = [v for v in (macro, market) if v is not None]
    if not voices:
        return None
    mean = sum(voices) / len(voices)
    return round(100 * max(-1.0, min(1.0, mean / C.SCORE_FULL_SCALE)))


def divergence_threshold(past_gaps: list[float]) -> tuple[float, str]:
    """Alarm threshold from the history of |market − macro| gaps (see config)."""
    gaps = sorted(abs(g) for g in past_gaps if g is not None and not math.isnan(g))
    if len(gaps) < C.DIVERGENCE_MIN_MONTHS:
        return C.DIVERGENCE_FALLBACK, "fissa"
    # Nearest-rank percentile
    k = max(0, math.ceil(C.DIVERGENCE_PERCENTILE * len(gaps)) - 1)
    return gaps[k], "storica"


def gap_percentile(gap: float, past_gaps: list[float]) -> float | None:
    """Share of past months with a smaller gap than ``gap`` (0–1)."""
    gaps = [abs(g) for g in past_gaps if g is not None and not math.isnan(g)]
    if not gaps:
        return None
    return sum(1 for g in gaps if g < abs(gap)) / len(gaps)


def divergence(macro: float | None, market: float | None, threshold: float) -> dict | None:
    """Divergence alarm: the voices are further apart than ``threshold`` (σ)."""
    if macro is None or market is None:
        return None
    gap = market - macro
    if abs(gap) < threshold:
        return None
    return {"gap": round(gap, 2), "leader": "mercato" if gap > 0 else "macro"}


def stance(aligned: float | None) -> str:
    if aligned is None or math.isnan(aligned):
        return "mancante"
    if aligned >= C.SUPPORT_THRESHOLD:
        return "sostiene"
    if aligned <= -C.SUPPORT_THRESHOLD:
        return "contraddice"
    return "neutro"
