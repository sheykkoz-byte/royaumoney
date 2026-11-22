"""Catalog of every series the data engine tracks.

Each entry records what we expect from the source (unit text, frequency) so that
`verify` can refuse to ingest a series whose definition changed upstream, and how
we normalise it (``scale``) into the unit we store.

Units were checked on fred.stlouisfed.org on 2026-11-21 (see docs/serie-verificate.md).
"""

from dataclasses import dataclass, field
from typing import Literal

Category = Literal["liquidity", "macro", "market", "fx"]
Source = Literal["fred", "yahoo", "derived"]
Frequency = Literal["daily", "weekly", "monthly", "quarterly"]


@dataclass(frozen=True)
class SeriesDef:
    id: str
    name: str  # Italian label shown in the UI
    category: Category
    source: Source
    unit: str  # unit of the stored value, after scaling
    frequency: Frequency
    max_age_days: int  # older than this (from ref_date to today) = late
    source_id: str | None = None
    source_unit: str | None = None  # exact unit text expected from the source
    scale: float = 1.0  # stored = raw * scale
    release_lag_days: int = 0  # typical ref_date -> publication delay
    revised: bool = False  # true = fetch full ALFRED vintages when a key is available
    inputs: tuple[str, ...] = field(default_factory=tuple)  # for derived series
    notes: str = ""


def fred(
    id: str,
    name: str,
    category: Category,
    source_unit: str,
    unit: str,
    frequency: Frequency,
    max_age_days: int,
    release_lag_days: int,
    scale: float = 1.0,
    revised: bool = False,
    notes: str = "",
) -> SeriesDef:
    return SeriesDef(
        id=id,
        name=name,
        category=category,
        source="fred",
        source_id=id,
        source_unit=source_unit,
        unit=unit,
        scale=scale,
        frequency=frequency,
        max_age_days=max_age_days,
        release_lag_days=release_lag_days,
        revised=revised,
        notes=notes,
    )


def yahoo(id: str, ticker: str, name: str, unit: str) -> SeriesDef:
    return SeriesDef(
        id=id,
        name=name,
        category="market",
        source="yahoo",
        source_id=ticker,
        unit=unit,
        frequency="daily",
        max_age_days=5,
        release_lag_days=0,
        notes="Unadjusted close (yfinance, prototype only — not licensed for commercial use).",
    )


BN_USD = "Miliardi di USD"

SERIES: list[SeriesDef] = [
    # ---- Liquidity ---------------------------------------------------------------------
    fred("M2SL", "Massa monetaria M2 USA", "liquidity", "Billions of Dollars", BN_USD,
         "monthly", 90, 55, revised=True),
    fred("WALCL", "Bilancio della Fed", "liquidity", "Millions of U.S. Dollars", BN_USD,
         "weekly", 12, 1, scale=1e-3, notes="Wednesday level."),
    fred("WTREGEN", "Conto del Tesoro (TGA)", "liquidity", "Millions of U.S. Dollars", BN_USD,
         "weekly", 12, 1, scale=1e-3, notes="Week average ending Wednesday."),
    fred("RRPONTSYD", "Reverse repo overnight", "liquidity", "Billions of US Dollars", BN_USD,
         "daily", 5, 0),
    fred("ECBASSETSW", "Bilancio BCE", "liquidity", "Millions of Euros", "Miliardi di EUR",
         "weekly", 14, 4, scale=1e-3),
    fred("JPNASSETS", "Bilancio Banca del Giappone", "liquidity", "100 Million Yen",
         "Miliardi di JPY", "monthly", 70, 33, scale=0.1,
         notes="End-of-period value; FRED dates it on the first day of the month."),
    # ---- Macro -------------------------------------------------------------------------
    fred("CPIAUCSL", "Inflazione CPI", "macro", "Index 1982-1984=100", "Indice 1982-84=100",
         "monthly", 75, 43, revised=True),
    fred("PCEPILFE", "Core PCE", "macro", "Index 2017=100", "Indice 2017=100",
         "monthly", 90, 58, revised=True),
    fred("UNRATE", "Disoccupazione", "macro", "Percent", "%", "monthly", 70, 35, revised=True),
    fred("PAYEMS", "Payroll non agricoli", "macro", "Thousands of Persons", "Migliaia",
         "monthly", 70, 35, revised=True),
    fred("ICSA", "Richieste iniziali di sussidio", "macro", "Number", "Migliaia",
         "weekly", 14, 5, scale=1e-3, revised=True, notes="Week ending Saturday."),
    fred("CCSA", "Richieste continuative", "macro", "Number", "Migliaia",
         "weekly", 21, 12, scale=1e-3, revised=True, notes="Week ending Saturday."),
    fred("INDPRO", "Produzione industriale", "macro", "Index 2017=100", "Indice 2017=100",
         "monthly", 60, 16, revised=True),
    fred("DFF", "Fed funds effettivo", "macro", "Percent", "%", "daily", 5, 1),
    fred("T10YIE", "Inflazione attesa 10 anni (breakeven)", "macro", "Percent", "%",
         "daily", 5, 1),
    # ---- Market (FRED) -----------------------------------------------------------------
    fred("DGS10", "Rendimento Treasury 10 anni", "market", "Percent", "%", "daily", 5, 1),
    fred("DGS2", "Rendimento Treasury 2 anni", "market", "Percent", "%", "daily", 5, 1),
    fred("T10Y2Y", "Curva 10–2 anni", "market", "Percent", "Punti %", "daily", 5, 1),
    fred("BAMLH0A0HYM2", "Spread high yield", "market", "Percent", "%", "daily", 6, 1),
    fred("BAMLC0A0CM", "Spread investment grade", "market", "Percent", "%", "daily", 6, 1),
    fred("BAA10Y", "Spread Baa − Treasury 10 anni", "market", "Percent", "%", "daily", 6, 1,
         notes="Moody's Baa corporate yield minus 10y Treasury. Long history; "
               "investment grade only. Used alongside the 3-year ICE spreads."),
    fred("DTWEXBGS", "Dollaro (indice ampio)", "market", "Index Jan 2006=100",
         "Indice gen 2006=100", "daily", 14, 7, notes="Published weekly (H.10)."),
    # ---- FX helpers (to express ECB and BoJ balance sheets in USD) -----------------------
    fred("DEXUSEU", "Cambio USD per EUR", "fx", "U.S. Dollars to One Euro", "USD per EUR",
         "daily", 14, 7),
    fred("DEXJPUS", "Cambio JPY per USD", "fx", "Japanese Yen to One U.S. Dollar",
         "JPY per USD", "daily", 14, 7),
    # ---- Regime & Quality Engine (Dalio growth/inflation signals, asset proxies) ---------
    fred("IPMAN", "Produzione manifatturiera", "macro", "Index 2017=100", "Indice 2017=100",
         "monthly", 60, 16, revised=True,
         notes="Stand-in for the ISM PMI, which is no longer on FRED (ISM licence)."),
    fred("RRSFS", "Vendite al dettaglio reali", "macro", "Millions of 1982-84 CPI Adjusted Dollars",
         "Miliardi di $ 1982-84", "monthly", 60, 16, scale=1e-3, revised=True),
    fred("GDPNOW", "PIL USA, stima in tempo reale (GDPNow)", "macro",
         "Percent Change at Annual Rate", "% annualizzato", "quarterly", 120, 0, revised=True,
         notes="Atlanta Fed nowcast; quarterly, from 2011."),
    fred("T5YIE", "Inflazione attesa 5 anni", "market", "Percent", "%", "daily", 5, 1),
    fred("PPIACO", "Prezzi alla produzione, tutte le materie", "macro", "Index 1982=100",
         "Indice 1982=100", "monthly", 60, 14, revised=True),
    fred("DGS20", "Treasury 20 anni", "market", "Percent", "%", "daily", 5, 1),
    fred("DFII10", "TIPS 10 anni (rendimento reale)", "market", "Percent", "%", "daily", 5, 1),
    fred("DTB3", "T-bill 3 mesi", "market", "Percent", "%", "daily", 5, 1),
    # ---- Market prices (Yahoo, prototype) ----------------------------------------------
    yahoo("GOLD", "GC=F", "Oro (future)", "USD/oncia"),
    yahoo("COPPER", "HG=F", "Rame (future)", "USD/libbra"),
    yahoo("OIL_WTI", "CL=F", "Petrolio WTI (future)", "USD/barile"),
    yahoo("VIX", "^VIX", "VIX", "Indice"),
    yahoo("SPY", "SPY", "S&P 500 (ETF SPY)", "USD"),
    *[
        yahoo(t, t, f"Settore {label}", "USD")
        for t, label in [
            ("XLK", "tecnologia"), ("XLF", "finanziari"), ("XLE", "energia"),
            ("XLI", "industriali"), ("XLY", "consumi discrezionali"),
            ("XLP", "beni di prima necessità"), ("XLU", "utility"), ("XLV", "sanità"),
            ("XLB", "materiali"), ("XLRE", "immobiliare"), ("XLC", "comunicazioni"),
        ]
    ],
    # ---- Derived -----------------------------------------------------------------------
    SeriesDef("FED_NET_LIQ", "Liquidità netta Fed", "liquidity", "derived", BN_USD, "weekly",
              12, inputs=("WALCL", "WTREGEN", "RRPONTSYD"),
              notes="WALCL − WTREGEN − RRPONTSYD, on the Wednesday of each week."),
    SeriesDef("ECB_ASSETS_USD", "Bilancio BCE in USD", "liquidity", "derived", BN_USD, "weekly",
              14, inputs=("ECBASSETSW", "DEXUSEU")),
    SeriesDef("BOJ_ASSETS_USD", "Bilancio BoJ in USD", "liquidity", "derived", BN_USD,
              "monthly", 70, inputs=("JPNASSETS", "DEXJPUS"),
              notes="Converted at the last JPY/USD rate on or before month end."),
    SeriesDef("COPPER_GOLD", "Rapporto rame/oro", "market", "derived", "Rapporto ×1000",
              "daily", 5, inputs=("COPPER", "GOLD"),
              notes="(USD/lb copper ÷ USD/oz gold) × 1000."),
    SeriesDef("CYCL_DEF", "Ciclici vs difensivi", "market", "derived", "Indice (base 100)",
              "daily", 5, inputs=("XLY", "XLI", "XLF", "XLB", "XLP", "XLU", "XLV"),
              notes="Geometric mean of XLY, XLI, XLF, XLB over geometric mean of XLP, XLU, "
                    "XLV, rebased to 100 on the first common date. Scale-free, so it does "
                    "not depend on the ETFs' price levels."),
]

BY_ID: dict[str, SeriesDef] = {s.id: s for s in SERIES}


def get(series_id: str) -> SeriesDef:
    try:
        return BY_ID[series_id]
    except KeyError as e:
        raise KeyError(f"Unknown series {series_id!r}") from e
