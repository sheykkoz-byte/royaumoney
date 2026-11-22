# Cabina del trader (uso personale)

Piattaforma **di sola visione** (nessun ordine): è la **pagina principale** del sito (`frontend/src/app/page.tsx`, indirizzo `/`; `/cabina` porta lì). Jarvis con la sfera grande è su `/jarvis`.

## Disposizione

Pensata per un monitor 49" 32:9 (5120×1440), da sinistra a destra:

| Zona | Contenuto |
|---|---|
| Watchlist | Preferiti (★, nell'ordine scelto) e tutti i mercati per categoria, con ricerca. Si può aggiungere qualsiasi simbolo TradingView scrivendolo per intero (es. `NASDAQ:AMD`). |
| Grafico principale | Grafico TradingView a candele, con timeframe da 1 minuto a settimanale, indicatori e strumenti di disegno. |
| Grafici di controllo | Quattro grafici giornalieri. ⇄ mette nello spazio il simbolo del grafico principale. |
| Plancia macro | Metriche macro con valore, variazioni, mini-grafico e semaforo. Un clic apre la metrica sul grafico principale. |
| Jarvis | Sfera, regime macro, convergenza e scenari, previsione aperta. |

In alto ci sono la barra dei prezzi dei preferiti e gli orologi delle borse (orari regolari, festività escluse).

Sotto i 3200 px di larghezza i grafici di controllo vanno sotto il grafico principale. Sotto i 2000 px plancia e Jarvis condividono la colonna destra. Sotto i 1100 px tutto si dispone in una colonna sola.

Preferiti, simbolo, timeframe e grafici di controllo restano salvati nel browser.

## Simboli e TradingView

I grafici sono i widget gratuiti di TradingView. Non sono collegati all'account TradingView personale, quindi layout e disegni salvati lì non compaiono.

Nei grafici incorporati TradingView **non concede** alcuni simboli (verificato il 22/11/2026 aprendo ogni simbolo):
- i suoi indici "TVC": DXY, VIX, rendimenti dei bond, indici esteri;
- i future CME e ICE: rame, gas, agricole, oro future;
- Ferrari (`MIL:RACE`).

Al loro posto ci sono:

| Mercato | Simbolo usato | Nota |
|---|---|---|
| DXY | `CAPITALCOM:DXY` | CFD |
| VIX ufficiale | `FRED:VIXCLS` | indice CBOE, chiusura giornaliera: è lo stesso dato della plancia e del grafico di controllo |
| VIX in tempo reale | `CAPITALCOM:VIX` | **CFD sul future**: può essere molto diverso dall'indice (il 22/11: 26,4 contro 35,9) |
| Rendimenti USA, curve, reale, Fed funds | `FRED:DGS2`, `FRED:DGS10`, `FRED:T10Y2Y`… | dati ufficiali, chiusura giornaliera |
| Bund 10 anni | `TRADEWEB:DE10Y` | |
| BTP, Gilt, JGB, spread BTP−Bund | `FRED:IRLTLT01…` | mensili |
| Indici esteri | `CAPITALCOM:EU50`, `UK100`, `J225`, `HK50`, `FOREXCOM:US2000` | CFD |
| Agricole e gas | `CAPITALCOM:…` | CFD |
| Rame, platino, palladio | `OANDA:XCUUSD`, `XPTUSD`, `XPDUSD` | spot |

Quando si aggiunge un simbolo, se il grafico dice «disponibile solo su TradingView» quel simbolo non è concesso nei widget: va cercato un equivalente (CFD, FRED, altro fornitore).

## Plancia macro

`backend/app/cabina.py` scrive `frontend/public/cabina/macro.json` (comando `python -m app.cli cabina`) dai dati del database. Contiene valore, data, variazioni (1 giorno, 1 mese, 1 anno; i tassi in punti base), un anno di mini-grafico e il semaforo. Contiene anche regime, convergenza e previsioni aperte per la colonna Jarvis.

### Regole dei semafori

Sono regole pratiche che descrivono la situazione, **non segnali operativi**. Si cambiano in un solo posto (`RULES` in `cabina.py`) e sono coperte da test (`tests/test_cabina.py`).

| Metrica | 🟢 | 🟡 | 🔴 |
|---|---|---|---|
| Curva 10−2 | > 0,25 | 0–0,25, oppure tornata positiva dopo un'inversione negli ultimi 12 mesi | < 0 (invertita) |
| Treasury 2 e 10 anni | — | +20…40 pb in un mese, o −40 pb | ≥ +40 pb in un mese |
| CPI e Core PCE (anno) | ≤ 2,5% | ≤ 3,5% | > 3,5% |
| Inflazione attesa 10 anni | 1,8–2,6% | 1,5–1,8% o 2,6–3,0% | fuori |
| Dollaro (indice ampio, 3 mesi) | < −1% | +1…+3% | > +3% |
| VIX | < 16 | 16–25 | ≥ 25 |
| Spread high yield | < 4 | 4–5,5 | ≥ 5,5 |
| Liquidità netta Fed (3 mesi) | > +1% | −3…+1% | < −3% |
| M2 (anno) | > 4% | 0–4% | < 0 |
| Disoccupazione (regola di Sahm: media 3 mesi contro il minimo dei 12 mesi precedenti) | < +0,3 | +0,3…+0,5 | ≥ +0,5 |
| Payroll (media 3 mesi) | > 150 mila | 50–150 mila | < 50 mila |
| Richieste di sussidio (media 4 settimane contro il minimo dell'anno) | < +15% | +15…+30% | ≥ +30% |
| Rame/oro, ciclici/difensivi (3 mesi) | in salita | in calo | — |

## Online in privato

Il sito si pubblica su Vercel (cartella `frontend`). Con la variabile `CABINA_PASSWORD` impostata, ogni pagina chiede la password (`src/middleware.ts`); senza, il sito è aperto, cosa che va bene solo in locale.

## Finestra di spiegazione dei riquadri

Un clic su un riquadro della plancia apre una finestra (`frontend/src/components/cabina/TileModal.tsx`), che si apre dal riquadro stesso con un'animazione. Contiene:
- **semaforo e valore** (il numero "conta" fino al valore di oggi) con le variazioni a 1 giorno, 1 mese e 1 anno; per gli indicatori di tensione (VIX, spread, sussidi, disoccupazione, inflazione) la salita è in rosso;
- il **grafico** a **1, 3 o 5 anni** (selettore sopra il grafico; lo storico lungo è in `storico` nel JSON della plancia), che si disegna da solo; passandoci sopra si leggono data e valore di ogni punto;
- la **scala "Dove siamo"**: le zone verde/giallo/rosso con le stesse soglie del semaforo (`scale()` in `backend/app/cabina.py`, un test verifica che zona e colore coincidano) e un indicatore che scivola sul valore di oggi;
- **Oggi** (la lettura del semaforo e la sintesi della sezione), **Cosa vuol dire** (il significato dell'indicatore) e **Perché conta** (la sezione), da `backend/app/cabina_guide.py` (regole fisse, senza AI);
- ← → per passare agli altri riquadri della sezione, Esc per chiudere, e il pulsante **Apri sul grafico principale** (prima era l'azione del clic).

All'apertura, un breve **suono** sintetizzato (Web Audio, nessun file: un soffio e due note, più chiare col verde e più gravi col rosso, `frontend/src/lib/sfx.ts`) e una **esplosione di particelle** del colore del semaforo. Nella finestra due interruttori, ricordati dal browser: **Suoni** acceso/spento e **Animazioni piene/ridotte** (con "ridotte" tutto compare subito, senza movimento).

In cima alla plancia resta "Come leggere i semafori". I testi si aggiornano con la plancia (`python -m app.cli cabina`). Con "riduci movimento" attivo nel sistema le animazioni si spengono.
