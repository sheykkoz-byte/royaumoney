# RoyauMoney × Jarvis

Piattaforma di intelligence sugli investimenti con un assistente vocale (Jarvis).
Il piano completo è in [`PIANO_ROYAUMONEY_JARVIS.md`](PIANO_ROYAUMONEY_JARVIS.md).

**Stato:** Fasi 0 (struttura), 1 (motore dati), 2 (regime e convergenza) e 3 (registro delle previsioni) completate.

## Avvio rapido

Servono Python 3.12+, [uv](https://docs.astral.sh/uv/) e Node 22.

```bash
make setup        # dipendenze + crea .env da .env.example
```

Apri `.env` e inserisci `FRED_API_KEY` (gratuita: https://fred.stlouisfed.org/docs/api/api_key.html).
Senza chiave funziona lo stesso, ma senza lo storico delle revisioni.

```bash
make verify       # controlla tutti gli ID FRED e le unità → docs/serie-verificate.md
make ingest       # primo download: ~25 secondi, dal 2000 a oggi
make health       # stato di ogni serie nel terminale
make analisi      # regime, scenari, convergenza e divergenze di oggi
make analisi AS_OF=2008-10-31   # la stessa analisi con i soli dati noti a quella data
make previsioni   # registro delle previsioni (es. P-0001, oro)
make previsione ID=P-0001       # dettaglio e diario degli eventi
make track-record # percentuale di successo, Brier score
make dev          # backend su :8000 + frontend su :3000
```

Poi apri:
- http://localhost:8000/health/data: lo stato di ogni serie in JSON (verde / giallo / rosso);
- http://localhost:8000/series/FED_NET_LIQ: una serie, con `?start=2025-01-01` e `?as_of=2026-06-30` (solo i dati già pubblicati a quella data);
- http://localhost:8000/analisi/oggi: regime, scenari, convergenza, divergenze e i dati a sostegno (`?as_of=2020-04-30` per una data passata);
- http://localhost:8000/previsioni e http://localhost:8000/track-record: il registro delle previsioni;
- http://localhost:8000/docs: tutte le API;
- http://localhost:3000: pagina provvisoria con track record e stato dei dati;
- `prototype/index.html`: il prototipo dell'interfaccia di Jarvis.

Con il backend acceso, ogni giorno alle **07:15** e alle **23:15** (ora di Roma) i dati si aggiornano e le previsioni aperte vengono verificate.

## Struttura

```
backend/            FastAPI + motore dati (Python)
  app/catalog.py    elenco delle 45 serie: fonte, unità, frequenza, ritardo ammesso
  app/sources/      FRED (API o CSV pubblico) e Yahoo (yfinance)
  app/store.py      salvataggio con storico delle revisioni e lettura "point in time"
  app/derived.py    liquidità netta Fed, BCE/BoJ in USD, rame/oro, ciclici/difensivi
  app/ingest.py     verifica + download + calcolo delle derivate
  app/health.py     /health/data
  app/analysis/     Fase 2: indicatori normalizzati, regime, scenari, convergenza
    config.py       tutte le scelte di metodo (indicatori, pesi, soglie)
  app/predictions/  Fase 3: registro delle previsioni, verifica, track record
  seeds/previsioni/ previsioni in JSON da registrare
  tests/            test automatici (offline)
frontend/           Next.js (UI immersiva dalle Fasi 4–6)
registro/           registro delle previsioni in git (non modificabile)
prototype/          prototipo HTML di Jarvis
docs/               fonti dati, serie verificate, metodo di analisi, registro previsioni
design/riferimenti/ immagini di riferimento per la UI
```

## Test

```bash
make test
make lint
```

La CI su GitHub Actions esegue gli stessi controlli ed esegue anche la build del frontend.
