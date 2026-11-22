"""OpenFIGI: CUSIP → ticker (13F filings give CUSIPs, prices need tickers). Free, no key:
25 requests per minute with 10 CUSIPs each. Results cached in a CSV (they never change)."""

import time
from pathlib import Path

import httpx
import pandas as pd

URL = "https://api.openfigi.com/v3/mapping"
BATCH = 10
PAUSE = 2.6  # seconds between requests: 25 per minute


def map_cusips(cusips: list[str], cache: Path, client: httpx.Client | None = None) -> dict:
    """{cusip: {"ticker", "nome", "tipo"}}; unknown CUSIPs map to ticker None."""
    known = pd.read_csv(cache, dtype=str).fillna("") if cache.exists() else \
        pd.DataFrame(columns=["cusip", "ticker", "nome", "tipo"])
    have = set(known["cusip"])
    todo = sorted({c for c in cusips if c and c not in have})
    client = client or httpx.Client(timeout=60)
    new = []
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        body = [{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk]
        for attempt in range(5):
            r = client.post(URL, json=body)
            if r.status_code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        else:
            break  # still rate limited: keep what we have, the rest next time
        for c, res in zip(chunk, r.json(), strict=False):
            d = (res.get("data") or [{}])[0]
            new.append({"cusip": c, "ticker": d.get("ticker", ""), "nome": d.get("name", ""),
                        "tipo": d.get("securityType2") or d.get("securityType", "")})
        if i + BATCH < len(todo):
            time.sleep(PAUSE)
    if new:
        known = pd.concat([known, pd.DataFrame(new)], ignore_index=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        known.to_csv(cache, index=False)
    return {r.cusip: {"ticker": r.ticker or None, "nome": r.nome, "tipo": r.tipo}
            for r in known.itertuples()}
