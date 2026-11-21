# Istruzioni per Claude Code

Leggi sempre **`PIANO_ROYAUMONEY_JARVIS.md`**: è il piano del progetto (visione, fasi, regole).

## Regole (dal piano, sezione 11)
- Lavorare per fasi, nell'ordine; alla fine di ogni fase mostrare cosa funziona e come provarlo.
- Mai inventare dati: se una fonte non è disponibile, dirlo e proporre alternative.
- Test automatici sul motore analitico.
- Codice e commenti in inglese; testi dell'interfaccia e voce di Jarvis in italiano.
- Chiavi solo in `.env`, mai nel repository.

## Stato
- Fasi 0, 1, 2 e 3: fatte (novembre 2026). Prossima: Fase 4 (cervello Claude + voce + direttore di scena).

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
- Oro: strumento `XAUUSD_EST` = spot stimato dai future COMEX (`app/sources/futures.py`); P-0001 usa `align_to_entry` (+18,44 $). Dettagli in `docs/registro-previsioni.md`.

## Comandi
`make setup` · `make verify` · `make ingest` · `make health` · `make analisi [AS_OF=…]` · `make previsioni` · `make previsione ID=…` · `make track-record` · `make dev` · `make test` · `make lint`
