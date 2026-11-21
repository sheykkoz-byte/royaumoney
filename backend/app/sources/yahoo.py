"""Market prices from Yahoo Finance via yfinance.

Prototype only: Yahoo's terms do not allow commercial use. The interface (tickers in,
RawPoints out) is what a licensed provider will implement later — see docs/fonti-dati.md.
"""

import time
from datetime import date

import pandas as pd

from app.sources import RawPoint


class YahooError(RuntimeError):
    pass


def download_closes(tickers: list[str], start: date) -> dict[str, list[RawPoint]]:
    import yfinance as yf

    last: Exception | None = None
    for attempt in range(4):
        try:
            df = yf.download(
                tickers,
                start=start.isoformat(),
                auto_adjust=False,  # unadjusted: adjusted history changes after every dividend
                progress=False,
                group_by="column",
                threads=True,
            )
            if df is None or df.empty:
                raise YahooError("empty response")
            return closes_to_points(df["Close"], tickers)
        except Exception as e:  # yfinance raises many types, incl. rate limits
            last = e
            time.sleep(3 * 2**attempt)
    raise YahooError(f"Yahoo download failed: {last}")


def closes_to_points(
    closes: pd.DataFrame | pd.Series, tickers: list[str]
) -> dict[str, list[RawPoint]]:
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(tickers[0])
    out: dict[str, list[RawPoint]] = {}
    for t in tickers:
        if t not in closes.columns:
            out[t] = []
            continue
        s = closes[t].dropna()
        out[t] = [
            RawPoint(d.date(), float(v), published_at=d.date()) for d, v in s.items()
        ]
    return out


def download_ohlc(
    tickers: list[str], start: date, end: date | None = None
) -> dict[str, pd.DataFrame]:
    """Daily OHLC per ticker (columns open, high, low, close; index = date)."""
    import yfinance as yf

    last: Exception | None = None
    for attempt in range(4):
        try:
            df = yf.download(
                tickers, start=start.isoformat(),
                end=None if end is None else (pd.Timestamp(end) + pd.Timedelta(days=1)).date()
                .isoformat(),
                auto_adjust=False, progress=False, group_by="ticker", threads=True,
            )
            if df is None or df.empty:
                raise YahooError("empty response")
            out = {}
            for t in tickers:
                if t not in df.columns.get_level_values(0):
                    continue
                sub = df[t][["Open", "High", "Low", "Close"]].dropna(subset=["Close"])
                sub.columns = ["open", "high", "low", "close"]
                sub.index = pd.DatetimeIndex(sub.index).tz_localize(None).normalize()
                out[t] = sub
            return out
        except Exception as e:  # yfinance raises many types, incl. rate limits
            last = e
            time.sleep(3 * 2**attempt)
    raise YahooError(f"Yahoo OHLC download failed: {last}")
