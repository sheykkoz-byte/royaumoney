# Registro delle previsioni (Fase 3)

Il registro rende **dimostrabile** l'accuratezza: ogni previsione è scritta prima che accada, non si può modificare e viene verificata ogni giorno in automatico sui prezzi.

## Come è fatta una previsione

| Campo | Significato |
|---|---|
| `author` | `yousef` o `jarvis` |
| `asset` | es. `XAUUSD`, `SPY`, `XLE` (qualunque ticker Yahoo) |
| `direction` | `long`, `short` o `path` (percorso a più fasi) |
| `entry_price` | prezzo di ingresso dichiarato |
| `targets` | obiettivi **in ordine**: zona di prezzo, `touch_above` / `touch_below`, data limite, eventuale "non prima del" |
| `invalidations` | condizioni che smentiscono la previsione: chiusura giornaliera o settimanale sopra/sotto un livello, oppure tocco, con un periodo di validità facoltativo |
| `probability` | probabilità dichiarata (0–1), serve per il Brier score |
| `scenario`, `reasoning`, `tags` | il perché; i `tags` (es. `fed`, `cpi`) danno le statistiche per tipo di evento |
| `align_to_entry` | vedi "Strumento di verifica" |

Stati: **aperta**, **colpita** (tutti gli obiettivi raggiunti in ordine), **invalidata**, **scaduta** (un obiettivo non raggiunto entro la sua data).

## Perché non si può barare

- Alla registrazione il contenuto viene congelato con un'**impronta SHA-256**. Ogni verifica la ricontrolla: se qualcuno modificasse la previsione nel database, la verifica si fermerebbe con un errore.
- Ogni previsione è salvata anche in `registro/P-xxxx.json`, **dentro il repository**. La storia di git mostra quando è stata scritta e che non è cambiata. Un database nuovo, per esempio sul PC, si ricostruisce da lì mantenendo id e data originali (`make previsioni-importa`, o in automatico all'avvio del backend).
- Il **diario degli eventi** non si riscrive: si aggiungono solo righe (registrata, fase raggiunta, invalidata…).
- La verifica ricalcola tutto da zero dalla data di registrazione. Rieseguirla non cambia nulla e non duplica gli eventi.

## Regole di verifica con barre giornaliere

Con un massimo e un minimo al giorno non si sa in che ordine sono avvenute le cose dentro la giornata. Per questo:
- contano solo i prezzi dal **giorno dopo** la registrazione;
- l'obiettivo successivo conta solo dal giorno dopo quello in cui è stato raggiunto il precedente;
- se nello stesso giorno vengono toccati un obiettivo e un'invalidazione, **vale l'invalidazione**: è la lettura prudente;
- la **chiusura settimanale** è l'ultima barra della settimana e conta solo a settimana finita.

## Strumento di verifica per l'oro

Dal 21/11/2026 l'oro si verifica sullo **spot vero XAU/USD di Twelve Data** (strumento `XAUUSD_SPOT`), con apertura, massimo, minimo e chiusura giornalieri e **nessuno scarto fisso**. La chiave si salva come credenziale dell'ambiente cloud, oppure come `TWELVEDATA_API_KEY` nel `.env` locale. Se i prezzi non sono disponibili la verifica lo segnala e, quando tornano, recupera i giorni mancanti dallo storico.

Le fonti scartate:
- `GC=F` (Yahoo) salta di circa 30 $ al cambio di contratto;
- la stima dello spot dai future COMEX (`XAUUSD_EST`, costo di mantenimento) differiva di circa 18 $ dalle quotazioni del broker, uno scarto che andrebbe ricalcolato ogni giorno;
- Stooq ora richiede una verifica anti-bot da browser.

La stima dai future resta nel codice solo per P-0001, che è stata annullata.

## Annullamento

Una previsione si può **ritirare solo prima che esista un qualsiasi prezzo successivo alla registrazione** (`previsioni annulla P-xxxx --motivo …`). Dopo, si può solo chiudere come colpita, invalidata o scaduta. L'annullamento:
- viene scritto in `registro/P-xxxx.annullamento.json` con motivo e sostituta;
- compare nel diario della previsione;
- esclude la previsione dalle statistiche, che riportano comunque quante previsioni sono state annullate.

Esempio: P-0001 è stata annullata il 21/11/2026, prima dell'apertura dei mercati, e sostituita da P-0002 (fase 2 entro il 31/12/2026, probabilità 55%, spot vero).

## Verifica giornaliera nel cloud

Un'attività pianificata (ogni sera alle 23:37, ora di Roma) apre una sessione cloud nuova sull'ambiente `royaumoney`. Lì esegue `uv run python -m app.cli previsioni ciclo`, che:
1. ricostruisce il registro da `registro/*.json`;
2. ricarica i prezzi già salvati in `registro/prezzi/`;
3. scarica i prezzi nuovi;
4. verifica e scrive `registro/stato/P-xxxx.json`, `registro/prezzi/*.csv` e `registro/track-record.json`.

Poi fa commit e push. Se lo scaricamento dei prezzi fallisce, il comando esce con errore e non viene fatto nessun commit.

## Statistiche (track record)

- **Percentuale di successo** = colpite / chiuse, in totale e per asset, autore, orizzonte (≤ 1 settimana, ≤ 1 mese, ≤ 3 mesi, oltre) e tipo di evento (tag).
- **Brier score** = media di (probabilità − esito)², dove l'esito vale 1 se colpita e 0 se invalidata o scaduta. 0 è perfetto; 0,25 equivale a dire sempre 50%. Conta solo le previsioni chiuse con una probabilità dichiarata.
- **Calibrazione**: per fasce di probabilità (0–20%, 20–40%…), quanto spesso le previsioni si sono davvero avverate.
- **Fasi**: quante fasi intermedie sono state raggiunte, anche nelle previsioni poi non colpite.
- Ogni previsione salva il **contesto della Fase 2** al momento della registrazione (regime e punteggi degli scenari), per studiare in seguito in quali regimi il metodo funziona meglio.

## Comandi

```bash
make previsioni                 # elenco e stato
make previsione ID=P-0001       # dettaglio con diario degli eventi
make previsioni-verifica        # verifica adesso (lo fa anche il job delle 07:15 e 23:15)
make track-record               # statistiche
make previsioni-importa         # ricostruisce il database da registro/
cd backend && uv run python -m app.cli previsioni ciclo     # il ciclo giornaliero completo
```

Per registrare una previsione nuova: scrivi un file JSON come `backend/seeds/previsioni/2026-11-21-oro.json` e lancia `cd backend && uv run python -m app.cli previsioni add percorso/file.json`. In alternativa usa `POST /previsioni` (è lo stesso che userà Jarvis in Fase 4).

API: `GET /previsioni`, `GET /previsioni/{id}`, `POST /previsioni`, `GET /track-record`.
