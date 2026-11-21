"""Jarvis's brain with Claude (plan, section 6).

Claude answers with the fixed method (liquidity → regime → market confirmation → net
scenario with direction, targets, timing and invalidation), reads every number through the
tools, and returns a *script* — what Jarvis says and the scene actions — as JSON constrained
by a schema. The scene director then aligns it with the voice and attaches the data.
"""

import json
import logging
import math
from datetime import date

import anthropic
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jarvis import tools
from app.jarvis.scene import Script

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
HISTORY_TURNS = 4
VALUE_TOLERANCE = 0.005  # a number in a cue must match a tool result within 0.5%

SYSTEM = """Sei Jarvis, l'analista vocale di RoyauMoney (intelligence sugli investimenti per \
i marocchini e la diaspora). Rispondi SEMPRE in italiano, a voce: frasi brevi e naturali, \
niente elenchi, niente markdown, numeri scritti come si leggono ("3.533 dollari", "4,1%").

Metodo fisso, in quest'ordine, quando la domanda riguarda mercati o macro:
1. liquidità (liquidità netta Fed, M2, banche centrali);
2. regime macro (regime_attuale);
3. conferma del mercato: la voce della macro e quella del mercato concordano o divergono \
(punteggio_convergenza). Una divergenza è il segnale più prezioso: dillo chiaramente;
4. scenario netto con direzione, obiettivi, tempistica e livello di invalidazione.
Niente risposte vaghe. Se i dati sono contraddittori, dillo e spiega perché.

Regole sui numeri: ogni numero che pronunci deve venire da uno strumento chiamato in questa \
conversazione, mai dalla memoria. Se un dato non c'è, dillo. Cita la data dell'ultimo dato \
quando conta.

Previsioni: per registrarne una chiama registra_previsione senza conferma, leggi l'anteprima \
all'utente e registra (conferma=true) solo dopo un sì esplicito nella conversazione.

Natura del servizio: è ricerca e informazione finanziaria generale, non consulenza \
personalizzata. Non dire all'utente cosa comprare o vendere con i suoi soldi; descrivi \
scenari, livelli e rischi.

Formato della risposta finale (JSON secondo lo schema):
- "parlato": il testo che Jarvis pronuncia, 40-130 parole.
- "scene": azioni sull'interfaccia, ognuna legata a una parola del parlato ("alla_parola" \
deve comparire nel parlato, nell'ordine in cui la dici). Azioni:
  apri_grafico {id, periodo: 1m|3m|6m|1y|2y|5y|10y|max} · sovrapponi {id, su} · \
mostra_livello {su, valore, etichetta} · evidenzia_tratto {su, da, a (YYYY-MM-DD)} · \
mostra_valore {etichetta, valore, unita} · mostra_correlazione {id_a, id_b, sfasamento_mesi} · \
mostra_regime · mostra_scenari {scenario?} · mostra_previsione {id} · chiudi {su?}.
  Gli id delle serie sono quelli di elenca_serie (es. GOLD, M2SL, FED_NET_LIQ, UNRATE). \
"su" è l'id del grafico già aperto. I valori di mostra_livello e mostra_valore devono essere \
numeri restituiti da uno strumento (o livelli della previsione registrata). \
Usa 1-4 azioni: poche, ben sincronizzate con le parole."""

CUE_PROPS = {
    "alla_parola": {"type": "string"},
    "azione": {"type": "string", "enum": [
        "apri_grafico", "evidenzia_tratto", "sovrapponi", "mostra_livello", "mostra_valore",
        "mostra_correlazione", "mostra_regime", "mostra_scenari", "mostra_previsione",
        "chiudi"]},
    "id": {"type": "string"}, "periodo": {"type": "string"}, "su": {"type": "string"},
    "da": {"type": "string"}, "a": {"type": "string"}, "valore": {"type": "number"},
    "etichetta": {"type": "string"}, "unita": {"type": "string"},
    "id_a": {"type": "string"}, "id_b": {"type": "string"},
    "sfasamento_mesi": {"type": "integer"}, "scenario": {"type": "string"},
}
SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "parlato": {"type": "string"},
        "scene": {"type": "array", "items": {
            "type": "object", "properties": CUE_PROPS,
            "required": ["alla_parola", "azione"], "additionalProperties": False}},
    },
    "required": ["parlato", "scene"],
    "additionalProperties": False,
}


class BrainError(RuntimeError):
    pass


def enabled() -> bool:
    s = get_settings()
    if s.brain == "demo":
        return False
    return bool(s.anthropic_api_key)


def _numbers(obj, out: list[float]) -> list[float]:
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int | float) and math.isfinite(obj):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list | tuple):
        for v in obj:
            _numbers(v, out)
    return out


def check_cue_numbers(script: dict, seen: list[float]) -> tuple[dict, list[str]]:
    """Drop cues whose value did not come from a tool result (plan: no invented numbers)."""
    kept, dropped = [], []
    for cue in script.get("scene", []):
        v = cue.get("valore")
        if cue.get("azione") in ("mostra_livello", "mostra_valore") and v is not None:
            ok = any(abs(v - n) <= VALUE_TOLERANCE * max(1.0, abs(n)) for n in seen)
            if not ok:
                dropped.append(f"{cue['azione']} {v}: numero non restituito da uno strumento")
                continue
        kept.append(cue)
    return {**script, "scene": kept}, dropped


def _client() -> anthropic.Anthropic:
    s = get_settings()
    return anthropic.Anthropic(api_key=s.anthropic_api_key or None, timeout=90, max_retries=2)


def answer(session: Session, question: str, history: list[dict] | None = None,
           client=None) -> dict:
    """Ask Claude. ``history``: earlier turns [{"domanda", "parlato"}], most recent last."""
    s = get_settings()
    client = client or _client()
    messages: list = []
    for h in (history or [])[-HISTORY_TURNS:]:
        messages.append({"role": "user", "content": h["domanda"]})
        messages.append({"role": "assistant", "content": h["parlato"]})
    today = date.today().isoformat()
    messages.append({"role": "user", "content": f"[Oggi è il {today}]\n{question}"})

    tool_schemas = [t.schema() for t in tools.TOOLS]
    seen: list[float] = []
    called: list[str] = []
    response = None
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.beta.messages.create(
            model=s.jarvis_model,
            max_tokens=16000,
            # tools → system render first: the cache breakpoint on the system block keeps
            # both cached across questions (only the messages change)
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=tool_schemas,
            messages=messages,
            output_config={"effort": s.jarvis_effort,
                           "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise BrainError("Claude ha rifiutato la richiesta")
        if response.stop_reason == "max_tokens":
            raise BrainError("risposta troncata (max_tokens)")
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        uses = [b for b in response.content if b.type == "tool_use"]
        if not uses:
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for u in uses:
            out = tools.call(session, u.name, u.input if isinstance(u.input, dict) else {})
            called.append(u.name)
            _numbers(out, seen)
            results.append({"type": "tool_result", "tool_use_id": u.id,
                            "content": json.dumps(out, ensure_ascii=False, default=str),
                            **({"is_error": True} if "errore" in out else {})})
        messages.append({"role": "user", "content": results})
    else:
        raise BrainError("troppi passaggi di strumenti senza una risposta")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise BrainError("nessuna risposta testuale")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise BrainError(f"JSON non valido: {e}") from None
    script, dropped = check_cue_numbers(raw, seen)
    Script.model_validate(script)
    usage = getattr(response, "usage", None)
    return script | {
        "modalita": "claude",
        "intento": None,
        "strumenti": called,
        "scene_scartate": dropped,
        "modello": getattr(response, "model", s.jarvis_model),
        "token": None if usage is None else {
            "input": getattr(usage, "input_tokens", None),
            "output": getattr(usage, "output_tokens", None),
            "cache_letti": getattr(usage, "cache_read_input_tokens", None),
        },
    }
