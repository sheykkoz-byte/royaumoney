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
