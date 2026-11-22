# Istituzionali: 13F dei grandi gestori × regime macro

Pagina `/istituzionali`, dati `frontend/public/istituzionali/13f.json` (`python -m app.cli istituzionali`, anche nel job delle 07:15 e 23:15). Codice in `backend/app/institutions/` e `backend/app/sources/{sec13f,openfigi}.py`.

## Il dato e il suo ritardo

- **Form 13F** (SEC EDGAR, gratuito, senza chiave): posizioni lunghe in titoli quotati USA dei gestori con più di 100 milioni di dollari, **alla fine del trimestre**.
- Si deposita **entro 45 giorni** dalla fine del trimestre (30/09 → entro il 14/11). Un acquisto può essere avvenuto in qualsiasi giorno del trimestre, quindi quando lo leggiamo ha da circa 45 a circa 135 giorni.
- Non contiene: vendite allo scoperto, titoli esteri, obbligazioni, liquidità, operazioni dentro il trimestre. I prezzi pagati non sono dichiarati.
- Più veloci ma parziali: Schedule 13D/13G (quote sopra il 5%, entro 5–10 giorni) e Form 4 (insider e quote sopra il 10%, entro 2 giorni). Non ancora collegati.

## Gestori seguiti (`institutions/config.py`)

| Gestore | Stile | Perché |
|---|---|---|
| Berkshire Hathaway | opinioni | Buffett: poche posizioni, lungo periodo |
| Bridgewater | opinioni | il fondo di Dalio |
| Pershing Square (Pershing Square Inc., CIK 2026053) | opinioni | Ackman; dal 2026 la vecchia società deposita solo 13F-NT che rimandano qui |
| Appaloosa | opinioni | Tepper |
| Duquesne Family Office | opinioni | Druckenmiller (valori dichiarati in migliaia: convertiti) |
| BlackRock, JPMorgan | flussi clienti | soprattutto fondi indice e conti clienti: mostrati ma esclusi dalle idee |

## Come si analizza

1. **Variazioni** tra gli ultimi due 13F (con gli emendamenti: un *restatement* sostituisce, *new holdings* aggiunge): nuova, aumentata (≥ +25% delle quote), ridotta, venduta. Movimenti sotto lo 0,2% del portafoglio ignorati.
2. **Correzioni**: split azionari dallo storico ufficiale (Yahoo), così uno split 4:1 non sembra un acquisto; cambi di codice CUSIP (stesso emittente, quote simili) non sembrano vendita + acquisto.
3. **Prezzo pagato stimato** = media delle chiusure del trimestre (con minimo e massimo). **Margine** = prezzo di oggi rispetto a quella media.
4. **Regime**: probabilità che il regime attuale sia uno di quelli che favoriscono il settore del titolo (settori per regime in `rqe/config.py`).
5. **Qualità alla Buffett** (Yahoo, solo prototipo): ROE ≥ 15%, debito/patrimonio ≤ 1, P/E atteso ≤ 30.
6. **Giudizio**: «C'è margine», «Da seguire», «Treno passato» (oltre +25% dal loro prezzo), «Contro il regime» (probabilità sotto il 20%), con i motivi scritti.

Regole tutte in `institutions/config.py`, test in `backend/tests/test_institutions.py`.

## Approfondimento di un titolo (clic su un'idea)

- **Prezzo**: grafico di un anno con l'intervallo del trimestre dell'acquisto, il prezzo medio stimato pagato e il valore intrinseco.
- **Lente Buffett** (`analysis.buffett`): ROE ≥ 15%, debito/EBITDA ≤ 2, margine operativo ≥ 15%, flusso di cassa libero positivo, rendimento degli utili sopra il Treasury 10 anni, margine di sicurezza ≥ 25%. Valore intrinseco con flussi di cassa scontati (`analysis.dcf`): flusso di cassa libero degli ultimi 12 mesi che cresce come gli utili (tetto 12%) e scende fino al 2,5% in 10 anni, tasso di sconto = max(8%, Treasury 10 anni + 5%), più cassa meno debito; tre scenari (crescita dimezzata, base, ×1,5 con tetto). Niente valore intrinseco se i bilanci non sono in dollari.
- **Lente Dalio** (`analysis.sector_by_regime`): rendimento in più del fondo settoriale SPDR (XLK, XLE…) rispetto all'S&P 500 nel mese dopo ogni mese in cui ciascun regime era il più probabile, dal 1999 (XLC dal 2018, XLRE dal 2015), e la media pesata con le probabilità di oggi. Mostrato accanto alla teoria: al 22/11/2026 i settori «da reflazione» (energia, industria, materiali) hanno storicamente fatto peggio dell'S&P 500 nei mesi di reflazione, la tecnologia meglio.

## Artefatto claude.ai

`frontend/artifact-ricerca/`: `template.html` + `build.py` (incorpora regime, taratura e 13F in una pagina). Si pubblica con la capacità `sample`: il pulsante «Chiedi a Claude» fa analizzare i dati a Claude sull'account di chi guarda, senza chiavi, con l'istruzione di non inventare numeri.

## Limiti

- Yahoo per prezzi, settori e fondamentali: solo prototipo (con FMP si passa ai bilanci veri).
- OpenFIGI senza chiave (25 richieste al minuto): CUSIP → ticker, in cache. Alcuni titoli (non quotati, esteri, appena fusi) restano senza ticker.
- `SEC_USER_AGENT` in `.env` per dichiarare un contatto proprio alla SEC (di default uno generico).
- Ricerca, non consulenza personalizzata.
