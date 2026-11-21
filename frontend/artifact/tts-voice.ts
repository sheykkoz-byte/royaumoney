// Jarvis's voice in Claude mode: the platform's `tts` capability behind the browser's
// speechSynthesis API, so src/lib/voice.ts (play) works unchanged. Sentences become the
// lines of one reading; `boundary` events come from each line's start and its progress in
// milliseconds (≈14 characters a second), which is what play() uses to fire the cues.
/* eslint-disable @typescript-eslint/no-explicit-any */
import { lines } from "./tts-voice-lines";

const CHARS_PER_SECOND = 14;

type Tts = {
  speak(what: { text: string; id?: string }[], o?: { language?: string; rate?: number }): Promise<unknown>;
  stop(): Promise<void>;
  onLine(h: (e: { line: number }) => void): () => void;
  onPosition(h: (e: { ms: number; line: number }) => void): () => void;
};

function install(t: Tts, native: SpeechSynthesis | undefined) {
  let current: { u: SpeechSynthesisUtterance; parts: { text: string; start: number }[] } | null = null;
  const boundary = (charIndex: number) =>
    current?.u.onboundary?.({ charIndex } as SpeechSynthesisEvent);

  t.onLine(({ line }) => {
    const c = current;
    if (!c) return;
    if (line === 0) c.u.onstart?.({} as SpeechSynthesisEvent);
    const p = c.parts[line];
    if (p) boundary(p.start);
  });
  t.onPosition(({ ms, line }) => {
    const p = current?.parts[line];
    if (p) boundary(p.start + Math.min(p.text.length - 1, Math.floor((ms / 1000) * CHARS_PER_SECOND)));
  });

  const synth = {
    speaking: false,
    pending: false,
    paused: false,
    onvoiceschanged: null as any,
    getVoices: () => [] as SpeechSynthesisVoice[],
    speak(u: SpeechSynthesisUtterance) {
      const parts = lines(u.text);
      current = { u, parts };
      synth.speaking = true;
      t.speak(parts.map((p, i) => ({ text: p.text, id: String(i) })), { language: "it" })
        .then(() => { if (current?.u === u) { current = null; synth.speaking = false; u.onend?.({} as SpeechSynthesisEvent); } })
        .catch((e: { code?: string; reason?: string }) => {
          if (current?.u !== u) return; // replaced by a newer reading
          current = null;
          synth.speaking = false;
          if (e?.code === "stopped") u.onend?.({} as SpeechSynthesisEvent);
          else u.onerror?.({ error: e?.code } as any); // play() falls back to the estimated timing
        });
    },
    cancel() {
      current = null;
      synth.speaking = false;
      t.stop().catch(() => {});
      native?.cancel();
    },
    pause() {}, resume() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent: () => true,
  };
  if (!(window as any).SpeechSynthesisUtterance) {
    (window as any).SpeechSynthesisUtterance = class { lang = ""; rate = 1; pitch = 1; voice = null;
      onstart = null; onend = null; onerror = null; onboundary = null; constructor(public text: string) {} };
  }
  try {
    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
  } catch { /* keep the browser voice */ }
}

const native = (window as any).speechSynthesis as SpeechSynthesis | undefined;
(window as any).claude?.use?.("tts").then((t: Tts | null) => { if (t) install(t, native); }).catch(() => {});
