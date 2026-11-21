"""Twelve Data: real spot quotes (e.g. XAU/USD) with daily OHLC.

The key is sent in the ``Authorization: apikey …`` header. In the cloud environment the
network proxy injects the saved key into that header, so the code works with no key set;
locally put TWELVEDATA_API_KEY in .env.
"""

import time
from datetime import date

import httpx
import pandas as pd

API = "https://api.twelvedata.com"
PROXY_PLACEHOLDER = "injected-by-proxy"


class TwelveDataError(RuntimeError):
    pass


def download_ohlc(symbol: str, start: date, end: date, api_key: str = "",
                  client: httpx.Client | None = None) -> pd.DataFrame:
    client = client or httpx.Client(timeout=60)
    params = {"symbol": symbol, "interval": "1day", "start_date": start.isoformat(),
              "end_date": (pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat(),
              "outputsize": 5000, "order": "ASC"}
    headers = {"Authorization": f"apikey {api_key or PROXY_PLACEHOLDER}"}
    last: Exception | None = None
    for attempt in range(4):
        try:
            r = client.get(f"{API}/time_series", params=params, headers=headers)
            if r.status_code in (401, 403):
                raise TwelveDataError(f"HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            if data.get("status") == "error":
                code = data.get("code")
                if code == 429:
                    raise TwelveDataError("rate limit")
                raise TwelveDataError(f"{code}: {data.get('message')}")  # not retried below
            return parse(data)
        except TwelveDataError as e:
            if "rate limit" not in str(e):  # auth/symbol errors: retrying will not help
                raise
            last = e
        except httpx.ProxyError as e:  # host not allowed: retrying will not help
            raise TwelveDataError(f"network: {e}") from None
        except (httpx.TransportError, ValueError) as e:
            last = e
        time.sleep(8 * (attempt + 1))
    raise TwelveDataError(f"Twelve Data request failed: {last}")


def parse(data: dict) -> pd.DataFrame:
    rows = data.get("values") or []
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["datetime"]).dt.normalize()
    df = df[["open", "high", "low", "close"]].astype(float).sort_index()
    return df[~df.index.duplicated(keep="last")]


# ---- daily bars with the FX/metals convention --------------------------------------------
# Twelve Data's daily XAU/USD bars use their own day boundary and include weekend quotes.
# Brokers and the spot market use a trading day from 17:00 to 17:00 New York, Monday to
# Friday: we rebuild that from hourly bars (timestamps = bar start, New York time).
NY_CLOSE_SHIFT = pd.Timedelta(hours=7)  # 17:00 NY + 7h = 00:00 of the next trading day
HOURLY_CHUNK_DAYS = 180  # 5,000 hourly bars per request ≈ 208 days


def daily_from_hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    if hourly.empty:
        return hourly
    session = (hourly.index + NY_CLOSE_SHIFT).normalize()
    h = hourly.assign(session=session)
    h = h[h["session"].dt.day_of_week < 5]  # Friday 17:00 → Sunday 17:00 is the weekend
    out = h.groupby("session").agg(open=("open", "first"), high=("high", "max"),
                                   low=("low", "min"), close=("close", "last"))
    out.index.name = None
    return out


def download_daily_ny(symbol: str, start: date, end: date, api_key: str = "",
                      client: httpx.Client | None = None) -> pd.DataFrame:
    """Daily OHLC with 17:00 New York sessions, built from hourly bars."""
    client = client or httpx.Client(timeout=60)
    chunks = []
    cur = pd.Timestamp(start) - pd.Timedelta(days=2)
    stop = pd.Timestamp(end) + pd.Timedelta(days=1)
    while cur < stop:
        nxt = min(cur + pd.Timedelta(days=HOURLY_CHUNK_DAYS), stop)
        chunks.append(_hourly(symbol, cur, nxt, api_key, client))
        cur = nxt
    hourly = pd.concat([c for c in chunks if not c.empty]) if chunks else pd.DataFrame()
    if hourly.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    hourly = hourly[~hourly.index.duplicated(keep="last")].sort_index()
    daily = daily_from_hourly(hourly)
    return daily[(daily.index >= pd.Timestamp(start)) & (daily.index <= pd.Timestamp(end))]


def _hourly(symbol, start, end, api_key, client) -> pd.DataFrame:
    params = {"symbol": symbol, "interval": "1h", "timezone": "America/New_York",
              "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
              "end_date": end.strftime("%Y-%m-%d %H:%M:%S"), "outputsize": 5000,
              "order": "ASC"}
    headers = {"Authorization": f"apikey {api_key or PROXY_PLACEHOLDER}"}
    last: Exception | None = None
    for attempt in range(4):
        try:
            r = client.get(f"{API}/time_series", params=params, headers=headers)
            if r.status_code in (401, 403):
                raise TwelveDataError(f"HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            if data.get("status") == "error":
                if data.get("code") == 429:
                    raise TwelveDataError("rate limit")
                if "No data" in str(data.get("message")):
                    return pd.DataFrame(columns=["open", "high", "low", "close"])
                raise TwelveDataError(f"{data.get('code')}: {data.get('message')}")
            rows = data.get("values") or []
            if not rows:
                return pd.DataFrame(columns=["open", "high", "low", "close"])
            df = pd.DataFrame(rows)
            df.index = pd.to_datetime(df["datetime"])
            return df[["open", "high", "low", "close"]].astype(float)
        except TwelveDataError as e:
            if "rate limit" not in str(e):
                raise
            last = e
        except httpx.ProxyError as e:
            raise TwelveDataError(f"network: {e}") from None
        except (httpx.TransportError, ValueError) as e:
            last = e
        time.sleep(8 * (attempt + 1))  # free plan: 8 requests per minute
    raise TwelveDataError(f"Twelve Data request failed: {last}")
