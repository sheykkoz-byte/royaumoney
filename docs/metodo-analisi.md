# Metodo di analisi (Fase 2)

Come il motore passa dai dati grezzi al regime, agli scenari e all'allarme divergenza.
Tutte le scelte numeriche (indicatori, pesi, soglie) stanno in un solo file,
`backend/app/analysis/config.py`, così si possono rivedere senza toccare i calcoli.

## 1. Indicatori normalizzati

Ogni indicatore nasce da una o due serie del database con una trasformazione:

| Trasformazione | Esempio |
|---|---|
| livello | disoccupazione, spread, VIX |
| variazione a/a | CPI, core PCE, produzione industriale |
| media 4 settimane | richieste iniziali di sussidio |
| media 3 mesi della variazione mensile | payroll |
| differenza tra due serie | Treasury 2 anni − Fed funds (quanti rialzi o tagli prezza il mercato) |

Per ogni data si calcolano:
- le **variazioni a 1, 3 e 6 mesi**: in % per le grandezze in livelli (bilanci, prezzi), in punti per tassi e percentuali;
- lo **z-score su 5 anni** del valore e di ogni variazione, cioè quanto il dato è insolito rispetto agli ultimi 5 anni. Per gli spread ICE (high yield e investment grade) la finestra è di **3 anni**, perché FRED non ne ha di più;
- la **variazione scalata**: la variazione divisa per la sua ampiezza tipica. Non sottrae la media, quindi il segno resta quello della variazione e dice se l'indicatore sale o scende. Serve per il regime.

Ogni riga ha anche la data in cui era **conoscibile**, cioè la data di pubblicazione. L'analisi di un giorno passato usa solo i dati già pubblicati quel giorno, comprese le revisioni successive da escludere.

## 2. Regime macro

Tre assi, ognuno è la media pesata delle variazioni scalate (limitate a ±3):

| Asse | Componenti (peso) |
|---|---|
| **Liquidità** | liquidità netta Fed a 3 mesi (0,4) · M2 a 6 mesi (0,3) · bilancio BCE a 6 mesi (0,15) · bilancio BoJ a 6 mesi (0,15) |
| **Crescita** | payroll (0,3) · disoccupazione, segno invertito (0,3) · richieste di sussidio, segno invertito (0,2) · produzione industriale a/a (0,2) |
| **Inflazione** | CPI a/a (0,5) · core PCE a/a (0,5) |

Asse > 0: in espansione o in accelerazione; asse < 0: in contrazione o in rallentamento. Un asse con valore assoluto sotto 0,25 viene segnalato come **al confine**.

Il nome del regime è *Liquidità in espansione/contrazione* · *quadrante*:

|  | Inflazione su | Inflazione giù |
|---|---|---|
| **Crescita su** | Reflazione | Goldilocks |
| **Crescita giù** | Stagflazione | Rallentamento disinflazionistico |

**Storico dei regimi**: per ogni fine mese dal 2004 si ricalcola il regime con i soli dati pubblicati a quella data. Poi si misura il rendimento del **mese successivo** di S&P 500, oro, dollaro e degli 11 settori, confrontato con la media di tutti i mesi.

## 3. Scenari e convergenza

Ci sono quattro scenari: **atterraggio morbido, stagflazione, recessione, reflazione**. Per ognuno, ogni indicatore ha un **segno atteso** (alto o basso) e un **peso**.

- **z allineato** = segno × z-score, limitato a ±3. Positivo = il dato sostiene lo scenario.
- **Voce della macro** = media pesata degli z allineati degli indicatori macro (liquidità, inflazione, lavoro, produzione, tassi ufficiali).
- **Voce del mercato** = la stessa cosa per gli indicatori di mercato (curva, spread di credito, rame/oro, ciclici/difensivi, dollaro, VIX, petrolio, oro, breakeven, prezzi impliciti della Fed).
- **Punteggio** (−100…+100) = media delle due voci, dove 2σ vale 100.
- **Convergenza** (−100…+100) = 100 · m · k / max(m², k²):
  - +100: le due voci dicono la stessa cosa con la stessa forza;
  - −100: dicono cose opposte;
  - ~0: una delle due voci tace.
- **Allarme divergenza**: scatta quando la distanza tra le due voci è più ampia del **90% dei mesi precedenti** (soglia calcolata scenario per scenario sullo storico dal 2004). Con meno di 36 mesi di storico la soglia è fissa a 1,5σ.
  - Se è il **mercato** a essere più avanti, il mercato prezza un cambiamento che i dati non mostrano ancora: il segnale più prezioso, come dice il piano.
  - Se è la **macro** a essere più avanti, i dati vanno in una direzione ma il mercato non ci crede.
- **Verdetto**: c'è uno scenario dominante solo se il suo punteggio è almeno 20 e supera il secondo di almeno 10 punti. Altrimenti l'analisi dice esplicitamente che **i dati sono contrastanti**.

Per ogni scenario l'output elenca i dati che lo **sostengono**, quelli che lo **contraddicono** e quelli **neutri**, con valore, z-score e data.

## 4. Verifica sul passato

Analisi rifatte con i soli dati disponibili a quelle date:

| Data | Regime | Verdetto |
|---|---|---|
| 31/10/2008 | Liquidità in espansione · Stagflazione | **Recessione 94**: macro +2,33, mercato +1,42, convergenza 61. Allarme divergenza su "stagflazione": la macro la vedeva, il mercato no (l'inflazione poi è crollata) |
| 30/04/2020 | Liquidità in espansione · Rallentamento disinflazionistico | **Recessione 100**: richieste di sussidio a +7,6σ |
| 30/06/2022 | Liquidità in contrazione · Rallentamento disinflazionistico | Nessuno scenario prevale: segnali contrastanti |

Si rifanno con `make analisi AS_OF=2008-10-31`.

## 5. Limiti noti

- Gli spread ICE hanno solo 3 anni di storico: z-score su 3 anni, affiancati dallo spread Baa con storico lungo.
- ALFRED non ha la prima versione di alcune osservazioni vecchie (richieste di sussidio prima del 2009): per quelle la data di pubblicazione è stimata.
- Pesi e soglie sono scelte ragionate, non ottimizzate: andranno messe alla prova con il registro delle previsioni (Fase 3).
- Manca ancora la liquidità cinese (vedi `fonti-dati.md`).
