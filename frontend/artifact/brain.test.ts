// Tests for the artifact's brain and scene director (same cases as backend/tests/test_jarvis.py).
// Run: frontend/artifact/test.sh DATA_JSON   (build.sh runs it before bundling)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { align, buildTurns, checkScript, direct, findWord, fold, numbers, systemText, type Data } from "./brain";
import { lines } from "./tts-voice-lines";

const tests: [string, () => void][] = [];
const test = (name: string, fn: () => void) => tests.push([name, fn]);
const d: Data = JSON.parse(readFileSync(process.argv[2], "utf8"));

test("fold keeps length and removes accents", () => {
  const t = "Liquidità è già più alta, M2!";
  assert.equal(fold(t).length, t.length);
  assert.equal(fold(t), "liquidita e gia piu alta  m2 ");
});

test("findWord: prefix and word boundary", () => {
  const f = fold("La M2 sta risalendo, poi il dollaro risale");
  assert.equal(findWord(f, "risal"), f.indexOf("risalendo"));
  assert.equal(findWord(f, "salendo"), null);
  assert.equal(findWord(f, "M2"), 3);
  assert.equal(findWord(f, "il dollaro"), f.indexOf("il dollaro"));
});

test("align follows speaking order and repeats", () => {
  const pos = align("L'oro sale. Poi l'oro scende, e l'oro riparte.",
    [{ alla_parola: "oro" }, { alla_parola: "oro" }, { alla_parola: "riparte" }]).map((p) => p.char_index);
  assert.deepEqual(pos, [2, 18, 38]);
});

test("align: accents and missing word", () => {
  const a = align("La liquidità cresce.", [{ alla_parola: "LIQUIDITA" }, { alla_parola: "inesistente" }]);
  assert.equal(a[0].char_index, 3);
  assert.equal(a[0].warning, null);
  assert.match(a[1].warning ?? "", /non presente/);
});

test("every prompt adaptation applies to the backend system prompt", () => {
  const s = systemText(d);
  assert.ok(!s.includes("strumento chiamato in questa conversazione"));
  assert.ok(!s.includes("mostra_correlazione"));
  assert.ok(!s.includes("registra_previsione"));
  assert.ok(s.includes("dai DATI qui sotto"));
});

test("cues with invented numbers are dropped, data numbers kept", () => {
  const gold = d.serie.GOLD["1y"].ultimo.valore;
  const seen = numbers({ x: [gold] });
  const r = checkScript({ parlato: "L'oro.", scene: [
    { alla_parola: "oro", azione: "mostra_livello", su: "GOLD", valore: gold },
    { alla_parola: "oro", azione: "mostra_livello", su: "GOLD", valore: 1234.5 },
    { alla_parola: "oro", azione: "mostra_correlazione", id_a: "M2SL", id_b: "GOLD" },
  ] }, seen);
  assert.equal(r.scene.length, 1);
  assert.equal(r.dropped.length, 2);
});

test("a script without parlato is an error", () => {
  assert.throws(() => checkScript({ scene: [] }, []));
});

test("director attaches recorded series and cards", () => {
  const out = direct(d, { parlato: "L'oro e il regime.", scene: [
    { alla_parola: "oro", azione: "apri_grafico", id: "GOLD", periodo: "5y" },
    { alla_parola: "regime", azione: "mostra_regime" },
    { alla_parola: "regime", azione: "apri_grafico", id: "NOPE" },
  ] });
  assert.equal(out.scene[0].dati.serie.periodo, "5y");
  assert.ok(out.scene[0].dati.serie.punti.length > 10);
  assert.equal(out.scene[0].parametri.id, "GOLD");
  assert.ok(out.scene[1].dati.regime.regime);
  assert.ok(out.scene[2].dati.errore);
});

test("the prompt fits the sample input limit (256 KiB)", () => {
  const turns = buildTurns(d, "Come sta l'oro?", []);
  const bytes = Buffer.byteLength(turns.map((t) => t.content).join(""), "utf8");
  assert.ok(bytes < 200 * 1024, `prompt is ${bytes} bytes`);
});

test("voice lines cover the text at the right offsets", () => {
  const t = "L'oro ha chiuso a 3.515 dollari. Poi la Fed. Fine!";
  const ls = lines(t);
  assert.ok(ls.length >= 2);
  for (const l of ls) assert.equal(t.slice(l.start, l.start + l.text.length), l.text);
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); console.log(`ok   ${name}`); } catch (e) { failed++; console.log(`FAIL ${name}\n     ${(e as Error).message}`); }
}
console.log(`${tests.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
