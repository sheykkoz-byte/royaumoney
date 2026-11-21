"""Everything that is a methodological choice lives here, so it can be reviewed and tuned
without touching the maths: which indicators exist, how the regime axes are built, and what
each scenario expects from each indicator.
"""

from dataclasses import dataclass
from typing import Literal

from app.analysis.indicators import Indicator

ICE_NOTE = "Storico di soli 3 anni su FRED (licenza ICE): z-score calcolato su 3 anni."

# ---- Indicators ---------------------------------------------------------------------------
INDICATORS: list[Indicator] = [
    # Macro voice: liquidity
    Indicator("fed_net_liq", "Liquidità netta Fed", "macro", ("FED_NET_LIQ",), "level", "pct",
              "mld $"),
    Indicator("m2", "Massa monetaria M2", "macro", ("M2SL",), "level", "pct", "mld $"),
    Indicator("ecb", "Bilancio BCE", "macro", ("ECBASSETSW",), "level", "pct", "mld €"),
    Indicator("boj", "Bilancio BoJ", "macro", ("JPNASSETS",), "level", "pct", "mld ¥"),
    # Macro voice: inflation
    Indicator("cpi", "Inflazione CPI", "macro", ("CPIAUCSL",), "yoy", "diff", "% a/a"),
    Indicator("core_pce", "Core PCE", "macro", ("PCEPILFE",), "yoy", "diff", "% a/a"),
    # Macro voice: labour and growth
    Indicator("unrate", "Disoccupazione", "macro", ("UNRATE",), "level", "diff", "%"),
    Indicator("payrolls", "Payroll (media 3 mesi)", "macro", ("PAYEMS",), "mavg3_diff", "diff",
              "migliaia/mese"),
    Indicator("claims", "Richieste iniziali (media 4 sett.)", "macro", ("ICSA",), "avg4", "pct",
              "migliaia"),
    Indicator("claims_cont", "Richieste continuative", "macro", ("CCSA",), "level", "pct",
              "migliaia"),
    Indicator("indpro", "Produzione industriale", "macro", ("INDPRO",), "yoy", "diff", "% a/a"),
    # Macro voice: policy rate
    Indicator("fed_funds", "Fed funds effettivo", "macro", ("DFF",), "level", "diff", "%"),
    # Market voice
    Indicator("curve", "Curva 10–2 anni", "market", ("T10Y2Y",), "level", "diff", "punti %"),
    Indicator("y10", "Treasury 10 anni", "market", ("DGS10",), "level", "diff", "%"),
    Indicator("fed_pricing", "Treasury 2 anni − Fed funds", "market", ("DGS2", "DFF"), "spread",
              "diff", "punti %",
              note="Positivo: il mercato prezza rialzi dei tassi; negativo: tagli."),
    Indicator("breakeven", "Inflazione attesa 10 anni", "market", ("T10YIE",), "level", "diff",
              "%", note="È un prezzo di mercato (TIPS), quindi sta nella voce del mercato."),
    Indicator("hy", "Spread high yield", "market", ("BAMLH0A0HYM2",), "level", "diff", "%",
              z_years=3, z_min_years=2, note=ICE_NOTE),
    Indicator("ig", "Spread investment grade", "market", ("BAMLC0A0CM",), "level", "diff", "%",
              z_years=3, z_min_years=2, note=ICE_NOTE),
    Indicator("baa", "Spread Baa − Treasury 10 anni", "market", ("BAA10Y",), "level", "diff", "%"),
    Indicator("usd", "Dollaro (indice ampio)", "market", ("DTWEXBGS",), "level", "pct", "indice"),
    Indicator("cu_au", "Rapporto rame/oro", "market", ("COPPER_GOLD",), "level", "pct", "×1000"),
    Indicator("cyc_def", "Ciclici vs difensivi", "market", ("CYCL_DEF",), "level", "pct",
              "indice"),
    Indicator("vix", "VIX", "market", ("VIX",), "level", "diff", "punti"),
    Indicator("oil", "Petrolio WTI", "market", ("OIL_WTI",), "level", "pct", "$/barile"),
    Indicator("gold", "Oro", "market", ("GOLD",), "level", "pct", "$/oncia"),
]

INDICATOR_BY_ID = {i.id: i for i in INDICATORS}

# What a signal reads from an indicator, in words (Italian, for explanations).
FIELD_LABELS = {
    "z": "livello rispetto agli ultimi anni",
    "z_chg1": "variazione a 1 mese",
    "z_chg3": "variazione a 3 mesi",
    "z_chg6": "variazione a 6 mesi",
    "s_chg3": "direzione a 3 mesi",
    "s_chg6": "direzione a 6 mesi",
}
FIELD_RAW = {"z": "value", "z_chg1": "chg1", "z_chg3": "chg3", "z_chg6": "chg6",
             "s_chg3": "chg3", "s_chg6": "chg6"}


@dataclass(frozen=True)
class Signal:
    indicator: str
    field: str  # a column of the indicator frame, see FIELD_LABELS
    sign: Literal[1, -1]  # +1: a high value supports, −1: a low value supports
    weight: float = 1.0


# ---- Regime (plan 4.2) --------------------------------------------------------------------
# Each axis is the weighted mean of *scaled changes* (sign = direction), clipped at ±3.
REGIME_AXES: dict[str, list[Signal]] = {
    "liquidity": [
        Signal("fed_net_liq", "s_chg3", 1, 0.4),
        Signal("m2", "s_chg6", 1, 0.3),
        Signal("ecb", "s_chg6", 1, 0.15),
        Signal("boj", "s_chg6", 1, 0.15),
    ],
    "growth": [
        Signal("payrolls", "s_chg3", 1, 0.3),
        Signal("unrate", "s_chg3", -1, 0.3),
        Signal("claims", "s_chg3", -1, 0.2),
        Signal("indpro", "s_chg3", 1, 0.2),
    ],
    "inflation": [
        Signal("cpi", "s_chg3", 1, 0.5),
        Signal("core_pce", "s_chg3", 1, 0.5),
    ],
}
AXIS_LABELS = {"liquidity": "Liquidità", "growth": "Crescita", "inflation": "Inflazione"}
# An axis this close to zero is reported as "al confine" (borderline).
BORDERLINE = 0.25

QUADRANTS = {
    (True, True): ("reflazione", "Reflazione", "crescita in accelerazione, inflazione in salita"),
    (True, False): ("goldilocks", "Goldilocks", "crescita in accelerazione, inflazione in calo"),
    (False, True): ("stagflazione", "Stagflazione",
                    "crescita in rallentamento, inflazione in salita"),
    (False, False): ("disinflazione", "Rallentamento disinflazionistico",
                     "crescita in rallentamento, inflazione in calo"),
}

# Assets whose behaviour is measured in each historical regime.
REGIME_ASSETS: list[tuple[str, str]] = [
    ("SPY", "S&P 500"), ("GOLD", "Oro"), ("DTWEXBGS", "Dollaro"),
    ("XLK", "Tecnologia"), ("XLF", "Finanziari"), ("XLE", "Energia"), ("XLI", "Industriali"),
    ("XLY", "Consumi discrezionali"), ("XLP", "Beni di prima necessità"), ("XLU", "Utility"),
    ("XLV", "Sanità"), ("XLB", "Materiali"), ("XLRE", "Immobiliare"), ("XLC", "Comunicazioni"),
]


# ---- Scenarios (plan 4.3) -----------------------------------------------------------------
@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    signals: tuple[Signal, ...]


SCENARIOS: list[Scenario] = [
    Scenario(
        "soft_landing", "Atterraggio morbido",
        "L'inflazione scende senza che il lavoro si rompa; la Fed può tagliare.",
        (
            Signal("cpi", "z_chg3", -1), Signal("core_pce", "z_chg3", -1),
            Signal("unrate", "z_chg3", -1, 0.5), Signal("payrolls", "z", 1),
            Signal("claims", "z", -1, 0.5), Signal("fed_funds", "z_chg6", -1, 0.5),
            Signal("hy", "z", -1), Signal("baa", "z", -1, 0.5),
            Signal("cyc_def", "z_chg3", 1), Signal("vix", "z", -1, 0.5),
            Signal("fed_pricing", "z", -1, 0.5), Signal("cu_au", "z_chg3", 1, 0.5),
        ),
    ),
    Scenario(
        "stagflation", "Stagflazione",
        "L'inflazione riaccelera mentre la crescita e il lavoro rallentano.",
        (
            Signal("cpi", "z_chg3", 1), Signal("core_pce", "z_chg3", 1),
            Signal("cpi", "z", 1, 0.5), Signal("unrate", "z_chg3", 1),
            Signal("payrolls", "z", -1, 0.5), Signal("claims", "z_chg3", 1, 0.5),
            Signal("breakeven", "z_chg3", 1), Signal("oil", "z_chg3", 1, 0.5),
            Signal("gold", "z_chg3", 1, 0.5), Signal("cyc_def", "z_chg3", -1),
            Signal("hy", "z_chg3", 1, 0.5), Signal("y10", "z_chg3", 1, 0.5),
        ),
    ),
    Scenario(
        "recession", "Recessione",
        "Il lavoro si deteriora, la produzione cala, il credito si allarga.",
        (
            Signal("unrate", "z_chg3", 1), Signal("payrolls", "z", -1),
            Signal("claims", "z_chg3", 1), Signal("claims_cont", "z_chg3", 1, 0.5),
            Signal("indpro", "z", -1, 0.5), Signal("cpi", "z_chg3", -1, 0.5),
            Signal("hy", "z", 1), Signal("baa", "z", 1, 0.5),
            Signal("cyc_def", "z_chg3", -1), Signal("cu_au", "z_chg3", -1, 0.5),
            Signal("vix", "z", 1, 0.5), Signal("fed_pricing", "z", -1),
            Signal("y10", "z_chg3", -1, 0.5), Signal("oil", "z_chg3", -1, 0.5),
        ),
    ),
    Scenario(
        "reflation", "Reflazione",
        "Crescita e inflazione salgono insieme, spinte dalla liquidità.",
        (
            Signal("payrolls", "z", 1), Signal("unrate", "z_chg3", -1, 0.5),
            Signal("indpro", "z_chg3", 1, 0.5), Signal("cpi", "z_chg3", 1),
            Signal("fed_net_liq", "z_chg3", 1, 0.5), Signal("m2", "z_chg6", 1, 0.5),
            Signal("breakeven", "z_chg3", 1), Signal("cu_au", "z_chg3", 1),
            Signal("cyc_def", "z_chg3", 1), Signal("y10", "z_chg3", 1, 0.5),
            Signal("usd", "z_chg3", -1, 0.5), Signal("oil", "z_chg3", 1, 0.5),
        ),
    ),
]

# ---- Scoring constants --------------------------------------------------------------------
Z_CLIP = 3.0  # a single indicator cannot count for more than ±3σ
SUPPORT_THRESHOLD = 0.25  # |aligned z| below this: neutral, neither supports nor contradicts
CONVERGENCE_DEADZONE = 0.25  # both voices weaker than this: convergence 0 (nothing to compare)
# Divergence alarm: the gap |market − macro| is wider than this share of past months
# (per scenario, using only months before the analysis date). With too little history the
# fixed fallback threshold (in σ) is used instead.
DIVERGENCE_PERCENTILE = 0.90
DIVERGENCE_MIN_MONTHS = 36
DIVERGENCE_FALLBACK = 1.5
SCORE_FULL_SCALE = 2.0  # average aligned z of 2σ = score 100
DOMINANT_MIN_SCORE = 20  # below this no scenario is called dominant: the data are mixed
DOMINANT_MIN_LEAD = 10  # ...or when the top two are closer than this


def change_unit(ind: Indicator) -> str:
    """Unit of the indicator's 1/3/6-month changes."""
    if ind.change == "pct":
        return "%"
    if "%" in ind.unit:
        return "punti %"
    return ind.unit
