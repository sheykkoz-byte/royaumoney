"""FRED / ALFRED client.

With FRED_API_KEY: official JSON API; revised series are downloaded with all their
vintages (ALFRED), so ``published_at`` is exact.

Without a key: the public CSV export used by fred.stlouisfed.org charts, and the series
web page for metadata. Same data, but no vintage history.
"""

import csv
import html
import io
import re
import time
from datetime import date

import httpx

from app.sources import RawPoint, SourceMeta

API = "https://api.stlouisfed.org/fred"
WEB = "https://fred.stlouisfed.org"
REALTIME_ALL = {"realtime_start": "1776-07-04", "realtime_end": "9999-12-31"}
PAGE_LIMIT = 100_000


class FredError(RuntimeError):
    pass


def _get(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(4):
        try:
            r = client.get(url, params=params, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                raise FredError(f"HTTP {r.status_code}")
            if r.status_code >= 400:
                # FRED puts the reason in error_message; never echo the URL (it has the key).
                msg = r.text[:300]
                try:
                    msg = r.json().get("error_message", msg)
                except ValueError:
                    pass
                raise FredError(f"HTTP {r.status_code}: {msg}")
            return r
        except (httpx.TransportError, FredError) as e:
            if isinstance(e, FredError) and "HTTP 4" in str(e) and "429" not in str(e):
                raise
            last = e
            time.sleep(2**attempt)
    raise FredError(f"FRED request failed after retries: {last}")


def _parse_value(s: str) -> float | None:
    s = s.strip()
    if s in ("", "."):
        return None
    return float(s)


class FredClient:
    def __init__(self, api_key: str = "", client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(headers={"User-Agent": "royaumoney-data/0.1"})

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    # ---- metadata --------------------------------------------------------------------
    def metadata(self, series_id: str) -> SourceMeta:
        if self.has_key:
            r = _get(self.client, f"{API}/series",
                     {"series_id": series_id, "api_key": self.api_key, "file_type": "json"})
            items = r.json().get("seriess") or []
            if not items:
                raise FredError(f"{series_id}: not found on FRED")
            s = items[0]
            return SourceMeta(s["title"], s["units"], s["frequency"], s.get("last_updated"))
        r = self.client.get(f"{WEB}/series/{series_id}", timeout=60, follow_redirects=True)
        if r.status_code == 404:
            raise FredError(f"{series_id}: not found on FRED")
        r.raise_for_status()
        return parse_series_page(r.text, series_id)

    # ---- observations ----------------------------------------------------------------
    def observations(self, series_id: str, start: date, vintages: bool = False) -> list[RawPoint]:
        if self.has_key:
            return self._api_observations(series_id, start, vintages)
        return self._csv_observations(series_id, start)

    def _api_observations(self, series_id: str, start: date, vintages: bool) -> list[RawPoint]:
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "limit": PAGE_LIMIT,
        }
        if vintages:
            params |= REALTIME_ALL | {"output_type": 1}
        out: list[RawPoint] = []
        offset = 0
        while True:
            r = _get(self.client, f"{API}/series/observations", params | {"offset": offset})
            data = r.json()
            obs = data.get("observations", [])
            for o in obs:
                v = _parse_value(o["value"])
                if v is None:
                    continue
                pub = date.fromisoformat(o["realtime_start"]) if vintages else None
                out.append(RawPoint(date.fromisoformat(o["date"]), v, pub))
            offset += len(obs)
            if not obs or offset >= int(data.get("count", 0)):
                break
        return out

    def _csv_observations(self, series_id: str, start: date) -> list[RawPoint]:
        r = _get(self.client, f"{WEB}/graph/fredgraph.csv",
                 {"id": series_id, "cosd": start.isoformat()})
        return parse_csv(r.text, series_id)


def parse_csv(text: str, series_id: str) -> list[RawPoint]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or len(header) < 2 or header[1] != series_id:
        raise FredError(f"{series_id}: unexpected CSV header {header!r}")
    out = []
    for row in reader:
        if len(row) < 2:
            continue
        v = _parse_value(row[1])
        if v is not None:
            out.append(RawPoint(date.fromisoformat(row[0]), v))
    return out


_TAG = re.compile(r"<[^>]+>")


def parse_series_page(page: str, series_id: str) -> SourceMeta:
    text = html.unescape(_TAG.sub(" ", page)).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    title_m = re.search(r"<title>(.*?)</title>", page, re.S)
    title = html.unescape(title_m.group(1)).split(" | ")[0].strip() if title_m else series_id
    unit_m = re.search(r"Units: (.+?) Frequency:", text)
    freq_m = re.search(r"Frequency: ([A-Za-z ,]+?)(?: WebFontConfig| \d|$| [A-Z][a-z]+:)", text)
    if not unit_m:
        raise FredError(f"{series_id}: could not read units from the FRED page")
    unit = unit_m.group(1).split(",")[0].strip()
    freq = freq_m.group(1).strip().rstrip(",") if freq_m else ""
    return SourceMeta(title, unit, freq)
