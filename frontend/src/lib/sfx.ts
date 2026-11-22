// Soft interface sounds, synthesised with Web Audio (no files): a short airy "whoosh" and a
// two-note chime whose pitch follows the traffic light. Off/on and the animation level are
// per-viewer preferences kept in localStorage.

let ctx: AudioContext | null = null;

const KEY_SOUND = "cabina-suono";
const KEY_MOTION = "cabina-animazioni";

function read(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function write(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* private mode: keep it in memory only */ }
}

export const prefs = {
  sound: () => read(KEY_SOUND, "on") === "on",
  setSound: (on: boolean) => write(KEY_SOUND, on ? "on" : "off"),
  fullMotion: () => {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return read(KEY_MOTION, "") === "piene"; // the system asks for less, unless chosen here
    }
    return read(KEY_MOTION, "piene") === "piene";
  },
  setFullMotion: (on: boolean) => write(KEY_MOTION, on ? "piene" : "ridotte"),
};

// Notes per state: green bright and open, yellow suspended, red low and tense, neutral soft
const CHIMES: Record<string, [number, number]> = {
  verde: [659.25, 987.77], giallo: [587.33, 830.61], rosso: [349.23, 466.16], neutro: [523.25, 783.99],
};

export function playOpen(state: string) {
  if (typeof window === "undefined" || !prefs.sound()) return;
  try {
    ctx = ctx ?? new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    if (ctx.state === "suspended") void ctx.resume();
    const now = ctx.currentTime;
    const master = ctx.createGain();
    master.gain.value = 0.16;
    master.connect(ctx.destination);

    // whoosh: filtered noise sweeping up
    const len = Math.floor(ctx.sampleRate * 0.45);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const noise = ctx.createBufferSource();
    noise.buffer = buf;
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass"; bp.Q.value = 1.2;
    bp.frequency.setValueAtTime(300, now);
    bp.frequency.exponentialRampToValueAtTime(2400, now + 0.4);
    const ng = ctx.createGain();
    ng.gain.setValueAtTime(0, now);
    ng.gain.linearRampToValueAtTime(0.5, now + 0.08);
    ng.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
    noise.connect(bp).connect(ng).connect(master);
    noise.start(now);

    // chime: two soft sine notes
    const [a, b] = CHIMES[state] ?? CHIMES.neutro;
    [a, b].forEach((f, i) => {
      const t0 = now + 0.12 + i * 0.11;
      const o = ctx!.createOscillator();
      o.type = "sine"; o.frequency.value = f;
      const g = ctx!.createGain();
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(0.35, t0 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + 0.9);
      o.connect(g).connect(master);
      o.start(t0); o.stop(t0 + 1);
    });
  } catch {
    // audio unavailable: silence is fine
  }
}
