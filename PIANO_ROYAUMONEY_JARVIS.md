# RoyauMoney × Jarvis — Piano di progetto per Claude Code

> Da mettere nella root del repository (anche come `CLAUDE.md`) e da far leggere a Claude Code all'inizio di ogni sessione.
> Autore: Yousef · Versione 1 · 21 novembre 2026

---

## 1. Visione

**RoyauMoney** è una piattaforma di intelligence sugli investimenti, pensata prima per i marocchini e la diaspora. È l'evoluzione di Meridian.

**Jarvis** è la sua interfaccia: un assistente vocale che ragiona da analista, risponde a voce e intanto costruisce davanti all'utente grafici e scenari interattivi e immersivi, nello stile delle scene di Tony Stark con Jarvis.

Il valore non sta nel modello AI, che tutti possono usare, ma in tre cose che gli altri non hanno insieme:

1. **I dati incrociati.** Liquidità globale, regime macro e segnali del mercato, scaricati e confrontati in automatico ogni giorno.
2. **Un metodo fisso.** Ogni analisi segue la stessa catena logica: liquidità → regime → conferma del mercato → scenario netto → livello di invalidazione → selezione di azioni.
3. **Un registro delle previsioni.** Ogni previsione viene salvata, verificata automaticamente e misurata, così l'accuratezza è dimostrabile al cliente.

Il cuore logico è il **confronto tra due voci**:
- **la voce della macro**: liquidità, inflazione, lavoro, tassi;
- **la voce del mercato**: curva dei tassi, spread del credito, rame/oro, settori ciclici e difensivi, dollaro.

Quando le due voci concordano, la conclusione è forte. Quando divergono, quello è il segnale più prezioso, perché il mercato sta prezzando un cambiamento che i dati non mostrano ancora.

---

## 2. Architettura

```
┌──────────────────────────────────────────────────────────────┐
│  FRONTEND (web + PWA per il telefono, Tauri per il desktop)  │
│  Sfera vocale 3D · Coreografia dei grafici · Scroll immersivo │
└───────────────▲───────────────────────────────┬──────────────┘
                │ WebSocket (audio + comandi    │ microfono
                │ di scena + allineamento)      ▼
┌──────────────────────────────────────────────────────────────┐
│  BACKEND (Python · FastAPI)                                   │
│  ┌────────────┐  ┌────────────────┐  ┌─────────────────────┐  │
│  │ Cervello   │→ │ Direttore di   │→ │ Voce                │  │
│  │ Claude API │  │ scena (JSON)   │  │ ElevenLabs stream   │  │
│  │ + strumenti│  └────────────────┘  │ + timestamp         │  │
│  └─────┬──────┘                      └─────────────────────┘  │
│        │ strumenti: query_dati, punteggio_convergenza,        │
│        │ ricerca_web, registra_previsione, classifica_azioni  │
│  ┌─────▼──────────────────────────────────────────────────┐   │
│  │ Motore analitico: regime · convergenza · selezione      │   │
│  └─────▲──────────────────────────────────────────────────┘   │
│  ┌─────┴──────────────────────────────────────────────────┐   │
│  │ Motore dati: job pianificati → Postgres/TimescaleDB     │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### Stack
| Livello | Scelta | Note |
|---|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn | async, WebSocket nativo |
| Job | APScheduler (poi Celery se serve) | download giornalieri e intraday |
| Database | PostgreSQL + TimescaleDB | serie storiche; all'inizio va bene SQLite |
| Cervello | Claude API (tool use + streaming) | il modello chiama gli strumenti del motore |
| Voce in uscita | ElevenLabs, streaming con timestamp | voce dedicata a Jarvis; poi clonazione |
| Voce in entrata | Speech-to-text in streaming (ElevenLabs, Deepgram o Whisper) | da scegliere con un test di latenza sull'italiano |
| Frontend | Next.js + React Three Fiber + GSAP (ScrollTrigger) | 3D, coreografie, scroll |
| Grafici | D3 / visx per i grafici animati, TradingView Lightweight Charts per i prezzi | |
| Telefono | PWA installabile | stesso codice |
| Desktop | Tauri (fase successiva) | per agire sul PC |

Le chiavi API stanno solo nel file `.env` del backend e non vanno mai nel frontend né nel repository.

---

## 3. Motore dati (Fase 1)

### 3.1 Liquidità (la voce dei soldi)
Fonte principale: **FRED** (Fed di St. Louis), gratuita con chiave API.

| Indicatore | Serie FRED | Frequenza |
|---|---|---|
| Massa monetaria M2 USA | `M2SL` | mensile |
| Bilancio della Fed | `WALCL` | settimanale |
| Conto del Tesoro (TGA) | `WTREGEN` | settimanale |
| Reverse repo overnight | `RRPONTSYD` | giornaliera |
| **Liquidità netta Fed** | calcolata: `WALCL − WTREGEN − RRPONTSYD` | settimanale |
| Bilancio BCE | `ECBASSETSW` | settimanale |
| Bilancio Banca del Giappone | `JPNASSETS` | mensile |

> Claude Code: verifica ogni ID su FRED prima di usarlo e controlla le unità di misura (milioni o miliardi), perché le serie usano unità diverse. Per la Cina (PBoC, M2 cinese) cerca una fonte affidabile e segnala se è solo a pagamento.

### 3.2 Macro (la voce dei dati)
| Indicatore | Serie FRED |
|---|---|
| Inflazione CPI | `CPIAUCSL` |
| Core PCE (il riferimento della Fed) | `PCEPILFE` |
| Disoccupazione | `UNRATE` |
| Payroll non agricoli | `PAYEMS` |
| Richieste iniziali di sussidio | `ICSA` |
| Richieste continuative | `CCSA` |
| Fed funds effettivo | `DFF` |
| Inflazione attesa a 10 anni (breakeven) | `T10YIE` |

### 3.3 Mercato (la voce del mercato)
| Indicatore | Fonte |
|---|---|
| Rendimento 10 anni e 2 anni, curva 10–2 | FRED `DGS10`, `DGS2`, `T10Y2Y` |
| Spread high yield | FRED `BAMLH0A0HYM2` |
| Spread investment grade | FRED `BAMLC0A0CM` |
| Dollaro (indice ampio) | FRED `DTWEXBGS` |
| Oro, rame, petrolio (future) | fonte di prezzo di mercato (vedi sotto) |
| **Rapporto rame/oro** | calcolato |
| Settori: XLK, XLF, XLE, XLI, XLY, XLP, XLU, XLV, XLB, XLRE, XLC | fonte di prezzo di mercato |
| **Ciclici vs difensivi** | calcolato: (XLY+XLI+XLF+XLB) / (XLP+XLU+XLV) |
| VIX | fonte di prezzo di mercato |

**Fonte di prezzo:** per il prototipo va bene `yfinance`, ma non è adatto a un prodotto commerciale. Per RoyauMoney valuta un fornitore con licenza commerciale (es. Polygon, Twelve Data, EOD Historical Data). Claude Code deve confrontare costi e condizioni di licenza e mettere le opzioni nel file `docs/fonti-dati.md`.

### 3.4 Probabilità sui tassi
Le probabilità tipo CME FedWatch non hanno un'API gratuita. Strada: ricavarle dai prezzi dei future sui Fed funds (ZQ) con la formula standard, oppure usare un fornitore a pagamento. Per il prototipo l'agente può leggerle con la ricerca web.

### 3.5 Dati di Yousef già esistenti
Da integrare in una fase successiva: GEX (gamma exposure), volume profile, posizionamento COT (CFTC, gratuito) e quello che c'è già in Meridian.

### 3.6 Requisiti tecnici
- Ogni serie viene salvata con: valore, data di riferimento, **data di pubblicazione**, fonte e unità. La data di pubblicazione serve per non usare nei backtest dati che a quella data non esistevano ancora.
- Gestione delle revisioni: le serie macro vengono riviste, quindi si conserva lo storico delle versioni.
- Healthcheck: un endpoint `/health/data` che mostra per ogni serie quanto è vecchio l'ultimo dato e segnala quelle in ritardo.

---

## 4. Motore analitico (Fase 2)

### 4.1 Normalizzazione
Per ogni indicatore si calcolano la variazione a 1, 3 e 6 mesi e lo **z-score** su 5 anni, così indicatori diversi diventano confrontabili.

### 4.2 Regime macro
Una classificazione su due assi, con eventuali sottocasi:
- **asse liquidità**: in espansione o in contrazione (liquidità netta Fed + M2 + banche centrali);
- **asse crescita/inflazione**: crescita su/giù × inflazione su/giù.

Si ottiene un regime nominato, per esempio "Liquidità in espansione · disinflazione". Per ogni regime il sistema calcola sullo storico come si sono comportati settori, oro, dollaro e indici.

### 4.3 Punteggio di convergenza (il cuore)
Per ogni scenario (es. "atterraggio morbido", "stagflazione", "recessione", "reflazione"):
- ogni indicatore ha un segno atteso (+ o −) e un peso;
- **voce macro** = media pesata degli z-score degli indicatori macro allineati allo scenario;
- **voce mercato** = la stessa cosa per gli indicatori di mercato;
- **convergenza** = quanto le due voci concordano (da −100 a +100);
- **allarme divergenza** quando le due voci si separano oltre una soglia: va mostrato in modo evidente.

L'output è sempre spiegabile: per ogni scenario l'elenco dei dati che lo **sostengono** e di quelli che lo **contraddicono**, con i valori.

### 4.4 Selezione delle azioni (Fase 5)
1. Si parte dal regime e dallo scenario dominante.
2. I settori vengono classificati in base alla performance storica in quel regime.
3. Dentro i settori, le azioni vengono classificate per fondamentali (crescita, margini, debito, valutazione), momentum e sensibilità ai fattori macro (beta rispetto a tassi, dollaro e liquidità).
4. Output: una lista "più favorite / meno favorite" con la catena logica completa per ciascuna.

---

## 5. Registro delle previsioni (Fase 3)

È l'elemento che crea credibilità. Ogni previsione di Jarvis o di Yousef viene salvata in modo strutturato:

```
previsione:
  id, creata_il, autore (jarvis | yousef)
  asset, direzione, prezzo_ingresso
  obiettivi: [prezzo, entro_data]
  invalidazione: prezzo / condizione
  orizzonte
  probabilità (0–1)
  scenario_collegato, ragionamento
  stato: aperta | colpita | invalidata | scaduta
```

- Un job giornaliero verifica tutte le previsioni aperte rispetto ai prezzi.
- Statistiche: percentuale di successo per asset, orizzonte e tipo di evento; **Brier score** per misurare quanto sono calibrate le probabilità.
- Un pannello "Track record" sempre visibile, perché è l'argomento di vendita più forte.

Esempio da inserire subito come prima previsione registrata (scenario oro del 21/11/2026):
- asset XAU/USD, ingresso 3.537;
- fase 1: rimbalzo 3.720–3.760 entro il 9/12;
- fase 2: discesa 3.380–3.420 dopo Fed (9/12) e CPI (10/12);
- fase 3: 3.900–4.000 entro fine gennaio 2027;
- invalidazione: chiusura settimanale sopra 3.800 prima della Fed, oppure sotto 3.300.

---

## 6. Il cervello di Jarvis (Fase 4)

- Modello: Claude API con **tool use** e streaming.
- Il prompt di sistema definisce il **metodo fisso**: liquidità → regime → conferma del mercato → scenario netto con direzione, obiettivi, tempistica e invalidazione. Niente risposte vaghe; quando i dati sono contraddittori lo dice e spiega perché.
- Strumenti che il modello può chiamare:
  - `query_serie(id, periodo)` per leggere i dati dal database;
  - `punteggio_convergenza(scenario?)`;
  - `regime_attuale()`;
  - `ricerca_web(query)` per notizie, attese e calendario;
  - `registra_previsione(...)` e `track_record(filtro)`;
  - `classifica_azioni(scenario, settore?)`;
  - `mostra(scena)`, il comando che pilota l'interfaccia (vedi sezione 7).
- Ogni numero detto a voce deve venire da uno strumento, mai dalla memoria del modello. Le fonti vengono mostrate sul pannello.
- Memoria di lavoro: le analisi precedenti e le previsioni aperte vengono passate come contesto.

---

## 7. Interfaccia immersiva (Fasi 4–6)

### 7.1 Principio
Niente menu. L'utente chiede e la scena si costruisce da sola, sincronizzata con la voce.

### 7.2 Il direttore di scena
Il cervello non restituisce solo il testo, ma una **sceneggiatura**:

```json
{
  "parlato": "La M2 sta risalendo da sei mesi, e storicamente l'oro la segue con circa tre mesi di ritardo.",
  "scene": [
    {"alla_parola": "M2", "azione": "apri_grafico", "id": "M2SL", "periodo": "5y", "effetto": "particelle"},
    {"alla_parola": "risalendo", "azione": "evidenzia_tratto", "da": "2026-05", "a": "2026-11"},
    {"alla_parola": "oro", "azione": "sovrapponi", "id": "XAUUSD", "sfasamento_mesi": 3},
    {"alla_parola": "ritardo", "azione": "mostra_correlazione", "valore_da": "strumento"}
  ]
}
```

ElevenLabs restituisce i **timestamp** dell'audio, quindi ogni azione parte esattamente quando Jarvis pronuncia quella parola.

### 7.3 Elementi visivi
- **Sfera vocale 3D**: particelle che reagiscono all'ampiezza reale dell'audio, sia la voce dell'utente sia quella di Jarvis. Esiste già un prototipo (`prototype/index.html`).
- **Grafici "olografici"**: entrano componendosi da particelle; la linea si disegna con una scia luminosa; i livelli chiave (es. 3.498) si accendono con un impulso quando Jarvis li nomina.
- **Lente**: passando sopra il grafico, una lente ingrandisce il punto e mostra i dati.
- **Rami di scenario**: lo scenario si divide in rami ("se la Fed alza" / "se si ferma"), ognuno con il suo grafico proiettato. Cambiando ramo, i grafici si deformano in tempo reale.
- **Mappa 3D dei settori**: ogni settore è un nodo che si accende o si spegne secondo il regime; toccandolo si entra nelle azioni.
- **Scroll in profondità**: con lo scroll il grafico attivo viene in primo piano e si ingrandisce, gli altri restano sullo sfondo sfocati; continuando, quello si allontana e arriva il successivo, come un viaggio nello spazio (stessa logica di transizione del configuratore KonfiGlue).
- **Suoni d'interfaccia** leggeri, disattivabili.
- **Pannello convergenza** sempre visibile, con l'allarme divergenza.
- **Pannello track record**.

### 7.4 Stile
Scuro, viola/azzurro, vetro sfocato, linee sottili, numeri in font monospace. Yousef fornirà foto di interfacce di riferimento da replicare: salvarle in `design/riferimenti/` e analizzarle prima di toccare la UI.

### 7.5 Fase successiva
Controllo con i gesti della mano tramite webcam (MediaPipe Hands): afferrare, ingrandire e spostare i grafici.

---

## 8. Voce (Fase 4)
- **ElevenLabs** con il modello più recente, in streaming e con timestamp. Scegliere una voce maschile, calma e autorevole in italiano; poi eventualmente creare una voce dedicata a Jarvis.
- Obiettivo di latenza: meno di 1,5 secondi tra la fine della domanda e l'inizio della risposta. Si ottiene facendo partire il parlato mentre il modello sta ancora generando, frase per frase.
- Interruzione: se l'utente parla mentre Jarvis risponde, Jarvis si ferma.
- Parola di attivazione "Jarvis" (fase successiva).

---

## 9. Fasi e criteri di completamento

| Fase | Contenuto | Fatta quando… |
|---|---|---|
| 0 | Repo, struttura, `.env.example`, CI, prototipo importato | il progetto parte con un comando |
| 1 | Motore dati FRED + prezzi, database, job, healthcheck | tutte le serie della sezione 3 aggiornate ogni giorno, healthcheck verde |
| 2 | Regime + punteggio di convergenza + spiegazioni | endpoint `/analisi/oggi` restituisce regime, scenari, convergenza e divergenze con i dati a sostegno |
| 3 | Registro previsioni + verifica automatica + statistiche | la previsione oro del 21/11 è registrata e viene verificata ogni giorno |
| 4 | Cervello Claude + voce ElevenLabs + direttore di scena + sfera reattiva | domanda a voce → risposta a voce con grafici sincronizzati alle parole |
| 5 | Selezione azioni per regime | lista favorite/sfavorite con catena logica completa |
| 6 | Interfaccia immersiva completa, PWA, scroll in profondità | demo da mostrare a un cliente |
| 7 | Prodotto RoyauMoney: utenti, abbonamenti, lingue (italiano, francese, arabo) | beta chiusa |

---

## 10. Aspetti legali (da non saltare)
Dare raccomandazioni di investimento personalizzate a clienti è un'attività regolamentata: in Italia e in UE dalla normativa MiFID II (Consob), in Marocco dall'AMMC. Finché non ci sono autorizzazioni o un partner autorizzato, RoyauMoney va impostato come **ricerca e informazione finanziaria generale**, con avvertenze chiare, senza consigli personalizzati. Prima del lancio serve il parere di un avvocato esperto di servizi finanziari.

---

## 11. Regole per Claude Code
- Lavorare per fasi, nell'ordine; alla fine di ogni fase mostrare cosa funziona e come provarlo.
- Mai inventare dati: se una fonte non è disponibile, dirlo e proporre alternative.
- Test automatici sul motore analitico (calcoli di z-score, convergenza, verifica delle previsioni).
- Codice e commenti in inglese, testi dell'interfaccia e voce di Jarvis in italiano.
- Chiavi solo in `.env`, mai nel repository.

---

## 12. Primo messaggio da incollare in Claude Code

```
Leggi PIANO_ROYAUMONEY_JARVIS.md: è il piano completo del progetto.
Partiamo dalla Fase 0 e dalla Fase 1.

1. Crea la struttura del repository: backend/ (FastAPI), frontend/ (Next.js),
   prototype/ (ci metto io il file index.html del prototipo), docs/, design/riferimenti/.
2. Crea .env.example con FRED_API_KEY, ANTHROPIC_API_KEY, ELEVENLABS_API_KEY.
3. Implementa il motore dati della sezione 3: verifica ogni ID FRED prima di usarlo,
   salva le serie con data di riferimento, data di pubblicazione, fonte e unità,
   calcola la liquidità netta Fed, il rapporto rame/oro e ciclici/difensivi.
4. Usa yfinance per i prezzi nel prototipo e scrivi in docs/fonti-dati.md
   le alternative con licenza commerciale, con costi.
5. Aggiungi l'endpoint /health/data.

Prima di scrivere codice mostrami un piano breve e le domande che hai.
Alla fine dimmi come avviare tutto e come verificare che i dati arrivino.
```
