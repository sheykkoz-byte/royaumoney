"""Monthly total returns of the All Weather asset classes, from 2000.

ETF prices adjusted for dividends (Yahoo) where the ETF exists; before that, proxies:
- Treasuries and TIPS: carry minus duration × change in yield (FRED DGS20, DGS10, DFII10;
  TIPS also accrue CPI inflation). TIPS before 2003 do not exist and are left out.
- Gold: COMEX future (GC=F) before GLD.
- Commodities: equal mix of oil, gold and copper futures before DBC.
- Cash: 3-month T-bill (DTB3).
Downloads are cached in backend/data/cache (refreshed once a day).
"""

from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.rqe import config as C
from app.store import load_frame

CACHE = BACKEND_DIR / "data" / "cache" / "rqe_etf_monthly.csv"
ETF = {"equity": "SPY", "long_tsy": "TLT", "int_tsy": "IEF", "tips": "TIP", "gold": "GLD",
       "commodities": "DBC"}
FUTURES = ["GC=F", "CL=F", "HG=F"]


def _download_monthly(tickers: list[str], start: str = "1999-11-01") -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(tickers, start=start, interval="1mo", auto_adjust=True, progress=False)
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]
    close.index = pd.DatetimeIndex(close.index).tz_localize(None) + pd.offsets.MonthEnd(0)
    # Yahoo can add a second row for the current month (today's price): keep the last
    return close[~close.index.duplicated(keep="last")]


def etf_prices(refresh: bool = False, cache: Path = CACHE) -> pd.DataFrame:
    """Month-end adjusted prices of the ETFs and futures (cached for a day)."""
    fresh = cache.exists() and datetime.fromtimestamp(cache.stat().st_mtime) > \
        datetime.now() - timedelta(days=1)
    if cache.exists() and fresh and not refresh:
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        return df[~df.index.duplicated(keep="last")]
    df = _download_monthly(list(ETF.values()) + FUTURES)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache)
    return df


def _month_end(s: pd.Series) -> pd.Series:
    return s.resample("ME").last()


def bond_proxy(yield_pct: pd.Series, duration: float) -> pd.Series:
    """Monthly return of a constant-maturity bond: carry − duration × Δyield."""
    y = _month_end(yield_pct) / 100
    return y.shift(1) / 12 - duration * y.diff()


def tips_proxy(real_yield_pct: pd.Series, cpi: pd.Series, duration: float) -> pd.Series:
    y = _month_end(real_yield_pct) / 100
    infl = _month_end(cpi).pct_change()
    infl.index = infl.index + pd.offsets.MonthEnd(1)  # CPI of month m is known in m+1
    return y.shift(1) / 12 - duration * y.diff() + infl.reindex(y.index)


def splice(primary: pd.Series, proxy: pd.Series) -> pd.Series:
    """ETF return where the ETF exists, proxy before."""
    out = proxy.copy()
    out.loc[primary.dropna().index] = primary.dropna()
    return out


def returns(session: Session, prices: pd.DataFrame | None = None,
            start: str = "2000-01-31") -> pd.DataFrame:
    """Monthly total returns (decimal) of every asset in config.ASSETS."""
    prices = etf_prices() if prices is None else prices
    pr = prices.pct_change()

    def fred(sid: str) -> pd.Series:
        f = load_frame(session, sid, availability="first")
        return f["value"] if not f.empty else pd.Series(dtype=float)

    out = pd.DataFrame(index=pd.date_range(start, date.today(), freq="ME"))
    out["equity"] = pr.get("SPY")
    out["long_tsy"] = splice(pr.get("TLT"), bond_proxy(fred("DGS20"), C.DURATION["long_tsy"]))
    out["int_tsy"] = splice(pr.get("IEF"), bond_proxy(fred("DGS10"), C.DURATION["int_tsy"]))
    out["tips"] = splice(pr.get("TIP"), tips_proxy(fred("DFII10"), fred("CPIAUCSL"),
                                                   C.DURATION["tips"]))
    out["gold"] = splice(pr.get("GLD"), pr.get("GC=F"))
    fut = pr[[t for t in FUTURES if t in pr]].mean(axis=1, skipna=False)
    out["commodities"] = splice(pr.get("DBC"), fut)
    out["cash"] = _month_end(fred("DTB3")).shift(1) / 100 / 12
    out = out.reindex(out.index.intersection(pd.date_range(start, date.today(), freq="ME")))
    # The current, unfinished month is not a return yet
    out = out[out.index < pd.Timestamp(date.today()) + pd.offsets.MonthEnd(0)]
    return out.astype(float).replace([np.inf, -np.inf], np.nan)
