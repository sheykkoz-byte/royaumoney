"""Normalised indicators (plan, section 4.1).

An indicator is built from one or two stored series with a transform (e.g. CPI → year-on-year
inflation). For every date it gets:

- ``value``: the transformed value;
- ``chg1``, ``chg3``, ``chg6``: change over 1, 3 and 6 months (percent or difference);
- ``z``, ``z_chg1``, ``z_chg3``, ``z_chg6``: z-score of each over a trailing window (5 years
  by default), so different indicators become comparable;
- ``s_chg3``, ``s_chg6``: the change divided by its typical size (root mean square over the
  window). Unlike a z-score it is not demeaned, so its sign is the sign of the change:
  used where the question is "is it rising or falling?" rather than "is it unusual?";
- ``available``: first date on which the row could have been known (publication date).
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

Transform = Literal["level", "yoy", "avg4", "mavg3_diff", "spread"]
ChangeKind = Literal["pct", "diff"]
Voice = Literal["macro", "market"]

CHANGE_MONTHS = (1, 3, 6)
FIELDS = ("value", "chg1", "chg3", "chg6")


@dataclass(frozen=True)
class Indicator:
    id: str
    label: str  # Italian, shown in the UI and spoken by Jarvis
    voice: Voice
    series: tuple[str, ...]
    transform: Transform
    change: ChangeKind
    unit: str
    z_years: int = 5
    z_min_years: int = 3
    note: str = ""


# ---- building blocks ---------------------------------------------------------------------
def value_months_ago(s: pd.Series, months: int, tolerance_days: int = 45) -> pd.Series:
    """For each date t, the last value on or before t − ``months`` (NaN if none close enough)."""
    s = s.dropna()
    idx = _ns(s.index)
    target = pd.DataFrame({"t": idx, "lookup": idx - pd.DateOffset(months=months)})
    hist = pd.DataFrame({"lookup": idx, "prior": s.to_numpy()})
    m = pd.merge_asof(target.sort_values("lookup"), hist, on="lookup", direction="backward",
                      tolerance=pd.Timedelta(days=tolerance_days))
    out = m.set_index("t")["prior"].reindex(idx)
    out.index = s.index
    return out


def change_over(s: pd.Series, months: int, kind: ChangeKind) -> pd.Series:
    prior = value_months_ago(s, months)
    if kind == "pct":
        return (s / prior - 1) * 100
    return s - prior


# Robust statistics: median and MAD instead of mean and standard deviation, so a single
# extreme episode (the 2020 Covid crash) does not flatten every normal move for the next
# five years. 1.4826 × MAD equals the standard deviation for normally distributed data.
ROBUST = True
MAD_TO_STD = 1.4826
# Floor for the robust scale, from the 10th-90th percentile range (also robust to a few
# extremes): a series that barely moved for years (unemployment in 2003-2005, MAD ≈ 0)
# would otherwise turn a normal move into ±7σ. 2.563 = width of that range in σ units.
Q_RANGE_TO_STD = 2.563


def _window_days(years: float) -> str:
    return f"{int(years * 365.25)}D"


def _stats_sample(s: pd.Series) -> pd.Series:
    """Daily series: one value per week (last), to keep rolling medians fast."""
    if len(s) > 3 and (s.index[1:] - s.index[:-1]).median() < pd.Timedelta(days=6):
        return s.resample("W-FRI").last().dropna()
    return s


def _on_index(stat: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Map window statistics back to every date (last value on or before it)."""
    return _asof(stat.dropna(), index)


def _robust_center_scale(s: pd.Series, years: float, demean: bool):
    sample = _stats_sample(s)
    win = sample.rolling(_window_days(years), min_periods=5)
    if demean:
        center = win.median()
        mad = win.apply(lambda w: np.median(np.abs(w - np.median(w))), raw=True)
        fallback = win.std()
        floor = (win.quantile(0.9) - win.quantile(0.1)) / Q_RANGE_TO_STD
    else:
        center = pd.Series(0.0, index=sample.index)
        mad = win.apply(lambda w: np.median(np.abs(w)), raw=True)
        fallback = np.sqrt((sample**2).rolling(_window_days(years), min_periods=5).mean())
        floor = sample.abs().rolling(_window_days(years), min_periods=5).quantile(0.8) / 1.2816
    scale = (MAD_TO_STD * mad).where(mad > 0, fallback)
    scale = np.maximum(scale, floor.fillna(0))
    if sample is s:
        return center, scale
    return _on_index(center, s.index), _on_index(scale, s.index)


def _mask_short_history(out: pd.Series, s: pd.Series, min_years: float) -> pd.Series:
    out[s.index < s.index[0] + pd.Timedelta(days=int(min_years * 365.25))] = np.nan
    return out


def rolling_z(s: pd.Series, years: int, min_years: int) -> pd.Series:
    """z-score of each point against the trailing ``years`` window.

    Robust version (default): (x − median) / (1.4826 · MAD). NaN until the series has
    ``min_years`` of history, or where the window has no spread.
    """
    s = s.dropna()
    if s.empty:
        return s
    if ROBUST:
        center, scale = _robust_center_scale(s, years, demean=True)
    else:
        win = s.rolling(_window_days(years), min_periods=5)
        center, scale = win.mean(), win.std()
    z = (s - center) / scale.where(scale > 0)
    return _mask_short_history(z, s, min_years)


def rolling_scaled(s: pd.Series, years: int, min_years: int) -> pd.Series:
    """Value divided by its typical size over the trailing window (sign preserved).

    Typical size = 1.4826 · median(|x|) (robust) or root mean square.
    """
    s = s.dropna()
    if s.empty:
        return s
    if ROBUST:
        _, scale = _robust_center_scale(s, years, demean=False)
    else:
        scale = np.sqrt((s**2).rolling(_window_days(years), min_periods=5).mean())
    out = s / scale.where(scale > 0)
    return _mask_short_history(out, s, min_years)


def _ns(x) -> pd.DatetimeIndex:
    """Same datetime resolution on both sides of a merge_asof."""
    return pd.DatetimeIndex(x).as_unit("ns")


def _asof(s: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    left = pd.DataFrame({"ref_date": _ns(index)})
    right = pd.DataFrame({"ref_date": _ns(s.index), "v": s.to_numpy()})
    out = pd.merge_asof(left, right, on="ref_date", direction="backward").set_index(
        "ref_date")["v"]
    out.index = index
    return out


def transform(ind: Indicator, frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Apply the indicator's transform. Returns columns value, available."""
    first = frames[ind.series[0]]
    if first.empty:
        return pd.DataFrame(columns=["value", "available"], dtype=float)
    v = first["value"]
    pub = first["published_at"]
    if ind.transform == "level":
        out = v
    elif ind.transform == "yoy":
        out = change_over(v, 12, "pct")
    elif ind.transform == "avg4":
        out = v.rolling(4, min_periods=4).mean()
    elif ind.transform == "mavg3_diff":
        out = v.diff().rolling(3, min_periods=3).mean()
    elif ind.transform == "spread":
        other = frames[ind.series[1]]
        if other.empty:
            return pd.DataFrame(columns=["value", "available"], dtype=float)
        out = v - _asof(other["value"], v.index)
        pub = pd.concat([pub, _asof(other["published_at"], v.index)], axis=1).max(axis=1)
    else:  # pragma: no cover
        raise ValueError(ind.transform)
    # A transformed value uses earlier rows too: it is known once all of them are published.
    available = pub.cummax()
    return pd.DataFrame({"value": out, "available": available}).dropna(subset=["value"])


def build(ind: Indicator, frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base = transform(ind, frames)
    if base.empty:
        return base
    df = base.copy()
    for m in CHANGE_MONTHS:
        df[f"chg{m}"] = change_over(df["value"], m, ind.change)
    for f in FIELDS:
        df[f"z_{f}" if f != "value" else "z"] = rolling_z(df[f], ind.z_years, ind.z_min_years)
    for m in (3, 6):
        df[f"s_chg{m}"] = rolling_scaled(df[f"chg{m}"], ind.z_years, ind.z_min_years)
    return df


def latest(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series | None:
    """The most recent row that was already published on ``as_of``."""
    if df.empty:
        return None
    known = df[df["available"] <= as_of]
    return None if known.empty else known.iloc[-1]


def on_dates(df: pd.DataFrame, field: str, dates: pd.DatetimeIndex) -> pd.Series:
    """Value of ``field`` known on each date (by publication date, not reference date)."""
    if df.empty or field not in df:
        return pd.Series(np.nan, index=dates)
    s = df[["available", field]].dropna().sort_values("available", kind="stable")
    s = s.groupby("available")[field].last()  # several rows published the same day: keep newest
    return _asof(s, dates)
