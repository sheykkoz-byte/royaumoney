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


def rolling_z(s: pd.Series, years: int, min_years: int) -> pd.Series:
    """z-score of each point against the trailing ``years`` window (point included).

    NaN until the series has ``min_years`` of history, or where the window has no spread.
    """
    s = s.dropna()
    if s.empty:
        return s
    win = s.rolling(f"{int(years * 365.25)}D", min_periods=5)
    std = win.std()
    z = (s - win.mean()) / std.where(std > 0)
    z[s.index < s.index[0] + pd.Timedelta(days=int(min_years * 365.25))] = np.nan
    return z


def rolling_scaled(s: pd.Series, years: int, min_years: int) -> pd.Series:
    """Value divided by its root mean square over the trailing window (sign preserved)."""
    s = s.dropna()
    if s.empty:
        return s
    rms = np.sqrt((s**2).rolling(f"{int(years * 365.25)}D", min_periods=5).mean())
    out = s / rms.where(rms > 0)
    out[s.index < s.index[0] + pd.Timedelta(days=int(min_years * 365.25))] = np.nan
    return out


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
