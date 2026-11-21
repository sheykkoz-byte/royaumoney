// Types of the directed script sent by the backend, and the stage state built from it.

export type Point = { data: string; valore: number };

export type Serie = {
  id: string;
  nome: string;
  unita: string;
  fonte: string;
  ultimo: { data: string; valore: number; pubblicato: string };
  massimo: { data: string; valore: number };
  minimo: { data: string; valore: number };
  variazione_periodo_pct: number | null;
  punti: Point[];
  fonti: string[];
};

export type Cue = {
  alla_parola: string;
  azione:
    | "apri_grafico" | "evidenzia_tratto" | "sovrapponi" | "mostra_livello" | "mostra_valore"
    | "mostra_correlazione" | "mostra_regime" | "mostra_scenari" | "mostra_previsione" | "chiudi";
  parametri: Record<string, unknown>;
  char_index: number;
  warning: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  dati: Record<string, any>;
};

export type Risposta = {
  tipo: "risposta";
  domanda: string;
  parlato: string;
  scene: Cue[];
  tempi_stimati: number[];
  // ElevenLabs voice (absent when the browser voice is used)
  audio?: { formato: string; audio_base64: string; inizio_caratteri: number[] | null; durata: number | null };
  tempi_voce?: number[];
  voce_errore?: string;
  modalita: string;
  intento: string | null;
};

export type ChartState = {
  key: string;
  serie: Serie;
  overlay?: Serie;
  levels: { valore: number; etichetta?: string; at: number }[];
  bands: { da: string; a: string }[];
  born: number;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type CardState = { key: string; kind: string; data: any; born: number };

export type Stage = { charts: ChartState[]; cards: CardState[]; focus: string | null };

export const EMPTY_STAGE: Stage = { charts: [], cards: [], focus: null };

const MAX_CHARTS = 3;
const MAX_CARDS = 3;

// Apply one cue to the stage. Pure: returns a new stage.
export function applyCue(stage: Stage, cue: Cue, now: number): Stage {
  const p = cue.parametri as Record<string, string | number | undefined>;
  const target = (p.su as string) ?? stage.charts[stage.charts.length - 1]?.key;
  switch (cue.azione) {
    case "apri_grafico": {
      const serie = cue.dati.serie as Serie | undefined;
      if (!serie?.punti?.length) return stage;
      const charts = stage.charts.filter((c) => c.key !== serie.id);
      charts.push({ key: serie.id, serie, levels: [], bands: [], born: now });
      return { ...stage, charts: charts.slice(-MAX_CHARTS), focus: serie.id };
    }
    case "sovrapponi": {
      const serie = cue.dati.serie as Serie | undefined;
      if (!serie?.punti?.length || !target) return stage;
      return {
        ...stage,
        focus: target,
        charts: stage.charts.map((c) => (c.key === target ? { ...c, overlay: serie } : c)),
      };
    }
    case "mostra_livello": {
      if (!target || typeof p.valore !== "number") return stage;
      return {
        ...stage,
        focus: target,
        charts: stage.charts.map((c) =>
          c.key === target
            ? { ...c, levels: [...c.levels, { valore: p.valore as number, etichetta: p.etichetta as string, at: now }] }
            : c,
        ),
      };
    }
    case "evidenzia_tratto": {
      if (!target || !p.da || !p.a) return stage;
      return {
        ...stage,
        focus: target,
        charts: stage.charts.map((c) =>
          c.key === target ? { ...c, bands: [...c.bands, { da: String(p.da), a: String(p.a) }] } : c,
        ),
      };
    }
    case "chiudi": {
      if (!p.su) return EMPTY_STAGE;
      return { ...stage, charts: stage.charts.filter((c) => c.key !== p.su) };
    }
    default: {
      const kind = cue.azione.replace("mostra_", "");
      const data = cue.azione === "mostra_valore" ? p : cue.dati;
      if (!data || cue.dati.errore) return stage;
      const key = `${kind}-${now}`;
      return { ...stage, cards: [...stage.cards, { key, kind, data, born: now }].slice(-MAX_CARDS), focus: key };
    }
  }
}

// ---- Italian number formatting ----
export function itNum(x: number | null | undefined, nd = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return x.toLocaleString("it-IT", { minimumFractionDigits: nd, maximumFractionDigits: nd });
}

export function wsUrl(api: string): string {
  return api.replace(/^http/, "ws").replace(/\/$/, "") + "/ws/jarvis";
}

// A sentence ends at . ! ? followed by a space and a capital letter — not inside "3.539"
export function splitSentences(text: string): string[] {
  const parts = text.split(/(?<=[.!?])\s+(?=[A-ZÀ-ÝÈÉ«"(])/);
  return parts.map((p, i) => (i < parts.length - 1 ? p + " " : p));
}
