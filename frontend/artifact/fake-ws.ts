// Stands in for the backend WebSocket: answers come from snapshot.json, recorded from the
// real backend (demo brain, real data, ElevenLabs voice). Routing mirrors demo.INTENTS.
/* eslint-disable @typescript-eslint/no-explicit-any */

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

const snapshot: Promise<Record<string, any>> = fetch("snapshot.json").then((r) => r.json());

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
    snapshot.then((snap) => {
      const r = { ...snap[route(m.testo)], domanda: m.testo };
      window.setTimeout(() => this.onmessage?.({ data: JSON.stringify(r) }), 500);
    });
  }
  close() { this.readyState = 3; }
}

(globalThis as any).WebSocket = FakeWebSocket;
