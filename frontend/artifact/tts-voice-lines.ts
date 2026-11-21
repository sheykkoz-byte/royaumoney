// Sentences → the lines of one tts reading, with each line's offset in the text.
import { splitSentences } from "@/lib/jarvis";

const MAX_LINE = 1900; // tts takes up to 2,000 characters a line

export function lines(text: string): { text: string; start: number }[] {
  const out: { text: string; start: number }[] = [];
  let pos = 0;
  for (const s of splitSentences(text)) {
    for (let i = 0; i < s.length; i += MAX_LINE) {
      const t = s.slice(i, i + MAX_LINE);
      if (t.trim()) out.push({ text: t, start: pos + i });
    }
    pos += s.length;
  }
  return out;
}
