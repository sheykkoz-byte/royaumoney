"""Scene director (plan, section 7.2).

The brain returns a *script*: what Jarvis says (``parlato``) and the scene actions to fire
on specific words (``scene``). The director:

1. validates the actions;
2. finds where each cue word is spoken (character index in the text, in speaking order);
3. attaches the real data each action needs (series points, regime, scenarios…), so the
   frontend never shows a number that did not come from the database.

Turning a character index into a time is done where the audio is: with ElevenLabs the
character-level timestamps, with the browser voice its ``boundary`` events, otherwise an
estimate (``estimate_times``).
"""

import math
import unicodedata
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.jarvis import tools

Action = Literal[
    "apri_grafico",  # id, periodo, effetto
    "evidenzia_tratto",  # su, da, a
    "sovrapponi",  # id, su, sfasamento_mesi
    "mostra_livello",  # su, valore, etichetta
    "mostra_valore",  # etichetta, valore, unita
    "mostra_correlazione",  # id_a, id_b, sfasamento_mesi, periodo
    "mostra_regime",
    "mostra_scenari",  # scenario (optional)
    "mostra_previsione",  # id
    "chiudi",  # su (optional: all)
]


class Cue(BaseModel):
    model_config = ConfigDict(extra="allow")  # action parameters live next to the keys

    alla_parola: str = Field(min_length=1)
    azione: Action


class Script(BaseModel):
    parlato: str = Field(min_length=1)
    scene: list[Cue] = []


# ---- alignment -----------------------------------------------------------------------------
def _fold(ch: str) -> str:
    """One char → one lowercase base char (accents removed), so indices stay aligned."""
    base = unicodedata.normalize("NFKD", ch)[0] if ch else ch
    return base.lower() if base.isalnum() else " "


def fold(text: str) -> str:
    return "".join(_fold(c) for c in text)


def find_word(text_folded: str, word: str, start: int = 0) -> int | None:
    """Index of the first word (or phrase) in ``text_folded`` starting with ``word``,
    at a word boundary, from ``start``."""
    w = " ".join(fold(word).split())
    if not w:
        return None
    i = start
    while True:
        i = text_folded.find(w, i)
        if i < 0:
            return None
        if i == 0 or text_folded[i - 1] == " ":
            return i
        i += 1


def align(script: Script) -> list[dict]:
    """Character index of each cue, assuming cues follow the speaking order."""
    folded = fold(script.parlato)
    out, cursor = [], 0
    for cue in script.scene:
        idx = find_word(folded, cue.alla_parola, cursor)
        warning = None
        if idx is None:
            idx = find_word(folded, cue.alla_parola, 0)
            warning = "parola trovata prima della precedente" if idx is not None else None
        if idx is None:
            idx = cursor
            warning = f"parola «{cue.alla_parola}» non presente nel parlato"
        else:
            cursor = idx + 1
        out.append({"char_index": idx, "warning": warning})
    return out


def estimate_times(text: str, char_indices: list[int], chars_per_second: float = 14.0) -> list:
    """Fallback timing when the voice gives no timestamps (Italian ≈ 14 chars/s)."""
    return [round(i / chars_per_second, 2) for i in char_indices]


# ---- data resolution ------------------------------------------------------------------------
def _monthly_changes(points: list[dict]) -> "np.ndarray | None":
    import pandas as pd

    if len(points) < 3:
        return None
    s = pd.Series([p["valore"] for p in points],
                  index=pd.to_datetime([p["data"] for p in points]))
    return s.resample("ME").last().pct_change().dropna()


def correlation(session: Session, id_a: str, id_b: str, lag_months: int = 0,
                periodo: str = "5y") -> dict:
    """Correlation of monthly % changes, with ``id_b`` shifted ``lag_months`` later."""
    a = tools.query_serie(session, id_a, "max" if periodo == "max" else periodo)
    b = tools.query_serie(session, id_b, "max" if periodo == "max" else periodo)
    ca, cb = _monthly_changes(a["punti"]), _monthly_changes(b["punti"])
    if ca is None or cb is None:
        return {"valore": None, "nota": "dati insufficienti"}
    j = ca.to_frame("a").join(cb.shift(-lag_months).to_frame("b"), how="inner").dropna()
    if len(j) < 12:
        return {"valore": None, "mesi": len(j), "nota": "meno di 12 mesi in comune"}
    r = float(np.corrcoef(j["a"], j["b"])[0, 1])
    return {"valore": None if math.isnan(r) else round(r, 2), "mesi": int(len(j)),
            "metodo": "correlazione delle variazioni mensili %",
            "sfasamento_mesi": lag_months, "fonti": a["fonti"] + b["fonti"]}


def resolve_data(session: Session, cue: Cue) -> dict:
    p = cue.model_extra or {}
    a = cue.azione
    try:
        if a in ("apri_grafico", "sovrapponi"):
            return {"serie": tools.query_serie(session, p["id"], p.get("periodo", "1y"))}
        if a == "mostra_correlazione":
            return {"correlazione": correlation(session, p["id_a"], p["id_b"],
                                                int(p.get("sfasamento_mesi", 0)),
                                                p.get("periodo", "5y"))}
        if a == "mostra_regime":
            return {"regime": tools.regime_attuale(session)}
        if a == "mostra_scenari":
            return {"scenari": tools.punteggio_convergenza(session, p.get("scenario"))}
        if a == "mostra_previsione":
            return {"previsione": tools.previsione(session, p["id"])}
    except (KeyError, tools.ToolError) as e:
        return {"errore": f"{a}: {e}"}
    return {}


def direct(session: Session, script: Script | dict) -> dict:
    """Validate, align and attach data. The result is what the frontend plays."""
    if isinstance(script, dict):
        script = Script.model_validate(script)
    positions = align(script)
    cues = []
    for cue, pos in zip(script.scene, positions, strict=True):
        cues.append({"alla_parola": cue.alla_parola, "azione": cue.azione,
                     "parametri": cue.model_extra or {}, **pos,
                     "dati": resolve_data(session, cue)})
    return {
        "parlato": script.parlato,
        "scene": cues,
        "tempi_stimati": estimate_times(script.parlato, [c["char_index"] for c in cues]),
    }
