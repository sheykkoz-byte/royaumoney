// Microphone inside the artifact. The frame blocks getUserMedia and the Web Speech API, so the
// platform's `dictation` capability stands in: it holds the microphone and hands us the words.
// The page (src/app/page.tsx) is unchanged: we give it a SpeechRecognition look-alike and a
// silent stream. dictation.start() must run synchronously inside the click, so a capture
// listener on the mic button starts it before React's handler awaits anything.
/* eslint-disable @typescript-eslint/no-explicit-any */

type Dictation = {
  start(o?: { language?: string }): Promise<void>;
  stop(): Promise<void>;
  active(): boolean;
  onPartial(h: (e: { text: string }) => void): () => void;
  onFinal(h: (e: { text: string }) => void): () => void;
  onState(h: (e: { state: string; reason?: string }) => void): () => void;
};

const REASONS: Record<string, string> = {
  not_granted: "Microfono non autorizzato: si può riattivare dal menu Autorizzazioni dell'artefatto.",
  unavailable: "Dettatura non disponibile qui: scrivi la domanda.",
  rate_limited: "Microfono occupato: riprova tra poco.",
  upstream_error: "Il microfono non ha funzionato: riprova o scrivi la domanda.",
};

function toast(msg: string) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.appendChild(el);
  window.setTimeout(() => el.remove(), 5000);
}

let current: FakeRecognition | null = null;

class FakeRecognition {
  lang = "it-IT";
  interimResults = true;
  continuous = false;
  onresult: ((ev: any) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  finals: string[] = [];
  constructor(private d: Dictation) {}
  start() { current = this; }
  stop() { void this.d.stop(); }
  emit(partial: string) {
    const results: any[] = this.finals.map((t) => Object.assign([{ transcript: t }], { isFinal: true }));
    if (partial) results.push(Object.assign([{ transcript: partial }], { isFinal: false }));
    this.onresult?.({ results });
  }
}

function install(d: Dictation) {
  d.onPartial(({ text }) => current?.emit(text));
  d.onFinal(({ text }) => {
    if (!current || !text.trim()) return;
    current.finals.push(current.finals.length ? text : text.trimStart());
    current.emit("");
    void d.stop(); // one question per tap, like continuous = false
  });
  d.onState(({ state, reason }) => {
    if (state !== "idle") return;
    if (reason && REASONS[reason]) toast(REASONS[reason]);
    const r = current;
    current = null;
    r?.onend?.();
  });

  // Start dictation inside the click itself (no await before it)
  document.addEventListener("click", (e) => {
    const btn = (e.target as Element | null)?.closest?.(".btn.mic");
    if (!btn || d.active()) return;
    d.start({ language: "it" }).catch((err: { code?: string }) => {
      if (err?.code && REASONS[err.code]) toast(REASONS[err.code]);
      if (err?.code === "dismissed" || err?.code === "no_gesture") current?.onend?.();
    });
  }, true);

  // The page opens a stream only to animate the orb with the mic level: give it silence
  const silent = async () => new AudioContext().createMediaStreamDestination().stream;
  try {
    if (navigator.mediaDevices) (navigator.mediaDevices as any).getUserMedia = silent;
    else Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: silent } });
  } catch { /* the orb just won't react to the voice */ }
  (window as any).SpeechRecognition = function () { return new FakeRecognition(d); };
}

const claude = (window as any).claude;
claude?.use?.("dictation").then((d: Dictation | null) => { if (d) install(d); }).catch(() => {});
