// Plain-language explanations of Dalio's four economic seasons and the terms around them.
// Educational text: the numbers shown next to it always come from the data files.

export type Q = "A" | "B" | "C" | "D";

export const SPIEGAZIONI: Record<Q, {
  breve: string; cosa: string; perche: string; bene: string[]; male: string[]; esempi: string; segnali: string;
}> = {
  A: {
    breve: "Crescita sopra le attese, inflazione sotto le attese.",
    cosa: "L'economia accelera ma i prezzi restano calmi. Le aziende vendono di più senza che i costi esplodano, le banche centrali non hanno bisogno di stringere: è lo scenario «né troppo caldo né troppo freddo», da cui il nome della favola di Riccioli d'oro.",
    perche: "Di solito arriva dopo una fase di aggiustamento: produttività in salita, catene di fornitura scorrevoli, energia a buon mercato, tassi stabili o in calo.",
    bene: ["Azioni, soprattutto di crescita (tecnologia, consumi discrezionali)", "Credito societario", "Treasury intermedi (i tassi non salgono)"],
    male: ["Oro e materie prime (manca la spinta dell'inflazione)", "TIPS (l'inflazione delude)", "Liquidità (rende poco rispetto al resto)"],
    esempi: "Seconda metà degli anni '90; lunghi tratti del 2013–2019.",
    segnali: "Produzione e vendite in crescita, disoccupazione in calo, inflazione core stabile o in discesa, aspettative di inflazione basse.",
  },
  B: {
    breve: "Crescita e inflazione sopra le attese.",
    cosa: "L'economia corre e i prezzi salgono insieme. La domanda è forte, le aziende alzano i listini, le materie prime si apprezzano. Le banche centrali tendono ad alzare i tassi per raffreddare.",
    perche: "Spesso dopo stimoli monetari o fiscali, ripartenze dopo una crisi, oppure boom degli investimenti e della domanda di materie prime.",
    bene: ["Materie prime ed energia", "Azioni cicliche (industria, materiali, finanziari)", "TIPS (proteggono dall'inflazione)", "Mercati emergenti"],
    male: ["Treasury lunghi (i tassi salgono e i prezzi dei bond scendono)", "Obbligazioni a lunga scadenza in generale", "Liquidità in termini reali"],
    esempi: "2003–2006; la ripartenza del 2021.",
    segnali: "Crescita sopra il trend insieme a CPI, PCE core, prezzi alla produzione e aspettative di inflazione in salita.",
  },
  C: {
    breve: "Crescita sotto le attese, inflazione sopra le attese.",
    cosa: "Il caso peggiore per un portafoglio tradizionale: l'economia rallenta ma i prezzi continuano a salire. Le banche centrali sono strette tra sostenere la crescita e combattere l'inflazione, quindi azioni e obbligazioni possono scendere insieme.",
    perche: "Di solito uno shock dell'offerta: energia o materie prime che rincarano, guerre, colli di bottiglia, salari che rincorrono i prezzi.",
    bene: ["Oro", "TIPS", "Energia e materie prime", "Liquidità (i tassi a breve salgono)", "Settori difensivi con potere sui prezzi"],
    male: ["Azioni, soprattutto di crescita", "Treasury lunghi", "Il classico 60/40 (azioni e bond scendono insieme)"],
    esempi: "Anni '70; il 2022, quando il 60/40 ha perso su entrambe le gambe.",
    segnali: "Produzione e vendite che rallentano, disoccupazione in salita, mentre l'inflazione resta alta o accelera.",
  },
  D: {
    breve: "Crescita e inflazione sotto le attese.",
    cosa: "L'economia frena e i prezzi rallentano o scendono. È il territorio delle recessioni: profitti in calo, disoccupazione in salita, banche centrali che tagliano i tassi.",
    perche: "Fine di un ciclo di credito, crisi finanziarie, shock improvvisi della domanda, strette monetarie che hanno funzionato troppo.",
    bene: ["Treasury lunghi (i tassi scendono)", "Treasury intermedi", "Settori difensivi di qualità (sanità, beni di prima necessità, utility)", "Liquidità per avere munizioni"],
    male: ["Materie prime", "Azioni cicliche", "Credito di bassa qualità"],
    esempi: "2008–2009; lo shock Covid della primavera 2020; il 2001–2002.",
    segnali: "Produzione e vendite in calo, disoccupazione che sale in fretta, inflazione e aspettative di inflazione in discesa.",
  },
};

export const GLOSSARIO: { termine: string; testo: string }[] = [
  { termine: "Inflazione", testo: "Aumento generale dei prezzi. Qui conta se sale o scende rispetto al suo trend degli ultimi anni, non il livello assoluto: un'inflazione al 4% che scende è un segnale di inflazione in calo." },
  { termine: "Disinflazione", testo: "L'inflazione resta positiva ma rallenta (per esempio dal 5% al 3%). I prezzi salgono ancora, ma più piano." },
  { termine: "Deflazione", testo: "I prezzi scendono. Spesso accompagna le recessioni: si rimandano gli acquisti, i debiti pesano di più in termini reali." },
  { termine: "Reflazione", testo: "Ripresa insieme di crescita e inflazione, spesso spinta da stimoli monetari o fiscali dopo un periodo debole." },
  { termine: "Stagflazione", testo: "Stagnazione + inflazione: l'economia rallenta mentre i prezzi salgono. Difficile per le banche centrali e per i portafogli tradizionali." },
  { termine: "Goldilocks", testo: "Crescita solida con inflazione sotto controllo: lo scenario ideale per le azioni." },
  { termine: "Sopra / sotto le attese", testo: "Dalio guarda le sorprese: i mercati prezzano già quello che si aspettano, quindi conta se crescita e inflazione vanno meglio o peggio del previsto. Qui le attese sono approssimate dal trend degli ultimi 5 anni." },
  { termine: "Probabilità del regime", testo: "Per crescita e inflazione si stima la probabilità che siano sopra il trend; le probabilità dei quattro regimi sono i prodotti. Un 53% vuol dire che il regime è il più probabile, non che è certo." },
  { termine: "Risk parity / All Weather", testo: "Portafoglio in cui ogni classe di attivo pesa per il rischio che porta, non per i soldi: gli attivi più tranquilli (bond) pesano di più, quelli più volatili (azioni, materie prime) di meno. Così il portafoglio regge in tutte e quattro le stagioni." },
  { termine: "Tilt per regime", testo: "Piccolo spostamento dei pesi (massimo ±10 punti) verso gli attivi che il regime più probabile favorisce. Nei test non ha ancora dimostrato un vantaggio statistico." },
  { termine: "60/40", testo: "Il portafoglio classico: 60% azioni, 40% obbligazioni (qui Treasury intermedi). Funziona quando azioni e bond si muovono in direzioni opposte; soffre in stagflazione." },
];
