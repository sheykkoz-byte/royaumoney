"""Macro board of the trader's cockpit (frontend /cabina).

One JSON file, rebuilt every day from the database: for each metric the latest value, its
changes, a one-year sparkline and a traffic light with a one-line reading. It also carries
the regime, the convergence verdict and the open predictions for the Jarvis column.

The traffic lights are rules of thumb, written here in one place (RULES) and explained in
docs/cabina.md. They describe the situation; they are not trading signals.
"""

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd
from sqlalchemy.orm import Session

from app import catalog
from app.analysis.indicators import change_over
from app.jarvis import tools
from app.store import load_frame

State = Literal["verde", "giallo", "rosso", "neutro"]
Transform = Literal["level", "yoy", "mavg3_diff", "avg4"]

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "cabina" / "macro.json"
SPARK_POINTS = 120


@dataclass(frozen=True)
class Metric:
    id: str  # series id in the catalog
    section: str
    label: str
    unit: str
    decimals: int
    transform: Transform = "level"
    change: Literal["diff", "pct"] = "diff"  # how changes are shown
    tv: str | None = None  # TradingView symbol opened when the tile is clicked
    rule: str | None = None  # key in RULES


SECTIONS = ["Tassi", "Inflazione", "Dollaro e rischio", "Liquidità", "Crescita", "Materie prime"]

METRICS: list[Metric] = [
    Metric("DGS2", "Tassi", "Treasury 2 anni", "%", 2, tv="FRED:DGS2", rule="yield"),
    Metric("DGS10", "Tassi", "Treasury 10 anni", "%", 2, tv="FRED:DGS10", rule="yield"),
    Metric("T10Y2Y", "Tassi", "Curva 10 − 2 anni", "punti %", 2, tv="FRED:T10Y2Y",
           rule="curve"),
    Metric("DFF", "Tassi", "Fed funds", "%", 2, tv="FRED:DFF", rule="policy"),
    Metric("CPIAUCSL", "Inflazione", "Inflazione CPI (anno)", "%", 1, "yoy", tv="FRED:CPIAUCSL",
           rule="inflation"),
    Metric("PCEPILFE", "Inflazione", "Core PCE (anno)", "%", 1, "yoy", tv="FRED:PCEPILFE",
           rule="inflation"),
    Metric("T10YIE", "Inflazione", "Inflazione attesa 10 anni", "%", 2, tv="FRED:T10YIE",
           rule="breakeven"),
    Metric("DTWEXBGS", "Dollaro e rischio", "Dollaro (indice ampio)", "", 1, change="pct",
           tv="CAPITALCOM:DXY", rule="dollar"),
    Metric("VIX", "Dollaro e rischio", "VIX", "", 1, change="pct", tv="CAPITALCOM:VIX", rule="vix"),
    Metric("BAMLH0A0HYM2", "Dollaro e rischio", "Spread high yield", "punti %", 2,
           tv="FRED:BAMLH0A0HYM2", rule="hy"),
    Metric("DEXUSEU", "Dollaro e rischio", "EUR/USD", "", 4, change="pct", tv="FX:EURUSD"),
    Metric("DEXJPUS", "Dollaro e rischio", "USD/JPY", "", 2, change="pct", tv="FX:USDJPY"),
    Metric("FED_NET_LIQ", "Liquidità", "Liquidità netta Fed", "mld $", 0, change="pct",
           rule="liquidity"),
    Metric("M2SL", "Liquidità", "M2 (anno)", "%", 1, "yoy", tv="FRED:M2SL", rule="m2"),
    Metric("UNRATE", "Crescita", "Disoccupazione", "%", 1, tv="FRED:UNRATE", rule="sahm"),
    Metric("PAYEMS", "Crescita", "Payroll (media 3 mesi)", "mila/mese", 0, "mavg3_diff",
           tv="FRED:PAYEMS", rule="payrolls"),
    Metric("ICSA", "Crescita", "Richieste di sussidio (4 sett.)", "mila", 0, "avg4",
           change="pct", tv="FRED:ICSA", rule="claims"),
    Metric("COPPER_GOLD", "Crescita", "Rapporto rame/oro", "×1000", 2, change="pct",
           tv="OANDA:XCUUSD/OANDA:XAUUSD", rule="copper_gold"),
    Metric("CYCL_DEF", "Crescita", "Ciclici vs difensivi", "", 3, change="pct",
           rule="cycl_def"),
    Metric("GOLD", "Materie prime", "Oro", "$", 0, change="pct", tv="OANDA:XAUUSD"),
    Metric("OIL_WTI", "Materie prime", "Petrolio WTI", "$", 2, change="pct", tv="TVC:USOIL"),
    Metric("COPPER", "Materie prime", "Rame", "$", 3, change="pct", tv="OANDA:XCUUSD"),
]


# ---- series transforms ----------------------------------------------------------------------
def apply_transform(s: pd.Series, t: Transform) -> pd.Series:
    s = s.dropna()
    if t == "yoy":
        return change_over(s, 12, "pct").dropna()
    if t == "mavg3_diff":
        return s.diff().rolling(3).mean().dropna()
    if t == "avg4":
        return s.rolling(4).mean().dropna()
    return s


# ---- traffic lights -------------------------------------------------------------------------
# Each rule: (series as shown, its latest value) → (state, reading in Italian).
Rule = Callable[[pd.Series, float], tuple[State, str]]


def _chg(s: pd.Series, months: int, kind: Literal["diff", "pct"]) -> float | None:
    c = change_over(s, months, kind).dropna()
    return None if c.empty else float(c.iloc[-1])


def r_curve(s, v):
    last_year = s[s.index >= s.index[-1] - pd.DateOffset(months=12)]
    if v < 0:
        return "rosso", "Curva invertita: storicamente ha anticipato le recessioni."
    if last_year.min() < 0:
        return "giallo", ("Tornata positiva dopo l'inversione: fase che storicamente "
                          "precede la recessione.")
    if v < 0.25:
        return "giallo", "Curva piatta."
    return "verde", "Curva positiva: nessun segnale di recessione."


def r_yield(s, v):
    c = _chg(s, 1, "diff")
    if c is None:
        return "neutro", ""
    bp = round(c * 100)
    if bp >= 40:
        return "rosso", f"Rialzo rapido: +{bp} punti base in un mese."
    if bp >= 20:
        return "giallo", f"In rialzo: +{bp} punti base in un mese."
    if bp <= -40:
        return "giallo", f"Calo rapido: {bp} punti base in un mese."
    return "neutro", f"{bp:+d} punti base in un mese."


def r_policy(s, v):
    c = _chg(s, 3, "diff")
    if c is None or abs(c) < 0.1:
        return "neutro", "Fed ferma negli ultimi 3 mesi."
    return "neutro", ("Fed in taglio" if c < 0 else "Fed in rialzo") + \
        f": {round(c * 100):+d} punti base in 3 mesi."


def r_inflation(s, v):
    if v <= 2.5:
        return "verde", "Vicina all'obiettivo del 2% della Fed."
    if v <= 3.5:
        return "giallo", "Sopra l'obiettivo del 2%."
    return "rosso", "Inflazione alta."


def r_breakeven(s, v):
    if 1.8 <= v <= 2.6:
        return "verde", "Attese di inflazione ancorate."
    if 1.5 <= v <= 3.0:
        return "giallo", "Attese di inflazione " + ("in salita." if v > 2.6 else "basse.")
    return "rosso", "Attese di inflazione disancorate."


def r_dollar(s, v):
    c = _chg(s, 3, "pct")
    if c is None:
        return "neutro", ""
    if c > 3:
        return "rosso", (f"Dollaro forte ({c:+.1f}% in 3 mesi): vento contrario per oro "
                         "e materie prime.")
    if c > 1:
        return "giallo", f"Dollaro in rialzo ({c:+.1f}% in 3 mesi)."
    if c < -1:
        return "verde", (f"Dollaro in calo ({c:+.1f}% in 3 mesi): vento favorevole per oro "
                         "e materie prime.")
    return "neutro", f"Dollaro stabile ({c:+.1f}% in 3 mesi)."


def r_vix(s, v):
    if v < 16:
        return "verde", "Mercato calmo."
    if v < 25:
        return "giallo", "Tensione sull'azionario."
    return "rosso", "Paura sull'azionario."


def r_hy(s, v):
    if v < 4:
        return "verde", "Credito tranquillo."
    if v < 5.5:
        return "giallo", "Credito sotto osservazione."
    return "rosso", "Stress sul credito."


def r_liquidity(s, v):
    c = _chg(s, 3, "pct")
    if c is None:
        return "neutro", ""
    if c > 1:
        return "verde", f"Liquidità in aumento ({c:+.1f}% in 3 mesi)."
    if c < -3:
        return "rosso", f"Liquidità in calo ({c:+.1f}% in 3 mesi)."
    return "giallo", f"Liquidità ferma ({c:+.1f}% in 3 mesi)."


def r_m2(s, v):
    if v > 4:
        return "verde", "Massa monetaria in crescita."
    if v >= 0:
        return "giallo", "Massa monetaria in crescita lenta."
    return "rosso", "Massa monetaria in contrazione."


def r_sahm(s, v):
    m3 = s.rolling(3).mean().dropna()
    if len(m3) < 13:
        return "neutro", ""
    rise = float(m3.iloc[-1] - m3.iloc[-13:-1].min())
    if rise >= 0.5:
        return "rosso", f"Regola di Sahm scattata (+{rise:.2f}): segnale di recessione."
    if rise >= 0.3:
        return "giallo", f"Disoccupazione in salita (+{rise:.2f} dal minimo dell'ultimo anno)."
    return "verde", "Mercato del lavoro stabile."


def r_payrolls(s, v):
    if v > 150:
        return "verde", "Creazione di posti solida."
    if v > 50:
        return "giallo", "Creazione di posti in rallentamento."
    return "rosso", "Creazione di posti debole."


def r_claims(s, v):
    year = s[s.index >= s.index[-1] - pd.DateOffset(weeks=52)]
    rise = (v / float(year.min()) - 1) * 100
    if rise < 15:
        return "verde", "Licenziamenti bassi."
    if rise < 30:
        return "giallo", f"Richieste in salita ({rise:+.0f}% dal minimo dell'anno)."
    return "rosso", f"Richieste in forte salita ({rise:+.0f}% dal minimo dell'anno)."


def r_ratio(up: str, down: str):
    def rule(s, v):
        c = _chg(s, 3, "pct")
        if c is None:
            return "neutro", ""
        return ("verde", up) if c > 0 else ("giallo", down)
    return rule


RULES: dict[str, Rule] = {
    "curve": r_curve, "yield": r_yield, "policy": r_policy, "inflation": r_inflation,
    "breakeven": r_breakeven, "dollar": r_dollar, "vix": r_vix, "hy": r_hy,
    "liquidity": r_liquidity, "m2": r_m2, "sahm": r_sahm, "payrolls": r_payrolls,
    "claims": r_claims,
    "copper_gold": r_ratio("Il rame batte l'oro da 3 mesi: segnale di crescita.",
                           "L'oro batte il rame da 3 mesi: prudenza sulla crescita."),
    "cycl_def": r_ratio("I ciclici battono i difensivi da 3 mesi: mercato propenso al rischio.",
                        "I difensivi battono i ciclici da 3 mesi: mercato prudente."),
}


# ---- one tile -------------------------------------------------------------------------------
def _num(x: float | None, nd: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), nd)


def sparkline(s: pd.Series, n: int = SPARK_POINTS) -> list[list]:
    year = s[s.index >= s.index[-1] - pd.DateOffset(years=1)]
    if len(year) > n:
        step = len(year) / n
        idx = sorted({int(i * step) for i in range(n)} | {len(year) - 1})
        year = year.iloc[idx]
    return [[d.date().isoformat(), _num(v)] for d, v in year.items()]


def tile(m: Metric, s: pd.Series) -> dict:
    s = apply_transform(s, m.transform)
    if s.empty:
        return {"id": m.id, "label": m.label, "section": m.section, "errore": "nessun dato"}
    v = float(s.iloc[-1])
    sdef = catalog.get(m.id)
    state, reading = RULES[m.rule](s, v) if m.rule else ("neutro", "")
    changes = {}
    if sdef.frequency == "daily" and m.transform == "level":
        prev = s.iloc[-2] if len(s) > 1 else None
        changes["1g"] = _num(v - prev if m.change == "diff" else (v / prev - 1) * 100) \
            if prev is not None else None
    for key, months in (("1m", 1), ("1a", 12)):
        changes[key] = _num(_chg(s, months, m.change))
    return {
        "id": m.id, "label": m.label, "section": m.section, "unit": m.unit,
        "decimals": m.decimals, "change_kind": m.change, "tv": m.tv,
        "value": _num(v), "date": s.index[-1].date().isoformat(), "changes": changes,
        "state": state, "reading": reading, "spark": sparkline(s),
        "source": sdef.source if hasattr(sdef, "source") else None,
    }


def build(session: Session, today: date | None = None) -> dict:
    today = today or date.today()
    start = today - timedelta(days=3 * 366)
    tiles = []
    for m in METRICS:
        df = load_frame(session, m.id, start=start)
        tiles.append(tile(m, df["value"]))
    reg = tools.regime_attuale(session)
    conv = tools.punteggio_convergenza(session)
    prev = [p for p in tools.previsioni(session)["previsioni"] if p["status"] == "aperta"]
    return {
        "generato": datetime.now().isoformat(timespec="minutes"),
        "sezioni": SECTIONS,
        "metriche": tiles,
        "regime": {k: reg.get(k) for k in ("as_of", "regime", "descrizione", "assi")},
        "convergenza": {"as_of": conv.get("as_of"), "verdetto": conv.get("verdetto"),
                        "scenari": [{k: x.get(k) for k in (
                            "id", "nome", "punteggio", "voce_macro", "voce_mercato",
                            "convergenza", "allarme_divergenza")}
                            for x in conv.get("scenari", [])],
                        "divergenze": conv.get("divergenze", [])},
        "previsioni": [{k: p.get(k) for k in ("id", "title", "status", "targets", "invalidations",
                                               "last_bar_date")} for p in prev],
    }


def export(session: Session, out: Path = OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(session), ensure_ascii=False, separators=(",", ":"),
                              default=str), encoding="utf-8")
    return out
