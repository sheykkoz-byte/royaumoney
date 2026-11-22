// Stands in for the backend WebSocket inside the artifact.
// - Claude brain (brain.ts) on the viewer's own Claude account, with the tool results
//   recorded in data.json, when the `sample` capability is available.
// - Otherwise, or if Claude fails, the demo brain: answers recorded from the real backend
//   (snapshot.json, with ElevenLabs audio), routed like demo.INTENTS.
/* eslint-disable @typescript-eslint/no-explicit-any */
import { answer, type Data, type Turn } from "./brain";

const INTENTS: [RegExp, string][] = [
  [/previs|registro|track|scenario mio|mio scenario|il mio/, "predictions_intent"],
  [/\boro\b|gold|xau/, "gold"],
  [/regime/, "regime"],
  [/scenari|convergen|divergen|recession|stagflaz|atterraggio/, "scenarios"],
  [/liquidit|\bm2\b|bilanci|fed net|massa monetaria/, "liquidity"],
  [/lavoro|payroll|disoccup|sussid|occupaz/, "labour"],
  [/\b(ciao|ehi|hey|buongiorno|buonasera|jarvis)\b/, "greeting"],
];

export function route(q: string): string {
  const s = q.toLowerCase();
  return INTENTS.find(([re]) => re.test(s))?.[1] ?? "fallback";
}

const ERRORS: Record<string, string> = {
  not_granted: "Claude non è autorizzato per questa pagina: risponde il cervello dimostrativo.",
  sampling_disabled: "Claude non è disponibile per questo account: risponde il cervello dimostrativo.",
  rate_limited: "Troppe domande a Claude per ora: risponde il cervello dimostrativo. Riprova tra poco.",
  invalid_json: "Claude ha risposto in un formato non valido: risponde il cervello dimostrativo.",
};

const json = (url: string) => fetch(url).then((r) => r.json());
const snapshot: Promise<Record<string, any>> = json("snapshot.json");
const data: Promise<Data | null> = json("data.json").catch(() => null);
const claude = (window as any).claude;
const sample: Promise<any> = claude?.use ? claude.use("sample").catch(() => null) : Promise.resolve(null);

let blocked: string | null = null; // a permanent refusal: stop asking Claude in this view
const history: Turn[] = [];

async function respond(question: string): Promise<Record<string, any>> {
  const [snap, d, s] = await Promise.all([snapshot, data, sample]);
  let brainError: string | undefined;
  if (s && d && !blocked) {
    try {
      const r = await answer(s, d, question, history);
      history.push({ domanda: question, parlato: r.parlato });
      return { tipo: "risposta", domanda: question, ...r };
    } catch (e: any) {
      const code = e?.code ?? "upstream_error";
      if (["not_granted", "sampling_disabled", "not_declared", "tools_unavailable"].includes(code)) {
        blocked = code;
      }
      brainError = ERRORS[code] ?? `Claude non ha risposto (${code}): risponde il cervello dimostrativo.`;
      console.warn("Claude brain failed:", e);
    }
  }
  const r = { ...snap[route(question)], domanda: question };
  return brainError ? { ...r, cervello_errore: brainError } : r;
}

class FakeWebSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  constructor() {
    snapshot.then(() => { this.readyState = 1; this.onopen?.(); });
  }
  send(raw: string) {
    const m = JSON.parse(raw);
    this.onmessage?.({ data: JSON.stringify({ tipo: "stato", stato: "elaboro" }) });
    respond(String(m.testo)).then((r) => this.onmessage?.({ data: JSON.stringify(r) }));
  }
  close() { this.readyState = 3; }
}

(globalThis as any).WebSocket = FakeWebSocket;
