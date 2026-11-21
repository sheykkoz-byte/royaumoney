"""Derived series. Pure functions on frames from ``store.load_frame``.

Each input frame has columns ``value`` and ``published_at`` indexed by ref_date.
Each output has the same shape; ``published_at`` is the latest publication date among
the inputs actually used for that row, so a derived value is never "known" earlier than
its ingredients.
"""

import numpy as np
import pandas as pd

EMPTY = pd.DataFrame(
    {"value": pd.Series(dtype=float), "published_at": pd.Series(dtype="datetime64[ns]")},
    index=pd.DatetimeIndex([], name="ref_date"),
)


def _asof(left_index: pd.DatetimeIndex, right: pd.DataFrame, suffix: str) -> pd.DataFrame:
    """For each date in ``left_index``, the last row of ``right`` on or before it."""
    left = pd.DataFrame({"ref_date": left_index}).sort_values("ref_date")
    r = right.reset_index().rename(columns={"value": f"value{suffix}",
                                            "published_at": f"pub{suffix}"})
    r = r.sort_values("ref_date")
    return pd.merge_asof(left, r, on="ref_date", direction="backward").set_index("ref_date")


def _finish(values: pd.Series, pubs: list[pd.Series]) -> pd.DataFrame:
    pub = pd.concat(pubs, axis=1).max(axis=1)
    out = pd.DataFrame({"value": values, "published_at": pub}).dropna()
    out.index.name = "ref_date"
    return out


def fed_net_liquidity(walcl: pd.DataFrame, tga: pd.DataFrame, rrp: pd.DataFrame) -> pd.DataFrame:
    """WALCL − TGA − ON RRP, in the unit of the inputs (billions of USD), on WALCL dates.

    TGA is matched on the same Wednesday (or the last one before); RRP is daily, so we
    take the last value on or before the Wednesday.
    """
    if walcl.empty or tga.empty or rrp.empty:
        return EMPTY.copy()
    t = _asof(walcl.index, tga, "_t")
    r = _asof(walcl.index, rrp, "_r")
    val = walcl["value"] - t["value_t"] - r["value_r"]
    return _finish(val, [walcl["published_at"], t["pub_t"], r["pub_r"]])


def convert_with_fx(
    amount: pd.DataFrame,
    fx: pd.DataFrame,
    *,
    multiply: bool,
    period_end: bool = False,
) -> pd.DataFrame:
    """Convert an amount with the last FX rate on or before each date.

    ``multiply``: True for quotes like USD per EUR, False for JPY per USD.
    ``period_end``: monthly end-of-period series dated on the 1st (e.g. JPNASSETS):
    use the rate at month end instead of the 1st.
    """
    if amount.empty or fx.empty:
        return EMPTY.copy()
    lookup = amount.index + pd.offsets.MonthEnd(0) if period_end else amount.index
    f = _asof(pd.DatetimeIndex(lookup), fx, "_fx")
    f.index = amount.index
    rate = f["value_fx"]
    val = amount["value"] * rate if multiply else amount["value"] / rate
    return _finish(val, [amount["published_at"], f["pub_fx"]])


def ratio(num: pd.DataFrame, den: pd.DataFrame, factor: float = 1.0) -> pd.DataFrame:
    """num / den × factor on the dates both have."""
    j = pd.merge(num, den, left_index=True, right_index=True, suffixes=("_n", "_d"))
    if j.empty:
        return EMPTY.copy()
    val = j["value_n"] / j["value_d"] * factor
    return _finish(val, [j["published_at_n"], j["published_at_d"]])


def cyclicals_vs_defensives(
    cyclicals: dict[str, pd.DataFrame], defensives: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    """Geometric mean of cyclicals over geometric mean of defensives, first date = 100.

    The geometric mean makes the result independent of each ETF's price level (an ETF
    at $200 does not weigh more than one at $40), which a sum of prices would not.
    """
    frames = {**cyclicals, **defensives}
    if any(f.empty for f in frames.values()):
        return EMPTY.copy()
    prices = pd.concat({k: f["value"] for k, f in frames.items()}, axis=1).dropna()
    if prices.empty:
        return EMPTY.copy()
    pubs = pd.concat({k: f["published_at"] for k, f in frames.items()}, axis=1).loc[prices.index]
    logs = np.log(prices)
    raw = np.exp(logs[list(cyclicals)].mean(axis=1) - logs[list(defensives)].mean(axis=1))
    val = raw / raw.iloc[0] * 100
    return _finish(val, [pubs.max(axis=1)])
