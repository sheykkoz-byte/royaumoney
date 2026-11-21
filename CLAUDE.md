# Istruzioni per Claude Code

Leggi sempre **`PIANO_ROYAUMONEY_JARVIS.md`**: è il piano del progetto (visione, fasi, regole).

## Regole (dal piano, sezione 11)
- Lavorare per fasi, nell'ordine; alla fine di ogni fase mostrare cosa funziona e come provarlo.
- Mai inventare dati: se una fonte non è disponibile, dirlo e proporre alternative.
- Test automatici sul motore analitico.
- Codice e commenti in inglese; testi dell'interfaccia e voce di Jarvis in italiano.
- Chiavi solo in `.env`, mai nel repository.

## Stato
- Fase 0 e Fase 1: fatte (novembre 2026). Prossima: Fase 2 (regime + convergenza).

## Come è fatto il motore dati
- Ogni serie è in `backend/app/catalog.py`. Per aggiungerne una basta una riga lì; `make verify` controlla ID e unità su FRED.
- Le osservazioni non si sovrascrivono mai: una revisione aggiunge una riga con un `published_at` successivo. Per i backtest usare sempre `store.load_frame(..., as_of=data)`.
- `pub_method` dice quanto è affidabile `published_at`: `alfred` > `first_seen` > `estimated_lag`.
- Valori salvati in unità normalizzate (miliardi di USD, migliaia di persone…); `raw_value` conserva il valore originale.
- Limiti noti: spread ICE solo ultimi 3 anni su FRED; nessun M2 cinese aggiornato su FRED; yfinance solo per il prototipo. Dettagli in `docs/fonti-dati.md`.

## Comandi
`make setup` · `make verify` · `make ingest` · `make health` · `make dev` · `make test` · `make lint`
