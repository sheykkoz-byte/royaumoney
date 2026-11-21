"""Tools the brain can call (plan, section 6). Every number Jarvis says must come from here.

Each tool has a JSON schema (Anthropic tool-use format: name, description, input_schema)
and a handler ``fn(session, **args) -> dict``. Results always carry their sources.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import catalog
from app.analysis.engine import run as run_analysis
from app.config import get_settings
from app.db import Observation, Prediction
from app.predictions import service as predictions
from app.predictions.spec import PredictionSpec
from app.predictions.stats import track_record as tr_summary
from app.store import load_frame

PERIODS = {"1m": 31, "3m": 92, "6m": 183, "1y": 365, "2y": 730, "5y": 1826, "10y": 3652,
           "max": 40000}
MAX_POINTS = 400


class ToolError(ValueError):
    """Bad input from the model: returned to it as an error, not raised to the user."""


def _parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _downsample(df: pd.DataFrame, n: int = MAX_POINTS) -> pd.DataFrame:
    if len(df) <= n:
        return df
    step = -(-len(df) // n)  # ceil
    keep = df.iloc[::step]
    if keep.index[-1] != df.index[-1]:
        keep = pd.concat([keep, df.iloc[[-1]]])
    return keep


# ---- query_serie --------------------------------------------------------------------------
def query_serie(session: Session, id: str, periodo: str = "1y", as_of: str | None = None) -> dict:
    try:
        sdef = catalog.get(id)
    except KeyError:
        raise ToolError(f"Serie sconosciuta: {id}. Usa elenca_serie per gli id validi.") from None
    if periodo not in PERIODS:
        raise ToolError(f"periodo deve essere uno di {', '.join(PERIODS)}")
    asof = _parse_date(as_of)
    end = asof or date.today()
    df = load_frame(session, id, as_of=asof, start=end - timedelta(days=PERIODS[periodo]))
    if df.empty:
        return {"id": id, "nome": sdef.name, "punti": [], "nota": "nessun dato nel periodo"}
    last, first = df.iloc[-1], df.iloc[0]
    change_pct = (last.value / first.value - 1) * 100 if first.value else None
    pts = _downsample(df)
    return {
        "id": id, "nome": sdef.name, "unita": sdef.unit, "fonte": sdef.source,
        "frequenza": sdef.frequency, "periodo": periodo,
        "ultimo": {"data": df.index[-1].date().isoformat(), "valore": round(float(last.value), 4),
                   "pubblicato": last.published_at.date().isoformat()},
        "primo": {"data": df.index[0].date().isoformat(), "valore": round(float(first.value), 4)},
        "massimo": {"data": df["value"].idxmax().date().isoformat(),
                    "valore": round(float(df["value"].max()), 4)},
        "minimo": {"data": df["value"].idxmin().date().isoformat(),
                   "valore": round(float(df["value"].min()), 4)},
        "variazione_periodo_pct": None if change_pct is None else round(change_pct, 2),
        "punti": [{"data": d.date().isoformat(), "valore": round(float(v), 4)}
                  for d, v in pts["value"].items()],
        "fonti": [f"{sdef.source}:{sdef.source_id or id}"],
    }


def elenca_serie(session: Session) -> dict:
    return {"serie": [{"id": s.id, "nome": s.name, "categoria": s.category, "unita": s.unit}
                      for s in catalog.SERIES]}


# ---- analysis (cached: it takes a few seconds and data change twice a day) -----------------
_analysis_cache: dict[tuple, dict] = {}


def analysis(session: Session, as_of: str | None = None) -> dict:
    data_version = session.scalar(select(func.max(Observation.id)))
    key = (as_of or date.today().isoformat(), data_version)
    if key not in _analysis_cache:
        _analysis_cache.clear()
        _analysis_cache[key] = run_analysis(
            session, _parse_date(as_of), has_fred_key=bool(get_settings().fred_api_key),
            with_history=True)
    return _analysis_cache[key]


def regime_attuale(session: Session, as_of: str | None = None) -> dict:
    a = analysis(session, as_of)
    r = a["regime"]
    if not r.get("available"):
        return {"disponibile": False}
    cur = (r.get("history") or {}).get("current") or {}
    assets = cur.get("assets", [])
    return {
        "as_of": a["as_of"], "regime": r["name"], "descrizione": r["description"],
        "assi": {k: {"punteggio": v["score"], "direzione": v["direction"],
                     "al_confine": v["borderline"],
                     "componenti": [{"nome": c["label"], "variazione": c["change"],
                                     "unita": c["change_unit"], "scalata": c["scaled"]}
                                    for c in v["components"]]}
                 for k, v in r["axes"].items()},
        "storico_regime": {
            "mesi": cur.get("months"),
            "meglio": [{"asset": x["name"], "vs_media_mese_pct": x["vs_all_months_pct"]}
                       for x in assets[:3]],
            "peggio": [{"asset": x["name"], "vs_media_mese_pct": x["vs_all_months_pct"]}
                       for x in assets[-3:]],
        },
        "note": a["notes"],
        "fonti": ["analisi RoyauMoney (FRED, Yahoo)"],
    }


def punteggio_convergenza(session: Session, scenario: str | None = None,
                          as_of: str | None = None) -> dict:
    a = analysis(session, as_of)
    scs = a["scenarios"]
    if scenario:
        scs = [s for s in scs if s["id"] == scenario]
        if not scs:
            raise ToolError("scenario deve essere uno di soft_landing, stagflation, "
                            "recession, reflation")

    def ev(e):
        return {"indicatore": e["label"], "voce": e["voice"], "misura": e["measure"],
                "valore": e["value"], "unita": e["unit"], "z": e["z"], "data": e["date"]}

    return {
        "as_of": a["as_of"], "verdetto": a["verdict"]["text"],
        "scenari": [{
            "id": s["id"], "nome": s["name"], "punteggio": s["score"],
            "voce_macro": s["macro_voice"], "voce_mercato": s["market_voice"],
            "convergenza": s["convergence"], "allarme_divergenza": s["divergence_alarm"],
            "a_favore": [ev(e) for e in s["supports"][:4]],
            "contro": [ev(e) for e in s["contradicts"][:4]],
        } for s in scs],
        "divergenze": a["divergences"],
        "fonti": ["analisi RoyauMoney (FRED, Yahoo)"],
    }


# ---- predictions -------------------------------------------------------------------------
def previsioni(session: Session, stato: str | None = None) -> dict:
    return {"previsioni": predictions.list_predictions(session, stato)}


def track_record(session: Session) -> dict:
    return tr_summary(session)


def registra_previsione(session: Session, previsione: dict, conferma: bool = False) -> dict:
    """Without ``conferma`` only validates and returns a preview: Jarvis must read it back to
    the user and register it only after an explicit yes."""
    spec_in = dict(previsione) | {"author": "jarvis"}
    try:
        spec = PredictionSpec.model_validate(spec_in)
    except Exception as e:
        raise ToolError(f"Previsione non valida: {e}") from None
    if not conferma:
        return {"anteprima": spec.model_dump(mode="json"), "registrata": False,
                "istruzione": "Leggi l'anteprima all'utente e registra solo dopo un sì esplicito."}
    p = predictions.create(session, spec, predictions.analysis_context(session))
    return {"registrata": True, "id": p.id, "impronta": p.spec_hash}


def previsione(session: Session, id: str) -> dict:
    p = session.get(Prediction, id)
    if p is None:
        raise ToolError(f"Previsione {id} non trovata")
    return predictions.view(session, p)


# ---- registry ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., dict]

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": self.input_schema}


AS_OF = {"type": "string", "description": "Data YYYY-MM-DD per un'analisi nel passato "
                                          "(solo dati già pubblicati). Ometti per oggi."}

TOOLS: list[Tool] = [
    Tool("query_serie",
         "Legge una serie storica dal database (valori, ultimo dato, massimo, minimo, "
         "variazione nel periodo). Usala per ogni numero su liquidità, macro, tassi, prezzi.",
         {"type": "object", "properties": {
             "id": {"type": "string", "description": "id della serie, es. M2SL, FED_NET_LIQ, GOLD"},
             "periodo": {"type": "string", "enum": list(PERIODS), "default": "1y"},
             "as_of": AS_OF},
          "required": ["id"]},
         query_serie),
    Tool("elenca_serie", "Elenco degli id delle serie disponibili con nome e unità.",
         {"type": "object", "properties": {}}, elenca_serie),
    Tool("regime_attuale",
         "Regime macro (liquidità × crescita/inflazione) con i componenti di ogni asse e come "
         "si sono comportati gli asset in questo regime in passato.",
         {"type": "object", "properties": {"as_of": AS_OF}}, regime_attuale),
    Tool("punteggio_convergenza",
         "Scenari (soft_landing, stagflation, recession, reflation): punteggio, voce macro, "
         "voce mercato, convergenza, allarme divergenza e i dati a favore e contro.",
         {"type": "object", "properties": {
             "scenario": {"type": "string",
                          "enum": ["soft_landing", "stagflation", "recession", "reflation"]},
             "as_of": AS_OF}},
         punteggio_convergenza),
    Tool("previsioni", "Elenco delle previsioni registrate con il loro stato.",
         {"type": "object", "properties": {
             "stato": {"type": "string",
                       "enum": ["aperta", "colpita", "invalidata", "scaduta", "annullata"]}}},
         previsioni),
    Tool("previsione", "Dettaglio di una previsione con obiettivi, invalidazioni e diario.",
         {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
         previsione),
    Tool("track_record", "Statistiche del registro: percentuale di successo, Brier score.",
         {"type": "object", "properties": {}}, track_record),
    Tool("registra_previsione",
         "Registra una previsione di Jarvis. Prima chiamala SENZA conferma per l'anteprima, "
         "leggila all'utente, e richiamala con conferma=true solo dopo un sì esplicito. "
         "Una previsione registrata non si può più modificare.",
         {"type": "object", "properties": {
             "previsione": {"type": "object", "description": "Campi come in PredictionSpec: "
                            "asset, title, direction, entry_price, probability, reasoning, "
                            "tags, targets, invalidations"},
             "conferma": {"type": "boolean", "default": False}},
          "required": ["previsione"]},
         registra_previsione),
]
TOOL_BY_NAME = {t.name: t for t in TOOLS}


def call(session: Session, name: str, args: dict) -> dict:
    """Run a tool. Errors are returned as data so the model can correct itself."""
    tool = TOOL_BY_NAME.get(name)
    if tool is None:
        return {"errore": f"strumento sconosciuto: {name}"}
    try:
        return tool.fn(session, **(args or {}))
    except ToolError as e:
        return {"errore": str(e)}
    except TypeError as e:
        return {"errore": f"argomenti non validi: {e}"}
