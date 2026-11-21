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
- **Chiave nel cloud:** va come variabile d'ambiente `ANTHROPIC_API_KEY` dell'ambiente `royaumoney` (le chiavi Anthropic non possono essere credenziali di rete); serve una sessione nuova per leggerla. In locale: `.env`.
- **Latenza:** con 2–4 chiamate agli strumenti una risposta richiede alcuni secondi; per scendere sotto 1,5 s servirà lo streaming frase per frase verso la voce.
