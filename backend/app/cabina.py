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

from app import cabina_guide, catalog
from app.analysis.indicators import change_over
from app.jarvis import tools
from app.store import load_frame

State = Literal["verde", "giallo", "rosso", "neutro"]
Transform = Literal["level", "yoy", "mavg3_diff", "avg4"]

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "cabina" / "macro.json"
SPARK_POINTS = 120
HISTORY_POINTS = 160


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
    Metric("VIX", "Dollaro e rischio", "VIX", "", 1, change="pct", tv="FRED:VIXCLS", rule="vix"),
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


def _it(x: float) -> str:
    """Signed number with one decimal, Italian style: +2,9."""
    return f"{x:+.1f}".replace(".", ",")


def _it2(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


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
        return "rosso", (f"Dollaro forte ({_it(c)}% in 3 mesi): vento contrario per oro "
                         "e materie prime.")
    if c > 1:
        return "giallo", f"Dollaro in rialzo ({_it(c)}% in 3 mesi)."
    if c < -1:
        return "verde", (f"Dollaro in calo ({_it(c)}% in 3 mesi): vento favorevole per oro "
                         "e materie prime.")
    return "neutro", f"Dollaro stabile ({_it(c)}% in 3 mesi)."


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
        return "verde", f"Liquidità in aumento ({_it(c)}% in 3 mesi)."
    if c < -3:
        return "rosso", f"Liquidità in calo ({_it(c)}% in 3 mesi)."
    return "giallo", f"Liquidità ferma ({_it(c)}% in 3 mesi)."


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
        return "rosso", f"Regola di Sahm scattata (+{_it2(rise)}): segnale di recessione."
    if rise >= 0.3:
        return "giallo", f"Disoccupazione in salita (+{_it2(rise)} dal minimo dell'ultimo anno)."
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


# ---- scales for the explanation window ------------------------------------------------------
# For each rule: what the traffic light measures, its unit, a display range and the zones
# (same thresholds as RULES above; a test checks that the zone at the measured value has the
# tile's colour).
def _zones(*edges_states: tuple[float | None, float | None, State]) -> list[dict]:
    return [{"da": a, "a": b, "stato": st} for a, b, st in edges_states]


def _sahm_rise(s: pd.Series) -> float | None:
    m3 = s.rolling(3).mean().dropna()
    return None if len(m3) < 13 else float(m3.iloc[-1] - m3.iloc[-13:-1].min())


def _claims_rise(s: pd.Series, v: float) -> float:
    year = s[s.index >= s.index[-1] - pd.DateOffset(weeks=52)]
    return (v / float(year.min()) - 1) * 100


def scale(rule: str | None, s: pd.Series, v: float) -> dict | None:
    if rule is None or rule == "policy":
        return None
    if rule == "curve":
        meas, label, unit, lo, hi = v, "livello della curva", "punti %", -1.5, 2.5
        zones = _zones((None, 0, "rosso"), (0, 0.25, "giallo"), (0.25, None, "verde"))
    elif rule == "yield":
        c = _chg(s, 1, "diff")
        meas, label, unit, lo, hi = (None if c is None else c * 100), "variazione in un mese", \
            "punti base", -80, 80
        zones = _zones((None, -40, "giallo"), (-40, 20, "neutro"), (20, 40, "giallo"),
                       (40, None, "rosso"))
    elif rule == "inflation":
        meas, label, unit, lo, hi = v, "inflazione su un anno", "%", 0, 8
        zones = _zones((None, 2.5, "verde"), (2.5, 3.5, "giallo"), (3.5, None, "rosso"))
    elif rule == "breakeven":
        meas, label, unit, lo, hi = v, "inflazione attesa", "%", 1, 3.5
        zones = _zones((None, 1.5, "rosso"), (1.5, 1.8, "giallo"), (1.8, 2.6, "verde"),
                       (2.6, 3.0, "giallo"), (3.0, None, "rosso"))
    elif rule == "dollar":
        meas, label, unit, lo, hi = _chg(s, 3, "pct"), "variazione in 3 mesi", "%", -6, 6
        zones = _zones((None, -1, "verde"), (-1, 1, "neutro"), (1, 3, "giallo"),
                       (3, None, "rosso"))
    elif rule == "vix":
        meas, label, unit, lo, hi = v, "livello del VIX", "", 9, 50
        zones = _zones((None, 16, "verde"), (16, 25, "giallo"), (25, None, "rosso"))
    elif rule == "hy":
        meas, label, unit, lo, hi = v, "spread", "punti %", 2, 10
        zones = _zones((None, 4, "verde"), (4, 5.5, "giallo"), (5.5, None, "rosso"))
    elif rule == "liquidity":
        meas, label, unit, lo, hi = _chg(s, 3, "pct"), "variazione in 3 mesi", "%", -8, 8
        zones = _zones((None, -3, "rosso"), (-3, 1, "giallo"), (1, None, "verde"))
    elif rule == "m2":
        meas, label, unit, lo, hi = v, "crescita su un anno", "%", -5, 12
        zones = _zones((None, 0, "rosso"), (0, 4, "giallo"), (4, None, "verde"))
    elif rule == "sahm":
        meas, label, unit, lo, hi = _sahm_rise(s), "salita dal minimo dell'anno (media 3 mesi)", \
            "punti", 0, 1.5
        zones = _zones((None, 0.3, "verde"), (0.3, 0.5, "giallo"), (0.5, None, "rosso"))
    elif rule == "payrolls":
        meas, label, unit, lo, hi = v, "posti al mese (media 3 mesi)", "mila", -100, 400
        zones = _zones((None, 50, "rosso"), (50, 150, "giallo"), (150, None, "verde"))
    elif rule == "claims":
        meas, label, unit, lo, hi = _claims_rise(s, v), "salita dal minimo dell'anno", "%", 0, 60
        zones = _zones((None, 15, "verde"), (15, 30, "giallo"), (30, None, "rosso"))
    elif rule in ("copper_gold", "cycl_def"):
        meas, label, unit, lo, hi = _chg(s, 3, "pct"), "variazione in 3 mesi", "%", -15, 15
        zones = _zones((None, 0, "giallo"), (0, None, "verde"))
    else:
        return None
    if meas is None:
        return None
    return {"misura": label, "unita": unit, "valore": _num(meas), "min": lo, "max": hi,
            "zone": zones}


# ---- one tile -------------------------------------------------------------------------------
def _num(x: float | None, nd: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), nd)


def sparkline(s: pd.Series, n: int = SPARK_POINTS, years: int = 1) -> list[list]:
    year = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
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
    sc = scale(m.rule, s, v)
    if sc is not None:
        meas = sc["valore"]
        zone = next((z for z in sc["zone"] if (z["da"] is None or meas >= z["da"])
                     and (z["a"] is None or meas < z["a"])), None)
        if zone is not None and zone["stato"] != state:
            # The light also looks at history (e.g. a curve that was inverted this year)
            sc["nota"] = f"Il semaforo è {state} perché: {reading[0].lower()}{reading[1:]}"
    return {
        "id": m.id, "label": m.label, "section": m.section, "unit": m.unit,
        "decimals": m.decimals, "change_kind": m.change, "tv": m.tv,
        "value": _num(v), "date": s.index[-1].date().isoformat(), "changes": changes,
        "state": state, "reading": reading, "spark": sparkline(s),
        "scala": sc,
        # longer history for the explanation window's 1/3/5-year switch
        "storico": {"3a": sparkline(s, HISTORY_POINTS, 3), "5a": sparkline(s, HISTORY_POINTS, 5)},
        "source": sdef.source if hasattr(sdef, "source") else None,
    }


def build(session: Session, today: date | None = None) -> dict:
    today = today or date.today()
    start = today - timedelta(days=6 * 366)  # 5 years shown + 1 for year-on-year transforms
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
        "spiegazioni": cabina_guide.explain(SECTIONS, tiles),
        "guida_semafori": cabina_guide.TRAFFIC_LIGHTS,
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
