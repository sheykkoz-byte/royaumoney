"""Regime & Quality Engine: every methodological choice in one place.

Ray Dalio's four economic seasons (growth and inflation, each rising or falling relative to
trend) drive an All Weather-style allocation; Warren Buffett's quality and value rules pick
stocks in the sectors the regime favours. Numbers below are defaults to be reviewed, not
optimised values.
"""

from dataclasses import dataclass, field
from typing import Literal

# ---- 1. Macro signals --------------------------------------------------------------------
Field = Literal["z", "z_chg3", "z_chg6"]


@dataclass(frozen=True)
class Component:
    series: str
    label: str
    transform: Literal["level", "yoy"]
    sign: Literal[1, -1]
    weight: float
    # Which robust z-scores (5-year window) make the signal: changes over 3 and 6 months
    # measure the move relative to trend; "z" is used for series that are already a growth
    # rate (GDPNow).
    fields: tuple[Field, ...] = ("z_chg3", "z_chg6")


GROWTH: list[Component] = [
    Component("IPMAN", "Produzione manifatturiera (a/a)", "yoy", 1, 0.30),
    Component("RRSFS", "Vendite al dettaglio reali (a/a)", "yoy", 1, 0.25),
    Component("UNRATE", "Disoccupazione", "level", -1, 0.25),
    Component("GDPNOW", "PIL in tempo reale (GDPNow)", "level", 1, 0.20, ("z",)),
]
INFLATION: list[Component] = [
    Component("CPIAUCSL", "Inflazione CPI (a/a)", "yoy", 1, 0.30),
    Component("PCEPILFE", "Core PCE (a/a)", "yoy", 1, 0.30),
    Component("T5YIE", "Inflazione attesa 5 anni", "level", 1, 0.20),
    Component("PPIACO", "Prezzi delle materie, PPI (a/a)", "yoy", 1, 0.20),
]
Z_CLIP = 3.0
# Uncertainty of a composite signal: P(rising) = Φ(score / SIGMA). The composite of 4
# z-scores has a typical size around 0.5-0.7; SIGMA sets how quickly a reading becomes
# "sure". Calibrated by eye on 2000-2026, to be revisited with the backtest.
SIGMA = 0.6

QUADRANTS = {
    "A": {"name": "Goldilocks", "growth": True, "inflation": False,
          "desc": "Crescita sopra le attese, inflazione sotto le attese."},
    "B": {"name": "Reflazione", "growth": True, "inflation": True,
          "desc": "Crescita e inflazione sopra le attese."},
    "C": {"name": "Stagflazione", "growth": False, "inflation": True,
          "desc": "Crescita sotto le attese, inflazione sopra le attese."},
    "D": {"name": "Deflazione / recessione", "growth": False, "inflation": False,
          "desc": "Crescita e inflazione sotto le attese."},
}
# A regime-change alert fires when the most likely quadrant changes and the new one has
# at least this probability (hysteresis against flip-flopping around 50%).
ALERT_MIN_PROB = 0.40

# ---- 2. Asset allocation -----------------------------------------------------------------
ASSETS = {
    "equity": "Azioni USA (SPY)",
    "long_tsy": "Treasury lunghi (TLT)",
    "int_tsy": "Treasury intermedi (IEF)",
    "tips": "TIPS, indicizzati all'inflazione (TIP)",
    "gold": "Oro (GLD)",
    "commodities": "Materie prime (DBC)",
    "cash": "Liquidità (T-bill)",
}
RISKY = [a for a in ASSETS if a != "cash"]
VOL_MONTHS = 12  # risk parity: volatility of the last 12 monthly returns
VOL_MIN_MONTHS = 6
# Tilt preferences per quadrant, from −1 (underweight) to +1 (overweight). From the brief:
# A growth equities & corporate credit; B commodities, cyclicals, EM, short duration;
# C gold, TIPS, energy, high cash; D long Treasuries, defensive quality.
TILTS: dict[str, dict[str, float]] = {
    "A": {"equity": 1.0, "long_tsy": 0.0, "int_tsy": 0.5, "tips": -0.5, "gold": -0.5,
          "commodities": -0.5, "cash": -1.0},
    "B": {"equity": 0.5, "long_tsy": -1.0, "int_tsy": -0.5, "tips": 0.5, "gold": 0.0,
          "commodities": 1.0, "cash": -0.5},
    "C": {"equity": -1.0, "long_tsy": -0.5, "int_tsy": -0.5, "tips": 1.0, "gold": 1.0,
          "commodities": 0.5, "cash": 1.0},
    "D": {"equity": -0.5, "long_tsy": 1.0, "int_tsy": 0.5, "tips": -0.5, "gold": 0.0,
          "commodities": -1.0, "cash": 0.5},
}
TILT_STRENGTH = 0.5  # weight × (1 + strength × expected preference)
MAX_DEVIATION = 0.10  # each tilted weight stays within ±10 points of the base weight
COST_BPS = 10  # transaction cost per unit of turnover, in basis points

# Bond and TIPS proxies before the ETFs existed: monthly return ≈ carry − duration × Δyield
DURATION = {"long_tsy": 15.0, "int_tsy": 7.5, "tips": 7.0}


# ---- 3. Buffett screener (used from step 3, needs FMP fundamentals) ----------------------
@dataclass(frozen=True)
class ScreenerRules:
    min_roe: float = 0.15
    max_debt_ebitda: float = 2.0
    min_margin_of_safety: float = 0.25
    min_discount_rate: float = 0.08
    equity_risk_premium: float = 0.05
    terminal_growth: float = 0.025
    max_growth: float = 0.12
    years: int = 10
    # Weight of each score family per quadrant: valuation, pricing power (margins),
    # balance sheet, earnings stability & dividends
    regime_weights: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "A": {"valore": 0.40, "pricing": 0.20, "bilancio": 0.20, "stabilita": 0.20},
        "B": {"valore": 0.20, "pricing": 0.40, "bilancio": 0.20, "stabilita": 0.20},
        "C": {"valore": 0.20, "pricing": 0.20, "bilancio": 0.40, "stabilita": 0.20},
        "D": {"valore": 0.20, "pricing": 0.20, "bilancio": 0.20, "stabilita": 0.40},
    })


SCREENER = ScreenerRules()
SECTORS: dict[str, list[str]] = {
    "A": ["Technology", "Consumer Cyclical", "Communication Services"],
    "B": ["Energy", "Industrials", "Financial Services", "Basic Materials"],
    "C": ["Energy", "Consumer Defensive", "Utilities"],
    "D": ["Healthcare", "Consumer Defensive", "Utilities"],
}
