"use client";

// "Chiedi a Claude": quick questions and a free question, answer streamed from /api/analisi.
import { useEffect, useRef, useState } from "react";

function esc(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
}

// Minimal Markdown: ## headings, - lists, **bold**, paragraphs
function md(t: string) {
  let html = "", list = false;
  for (const raw of esc(t).split("\n")) {
    const l = raw.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    if (/^\s*[-•]\s+/.test(l)) { if (!list) { html += "<ul>"; list = true; } html += `<li>${l.replace(/^\s*[-•]\s+/, "")}</li>`; continue; }
    if (list) { html += "</ul>"; list = false; }
    if (/^#{1,4}\s+/.test(l)) html += `<h4>${l.replace(/^#{1,4}\s+/, "")}</h4>`;
    else if (l.trim()) html += `<p>${l}</p>`;
  }
  return html + (list ? "</ul>" : "");
}

export default function AskClaude({ ticker, quick, placeholder }: {
  ticker?: string; quick: { label: string; domanda: string }[]; placeholder?: string;
}) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const ctrl = useRef<AbortController | null>(null);

  useEffect(() => {
    fetch("/api/analisi").then((r) => r.json()).then((d) => setAvailable(Boolean(d.disponibile))).catch(() => setAvailable(false));
    return () => ctrl.current?.abort();
  }, []);

  async function ask(domanda: string) {
    ctrl.current?.abort();
    const c = new AbortController(); ctrl.current = c;
    setBusy(true); setText("");
    try {
      const r = await fetch("/api/analisi", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domanda, ticker }), signal: c.signal });
      if (!r.ok || !r.body) { setText(await r.text()); return; }
      const reader = r.body.getReader(), dec = new TextDecoder();
      let acc = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        acc += dec.decode(value, { stream: true });
        setText(acc);
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setText("Analisi non riuscita: errore di rete.");
    } finally { setBusy(false); }
  }

  if (available === false) {
    return <div className="ac"><p className="rq-muted">«Chiedi a Claude» si attiva quando nelle impostazioni di Vercel c&apos;è la chiave <code>ANTHROPIC_API_KEY</code>.</p></div>;
  }
  return (
    <div className="ac">
      <div className="ac-row">
        {quick.map((x) => <button key={x.label} type="button" className="ac-btn" disabled={busy || !available} onClick={() => ask(x.domanda)}>{x.label}</button>)}
      </div>
      <form className="ac-row" onSubmit={(e) => { e.preventDefault(); if (q.trim()) ask(q.trim()); }}>
        <input className="ac-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder ?? "Fai una domanda…"} aria-label="Domanda per Claude" disabled={!available} />
        <button type="submit" className="ac-btn primary" disabled={busy || !available || !q.trim()}>Chiedi</button>
      </form>
      {(busy || text) && (
        <div className="ac-answer" aria-live="polite">
          {text ? <div dangerouslySetInnerHTML={{ __html: md(text) }} /> : <p className="rq-muted">Claude sta leggendo i dati e ragionando…</p>}
        </div>
      )}
    </div>
  );
}
