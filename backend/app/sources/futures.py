"""Estimated gold spot (XAU/USD) from COMEX gold futures.

Yahoo has no gold spot quote any more, and the continuous ``GC=F`` jumps by the carry
(≈ $30 every two months) when it rolls to the next contract. Instead, on each day we take
the two nearest active contracts and remove the cost of carry implied by their spread:

    c      = ln(F_next / F_near) / (T_next − T_near)        (implied carry, per year)
    spot ≈ F_near · exp(−c · (T_near − t))

applied to open, high, low and close of the near contract. This is the standard
cost-of-carry relation; for gold the convenience yield is negligible. The near contract
is the first one not yet within ``ROLL_BDAYS`` business days of its first notice day.
"""

import json
import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

GOLD_MONTHS = {2: "G", 4: "J", 6: "M", 8: "Q", 10: "V", 12: "Z"}
ROLL_BDAYS = 3
BDAY = pd.offsets.BDay()


@dataclass(frozen=True)
class Contract:
    root: str
    year: int
    month: int

    @property
    def symbol(self) -> str:
        return f"{self.root}{GOLD_MONTHS[self.month]}{self.year % 100:02d}.CMX"

    @property
    def first_notice(self) -> date:
        """Last business day of the month before the delivery month."""
        first_of_month = pd.Timestamp(self.year, self.month, 1)
        return (first_of_month - BDAY).date()

    @property
    def roll_date(self) -> date:
        return (pd.Timestamp(self.first_notice) - ROLL_BDAYS * BDAY).date()

    @property
    def last_trade(self) -> date:
        """Third-last business day of the delivery month (COMEX gold)."""
        month_end = pd.Timestamp(self.year, self.month, 1) + pd.offsets.MonthEnd(0)
        last_bday = month_end if month_end.weekday() < 5 else month_end - BDAY
        return (last_bday - 2 * BDAY).date()


def contracts_from(d: date, n: int, root: str = "GC") -> list[Contract]:
    """The first ``n`` active contracts whose roll date is after ``d``."""
    out: list[Contract] = []
    y, m = d.year, d.month
    while len(out) < n:
        if m in GOLD_MONTHS:
            c = Contract(root, y, m)
            if c.roll_date > d:
                out.append(c)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def contracts_needed(start: date, end: date) -> list[Contract]:
    seen: dict[str, Contract] = {}
    for d in pd.bdate_range(start, end):
        for c in contracts_from(d.date(), 2):
            seen[c.symbol] = c
    return list(seen.values())


def estimate_spot(
    contract_bars: dict[str, pd.DataFrame], start: date, end: date
) -> pd.DataFrame:
    """Spot OHLC bars. ``contract_bars`` maps symbol → DataFrame(open, high, low, close)."""
    rows = []
    for d in pd.bdate_range(start, end):
        near, nxt = contracts_from(d.date(), 2)
        nb = contract_bars.get(near.symbol)
        xb = contract_bars.get(nxt.symbol)
        if nb is None or d not in nb.index or pd.isna(nb.loc[d, "close"]):
            continue
        if xb is None or d not in xb.index or pd.isna(xb.loc[d, "close"]):
            continue  # without the next contract we cannot measure the carry
        t_near = (pd.Timestamp(near.last_trade) - d).days / 365.0
        t_span = (pd.Timestamp(nxt.last_trade) - pd.Timestamp(near.last_trade)).days / 365.0
        carry = math.log(xb.loc[d, "close"] / nb.loc[d, "close"]) / t_span
        factor = math.exp(-carry * max(t_near, 0.0))
        bar = {k: float(nb.loc[d, k]) * factor for k in ("open", "high", "low", "close")}
        # A bar's high/low must contain open/close even after rounding
        bar["high"] = max(bar.values())
        bar["low"] = min(bar["open"], bar["low"], bar["close"])
        rows.append({
            "date": d, **bar,
            "detail": json.dumps({
                "contract": near.symbol, "next": nxt.symbol,
                "near_close": round(float(nb.loc[d, "close"]), 2),
                "carry_pct_year": round(carry * 100, 2),
                "days_to_expiry": round(t_near * 365),
            }),
        })
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "detail"])
    return pd.DataFrame(rows).set_index("date")
