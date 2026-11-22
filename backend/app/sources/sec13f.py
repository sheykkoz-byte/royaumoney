"""SEC EDGAR Form 13F: what large US managers held at the end of each quarter.

Free and public, no key. A 13F lists long positions in US-listed securities (shares,
listed options, convertible bonds) at quarter end; it is filed up to 45 days later. No
shorts, no non-US stocks, no cash or bonds, no trades within the quarter.
"""

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd

DATA = "https://data.sec.gov"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
PAUSE = 0.15  # SEC allows 10 requests per second


class SecError(RuntimeError):
    pass


@dataclass(frozen=True)
class Filing:
    cik: int
    accession: str  # 0001193125-26-463399
    form: str  # 13F-HR or 13F-HR/A
    filed: str  # filing date, ISO
    period: str  # quarter end the holdings refer to, ISO


class SecClient:
    def __init__(self, user_agent: str, cache_dir: Path | None = None,
                 client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=120, headers={"User-Agent": user_agent})
        self.cache_dir = cache_dir

    def _get(self, url: str) -> bytes:
        last: Exception | None = None
        for attempt in range(4):
            try:
                time.sleep(PAUSE)
                r = self.client.get(url)
                if r.status_code == 404:
                    raise SecError(f"404 {url}")
                if "Undeclared Automated Tool" in r.text[:2000]:
                    raise SecError("SEC refused the User-Agent: set SEC_USER_AGENT in .env")
                r.raise_for_status()
                return r.content
            except SecError:
                raise
            except Exception as e:  # network or 429/5xx: retry with backoff
                last = e
                time.sleep(2 * 2**attempt)
        raise SecError(f"{url}: {last}")

    def filings(self, cik: int) -> tuple[str, list[Filing]]:
        """Manager name and its 13F-HR filings (newest first), amendments included."""
        import json

        d = json.loads(self._get(f"{DATA}/submissions/CIK{cik:010d}.json"))
        r = d["filings"]["recent"]
        out = [Filing(cik, a, f, fd, p) for f, a, fd, p in
               zip(r["form"], r["accessionNumber"], r["filingDate"], r["reportDate"],
                   strict=False) if f in ("13F-HR", "13F-HR/A")]
        return d["name"], out

    def holdings(self, f: Filing) -> pd.DataFrame:
        """The information table of a filing, parsed (cached on disk: filings never change)."""
        cache = self.cache_dir / f"{f.accession}.csv" if self.cache_dir else None
        if cache and cache.exists():
            return normalize_units(pd.read_csv(cache, dtype={"cusip": str}).fillna(
                {"put_call": "", "tipo": "SH"}))
        base = f"{ARCHIVES}/{f.cik}/{f.accession.replace('-', '')}"
        import json

        items = json.loads(self._get(f"{base}/index.json"))["directory"]["item"]
        xmls = [i["name"] for i in items
                if i["name"].lower().endswith(".xml") and i["name"] != "primary_doc.xml"]
        if not xmls:
            raise SecError(f"no information table in {f.accession}")
        df = normalize_units(parse_infotable(self._get(f"{base}/{xmls[0]}")))
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache, index=False)
        return df


    def amendment_type(self, f: Filing) -> str:
        """"RESTATEMENT" (replaces the filing) or "NEW HOLDINGS" (adds positions)."""
        cache = self.cache_dir / f"{f.accession}.type" if self.cache_dir else None
        if cache and cache.exists():
            return cache.read_text().strip()
        base = f"{ARCHIVES}/{f.cik}/{f.accession.replace('-', '')}"
        root = ET.fromstring(self._get(f"{base}/primary_doc.xml"))
        t = next((el.text or "" for el in root.iter() if _strip(el.tag) == "amendmentType"),
                 "RESTATEMENT").strip().upper()
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(t)
        return t

    def period_holdings(self, filings: list[Filing], period: str) -> pd.DataFrame:
        """Holdings for a quarter with its amendments applied in filing order: a restatement
        replaces what came before, "new holdings" are added."""
        fs = sorted((f for f in filings if f.period == period),
                    key=lambda f: (f.filed, f.form != "13F-HR"))
        df = None
        for f in fs:
            h = self.holdings(f)
            if df is None or f.form == "13F-HR" or self.amendment_type(f) == "RESTATEMENT":
                df = h
            else:
                df = combine(df, h)
        return df if df is not None else pd.DataFrame()


def combine(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    df = pd.concat([a, b], ignore_index=True)
    return (df.groupby(["cusip", "put_call"], as_index=False)
              .agg(issuer=("issuer", "first"), classe=("classe", "first"),
                   tipo=("tipo", "first"), valore=("valore", "sum"),
                   quantita=("quantita", "sum")))


def _strip(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_infotable(xml: bytes) -> pd.DataFrame:
    """One row per (cusip, put/call): issuer, class, value in USD, shares.

    Managers split a position over many rows (one per sub-manager or discretion type):
    they are summed. Values are in dollars (since 2023 the SEC no longer uses thousands).
    """
    rows = []
    for _, el in ET.iterparse(__import__("io").BytesIO(xml), events=("end",)):
        if _strip(el.tag) != "infoTable":
            continue
        d = {}
        for c in el.iter():
            t = _strip(c.tag)
            if t in ("nameOfIssuer", "titleOfClass", "cusip", "value", "sshPrnamt",
                     "sshPrnamtType", "putCall"):
                d[t] = (c.text or "").strip()
        rows.append({
            "cusip": d.get("cusip", "").upper(),
            "issuer": d.get("nameOfIssuer", ""),
            "classe": d.get("titleOfClass", ""),
            "put_call": d.get("putCall", "") or "",
            "tipo": d.get("sshPrnamtType", "SH"),
            "valore": float(d.get("value") or 0),
            "quantita": float(d.get("sshPrnamt") or 0),
        })
        el.clear()
    df = pd.DataFrame(rows, columns=["cusip", "issuer", "classe", "put_call", "tipo", "valore",
                                     "quantita"])
    if df.empty:
        return df
    return (df.groupby(["cusip", "put_call"], as_index=False)
              .agg(issuer=("issuer", "first"), classe=("classe", "first"),
                   tipo=("tipo", "first"), valore=("valore", "sum"),
                   quantita=("quantita", "sum")))


def normalize_units(df: pd.DataFrame) -> pd.DataFrame:
    """Some managers still report values in thousands of dollars. Shares cost more than $1
    almost always, so a median implied price below $1 means thousands."""
    sh = df[(df["tipo"] == "SH") & (df["quantita"] > 0)]
    if not sh.empty and float((sh["valore"] / sh["quantita"]).median()) < 1.0:
        df = df.assign(valore=df["valore"] * 1000)
    return df
