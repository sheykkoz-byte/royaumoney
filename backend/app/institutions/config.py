"""Which managers to follow and the rules of the analysis. Every choice in one place."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Manager:
    cik: int
    nome: str
    # "discrezionale": a few people decide (Buffett, Tepper…): their moves are opinions.
    # "flussi": mostly index funds and clients' accounts: moves follow money flows, not views.
    stile: Literal["discrezionale", "flussi"]
    nota: str


MANAGERS = [
    Manager(1067983, "Berkshire Hathaway", "discrezionale",
            "Warren Buffett e i suoi gestori: poche posizioni, tenute a lungo."),
    Manager(1350694, "Bridgewater Associates", "discrezionale",
            "Il fondo fondato da Ray Dalio: molte posizioni, in gran parte sistematiche."),
    # Since mid-2026 the holdings are filed by Pershing Square Inc. (the old adviser, CIK
    # 1336528, files 13F-NT notices pointing to it)
    Manager(2026053, "Pershing Square", "discrezionale",
            "Bill Ackman: portafoglio molto concentrato, attivista."),
    Manager(1656456, "Appaloosa", "discrezionale", "David Tepper: posizioni macro e tattiche."),
    Manager(1536411, "Duquesne Family Office", "discrezionale",
            "Stanley Druckenmiller: macro, cambia spesso posizioni."),
    Manager(2012383, "BlackRock", "flussi",
            "Il più grande gestore al mondo: soprattutto fondi indice (iShares). I movimenti "
            "seguono i flussi dei clienti, non un'opinione."),
    Manager(19617, "JPMorgan Chase", "flussi",
            "Banca: gestione per conto clienti e coperture. Movimenti poco informativi."),
]

TOP_HOLDINGS = 25  # largest positions shown per manager
TOP_MOVES = 15  # largest buys and sells (by dollar change) per manager
NEW_PCT = 0.25  # an increase of at least 25% of the shares counts as "aumentata"
MIN_WEIGHT = 0.002  # ignore moves smaller than 0.2% of the manager's portfolio

# Entry check, on the price paid estimated as the quarter's average close
NEAR_PAID = 0.10  # within +10% of the estimated price: still close to their entry
RAN_AWAY = 0.25  # more than +25%: most of the move is gone
BELOW_PAID = -0.15  # more than 15% below: they are losing, find out why first
REGIME_GOOD = 0.50  # P(regimes that favour the sector) at least 50%
REGIME_BAD = 0.20

# Quality (Buffett-style, from Yahoo for the prototype; FMP later)
MIN_ROE = 0.15
MAX_DEBT_EQUITY = 1.0  # debt / equity
MAX_FORWARD_PE = 30.0
