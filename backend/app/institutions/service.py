"""Build the institutional-holdings report: latest two 13F per manager, what changed, prices
since then, macro regime fit and quality, a verdict per idea. Writes
frontend/public/istituzionali/13f.json."""

import json
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from app.config import BACKEND_DIR, get_settings
from app.institutions import analysis as A
from app.institutions import config as C
from app.rqe import config as RC
from app.sources import openfigi
from app.sources.sec13f import SecClient, SecError

log = logging.getLogger(__name__)
CACHE = BACKEND_DIR / "data" / "cache"
OUT = BACKEND_DIR.parent / "frontend" / "public" / "istituzionali" / "13f.json"
RQE = BACKEND_DIR.parent / "frontend" / "public" / "rqe" / "rqe.json"


def _regime() -> dict:
    """Current regime from the Regime & Quality Engine output (written daily)."""
    if RQE.exists():
        d = json.loads(RQE.read_text(encoding="utf-8"))
        r = d.get("regime") or {}
        return {"probabilita": r.get("probabilita") or {}, "nome": r.get("nome"),
                "dominante": r.get("dominante"), "as_of": d.get("as_of")}
    return {"probabilita": {}, "nome": None, "dominante": None, "as_of": None}


def _yahoo_splits(tickers: list[str], today: date) -> dict[str, pd.Series]:
    """Split history per ticker (Yahoo), cached for the day."""
    path = CACHE / "yahoo_splits.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    import yfinance as yf

    for t in tickers:
        if t in cache and cache[t].get("_giorno") == today.isoformat():
            continue
        try:
            sp = yf.Ticker(t).splits
            cache[t] = {"_giorno": today.isoformat(),
                        "split": {d.date().isoformat(): float(v) for d, v in sp.items()}}
        except Exception as e:
            log.warning("Yahoo splits %s: %s", t, e)
            cache[t] = {"_giorno": today.isoformat(), "split": {}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache))
    return {t: cache[t]["split"] for t in tickers}


def _manager_report(sec: SecClient, m: C.Manager) -> dict:
    name, fil = sec.filings(m.cik)
    hr = [f for f in fil if f.form == "13F-HR"]
    if not hr:
        return {"errore": "nessun 13F trovato"}
    curr = hr[0]
    prev = next((f for f in hr[1:] if f.period < curr.period), None)
    empty = pd.DataFrame(columns=["cusip", "issuer", "classe", "put_call", "tipo", "valore",
                                  "quantita"])
    before = sec.period_holdings(fil, prev.period) if prev else empty
    after = sec.period_holdings(fil, curr.period)
    return {"nome_sec": name, "deposito": curr, "precedente": prev, "prima": before,
            "dopo": after, "variazioni": A.changes(before, after)}


def _apply_splits(rep: dict, figi: dict, today: date) -> None:
    """Recompute the changes with the splits between the two quarter ends, for positions
    whose share count moved a lot (where a split would matter)."""
    ch, prev, curr = rep["variazioni"], rep["precedente"], rep["deposito"]
    if prev is None:
        return
    big = ch[(ch["prima"] > 0) & (ch["dopo"] > 0) & (ch["peso"] >= C.MIN_WEIGHT)
             & (((ch["dopo"] / ch["prima"]) >= 1.5) | ((ch["dopo"] / ch["prima"]) <= 0.67))]
    tick = {c: (figi.get(c) or {}).get("ticker") for c in big.index}
    tick = {c: t.replace("/", "-") for c, t in tick.items() if t}
    if not tick:
        return
    hist = _yahoo_splits(sorted(set(tick.values())), today)
    splits = {}
    for c, t in tick.items():
        k = 1.0
        for d, v in hist.get(t, {}).items():
            if prev.period < d <= curr.period:
                k *= v
        if k != 1.0:
            splits[c] = k
    if splits:
        rep["variazioni"] = A.changes(rep["prima"], rep["dopo"], splits)


def _yahoo_info(tickers: list[str], today: date) -> dict:
    """Sector and a few fundamentals (Yahoo, prototype only), cached for the day."""
    path = CACHE / "yahoo_info.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    import yfinance as yf

    for t in tickers:
        if t in cache and cache[t].get("_giorno") == today.isoformat():
            continue
        try:
            i = yf.Ticker(t).info
            de = i.get("debtToEquity")
            cache[t] = {"settore": i.get("sector"), "industria": i.get("industry"),
                        "roe": i.get("returnOnEquity"),
                        "debito_patrimonio": de / 100 if isinstance(de, (int, float)) else None,
                        "pe_atteso": i.get("forwardPE"), "pe": i.get("trailingPE"),
                        "capitalizzazione": i.get("marketCap"), "_giorno": today.isoformat()}
        except Exception as e:  # missing or delisted ticker: keep going
            log.warning("Yahoo info %s: %s", t, e)
            cache[t] = {"_giorno": today.isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache))
    return cache


def _closes(tickers: list[str], start: date) -> pd.DataFrame:
    import yfinance as yf

    if not tickers:
        return pd.DataFrame()
    df = yf.download(sorted(set(tickers)), start=start.isoformat(), auto_adjust=True,
                     progress=False, group_by="column", threads=True)
    c = df["Close"]
    return c.to_frame(tickers[0]) if isinstance(c, pd.Series) else c


def _row(r, ticker: str | None) -> dict:
    return {"cusip": r.Index, "ticker": ticker, "emittente": r.issuer, "tipo": r.tipo,
            "quote_prima": int(r.prima), "quote_dopo": int(r.dopo),
            "variazione_quote": int(r.variazione_quote),
            "variazione_pct": None if r.prima == 0 else round(r.dopo / r.prima - 1, 4),
            "valore": round(float(r.valore)), "peso": round(float(r.peso), 4),
            "variazione_valore": round(float(r.variazione_valore)),
            "frazionamento": None if pd.isna(getattr(r, "frazionamento", None)) else
            int(r.frazionamento)}


def build(today: date | None = None) -> dict:
    today = today or date.today()
    ts = pd.Timestamp(today)
    sec = SecClient(get_settings().sec_user_agent, CACHE / "13f")
    regime = _regime()
    reports = []
    for m in C.MANAGERS:
        try:
            reports.append((m, _manager_report(sec, m)))
        except SecError as e:
            reports.append((m, {"errore": str(e)}))
    # Tickers of the positions whose share count moved a lot: needed to look up splits
    big = [c for _, rep in reports if "variazioni" in rep
           for c, r in rep["variazioni"].iterrows()
           if r["prima"] > 0 and r["dopo"] > 0 and r["peso"] >= C.MIN_WEIGHT
           and not 0.67 < r["dopo"] / r["prima"] < 1.5]
    figi_big = openfigi.map_cusips(big, CACHE / "cusip_ticker.csv")
    managers, picked = [], []
    for m, rep in reports:
        if "errore" in rep:
            managers.append({"nome": m.nome, "stile": m.stile, "nota": m.nota, **rep})
            continue
        _apply_splits(rep, figi_big, today)
        ch, f = rep["variazioni"], rep["deposito"]
        if pd.Timestamp(f.period) < A.latest_due_quarter(ts):
            stale = f"Ultimo 13F riferito al {f.period}: dati vecchi, esclusi dalle idee."
        else:
            stale = None
        moves = ch[ch["peso_variazione"] >= C.MIN_WEIGHT]
        sel = {
            "posizioni": ch[ch["dopo"] > 0].nlargest(C.TOP_HOLDINGS, "valore"),
            "acquisti": moves[moves["tipo"].isin(["nuova", "aumentata"])]
            .nlargest(C.TOP_MOVES, "variazione_valore"),
            "vendite": moves[moves["tipo"].isin(["venduta", "ridotta"])]
            .nsmallest(C.TOP_MOVES, "variazione_valore"),
        }
        picked += [c for d in sel.values() for c in d.index]
        managers.append({"m": m, "f": f, "prev": rep["precedente"], "sel": sel, "vecchio": stale,
                         "totale": float(ch["valore"].sum()), "n": int((ch["dopo"] > 0).sum())})

    figi = openfigi.map_cusips(picked, CACHE / "cusip_ticker.csv")

    def tick(c):
        t = (figi.get(c) or {}).get("ticker")
        return t.replace("/", "-") if t else None  # BRK/B → BRK-B for Yahoo

    # Ideas: buys of the latest quarter; consensus among discretionary managers
    buyers: dict[str, set] = {}
    for mm in managers:
        if "m" in mm and mm["m"].stile == "discrezionale" and not mm["vecchio"]:
            for c in mm["sel"]["acquisti"].index:
                if tick(c):
                    buyers.setdefault(tick(c), set()).add(mm["m"].nome)
    tickers = sorted({tick(c) for mm in managers if "sel" in mm
                      for d in mm["sel"].values() for c in d.index if tick(c)})
    periods = [pd.Timestamp(mm["f"].period) for mm in managers if "f" in mm]
    start = (min(periods) - pd.offsets.QuarterEnd(1)).date() if periods else today
    closes = _closes(tickers, start)
    idea_tickers = sorted({tick(c) for mm in managers if "sel" in mm
                           for c in mm["sel"]["acquisti"].index if tick(c)})
    info = _yahoo_info(idea_tickers, today)

    out_managers, ideas = [], {}
    for mm in managers:
        if "m" not in mm:
            out_managers.append(mm)
            continue
        m, f = mm["m"], mm["f"]
        blocks = {}
        for k, d in mm["sel"].items():
            rows = []
            for r in d.itertuples():
                t = tick(r.Index)
                row = _row(r, t)
                if t and t in closes:
                    row["prezzi"] = A.price_context(closes[t], pd.Timestamp(f.period))
                if k == "acquisti" and t:
                    inf = info.get(t, {})
                    move = (row.get("prezzi") or {}).get("da_prezzo_medio")
                    fit = A.regime_fit(inf.get("settore"), regime["probabilita"], RC.SECTORS)
                    q = A.quality(inf)
                    n = len(buyers.get(t, ()))
                    row |= {"settore": inf.get("settore"), "favore_regime": fit,
                            "qualita": q, "fondamentali": {k2: A.safe(inf.get(k2)) for k2 in
                                                           ("roe", "debito_patrimonio",
                                                            "pe_atteso", "pe")},
                            **A.verdict(move, fit, q, n, r.tipo)}
                    if m.stile == "discrezionale" and not mm["vecchio"]:
                        idea = ideas.setdefault(t, row | {"gestori": [], "valore_acquisti": 0})
                        idea["gestori"].append(m.nome)
                        idea["valore_acquisti"] += row["variazione_valore"]
                rows.append(row)
            blocks[k] = rows
        out_managers.append({
            "nome": m.nome, "nome_sec": None, "stile": m.stile, "nota": m.nota, "cik": m.cik,
            "periodo": f.period, "depositato": f.filed, "periodo_precedente":
            mm["prev"].period if mm["prev"] else None,
            "valore_totale": round(mm["totale"]), "numero_posizioni": mm["n"],
            "avviso": mm["vecchio"],
            **A.days_late(f.period, f.filed, ts), **blocks})

    idea_list = sorted(ideas.values(), key=lambda x: (-x["punteggio"], -len(x["gestori"]),
                                                      -x["valore_acquisti"]))
    for i in idea_list:
        i["motivi"] = A.verdict((i.get("prezzi") or {}).get("da_prezzo_medio"),
                                i.get("favore_regime"), i.get("qualita"),
                                len(i["gestori"]), i["tipo"])["motivi"]
    return {
        "generato": datetime.now().isoformat(timespec="minutes"),
        "oggi": today.isoformat(),
        "regime": regime,
        "settori_per_regime": RC.SECTORS,
        "gestori": out_managers,
        "idee": idea_list,
        "regole": {"vicino_al_prezzo": C.NEAR_PAID, "treno_passato": C.RAN_AWAY,
                   "sotto_il_prezzo": C.BELOW_PAID, "regime_favorevole": C.REGIME_GOOD,
                   "regime_sfavorevole": C.REGIME_BAD, "roe_minimo": C.MIN_ROE,
                   "debito_massimo": C.MAX_DEBT_EQUITY, "pe_massimo": C.MAX_FORWARD_PE},
        "note": [
            "I 13F mostrano le posizioni lunghe in titoli quotati USA alla fine del trimestre, "
            "depositate fino a 45 giorni dopo: oggi il gestore può già averle cambiate.",
            "Niente vendite allo scoperto, derivati complessi, titoli esteri, obbligazioni o "
            "liquidità: il 13F è solo una parte del portafoglio.",
            "Il prezzo pagato non è dichiarato: è stimato con la media delle chiusure del "
            "trimestre (con minimo e massimo).",
            "BlackRock e JPMorgan muovono soprattutto soldi dei clienti e fondi indice: i loro "
            "acquisti non sono opinioni e non entrano nelle idee.",
            "Settori e fondamentali da Yahoo Finance (solo prototipo). Ricerca, non consulenza "
            "personalizzata.",
        ],
    }


def export(out: Path = OUT, today: date | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(today), ensure_ascii=False, separators=(",", ":"),
                              default=str), encoding="utf-8")
    return out
