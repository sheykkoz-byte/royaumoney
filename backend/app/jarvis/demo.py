"""Demo brain: no AI, fixed intents, real numbers.

It exists so the whole chain (question → tools → script → scene director → voice and
charts) works before the Anthropic key is configured. Every number comes from a tool call.
The answers say clearly what they are; the Claude brain replaces this in phase 4.
"""

import logging
import re

from sqlalchemy.orm import Session

from app.jarvis import tools

log = logging.getLogger(__name__)


def it_num(x: float | None, nd: int = 0) -> str:
    """Italian formatting: 3537.87 → '3.537,87'."""
    if x is None:
        return "n.d."
    s = f"{x:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def it_date(iso: str) -> str:
    months = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
              "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {months[m - 1]} {y}"


def it_month(iso: str) -> str:
    return it_date(iso).split(" ", 1)[1]


def _dir(score: float | None, up: str, down: str) -> str:
    if score is None:
        return "non disponibile"
    return up if score > 0 else down


# ---- intents ------------------------------------------------------------------------------
def gold(s: Session) -> dict:
    y = tools.query_serie(s, "GOLD", "1y")
    ath = tools.query_serie(s, "GOLD", "max")["massimo"]
    last = y["ultimo"]
    from_ath = (last["valore"] / ath["valore"] - 1) * 100
    text = (f"L'oro, sul future COMEX, ha chiuso a {it_num(last['valore'])} dollari il "
            f"{it_date(last['data'])}: il {it_num(abs(from_ath), 1)}% sotto il massimo storico "
            f"di chiusura, {it_num(ath['valore'])} del {it_date(ath['data'])}. "
            f"Nell'ultimo anno la variazione è del {it_num(y['variazione_periodo_pct'], 1)}%. "
            "Il tuo scenario, la previsione P-0002, cerca prima il rimbalzo verso 3.720, "
            "poi la discesa verso 3.420 dopo la Fed, e da gennaio la ripartenza verso 3.900.")
    return {"parlato": text, "scene": [
        {"alla_parola": "oro", "azione": "apri_grafico", "id": "GOLD", "periodo": "1y",
         "effetto": "particelle"},
        {"alla_parola": "massimo", "azione": "mostra_livello", "su": "GOLD",
         "valore": ath["valore"], "etichetta": f"Max chiusura {it_num(ath['valore'])}"},
        {"alla_parola": "rimbalzo", "azione": "mostra_livello", "su": "GOLD", "valore": 3720,
         "etichetta": "Fase 1 · 3.720"},
        {"alla_parola": "discesa", "azione": "mostra_livello", "su": "GOLD", "valore": 3420,
         "etichetta": "Fase 2 · 3.420"},
        {"alla_parola": "ripartenza", "azione": "mostra_previsione", "id": "P-0002"},
    ]}


def regime(s: Session) -> dict:
    r = tools.regime_attuale(s)
    if not r.get("assi"):
        return no_data(s)
    a = r["assi"]
    st = r["storico_regime"]
    best = ", ".join(x["asset"] for x in st["meglio"][:2])
    worst = ", ".join(x["asset"] for x in st["peggio"][-2:])
    confine = [k for k, v in a.items() if v["al_confine"]]
    text = (f"Il regime attuale è: {r['regime']}. "
            f"La liquidità è {_dir(a['liquidity']['punteggio'], 'in espansione', 'in contrazione')}"
            f", la crescita {_dir(a['growth']['punteggio'], 'accelera', 'rallenta')}, "
            f"l'inflazione {_dir(a['inflation']['punteggio'], 'sale', 'scende')}. "
            + ("L'asse della liquidità è al confine, quindi il quadro può cambiare in fretta. "
               if "liquidity" in confine else "")
            + f"Nei {st['mesi']} mesi passati in questo regime hanno fatto meglio della media "
              f"{best}, peggio {worst}.")
    return {"parlato": text, "scene": [
        {"alla_parola": "regime", "azione": "mostra_regime"},
    ]}


def scenarios(s: Session) -> dict:
    c = tools.punteggio_convergenza(s)
    top = c["scenari"][0]
    text = (f"{c['verdetto']} "
            f"Per {top['nome'].lower()} la voce della macro vale {it_num(top['voce_macro'], 2)} "
            f"e quella del mercato {it_num(top['voce_mercato'], 2)}, "
            f"con una convergenza di {top['convergenza']}. ")
    if c["divergenze"]:
        d = c["divergenze"][0]
        text += f"Attenzione: divergenza su {d['name'].lower()}. {d['text']}"
    else:
        text += "Nessun allarme di divergenza: le due voci non si separano più del solito."
    return {"parlato": text, "scene": [
        {"alla_parola": "scenario", "azione": "mostra_scenari"},
    ]}


def liquidity(s: Session) -> dict:
    f = tools.query_serie(s, "FED_NET_LIQ", "2y")
    m2 = tools.query_serie(s, "M2SL", "2y")
    from app.jarvis.scene import correlation

    corr = correlation(s, "M2SL", "GOLD", lag_months=3, periodo="10y")
    r = corr.get("valore")
    text = (f"La liquidità netta della Fed è a {it_num(f['ultimo']['valore'])} miliardi di "
            f"dollari, {it_num(f['variazione_periodo_pct'], 1)}% in due anni. "
            f"La M2 è a {it_num(m2['ultimo']['valore'])} miliardi a "
            f"{it_month(m2['ultimo']['data'])}, {it_num(m2['variazione_periodo_pct'], 1)}% "
            "in due anni. ")
    if r is not None:
        text += (f"Negli ultimi dieci anni la correlazione tra le variazioni mensili della M2 "
                 f"e quelle dell'oro tre mesi dopo è {it_num(r, 2)}: "
                 + ("un legame debole, da non usare da solo." if abs(r) < 0.3 else
                    "un legame da tenere d'occhio."))
    return {"parlato": text, "scene": [
        {"alla_parola": "liquidità", "azione": "apri_grafico", "id": "FED_NET_LIQ",
         "periodo": "2y"},
        {"alla_parola": "M2", "azione": "sovrapponi", "id": "M2SL", "su": "FED_NET_LIQ",
         "periodo": "2y"},
        {"alla_parola": "correlazione", "azione": "mostra_correlazione", "id_a": "M2SL",
         "id_b": "GOLD", "sfasamento_mesi": 3, "periodo": "10y"},
    ]}


def labour(s: Session) -> dict:
    u = tools.query_serie(s, "UNRATE", "2y")
    p = tools.query_serie(s, "PAYEMS", "6m")["punti"]
    ic = tools.query_serie(s, "ICSA", "3m")["ultimo"]
    cc = tools.query_serie(s, "CCSA", "3m")["ultimo"]
    gain = p[-1]["valore"] - p[-2]["valore"] if len(p) >= 2 else None
    text = (f"La disoccupazione è al {it_num(u['ultimo']['valore'], 1)}% "
            f"a {it_month(u['ultimo']['data'])}. "
            f"Nell'ultimo mese i posti di lavoro sono variati di {it_num(gain)} mila. "
            f"Le richieste iniziali di sussidio sono {it_num(ic['valore'])} mila, "
            f"le continuative {it_num(cc['valore'] / 1000, 3)} milioni.")
    return {"parlato": text, "scene": [
        {"alla_parola": "disoccupazione", "azione": "apri_grafico", "id": "UNRATE",
         "periodo": "2y"},
        {"alla_parola": "posti", "azione": "mostra_valore", "etichetta": "Payroll ultimo mese",
         "valore": gain, "unita": "mila"},
        {"alla_parola": "richieste", "azione": "apri_grafico", "id": "ICSA", "periodo": "1y"},
    ]}


def predictions_intent(s: Session) -> dict:
    ps = [p for p in tools.previsioni(s)["previsioni"] if p["status"] == "aperta"]
    tr = tools.track_record(s)["overall"]
    if not ps:
        return {"parlato": "Non ci sono previsioni aperte nel registro.", "scene": []}
    p = ps[0]
    active = next((t for t in p["targets"] if t.get("status") == "attiva"), None)
    n, o = tr["total"], tr["open"]
    text = ((f"Nel registro c'è {n} previsione" if n == 1 else
             f"Nel registro ci sono {n} previsioni")
            + (f", {o} aperta. " if o == 1 else f", {o} aperte. ")
            + f"La previsione {p['id']}: {p['title']}. ")
    if p.get("last_bar_date"):
        text += f"Ultimo prezzo verificato il {it_date(p['last_bar_date'])}. "
    else:
        text += "Non ha ancora prezzi verificati. "
    if active:
        text += (f"L'obiettivo attivo è {active['label'].lower()}: "
                 f"{it_num(active['trigger'])} entro il {it_date(active['deadline'])}.")
    return {"parlato": text, "scene": [
        {"alla_parola": "previsione", "azione": "mostra_previsione", "id": p["id"]},
    ]}


def greeting(s: Session) -> dict:
    return {"parlato": "Ciao Yousef. Sono operativo in modalità dimostrativa: chiedimi "
                       "dell'oro, del regime, degli scenari, della liquidità, del lavoro o "
                       "delle previsioni.", "scene": []}


def fallback(s: Session) -> dict:
    return {"parlato": "In modalità dimostrativa conosco l'oro, il regime macro, gli scenari "
                       "e la convergenza, la liquidità, il lavoro e il registro delle "
                       "previsioni. Quando sarà attivo il cervello Claude potrò rispondere "
                       "anche alle altre domande.",
            "scene": []}


def no_data(s: Session) -> dict:
    """The database lacks what the answer needs: say so, never make numbers up."""
    return {"parlato": "Non ho ancora i dati per rispondere: nel database mancano le serie "
                       "che servono. Vanno scaricate con make ingest; la pagina di stato "
                       "dice quali sono ferme.", "scene": []}


INTENTS = [
    (r"previs|registro|track|scenario mio|mio scenario|il mio", predictions_intent),
    (r"\boro\b|gold|xau", gold),
    (r"regime", regime),
    (r"scenari|convergen|divergen|recession|stagflaz|atterraggio", scenarios),
    (r"liquidit|\bm2\b|bilanci|fed net|massa monetaria", liquidity),
    (r"lavoro|payroll|disoccup|sussid|occupaz", labour),
    (r"\b(ciao|ehi|hey|buongiorno|buonasera|jarvis)\b", greeting),
]


def answer(session: Session, question: str) -> dict:
    q = question.lower()
    for pattern, fn in INTENTS:
        if re.search(pattern, q):
            try:
                script = fn(session)
            except (KeyError, IndexError, TypeError, ZeroDivisionError) as e:
                # A tool returned no points (empty database, stale series)
                log.warning("demo intent %s: missing data (%r)", fn.__name__, e)
                script = no_data(session)
            return script | {"modalita": "dimostrativa", "intento": fn.__name__}
    return fallback(session) | {"modalita": "dimostrativa", "intento": "fallback"}
