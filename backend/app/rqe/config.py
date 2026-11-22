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
# How to hold each asset class: the US ETF used in the backtest and a UCITS equivalent that
# an EU investor can buy (US ETFs have no KID, so EU brokers do not sell them to retail).
# London tickers checked on Yahoo; on Borsa Italiana or Xetra search by the fund's name.
INSTRUMENTS: dict[str, dict] = {
    "equity": {
        "usa": "SPY", "ucits": "CSPX",
        "nome_ucits": "iShares Core S&P 500 UCITS ETF (Acc)",
        "ruolo": "Motore di crescita: va bene quando l'economia accelera e l'inflazione "
                 "è sotto controllo.",
    },
    "long_tsy": {
        "usa": "TLT", "ucits": "DTLA",
        "nome_ucits": "iShares $ Treasury Bond 20+yr UCITS ETF (Acc)",
        "ruolo": "Protezione da recessione e deflazione: sale quando i tassi scendono.",
    },
    "int_tsy": {
        "usa": "IEF", "ucits": "CBU0",
        "nome_ucits": "iShares $ Treasury Bond 7-10yr UCITS ETF (Acc)",
        "ruolo": "Stabilizzatore: meno sensibile ai tassi dei lunghi, è la base difensiva.",
    },
    "tips": {
        "usa": "TIP", "ucits": "IDTP",
        "nome_ucits": "iShares $ TIPS UCITS ETF (Acc)",
        "ruolo": "Treasury indicizzati all'inflazione: difendono quando l'inflazione sorprende.",
    },
    "gold": {
        "usa": "GLD", "ucits": "SGLD",
        "nome_ucits": "Invesco Physical Gold ETC",
        "ruolo": "Riserva di valore: aiuta con inflazione alta, crisi e dollaro debole.",
    },
    "commodities": {
        "usa": "DBC", "ucits": "ICOM",
        "nome_ucits": "iShares Diversified Commodity Swap UCITS ETF",
        "ruolo": "Materie prime: vanno bene quando crescita e inflazione salgono insieme.",
    },
    "cash": {
        "usa": "BIL", "ucits": "IB01",
        "nome_ucits": "iShares $ Treasury Bond 0-1yr UCITS ETF (Acc)",
        "ruolo": "Liquidità in Treasury a breve: parcheggio quando i regimi difensivi "
                 "sono probabili.",
    },
}
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
# Chosen by the calibration (rqe/calibrate.py, train 2000-2012, judged on 2013+; see
# docs/rqe-taratura.json). "imparato" = preferences learned walk-forward from earlier
# months only; "teorico" = TILTS. Probabilities averaged over SMOOTH_MONTHS months.
TILT_STRENGTH = 1.0  # weight × (1 + strength × expected preference)
TILT_MODE = "imparato"
SMOOTH_MONTHS = 3
# Months a regime decision is held (overlapping portfolios) and over which preferences are
# learned. SOLO_REGIME: keep only the part of the learned preference that changes with the
# regime (no static over/underweight common to all quadrants).
HORIZON = 3
SOLO_REGIME = True
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
