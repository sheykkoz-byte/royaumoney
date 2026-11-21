# Fonti dati

Aggiornato al 21/11/2026. I prezzi dei fornitori cambiano spesso: prima di firmare, verificarli sempre sulle pagine ufficiali (link in fondo).

## 1. Cosa usa oggi il prototipo

| Dato | Fonte | Costo | Si può usare in un prodotto commerciale? |
|---|---|---|---|
| Liquidità, macro, tassi, spread, dollaro, cambi (22 serie) | FRED (Fed di St. Louis) | Gratis | **Sì, con attenzione**: i dati prodotti dalla Fed e da altri enti pubblici USA sono riutilizzabili. Alcune serie su FRED appartengono a terzi con diritti propri (vedi sotto gli spread ICE). |
| Oro, rame, petrolio, VIX, 11 ETF settoriali | Yahoo Finance tramite `yfinance` | Gratis | **No.** I termini di Yahoo vietano l'uso commerciale e `yfinance` non è un'API ufficiale: può smettere di funzionare senza preavviso. Va bene solo per il prototipo. |

### Avvertenze sulle serie FRED

- **Spread ICE BofA (`BAMLH0A0HYM2`, `BAMLC0A0CM`)**: per licenza ICE, FRED pubblica **solo gli ultimi 3 anni** (oggi dal 21/11/2023). Questo non basta per lo z-score su 5 anni previsto in Fase 2. Le alternative sono:
  - comprare lo storico da ICE o da un fornitore che lo redistribuisce;
  - usare come approssimazione lo spread Moody's Baa − Treasury 10 anni (`BAA10Y` su FRED, storico lungo, ma solo investment grade);
  - accumulare lo storico da qui in avanti, che però resta corto per anni.
- **M2 Cina / bilancio PBoC**: FRED **non ha dati aggiornati**. La serie IMF `MYAGM2CNM189N` si ferma ad agosto 2019, quella OCSE al 2013. Le alternative sono:
  - **PBoC, sito ufficiale**: gratis, mensile, tabelle HTML/PDF in 100 milioni di yuan. Va estratto con uno scraper, quindi è fragile. È la fonte autorevole.
  - **BIS, Central bank total assets**: gratis, con API. Il nostro ambiente cloud oggi blocca `stats.bis.org`: va abilitato. Resta da verificare la copertura della Cina.
  - **Trading Economics, CEIC, YCharts**: **a pagamento**, con licenze per la redistribuzione.

  Proposta: in Fase 2 partire con Fed + BCE + BoJ, già in database, e aggiungere la Cina dalla PBoC o dalla BIS come lavoro separato.
- **Data di pubblicazione**: senza chiave FRED il motore usa l'export CSV pubblico, che non ha lo storico delle versioni. In quel caso la data di pubblicazione dello storico è **stimata** (data di riferimento + ritardo tipico di pubblicazione, `pub_method = estimated_lag`). I dati nuovi hanno la data in cui il job li ha visti per la prima volta (`first_seen`, precisa a ±1 giorno). Con la `FRED_API_KEY` le serie che vengono riviste (M2, CPI, PCE, lavoro, sussidi) si scaricano da ALFRED con le date di pubblicazione esatte (`alfred`). **Per i backtest serve la chiave.**

## 2. Alternative con licenza commerciale per i prezzi

| Fornitore | Prezzi indicativi pubblici | Licenza commerciale / visualizzazione ai clienti | Note |
|---|---|---|---|
| **Massive** (ex Polygon.io) | Piani individuali ~0 / 29 / 79 / 199 $ al mese (fonti terze, discordanti) | I piani individuali **non** coprono l'uso commerciale. Per un business serve il piano Business, con prezzo non pubblico e da negoziare con il commerciale. | Ottimo per azioni ed ETF USA; futures e indici sono prodotti separati. |
| **Twelve Data** | Piano Basic gratuito; prezzi dei piani a pagamento sulla pagina ufficiale | I piani individuali sono solo per uso personale. Un'azienda deve usare i piani **Business** anche per uso interno. La **redistribuzione** richiede un accordo separato (add-on per le azioni USA). I prezzi non USA richiedono un'approvazione per l'uso commerciale. | Copre azioni globali, forex, materie prime ed ETF. |
| **EODHD** (EOD Historical Data) | Commercial internal use da ~399 $ al mese; tier superiori ~2.499 $ al mese (pagina commercial pricing) | Qualunque uso non personale è commerciale. Visualizzazione e redistribuzione si negoziano caso per caso. EODHD deve segnalare gli utenti commerciali alle borse. | Molto ampio: include la Borsa di Casablanca, utile per il pubblico marocchino. Da verificare. |
| **Tiingo** | 30 $ al mese (Power, individuale); ~50 $ al mese per uso commerciale interno | Solo uso interno. Per mostrare i dati ai clienti serve una **licenza di redistribuzione**, a prezzo fisso non pubblico. | Economico per iniziare; poca copertura di futures e materie prime. |

### Raccomandazione

1. **Fino alla beta chiusa (Fase 7)**: FRED + yfinance, usati solo internamente da Yousef. Nessun cliente vede prezzi Yahoo.
2. **Prima di mostrare dati a clienti**: chiedere un preventivo a **EODHD** (copertura Casablanca + USA + materie prime) e a **Twelve Data** (forex e oro spot XAU/USD). Lo scopo va descritto con precisione: *"visualizzazione di grafici e indicatori derivati agli abbonati, senza esportazione dei dati grezzi"*. I dati derivati (z-score, rapporti, punteggi) spesso costano meno della redistribuzione dei prezzi grezzi.
3. **Oro**: il registro delle previsioni usa XAU/USD **spot**, mentre il prototipo usa il future `GC=F`, che di solito sta qualche dollaro sopra lo spot. Con un fornitore commerciale conviene passare allo spot.

Nel codice, sostituire Yahoo significa scrivere un nuovo modulo in `backend/app/sources/` che restituisca gli stessi `RawPoint`. Il resto del motore non cambia.

## 3. Probabilità sui tassi (Fase 2+)

Non esiste un'API gratuita tipo CME FedWatch. Le strade possibili sono:
- calcolare le probabilità dai future sui Fed funds (ZQ) con la formula standard, che richiede i prezzi ZQ da un fornitore di futures;
- per il prototipo, usare la ricerca web del cervello di Jarvis.

## Fonti consultate

- [Massive (ex Polygon) – pricing, apis.io](https://apis.io/plans/polygon/polygon-plans-pricing/) · [FinOps profile](https://apis.io/finops/massive-com/polygon-finops/) · [QVeris guide](https://try.qveris.ai/polygon-pricing-optimized/)
- [Twelve Data – pricing](https://twelvedata.com/pricing) · [Uso commerciale e personale](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage) · [Business](https://twelvedata.com/pricing-business)
- [EODHD – commercial pricing](https://eodhd.com/commercial-pricing) · [Commercial vs personal](https://eodhd.com/financial-apis/commercial-vs-personal-license-use) · [B2B](https://eodhd.com/lp/b2b-solution)
- [Tiingo – documentazione](https://api.tiingo.com/documentation) · [Massive vs Tiingo](https://massive.com/compare/massive-vs-tiingo)
- [FRED – M2 Cina (MYAGM2CNM189N)](https://fred.stlouisfed.org/series/MYAGM2CNM189N) · [BIS – CBTA](https://www.bis.org/statistics/cbta/cbta_doc.pdf) · [Alphacast – bilancio PBoC](https://www.alphacast.io/datasets/monetary-china-people-s-bank-of-china-total-assets-and-liabilities-36138)
