// Jarvis's Claude brain inside the artifact, on the viewer's own Claude account (`sample`
// capability: no API key). Same method and script format as backend/app/jarvis/
// claude_brain.py; the data are the tool results recorded in data.json (record_data.py),
// given to Claude in the prompt. A port of the scene director (scene.py) then drops
// numbers no tool returned, finds each cue word and attaches the real data.
/* eslint-disable @typescript-eslint/no-explicit-any */

export type Data = {
  registrato_il: string;
  sistema: string;
  elenca_serie: { serie: { id: string; nome: string; categoria: string; unita: string }[] };
  serie: Record<string, Record<string, any>>;
  regime: any;
  scenari: Record<string, any>;
  previsioni: { previsioni: any[] };
  previsione: Record<string, any>;
  track_record: any;
};

export type Turn = { domanda: string; parlato: string };

const ACTIONS = new Set([
  "apri_grafico", "evidenzia_tratto", "sovrapponi", "mostra_livello", "mostra_valore",
  "mostra_regime", "mostra_scenari", "mostra_previsione", "chiudi",
]);
const VALUE_TOLERANCE = 0.005; // as claude_brain.VALUE_TOLERANCE
const HISTORY_TURNS = 4;

// ---- prompt ------------------------------------------------------------------------------
// The backend's system prompt, adapted where the artifact differs (data in the prompt,
// no registration, no correlation card). Each replacement must apply.
const ADAPT: [string, string][] = [
  ["ogni numero che pronunci deve venire da uno strumento chiamato in questa conversazione, mai dalla memoria.",
   "ogni numero che pronunci deve venire dai DATI qui sotto (risultati degli strumenti, registrati dal database), mai dalla memoria."],
  [" · mostra_correlazione {id_a, id_b, sfasamento_mesi}", ""],
  ["Gli id delle serie sono quelli di elenca_serie", "Gli id delle serie sono quelli dei DATI"],
  ["devono essere numeri restituiti da uno strumento", "devono essere numeri presenti nei DATI"],
];

export function systemText(d: Data): string {
  let s = d.sistema;
  for (const [a, b] of ADAPT) {
    if (!s.includes(a)) console.warn("brain: prompt adaptation not applied:", a.slice(0, 40));
    s = s.replace(a, b);
  }
  // Registration needs the backend (git registry): not from this page
  s = s.replace(/Previsioni: per registrarne una[\s\S]*?esplicito nella conversazione\./,
    "Previsioni: da questa pagina non si possono registrare; se l'utente lo chiede, digli " +
    "che si fa dall'app di RoyauMoney.");
  return s;
}

const round = (v: any) => (typeof v === "number" ? Math.round(v * 1e4) / 1e4 : v);

/** One line per series: last value and, per period, change, high and low. */
export function seriesSummary(d: Data) {
  return d.elenca_serie.serie.filter((x) => d.serie[x.id]).map((x) => {
    const per = d.serie[x.id];
    const any = per["1y"] ?? Object.values(per)[0];
    const periodi: Record<string, any> = {};
    for (const [p, q] of Object.entries(per)) {
      periodi[p] = { var_pct: q.variazione_periodo_pct, max: [q.massimo?.data, round(q.massimo?.valore)],
        min: [q.minimo?.data, round(q.minimo?.valore)] };
    }
    return { id: x.id, nome: x.nome, categoria: x.categoria, unita: x.unita,
      ultimo: [any.ultimo?.data, round(any.ultimo?.valore)], periodi };
  });
}

function dataBlock(d: Data) {
  const prev = d.previsioni.previsioni.map((p) => ({
    id: p.id, titolo: p.title, stato: p.status, direzione: p.direction, strumento: p.instrument_label,
    prezzo_ingresso: p.entry_price, probabilita: p.probability, fine_orizzonte: p.horizon_end,
    scenario: p.scenario, obiettivi: p.targets, invalidazioni: p.invalidations,
    ultimo_prezzo_verificato: p.last_bar_date,
  }));
  return {
    regime_attuale: d.regime,
    punteggio_convergenza: d.scenari[""],
    previsioni: prev,
    track_record: d.track_record,
    serie: seriesSummary(d),
  };
}

const FORMAT = `Rispondi SOLO con un oggetto JSON, senza altro testo:
{"parlato": "...", "scene": [{"alla_parola": "...", "azione": "...", ...parametri}]}
Esempio: {"parlato": "L'oro ha chiuso a 3.515 dollari...", "scene": [{"alla_parola": "oro", "azione": "apri_grafico", "id": "GOLD", "periodo": "1y"}]}`;

export function buildTurns(d: Data, question: string, history: Turn[]) {
  const rules = `${systemText(d)}

DATI (risultati degli strumenti di Jarvis, registrati dal database RoyauMoney il ${d.registrato_il}; \
"ultimo" e "max"/"min" sono [data, valore], var_pct è la variazione % nel periodo):
${JSON.stringify(dataBlock(d))}

${FORMAT}`;
  const turns: { role: "user" | "assistant"; content: string }[] = [{ role: "user", content: rules }];
  for (const h of history.slice(-HISTORY_TURNS)) {
    turns.push({ role: "user", content: h.domanda }, { role: "assistant", content: h.parlato });
  }
  turns.push({ role: "user", content: `[Oggi è il ${d.registrato_il}]\n${question}` });
  return turns;
}

// ---- checks (claude_brain.check_cue_numbers) ----------------------------------------------
export function numbers(obj: any, out: number[] = []): number[] {
  if (typeof obj === "number" && Number.isFinite(obj)) out.push(obj);
  else if (Array.isArray(obj)) obj.forEach((v) => numbers(v, out));
  else if (obj && typeof obj === "object") Object.values(obj).forEach((v) => numbers(v, out));
  return out;
}

export function checkScript(raw: any, seen: number[]) {
  if (!raw || typeof raw.parlato !== "string" || !raw.parlato.trim()) {
    throw new Error("risposta senza parlato");
  }
  const kept: any[] = [];
  const dropped: string[] = [];
  for (const cue of Array.isArray(raw.scene) ? raw.scene : []) {
    if (!cue || typeof cue.alla_parola !== "string" || !cue.alla_parola || !ACTIONS.has(cue.azione)) {
      dropped.push(`${cue?.azione ?? "?"}: azione non valida qui`);
      continue;
    }
    const v = cue.valore;
    if ((cue.azione === "mostra_livello" || cue.azione === "mostra_valore") && v !== undefined) {
      const ok = typeof v === "number" &&
        seen.some((n) => Math.abs(v - n) <= VALUE_TOLERANCE * Math.max(1, Math.abs(n)));
      if (!ok) { dropped.push(`${cue.azione} ${v}: numero non restituito da uno strumento`); continue; }
    }
    kept.push(cue);
  }
  return { parlato: raw.parlato.trim(), scene: kept, dropped };
}

// ---- scene director (scene.py) --------------------------------------------------------------
// One UTF-16 unit → one lowercase base char, so indices match the page's string indices.
export function fold(text: string): string {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const base = text[i].normalize("NFKD")[0] ?? " ";
    out += /[\p{L}\p{N}]/u.test(base) ? base.toLowerCase() : " ";
  }
  return out;
}

export function findWord(folded: string, word: string, start = 0): number | null {
  const w = fold(word).split(" ").filter(Boolean).join(" ");
  if (!w) return null;
  let i = start;
  for (;;) {
    i = folded.indexOf(w, i);
    if (i < 0) return null;
    if (i === 0 || folded[i - 1] === " ") return i;
    i += 1;
  }
}

export function align(parlato: string, cues: { alla_parola: string }[]) {
  const folded = fold(parlato);
  let cursor = 0;
  return cues.map((cue) => {
    let idx = findWord(folded, cue.alla_parola, cursor);
    let warning: string | null = null;
    if (idx === null) {
      idx = findWord(folded, cue.alla_parola, 0);
      warning = idx !== null ? "parola trovata prima della precedente" : null;
    }
    if (idx === null) {
      idx = cursor;
      warning = `parola «${cue.alla_parola}» non presente nel parlato`;
    } else {
      cursor = idx + 1;
    }
    return { char_index: idx, warning };
  });
}

export function resolveData(d: Data, cue: any): Record<string, any> {
  const a = cue.azione;
  if (a === "apri_grafico" || a === "sovrapponi") {
    const s = d.serie[cue.id]?.[cue.periodo ?? "1y"] ?? d.serie[cue.id]?.["1y"];
    return s ? { serie: s } : { errore: `${a}: serie ${cue.id} non disponibile` };
  }
  if (a === "mostra_regime") return { regime: d.regime };
  if (a === "mostra_scenari") return { scenari: d.scenari[cue.scenario ?? ""] ?? d.scenari[""] };
  if (a === "mostra_previsione") {
    const p = d.previsione[cue.id];
    return p ? { previsione: p } : { errore: `previsione ${cue.id} non trovata` };
  }
  return {};
}

export function direct(d: Data, script: { parlato: string; scene: any[] }) {
  const pos = align(script.parlato, script.scene);
  const scene = script.scene.map((cue, i) => {
    const { alla_parola, azione, ...parametri } = cue;
    return { alla_parola, azione, parametri, ...pos[i], dati: resolveData(d, cue) };
  });
  return {
    parlato: script.parlato,
    scene,
    tempi_stimati: scene.map((c) => Math.round((c.char_index / 14) * 100) / 100),
  };
}

// ---- the call ---------------------------------------------------------------------------------
export async function answer(sample: any, d: Data, question: string, history: Turn[]) {
  const turns = buildTurns(d, question, history);
  const raw = await sample.json(turns, { modelTier: "default", effort: "low", cache: false });
  const seen = numbers(dataBlock(d));
  const { dropped, ...script } = checkScript(raw, seen);
  return { ...direct(d, script), modalita: "claude", intento: null, scene_scartate: dropped };
}
