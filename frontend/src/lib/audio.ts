// Frequency bands of the sound the orb reacts to: Jarvis's voice (ElevenLabs audio) or
// the user's microphone. Written by whoever owns the analyser, read by the orb each frame.

export type Bands = { low: number; mid: number; high: number; level: number };

export const bands: Bands = { low: 0, mid: 0, high: 0, level: 0 };

// Hz ranges of the speaking voice: body (fundamental), presence (vowels), air (consonants)
const RANGES: [keyof Omit<Bands, "level">, number, number][] = [
  ["low", 80, 320], ["mid", 320, 2200], ["high", 2200, 7000],
];

/** Read one frame from the analyser into `bands` (0–1 each). */
export function measure(an: AnalyserNode, freq: Uint8Array<ArrayBuffer>, time: Uint8Array<ArrayBuffer>) {
  an.getByteFrequencyData(freq);
  const hz = an.context.sampleRate / an.fftSize;
  for (const [k, lo, hi] of RANGES) {
    const a = Math.max(1, Math.floor(lo / hz)), b = Math.min(freq.length - 1, Math.ceil(hi / hz));
    let s = 0;
    for (let i = a; i <= b; i++) s += freq[i];
    bands[k] = s / ((b - a + 1) * 255);
  }
  an.getByteTimeDomainData(time);
  let sum = 0;
  for (const v of time) { const x = (v - 128) / 128; sum += x * x; }
  bands.level = Math.sqrt(sum / time.length);
  return bands.level;
}

export function resetBands() {
  bands.low = bands.mid = bands.high = bands.level = 0;
}
