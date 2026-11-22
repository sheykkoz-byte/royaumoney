# Regime & Quality Engine (Dalio × Buffett)

Modulo `backend/app/rqe/`, dashboard su `/regime` (dati in `frontend/public/rqe/rqe.json`, scritti da `python -m app.cli rqe` e dal job giornaliero). Tutte le scelte di metodo stanno in `backend/app/rqe/config.py`.

## 1. Motore macro (Dalio)

| Segnale | Componenti (peso) |
|---|---|
| **Crescita** | produzione manifatturiera a/a (0,30) · vendite al dettaglio reali a/a (0,25) · disoccupazione, segno invertito (0,25) · GDPNow (0,20, dal 2011) |
| **Inflazione** | CPI a/a (0,30) · core PCE a/a (0,30) · inflazione attesa a 5 anni (0,20, dal 2003) · prezzi alla produzione PPI a/a (0,20) |

Ogni componente è la sua variazione a 3 e 6 mesi rispetto agli ultimi 5 anni (z-score robusto, limitato a ±3); per GDPNow, che è già un tasso di crescita, il livello. Il segnale è la media pesata delle componenti disponibili.

**Il PMI ISM non c'è:** dal 2016 non è più su FRED per licenza. Al suo posto c'è la produzione manifatturiera (`IPMAN`).

**Probabilità:** P(crescita sopra il trend) = Φ(segnale/σ), con σ = 0,6; lo stesso per l'inflazione. Le probabilità dei quattro regimi sono i prodotti:

| | Inflazione su | Inflazione giù |
|---|---|---|
| **Crescita su** | B · Reflazione | A · Goldilocks |
| **Crescita giù** | C · Stagflazione | D · Deflazione / recessione |

**Point in time vero:** per ogni fine mese dal 2000 le serie sono ricostruite **come si conoscevano quel mese**, revisioni comprese (versioni ALFRED). La storia è in cache (`backend/data/cache/rqe_regime_history.csv`): un mese passato non cambia più, quindi si calcolano solo i mesi nuovi.

Verifiche: giugno 2008 Stagflazione 77% · dicembre 2008 Deflazione 100% · settembre 2009 Goldilocks 74% · aprile 2020 Deflazione 95% · giugno 2021 Reflazione 100%.

## 2. Asset allocation

- **Base All Weather in risk parity:** azioni (SPY), Treasury lunghi (TLT), intermedi (IEF), TIPS (TIP), oro (GLD), materie prime (DBC); pesi inversamente proporzionali alla volatilità degli ultimi 12 mesi. Senza leva: rispetto all'All Weather originale (che usa la leva sulle obbligazioni) il portafoglio pesa di più le obbligazioni e rende meno.
- **Tilt:** peso × (1 + 0,5 × Σ probabilità × preferenza del regime), con preferenze da −1 a +1 per asset e regime; probabilità medie sugli ultimi 3 mesi; ogni peso resta entro **±10 punti** dalla base; la liquidità sale fino a 10 punti quando i regimi che la preferiscono sono probabili. Le preferenze in uso sono quelle **imparate** (vedi Taratura); quelle teoriche di Dalio sono in `TILTS`.

## 3. Backtest (dal 2000, mensile)

Prima degli ETF i rendimenti sono ricostruiti: obbligazioni e TIPS da rendimenti FRED (carry − duration × variazione; TIPS dal 2003), oro dal future, materie prime da un paniere di future (petrolio, oro, rame). Costo di 10 punti base per unità di turnover.

Risultato al 22/11/2026 (luglio 2000 – ottobre 2026), con il tilt tarato:

| Strategia | Rendimento annuo | Volatilità | Sharpe | Perdita massima |
|---|---|---|---|---|
| Risk parity | 5,6% | 6,3% | 0,60 | −15,5% |
| Risk parity + regime (tarato) | 5,8% | 6,4% | 0,62 | −16,5% |
| 60/40 | 7,0% | 9,0% | 0,59 | −29,5% |

### Taratura del tilt (`rqe/calibrate.py`, `python -m app.cli rqe-taratura`)

Per non adattare le regole al passato: i parametri si **scelgono solo sul 2000–2012** e si **giudicano sul 2013–oggi**, mai visto dalla scelta. Candidati (31):
- preferenze teoriche con forza 0 / 0,25 / 0,5 / 1 (0 = risk parity puro);
- σ 0,4 / 0,6 / 1,0;
- probabilità medie su 1, 3 o 6 mesi;
- preferenze **imparate in modo progressivo**: ogni mese si stimano solo dai mesi precedenti (rendimento del mese dopo rispetto al risk parity, pesato per la probabilità del regime), con prudenza statistica (poca storia → poco tilt) e almeno 5 anni di dati.

**Diagnosi:** la relazione regime → rendimento del mese dopo **cambia segno** tra i due periodi (per esempio materie prime in Goldilocks: +1,63% al mese in più nel 2000–2012, −1,17% nel 2013–2026). Le preferenze teoriche concordano col segno dei dati nel 32% dei casi nel primo periodo e nel 56% nel secondo.

**Scelta (sul solo 2000–2012):** preferenze imparate, media di 3 mesi, σ 0,6, forza 0,5. **Verifica 2013–2026:** Sharpe 0,33 contro 0,30 del risk parity puro, rendimento annuo 3,7% contro 3,5%, perdita massima −16,5% contro −15,5%. **Statistica t 1,7** (serve circa 2): **la differenza può essere rumore**. L'errore dello Sharpe su 14 anni è circa ±0,27.

**Cosa hanno imparato le preferenze:** soprattutto più azioni e oro e meno TIPS e liquidità quasi in ogni regime, cioè una preferenza stabile per gli asset più rischiosi rispetto a un risk parity che pesa molto le obbligazioni, più che un vero tempismo sui regimi. L'unico segnale specifico è in stagflazione: meno azioni e materie prime, più Treasury lunghi e oro.

**Conclusione:** il tilt è attivo come previsto dalla procedura (`TILT_MODE = "imparato"`, `SMOOTH_MONTHS = 3` in `config.py`), ma non ha ancora dimostrato un vantaggio reale e la dashboard lo dice. Per tornare alle preferenze teoriche basta `TILT_MODE = "teorico"`. La taratura va rifatta quando cambiano i segnali o le preferenze; il riepilogo è in `docs/rqe-taratura.json`.

## 4. Alert

Cambio di regime: quando il regime più probabile cambia e il nuovo supera il 40%. Gli alert sul margine di sicurezza arriveranno con lo screener.

## 5. Screener (Buffett) — in attesa dei dati FMP

Regole già in `config.py`: ROE medio > 15%, debito/EBITDA < 2, free cash flow positivo e in crescita, margini lordi alti e stabili, DCF con margine di sicurezza ≥ 25% (sconto = Treasury 10 anni + 5%, minimo 8%), pesi dei filtri per regime, settori favoriti per regime. Serve la chiave FMP. Il backtest dello screener non si fa: i bilanci FMP non sono point-in-time e l'universo ha il bias di sopravvivenza.

Allocazione modello a scopo di ricerca, non consulenza personalizzata (piano, sezione 10).
