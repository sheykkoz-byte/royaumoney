"""Build the claude.ai research artifact (regime + 13F) from the two exported JSON files.

    cd backend && python -m app.cli rqe && python -m app.cli istituzionali
    python frontend/artifact-ricerca/build.py   # → frontend/artifact-ricerca/regime-istituzionali.html

Publish the HTML as an artifact with capabilities {"sample": {}} (Claude analysis on the
viewer's account, no keys). The data is embedded: the page is a snapshot of the build day.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
PUB = HERE.parent / "public"


def compact() -> dict:
    r = json.loads((PUB / "rqe" / "rqe.json").read_text(encoding="utf-8"))
    i = json.loads((PUB / "istituzionali" / "13f.json").read_text(encoding="utf-8"))
    t, rg = r["taratura"], r["regime"]
    best: dict = {}
    for c in t["candidati"]:
        h = c.get("orizzonte", 1)
        if c["forza"] > 0 and h not in best:
            best[h] = c

    def idea(x):
        p = x.get("prezzi") or {}
        keep = ("ticker", "emittente", "tipo", "settore", "favore_regime", "giudizio",
                "punteggio", "motivi", "gestori", "valore_acquisti", "fondamentali")
        return {k: x.get(k) for k in keep} | {
            "prezzo_medio": p.get("prezzo_medio_trimestre"), "min": p.get("minimo_trimestre"),
            "max": p.get("massimo_trimestre"), "oggi": p.get("prezzo_oggi"),
            "data_prezzo": p.get("data_prezzo"), "da_loro": p.get("da_prezzo_medio")}

    def move(x):
        p = x.get("prezzi") or {}
        return {"ticker": x["ticker"], "emittente": x["emittente"], "tipo": x["tipo"],
                "valore": x["variazione_valore"], "peso": x["peso"],
                "da_fine_trim": p.get("da_fine_trimestre")}

    return {
        "oggi": i["oggi"],
        "regime": {"nome": rg["nome"], "dominante": rg["dominante"],
                   "descrizione": rg["descrizione"], "probabilita": rg["probabilita"],
                   "crescita": {k: rg["crescita"][k] for k in ("punteggio", "p_su")},
                   "inflazione": {k: rg["inflazione"][k] for k in ("punteggio", "p_su")},
                   "nomi": {q: v["name"] for q, v in r["quadranti"].items()}},
        "settori_per_regime": i["settori_per_regime"],
        "allocazione": [{k: x[k] for k in ("nome", "base", "consigliato", "scostamento")}
                        for x in r["allocazione"]["righe"]],
        "backtest": {k: {m: v[m] for m in ("cagr", "volatilita", "sharpe", "max_drawdown")}
                     for k, v in r["backtest"]["statistiche"].items()},
        "taratura": {
            "scelto": t["scelto"],
            "rp": {"train": t["risk_parity"]["train"]["sharpe"],
                   "test": t["risk_parity"]["test"]["sharpe"],
                   "dd_test": t["risk_parity"]["test"]["max_drawdown"]},
            "t": t["significativita_test"]["t"],
            "errore_sharpe": t["significativita_test"]["errore_sharpe"],
            "per_orizzonte": [{"orizzonte": h, "tipo": c["tipo"], "solo_regime": c.get("solo_regime"),
                               "forza": c["forza"], "sharpe_train": c["sharpe_train"],
                               "sharpe_test": c["sharpe_test"], "dd_test": c["dd_test"],
                               "t": c.get("t_test")} for h, c in sorted(best.items())]},
        "idee": [idea(x) for x in i["idee"]],
        "gestori": [{"nome": m["nome"], "stile": m["stile"], "nota": m["nota"],
                     "periodo": m.get("periodo"), "depositato": m.get("depositato"),
                     "giorni": m.get("giorni_dalla_fine_trimestre"),
                     "ritardo": m.get("giorni_di_ritardo_deposito"),
                     "valore_totale": m.get("valore_totale"), "n": m.get("numero_posizioni"),
                     "acquisti": [move(x) for x in m.get("acquisti", [])[:6]],
                     "vendite": [move(x) for x in m.get("vendite", [])[:6]]}
                    for m in i["gestori"]],
        "regole": i["regole"], "note": i["note"],
    }


if __name__ == "__main__":
    data = json.dumps(compact(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = HERE / "regime-istituzionali.html"
    out.write_text((HERE / "template.html").read_text(encoding="utf-8").replace("__DATA__", data),
                   encoding="utf-8")
    print(f"written {out}")
