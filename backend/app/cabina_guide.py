"""Plain-language explanations for the macro board ("Cosa vuol dire").

For each section: what it measures and why it matters, what each tile means, and today's
reading built from the tiles themselves (values and traffic lights), so the text changes
with the data. No AI: fixed rules, consistent with the thresholds in app/cabina.py.
"""

from collections.abc import Callable


def _n(x: float | None, nd: int = 1) -> str:
    if x is None:
        return "—"
    s = f"{x:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _bp(x: float | None) -> str:
    return "—" if x is None else f"{round(x * 100):+d} punti base"


TRAFFIC_LIGHTS = (
    "Verde: situazione tranquilla o favorevole. Giallo: da tenere d'occhio. Rosso: tensione "
    "o segnale di allarme. Grigio: solo informativo, senza giudizio. I semafori sono regole "
    "pratiche che descrivono la situazione: non sono segnali per comprare o vendere."
)

INTRO = {
    "Tassi": (
        "I tassi d'interesse sono il prezzo del denaro. Quelli a breve, come il 2 anni, seguono "
        "soprattutto ciò che il mercato si aspetta dalla Fed; quelli a lungo, come il 10 anni, "
        "dipendono da crescita, inflazione attesa e debito pubblico. Quando i tassi salgono, il "
        "credito costa di più per famiglie e imprese e soffrono di solito le azioni di crescita "
        "e l'oro; quando scendono succede il contrario. Le variazioni si misurano in punti base: "
        "1 punto base = 0,01%."
    ),
    "Inflazione": (
        "Misura quanto aumentano i prezzi. La Fed ha un obiettivo del 2% e guarda soprattutto al "
        "core PCE. Un'inflazione alta o in salita spinge la Fed a tenere i tassi alti; "
        "un'inflazione in calo le dà spazio per tagliarli. Conta anche cosa si aspetta il "
        "mercato per i prossimi anni: se le attese restano vicine al 2%, la Fed è credibile."
    ),
    "Dollaro e rischio": (
        "Dice quanto il mercato è disposto a rischiare. Un dollaro forte rende più cari i debiti "
        "in dollari e le materie prime per il resto del mondo, quindi stringe le condizioni "
        "finanziarie globali (anche per il Marocco e i paesi emergenti). Il VIX misura la paura "
        "sulle azioni, lo spread high yield quella sul credito delle aziende più indebitate: "
        "quando salgono insieme, la tensione è diffusa."
    ),
    "Liquidità": (
        "È la quantità di denaro che circola nel sistema finanziario: il primo passo del metodo "
        "di Jarvis. Quando la liquidità cresce tende a sostenere azioni, oro e criptovalute; "
        "quando si ritira, i mercati diventano più fragili anche se i dati economici sono buoni."
    ),
    "Crescita": (
        "Dice se l'economia accelera o rallenta, guardando sia i dati (il lavoro) sia il mercato "
        "(rame contro oro, settori ciclici contro difensivi). Il lavoro è il segnale più "
        "affidabile: le recessioni iniziano quasi sempre con licenziamenti in aumento. Quando i "
        "dati e il mercato non dicono la stessa cosa, il mercato spesso sta anticipando un "
        "cambiamento."
    ),
    "Materie prime": (
        "I prezzi delle materie prime chiave. L'oro reagisce ai tassi reali, al dollaro e alla "
        "paura; il petrolio all'inflazione e alla domanda mondiale (e alla geopolitica); il rame "
        "alla crescita industriale, soprattutto in Cina. Qui non c'è semaforo: sono prezzi da "
        "leggere insieme alle altre sezioni."
    ),
}

MEANING = {
    "DGS2": "Rendimento del titolo di Stato USA a 2 anni: dice dove il mercato si aspetta i "
            "tassi della Fed nei prossimi due anni.",
    "DGS10": "Rendimento a 10 anni: il riferimento per mutui e valutazioni delle azioni. Sale "
             "con crescita e inflazione attesa, o quando gli investitori chiedono più premio "
             "per prestare a lungo allo Stato.",
    "T10Y2Y": "Differenza tra 10 e 2 anni. Se è negativa (curva invertita) il mercato si aspetta "
              "tagli dei tassi in futuro: storicamente ha anticipato le recessioni. Il momento "
              "delicato è spesso quando torna positiva dopo un'inversione.",
    "DFF": "Il tasso deciso dalla Fed per i prestiti di un giorno tra banche: la leva "
           "principale della politica monetaria.",
    "CPIAUCSL": "Prezzi al consumo negli USA, variazione su un anno. È il dato più seguito dai "
                "mercati; esce ogni mese verso metà mese.",
    "PCEPILFE": "Prezzi della spesa per consumi senza cibo ed energia, su un anno: il "
                "riferimento ufficiale della Fed per il suo obiettivo del 2%.",
    "T10YIE": "Inflazione media che il mercato si aspetta nei prossimi 10 anni (differenza tra "
              "titoli di Stato normali e indicizzati all'inflazione). Tra 1,8% e 2,6% le "
              "attese sono considerate ancorate.",
    "DTWEXBGS": "Il dollaro contro un paniere ampio di valute dei partner commerciali USA. Sale "
                "quando il dollaro si rafforza.",
    "VIX": "Volatilità attesa sull'S&P 500 nei prossimi 30 giorni, ricavata dai prezzi delle "
           "opzioni: è l'indice della paura. Sotto 16 calma, 16–25 tensione, sopra 25 paura.",
    "BAMLH0A0HYM2": "Rendimento in più chiesto alle aziende più indebitate rispetto ai titoli "
                    "di Stato. Sotto 4 punti il credito è tranquillo, sopra 5,5 è sotto stress: "
                    "spesso anticipa le difficoltà dell'economia.",
    "DEXUSEU": "Quanti dollari servono per comprare un euro. Sale quando il dollaro si "
               "indebolisce contro l'euro.",
    "DEXJPUS": "Quanti yen servono per comprare un dollaro. Molto sensibile alla differenza di "
               "tassi tra USA e Giappone; un calo rapido segnala spesso fuga dal rischio.",
    "FED_NET_LIQ": "Bilancio della Fed meno il conto del Tesoro e il reverse repo: stima il "
                   "denaro della banca centrale davvero disponibile per il sistema, in miliardi "
                   "di dollari. Sopra +1% in 3 mesi è in aumento, sotto −3% in calo.",
    "M2SL": "Contanti, conti correnti e depositi di famiglie e imprese USA, variazione su un "
            "anno. Sopra il 4% la massa monetaria cresce in modo sostenuto; sotto zero si "
            "contrae.",
    "UNRATE": "Disoccupazione USA. Regola di Sahm: quando la media di 3 mesi sale di 0,5 punti "
              "sopra il minimo dell'ultimo anno, storicamente una recessione era già iniziata.",
    "PAYEMS": "Posti di lavoro creati in media negli ultimi 3 mesi, in migliaia al mese. Sopra "
              "150 mila la crescita è solida, sotto 50 mila è debole.",
    "ICSA": "Nuove richieste settimanali di sussidio di disoccupazione, media di 4 settimane: il "
            "dato più tempestivo sui licenziamenti. Il semaforo guarda quanto sono salite dal "
            "minimo dell'ultimo anno.",
    "COPPER_GOLD": "Il rame serve all'industria, l'oro è un bene rifugio. Se il rapporto sale il "
                   "mercato scommette sulla crescita; se scende, sulla prudenza.",
    "CYCL_DEF": "Settori ciclici (consumi discrezionali, industriali, finanziari, materiali) "
                "contro difensivi (beni di prima necessità, utility, sanità). Sale quando il "
                "mercato crede nella crescita.",
    "GOLD": "Prezzo dell'oro in dollari per oncia. Sale con tassi reali in calo, dollaro debole "
            "e paura; scende quando i tassi reali salgono.",
    "OIL_WTI": "Petrolio americano in dollari al barile: pesa sull'inflazione e sui conti dei "
               "paesi importatori.",
    "COPPER": "Rame in dollari per libbra: il termometro della domanda industriale mondiale.",
}


def _counts(tiles: list[dict]) -> str:
    c = {s: sum(1 for t in tiles if t.get("state") == s) for s in ("verde", "giallo", "rosso")}
    parts = [f"{v} {k if v == 1 else {'verde': 'verdi', 'giallo': 'gialli', 'rosso': 'rossi'}[k]}"
             for k, v in c.items() if v]
    return ("Semafori: " + ", ".join(parts) + ".") if parts else ""


def _by_id(tiles: list[dict]) -> dict[str, dict]:
    return {t["id"]: t for t in tiles if not t.get("errore")}


def _ch(t: dict | None, k: str) -> float | None:
    return None if t is None else (t.get("changes") or {}).get(k)


def today_tassi(t: dict[str, dict]) -> list[str]:
    out = []
    ff, y2, y10, curve = t.get("DFF"), t.get("DGS2"), t.get("DGS10"), t.get("T10Y2Y")
    if ff and ff.get("reading"):
        out.append(ff["reading"])
    if ff and y2:
        gap = y2["value"] - ff["value"]
        if gap > 0.1:
            out.append(f"Il 2 anni ({_n(y2['value'], 2)}%) è sopra i Fed funds "
                       f"({_n(ff['value'], 2)}%): il mercato si aspetta altri rialzi.")
        elif gap < -0.1:
            out.append(f"Il 2 anni ({_n(y2['value'], 2)}%) è sotto i Fed funds "
                       f"({_n(ff['value'], 2)}%): il mercato si aspetta tagli.")
        else:
            out.append("Il 2 anni è allineato ai Fed funds: il mercato non si aspetta grandi "
                       "mosse a breve.")
    if y10 and _ch(y10, "1m") is not None:
        out.append(f"Il 10 anni è a {_n(y10['value'], 2)}% ({_bp(_ch(y10, '1m'))} in un mese).")
    if curve and curve.get("reading"):
        out.append(f"La curva 10−2 è a {_n(curve['value'], 2)} punti. {curve['reading']}")
    return out


def today_inflazione(t: dict[str, dict]) -> list[str]:
    out = []
    cpi, pce, be = t.get("CPIAUCSL"), t.get("PCEPILFE"), t.get("T10YIE")
    if cpi:
        out.append(f"Il CPI è al {_n(cpi['value'])}% su un anno: {cpi['reading'].lower()}")
    if pce:
        out.append(f"Il core PCE, il dato che guarda la Fed, è al {_n(pce['value'])}%.")
    if be:
        out.append(f"Il mercato si aspetta in media il {_n(be['value'], 2)}% per i prossimi 10 "
                   f"anni: {be['reading'].lower()}")
    hot = [x for x in (cpi, pce) if x and x["state"] in ("giallo", "rosso")]
    if hot and be and be["state"] == "verde":
        out.append("In sintesi: l'inflazione di oggi è sopra l'obiettivo, ma il mercato crede "
                   "che rientrerà. La Fed ha motivo di restare prudente sui tagli.")
    elif hot:
        out.append("In sintesi: l'inflazione è sopra l'obiettivo e le attese non aiutano: "
                   "pressione sulla Fed per tassi alti.")
    elif cpi:
        out.append("In sintesi: l'inflazione è vicina all'obiettivo: la Fed ha margini.")
    return out


def today_rischio(t: dict[str, dict]) -> list[str]:
    out = []
    usd, vix, hy = t.get("DTWEXBGS"), t.get("VIX"), t.get("BAMLH0A0HYM2")
    if usd and usd.get("reading"):
        out.append(usd["reading"])
    if vix:
        out.append(f"VIX a {_n(vix['value'])}: {vix['reading'].lower()}")
    if hy:
        out.append(f"Spread high yield a {_n(hy['value'], 2)} punti: {hy['reading'].lower()}")
    if vix and hy:
        if vix["state"] == "rosso" and hy["state"] == "verde":
            out.append("In sintesi: la paura è concentrata sulle azioni, il credito non la "
                       "conferma ancora. Se anche lo spread si allargasse, il segnale "
                       "diventerebbe più serio.")
        elif vix["state"] == "rosso" and hy["state"] in ("giallo", "rosso"):
            out.append("In sintesi: tensione sia sulle azioni sia sul credito: fase di "
                       "avversione al rischio diffusa.")
        elif vix["state"] == "verde" and hy["state"] == "verde":
            out.append("In sintesi: mercato calmo, nessuna tensione visibile.")
    return out


def today_liquidita(t: dict[str, dict]) -> list[str]:
    out = []
    fed, m2 = t.get("FED_NET_LIQ"), t.get("M2SL")
    if fed:
        out.append(f"Liquidità netta Fed: {_n(fed['value'], 0)} miliardi di dollari. "
                   f"{fed.get('reading', '')}")
    if m2:
        out.append(f"M2 al {_n(m2['value'])}% su un anno: {m2['reading'].lower()}")
    if fed and m2:
        if fed["state"] == "verde" and m2["state"] == "verde":
            out.append("In sintesi: la liquidità cresce: vento favorevole per gli asset a "
                       "rischio.")
        elif fed["state"] == "rosso" or m2["state"] == "rosso":
            out.append("In sintesi: la liquidità si sta ritirando: i mercati diventano più "
                       "fragili.")
        else:
            out.append("In sintesi: segnali misti. La massa monetaria cresce, ma la liquidità "
                       "della Fed è ferma: non c'è una spinta forte in nessuna direzione.")
    return out


def today_crescita(t: dict[str, dict]) -> list[str]:
    out = []
    labour = [t.get(k) for k in ("UNRATE", "PAYEMS", "ICSA") if t.get(k)]
    market = [t.get(k) for k in ("COPPER_GOLD", "CYCL_DEF") if t.get(k)]
    for x in labour + market:
        if x.get("reading"):
            out.append(f"{x['label']}: {x['reading'][0].lower()}{x['reading'][1:]}")
    bad_l = sum(1 for x in labour if x["state"] in ("giallo", "rosso"))
    bad_m = sum(1 for x in market if x["state"] in ("giallo", "rosso"))
    if labour and market:
        if bad_l == 0 and bad_m == 0:
            out.append("In sintesi: dati e mercato concordano: l'economia tiene.")
        elif bad_l and bad_m == 0:
            out.append("In sintesi: il lavoro dà qualche segnale di rallentamento, ma il "
                       "mercato non lo vede ancora.")
        elif bad_m and bad_l <= 1:
            out.append("In sintesi: i dati sul lavoro sono ancora buoni, ma una parte del "
                       "mercato si sta mettendo sulla difensiva: possibile rallentamento non "
                       "ancora visibile nei dati.")
        else:
            out.append("In sintesi: dati e mercato indicano entrambi un rallentamento.")
    return out


def today_materie(t: dict[str, dict]) -> list[str]:
    out = []
    for k, unit in (("GOLD", "$"), ("OIL_WTI", "$"), ("COPPER", "$")):
        x = t.get(k)
        if not x:
            continue
        m, y = _ch(x, "1m"), _ch(x, "1a")
        parts = [f"{x['label']} a {_n(x['value'], x.get('decimals', 2))} {unit}"]
        if m is not None:
            parts.append(f"{m:+.1f}% in un mese".replace(".", ","))
        if y is not None:
            parts.append(f"{y:+.1f}% in un anno".replace(".", ","))
        out.append(", ".join(parts) + ".")
    return out


TODAY: dict[str, Callable[[dict[str, dict]], list[str]]] = {
    "Tassi": today_tassi, "Inflazione": today_inflazione, "Dollaro e rischio": today_rischio,
    "Liquidità": today_liquidita, "Crescita": today_crescita, "Materie prime": today_materie,
}


def explain(sections: list[str], tiles: list[dict]) -> dict:
    """{section: {cosa_misura, riquadri: [{label, significato}], oggi: [frasi], semafori}}."""
    out = {}
    for sec in sections:
        sec_tiles = [t for t in tiles if t.get("section") == sec]
        by_id = _by_id(sec_tiles)
        fn = TODAY.get(sec)
        out[sec] = {
            "cosa_misura": INTRO.get(sec, ""),
            "riquadri": [{"label": t["label"], "significato": MEANING.get(t["id"], "")}
                         for t in sec_tiles if MEANING.get(t["id"])],
            "oggi": [s.strip() for s in (fn(by_id) if fn else []) if s and s.strip()],
            "semafori": _counts(sec_tiles),
        }
    return out
