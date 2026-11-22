# Jarvis (Fase 4)

## Stato al 21/11/2026

| Parte | Stato |
|---|---|
| Strumenti del cervello (`backend/app/jarvis/tools.py`) | ✅ fatti |
| Direttore di scena (`backend/app/jarvis/scene.py`) | ✅ fatto |
| Cervello dimostrativo senza AI (`backend/app/jarvis/demo.py`) | ✅ fatto: domande fisse, numeri veri |
| WebSocket `/ws/jarvis` e `POST /jarvis/domanda` | ✅ fatti |
| Frontend: sfera 3D, grafici "olografici", schede, microfono, voce del browser | ✅ fatti (`frontend/src/app/page.tsx`) |
| Cervello Claude (tool use + streaming) | ⏳ serve `ANTHROPIC_API_KEY` |
| Voce ElevenLabs con timestamp | ✅ voce "Daniel", modello `eleven_flash_v2_5`; ogni scena parte sul carattere esatto dell'audio, la sfera segue il volume reale |
| Latenza < 1,5 s, interruzione mentre parla, parola di attivazione | ⏳ con ElevenLabs |

## Come funziona una risposta

```
domanda (voce o testo)
  → WebSocket /ws/jarvis  {"tipo": "domanda", "testo": "Come sta l'oro?"}
  → cervello (oggi: dimostrativo; poi: Claude) chiama gli strumenti
  → sceneggiatura {"parlato": "...", "scene": [{"alla_parola": "oro", "azione": "apri_grafico", "id": "GOLD"}, ...]}
  → direttore di scena: valida, trova dove cade ogni parola, allega i dati veri
  → frontend: parla e fa partire ogni azione quando la voce arriva a quella parola
```

**Strumenti** (formato Anthropic tool use, pronti per Claude): `query_serie`, `elenca_serie`, `regime_attuale`, `punteggio_convergenza`, `previsioni`, `previsione`, `track_record`, `registra_previsione`. Quest'ultimo senza `conferma=true` restituisce solo l'anteprima: Jarvis deve leggerla e registrare solo dopo un sì esplicito. Gli errori di input vengono restituiti come dati, così il modello può correggersi. `classifica_azioni` arriverà con la Fase 5, `ricerca_web` con il cervello Claude (strumento lato server di Anthropic).

**Azioni di scena**:

| Azione | Effetto |
|---|---|
| `apri_grafico` | apre il grafico di una serie |
| `sovrapponi` | aggiunge una seconda serie con la sua scala |
| `mostra_livello` | accende una linea di livello con un impulso |
| `evidenzia_tratto` | evidenzia un periodo nel grafico |
| `mostra_valore` | mostra un numero grande |
| `mostra_correlazione` | calcolata dal direttore sulle variazioni mensili, mai dichiarata dal modello |
| `mostra_regime` | scheda del regime macro |
| `mostra_scenari` | scheda di convergenza e divergenza |
| `mostra_previsione` | scheda di una previsione |
| `chiudi` | toglie un grafico, o tutta la scena |

**Sincronizzazione con la voce**: il direttore calcola l'indice del carattere di ogni parola chiave. Gli accenti vengono ignorati, una parola può essere l'inizio di una più lunga ("risal" trova "risalendo") e l'ordine segue quello del parlato.
- Con la **voce del browser**, gli eventi `boundary` dicono quale carattere si sta pronunciando.
- Se il browser non li invia, valgono i **tempi stimati** (circa 14 caratteri al secondo).
- Con **ElevenLabs** (`backend/app/jarvis/voice.py`) ogni carattere ha il suo istante nell'audio: il backend calcola `tempi_voce` per ogni scena e il frontend (`playAudio` in `src/lib/voice.ts`) le fa partire quando l'audio arriva a quel punto. Se ElevenLabs non risponde, si usa la voce del browser e compare un avviso.
- Voce, modello e modalità si cambiano con `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL` e `VOICE` (`auto` | `elevenlabs` | `browser`). Nel cloud la chiave è una credenziale dell'ambiente `royaumoney` (la inietta la rete), quindi serve `VOICE=elevenlabs`.
- Latenza misurata: 1,0–1,7 s per l'intera risposta. Per stare sempre sotto 1,5 s il passo successivo è sintetizzare frase per frase.

## Provarlo

```bash
make dev
```

Apri http://localhost:3000 e usa i pulsanti, scrivi una domanda, oppure tocca il microfono (il riconoscimento vocale funziona su Chrome). La pagina con lo stato dei dati e il track record è su http://localhost:3000/stato.

In modalità dimostrativa il badge giallo in alto lo segnala. Jarvis risponde su oro, regime, scenari e convergenza, liquidità e M2, lavoro, previsioni. Ogni numero viene dal database.

## Collaudo del 21/11/2026 (cervello dimostrativo + ElevenLabs)

Backend vero, dati scaricati con `make ingest` (44 serie verdi su 45, XLE senza dati da Yahoo).

| Domanda | Tempo | Esito |
|---|---|---|
| Come sta l'oro? | 1,7 s | ✅ 3.515 $, −33,9% dal massimo di chiusura 5.318; 5 scene, la prima a 0,17 s di audio |
| In che regime siamo? | 7,8 s (prima chiamata) | ✅ Liquidità in espansione · Reflazione, asse liquidità al confine |
| Quali sono gli scenari? | 0,9 s | ✅ Stagflazione e Reflazione quasi alla pari |
| Cosa dice la liquidità? | 1,1 s | ✅ Fed netta 5.825 mld, M2 23.414 mld, correlazione M2→oro 0,11 |
| Come va il lavoro? | 0,7 s | ✅ disoccupazione 4,1%, +165 mila posti |
| Come vanno le previsioni? | 0,7 s | ✅ P-0002 aperta |
| Che tempo fa a Roma? | 0,6 s | ✅ risposta di ripiego |

- **Ripiego con chiave non valida:** 401 da `api.anthropic.com` → risponde il cervello dimostrativo e `cervello_errore` lo segnala. L'host è raggiungibile dalla rete dell'ambiente.
- **Corretto:** con il database vuoto (container nuovo) oro e liquidità andavano in errore e il regime dava il testo di ripiego. Ora Jarvis dice che mancano i dati e di lanciare `make ingest` (test `test_demo_empty_database_says_data_is_missing`).
- **Script di avvio dell'ambiente:** ora lancia anche l'ingest (log in `/tmp/ingest.log`; se fallisce la sessione parte lo stesso).
- **Da fare:** collaudo del cervello Claude con la chiave vera. La variabile `ANTHROPIC_API_KEY` è nell'ambiente `royaumoney` ma una sessione la legge solo se nasce dopo che è stata aggiunta.

## Artefatto (Jarvis senza backend e senza chiavi)

`frontend/artifact/`: l'interfaccia vera (sfera, grafici, schede) impacchettata in un'unica pagina pubblicata come artefatto claude.ai. Una finta WebSocket (`fake-ws.ts`) sostituisce il backend:

- **Cervello Claude sull'account di chi guarda** (`brain.ts`, capacità `sample`): nessuna chiave API. Stesso prompt di `claude_brain.py` (adattato: dati nel prompt, niente registrazione, niente correlazione), stesso copione JSON. I dati sono i risultati degli strumenti di `tools.py` registrati in `data.json` da `record_data.py`: 45 serie con tutti i periodi, regime, scenari, previsioni, track record. Il direttore di scena è portato in JavaScript: scarta i numeri che non vengono dai dati, allinea le parole, allega i dati ai grafici. Memoria: ultime 4 domande.
- **Voce di Claude** (`tts-voice.ts`, capacità `tts`) al posto della sintesi del browser: una frase per riga, le scene partono all'inizio della frase e avanzano a ≈14 caratteri al secondo.
- **Microfono** (`mic.ts`, capacità `dictation`): funziona su Chrome e nell'app desktop di Claude, non su Safari, Firefox o le app per telefono.
- **Ripiego**: se Claude non è disponibile o non è autorizzato, risponde il cervello dimostrativo con le risposte registrate dal backend (`snapshot.json`, `record.py`, voce ElevenLabs), e l'interfaccia lo segnala.

Test: `frontend/artifact/test.sh DATA_JSON` (direttore, controllo dei numeri, adattamenti del prompt, dimensione del prompt). Rigenerare con dati nuovi (backend acceso su :8000):

```bash
frontend/artifact/build.sh /percorso/uscita
```

Pubblicare `index.html` con `app.js`, `snapshot.json`, `data.json` e le capacità `{sample: {}, tts: {}, dictation: {}}`.

## Note sui dati mostrati

- L'oro nel grafico è il **future COMEX continuo** (`GC=F`) su prezzi di **chiusura**: il "massimo storico" è quello di chiusura (5.318), non il massimo intraday spot (5.598,75). La verifica delle previsioni invece usa lo spot vero di Twelve Data.


## Cervello Claude

`backend/app/jarvis/claude_brain.py`. Si attiva quando c'è `ANTHROPIC_API_KEY` (impostazione `BRAIN`: `auto` | `demo`).

- **Modello:** `claude-opus-5-5`, effort `medium` (`JARVIS_MODEL`, `JARVIS_EFFORT`: `low` per risposte più rapide). Con il `fallback` lato server, se il modello rifiuta una richiesta ne risponde un altro.
- **Metodo fisso nel prompt di sistema:** liquidità → regime → conferma del mercato → scenario netto con direzione, obiettivi, tempistica e invalidazione. Le divergenze vanno dette chiaramente. È informazione generale, non consulenza personalizzata (piano, sezione 10).
- **Numeri:** Claude li legge con gli strumenti di `tools.py`. Le scene `mostra_livello` e `mostra_valore` con un numero che nessuno strumento ha restituito vengono **scartate** e elencate in `scene_scartate`.
- **Risposta:** JSON vincolato a uno schema (`parlato` + `scene`), poi il direttore di scena lo sincronizza con la voce.
- **Memoria:** la WebSocket conserva le ultime domande e risposte della conversazione (serve, per esempio, a confermare una previsione con "sì").
- **Cache:** strumenti e prompt di sistema sono in cache tra una domanda e l'altra.
- **Se Claude non risponde** (rete, chiave, rifiuto): risponde il cervello dimostrativo e l'interfaccia lo segnala.
- **Chiave nel cloud:** va come variabile d'ambiente `JARVIS_ANTHROPIC_API_KEY` dell'ambiente `royaumoney`. Il nome `ANTHROPIC_API_KEY` non arriva alle sessioni cloud: lo usa Claude Code per sé (verificato il 21/11/2026 con una sessione nuova). Le chiavi Anthropic non possono essere credenziali di rete; serve una sessione nuova per leggerla. In locale: `.env`, con uno dei due nomi.
- **Latenza:** con 2–4 chiamate agli strumenti una risposta richiede alcuni secondi; per scendere sotto 1,5 s servirà lo streaming frase per frase verso la voce.
