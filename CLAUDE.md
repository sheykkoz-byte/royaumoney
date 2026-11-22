# Istruzioni per Claude Code

Leggi sempre **`PIANO_ROYAUMONEY_JARVIS.md`**: è il piano del progetto (visione, fasi, regole).

## Regole (dal piano, sezione 11)
- Lavorare per fasi, nell'ordine; alla fine di ogni fase mostrare cosa funziona e come provarlo.
- Mai inventare dati: se una fonte non è disponibile, dirlo e proporre alternative.
- Test automatici sul motore analitico.
- Codice e commenti in inglese; testi dell'interfaccia e voce di Jarvis in italiano.
- Chiavi solo in `.env`, mai nel repository.

## Stato
- Fasi 0, 1, 2 e 3: fatte (novembre 2026). Fase 4 in corso: fatte le parti senza chiavi (strumenti, direttore di scena, cervello dimostrativo, WebSocket, frontend). Voce ElevenLabs fatta (credenziale nell'ambiente cloud, `VOICE=elevenlabs`). Cervello Claude scritto e testato con un client finto (`claude_brain.py`); si attiva appena c'è JARVIS_ANTHROPIC_API_KEY (variabile dell'ambiente cloud `royaumoney`: il nome ANTHROPIC_API_KEY non arriva alle sessioni cloud) o ANTHROPIC_API_KEY nel .env locale. Collaudato il 21/11/2026 con cervello dimostrativo + ElevenLabs (vedi `docs/jarvis.md`); il cervello Claude va collaudato con la chiave vera in una sessione nuova. Artefatto claude.ai con cervello Claude sull'account di chi guarda, senza chiavi (`frontend/artifact/`, vedi `docs/jarvis.md`). Lo script di avvio dell'ambiente cloud lancia l'ingest, così il database non parte vuoto. Dettagli in `docs/jarvis.md`.

## Come è fatto il motore dati
- Ogni serie è in `backend/app/catalog.py`. Per aggiungerne una basta una riga lì; `make verify` controlla ID e unità su FRED.
- Le osservazioni non si sovrascrivono mai: una revisione aggiunge una riga con un `published_at` successivo. Per i backtest usare sempre `store.load_frame(..., as_of=data)`.
- `pub_method` dice quanto è affidabile `published_at`: `alfred` > `first_seen` > `estimated_lag`.
- Valori salvati in unità normalizzate (miliardi di USD, migliaia di persone…); `raw_value` conserva il valore originale.
- Limiti noti: spread ICE solo ultimi 3 anni su FRED; nessun M2 cinese aggiornato su FRED; yfinance solo per il prototipo. Dettagli in `docs/fonti-dati.md`.

## Motore analitico (Fase 2)
- `backend/app/analysis/`: `indicators.py` (trasformazioni, z-score, variazioni), `regime.py`, `scoring.py` (formule pure), `engine.py` (orchestrazione, `analyze()` è puro e point-in-time).
- Tutte le scelte di metodo stanno in `analysis/config.py`; il metodo è spiegato in `docs/metodo-analisi.md`.
- Ogni indicatore ha una colonna `available` (data di pubblicazione): l'analisi a una data usa solo righe con `available <= as_of`. Il test `test_analyze_is_point_in_time` lo garantisce.

## Registro delle previsioni (Fase 3)
- `backend/app/predictions/`: `spec.py` (cosa dice una previsione), `evaluate.py` (verifica pura su barre giornaliere), `service.py` (crea, verifica, registro in git), `stats.py` (track record, Brier).
- Una previsione non si modifica MAI dopo la registrazione: spec congelata con SHA-256, copia in `registro/P-xxxx.json` (committare sempre questi file).
- Oro: strumento `XAUUSD_SPOT` = spot vero XAU/USD da Twelve Data (`app/sources/twelvedata.py`). `XAUUSD_EST` (stima dai future) resta solo per P-0001, annullata e sostituita da P-0002.
- Annullare è permesso solo prima di qualsiasi prezzo successivo alla registrazione (`previsioni annulla`).
- Verifica giornaliera: attività pianificata nel cloud → `previsioni ciclo` → commit di `registro/stato`, `registro/prezzi`, `registro/track-record.json`.
- Statistiche robuste (mediana/MAD) negli z-score: vedi `docs/metodo-analisi.md` (caso giugno 2022).

## Jarvis (Fase 4)
- `backend/app/jarvis/`: `tools.py` (strumenti in formato tool use, unica fonte dei numeri), `claude_brain.py` (Claude con tool use + risposta JSON a schema), `voice.py` (ElevenLabs con timestamp), `scene.py` (direttore di scena: valida, allinea le parole, allega i dati), `demo.py` (cervello senza AI), `session.py` (sceglie il cervello).
- Frontend: `src/app/jarvis/page.tsx` (Jarvis), `src/components/{Orb,Chart,Cards}.tsx`, `src/lib/{jarvis,voice}.ts`. La pagina di stato è in `src/app/stato/`.
- Regola: il modello non scrive mai numeri nei grafici; il direttore li prende dagli strumenti.

## Cabina del trader (uso personale)
- Piattaforma di sola visione, pagina principale `/` (Jarvis su `/jarvis`), per il monitor 49" 32:9: watchlist con preferiti, grafico TradingView, grafici di controllo, plancia macro con semafori, colonna Jarvis. Dettagli in `docs/cabina.md`.
- Plancia: `backend/app/cabina.py` → `frontend/public/cabina/macro.json` (`python -m app.cli cabina`). Regole dei semafori in `RULES`, con test.
- Nei widget TradingView i simboli TVC e i future CME/ICE non sono concessi: usare CFD, FRED o altri fornitori (tabella in `docs/cabina.md`). Verificare ogni simbolo nuovo aprendolo.
- Online privato: Vercel + `CABINA_PASSWORD` (`frontend/src/middleware.ts`).

## Regime & Quality Engine (Dalio × Buffett)
- `backend/app/rqe/`: `config.py` (tutte le scelte), `macro.py` (crescita/inflazione, probabilità dei 4 regimi, storia point-in-time con le revisioni), `assets.py` (rendimenti mensili con proxy pre-ETF), `allocation.py` (risk parity + tilt ±10 pt), `backtest.py` (dal 2000, contro 60/40), `service.py` (cache della storia, snapshot, `rqe.json`).
- Dashboard `/regime` (`frontend/src/app/regime/page.tsx`), dati `frontend/public/rqe/rqe.json` (`python -m app.cli rqe`). Metodo e risultati in `docs/regime-quality-engine.md`.
- Screener Buffett: regole in config, codice da fare quando c'è la chiave FMP. Niente backtest dello screener (bilanci non point-in-time).
- Storico FRED dal 1990 (`backfill_start`). `store.load_versions` + `as_known_on` danno una serie come era nota a una data; `load_frame(..., availability="first")` usa la data di prima pubblicazione.

## Comandi
`make setup` · `make verify` · `make ingest` · `make health` · `make analisi [AS_OF=…]` · `make previsioni` · `make previsione ID=…` · `make track-record` · `python -m app.cli cabina` · `make dev` · `make test` · `make lint`
