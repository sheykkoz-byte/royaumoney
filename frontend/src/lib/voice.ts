// Speaks the script and fires each cue when its word is spoken.
//
// With the browser voice, `boundary` events give the character being spoken: a cue fires
// when that index reaches the cue's `char_index`. Some voices send no boundary events; if
// none arrives shortly after the start, cues fire on the backend's estimated times instead.
// ElevenLabs (with its character timestamps) will plug in here in place of the browser voice.

export type PlayHandlers = {
  onCue: (index: number) => void;
  onWord: (charIndex: number) => void; // progress of the spoken text, and a pulse for the orb
  onEnd: () => void;
};

const RATE = 1.04;
const NO_BOUNDARY_AFTER_MS = 900;

let itVoice: SpeechSynthesisVoice | null = null;

function pickVoice() {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  const vs = speechSynthesis.getVoices();
  itVoice =
    vs.find((v) => /it[-_]IT/i.test(v.lang) && /google|luca|alice|federica|neural/i.test(v.name)) ||
    vs.find((v) => /^it/i.test(v.lang)) ||
    null;
}

if (typeof window !== "undefined" && "speechSynthesis" in window) {
  pickVoice();
  speechSynthesis.onvoiceschanged = pickVoice;
}

export function stopSpeaking() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) speechSynthesis.cancel();
}

export function play(
  text: string,
  cueChars: number[],
  estimatedSeconds: number[],
  h: PlayHandlers,
): () => void {
  const fired = new Set<number>();
  const timers: ReturnType<typeof setTimeout>[] = [];
  let sawBoundary = false;
  let ended = false;

  const fireUpTo = (charIndex: number) => {
    cueChars.forEach((c, i) => {
      if (!fired.has(i) && c <= charIndex) {
        fired.add(i);
        h.onCue(i);
      }
    });
  };
  const useEstimates = () => {
    // Progress of the text at the estimated reading speed
    const t0 = Date.now();
    const tick = setInterval(() => {
      const c = ((Date.now() - t0) / 1000) * 14 * RATE;
      if (ended || c > text.length) return clearInterval(tick);
      h.onWord(c);
    }, 250);
    timers.push(tick);
    estimatedSeconds.forEach((t, i) => {
      timers.push(setTimeout(() => {
        if (!fired.has(i)) {
          fired.add(i);
          h.onCue(i);
        }
      }, (t * 1000) / RATE));
    });
  };
  const finish = () => {
    if (ended) return;
    ended = true;
    fireUpTo(Number.MAX_SAFE_INTEGER); // anything left (e.g. voice cut short) still shows
    h.onEnd();
  };

  // Cues at the very start show immediately
  fireUpTo(0);

  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    useEstimates();
    timers.push(setTimeout(finish, (text.length / 14) * 1000));
    return () => timers.forEach((t) => { clearTimeout(t); clearInterval(t); });
  }

  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "it-IT";
  if (itVoice) u.voice = itVoice;
  u.rate = RATE;
  u.pitch = 0.95;
  u.onboundary = (e) => {
    sawBoundary = true;
    fireUpTo(e.charIndex);
    h.onWord(e.charIndex);
  };
  let started = false;
  const armFallback = () => {
    if (started) return;
    started = true;
    timers.push(setTimeout(() => { if (!sawBoundary) useEstimates(); }, NO_BOUNDARY_AFTER_MS));
  };
  u.onstart = armFallback;
  u.onend = finish;
  u.onerror = () => {
    if (!sawBoundary) useEstimates();
    timers.push(setTimeout(finish, (text.length / 14) * 1000));
  };
  speechSynthesis.speak(u);
  // If the voice never starts (no Italian voice installed), cues still follow the estimate
  timers.push(setTimeout(armFallback, 1500));
  // Safety net: some browsers never fire `end`
  timers.push(setTimeout(finish, (text.length / 14) * 1000 * 2 + 3000));

  return () => {
    timers.forEach((t) => { clearTimeout(t); clearInterval(t); });
    speechSynthesis.cancel();
  };
}
