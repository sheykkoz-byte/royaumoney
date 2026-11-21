"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Card from "@/components/Cards";
import Chart from "@/components/Chart";
import type { OrbMode, OrbSignals } from "@/components/Orb";
import { EMPTY_STAGE, applyCue, splitSentences, wsUrl, type Risposta, type Stage } from "@/lib/jarvis";
import { play, stopSpeaking } from "@/lib/voice";

const Orb = dynamic(() => import("@/components/Orb"), { ssr: false });
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CHIPS = ["Come sta l'oro?", "Qual è il regime?", "Cosa dicono gli scenari?", "Liquidità e M2", "Dati sul lavoro", "Il mio scenario"];
const STATUS: Record<OrbMode, string> = { idle: "PRONTO", listen: "IN ASCOLTO", think: "ELABORO", speak: "JARVIS PARLA" };

/* eslint-disable @typescript-eslint/no-explicit-any */
type Recognition = any;

export default function Jarvis() {
  const signals = useRef<OrbSignals>({ mode: "idle", mic: 0, spike: 0 });
  const [mode, setModeState] = useState<OrbMode>("idle");
  const [stage, setStage] = useState<Stage>(EMPTY_STAGE);
  const [you, setYou] = useState("");
  const [reply, setReply] = useState("Ciao Yousef. Tocca il microfono o scrivimi.");
  const [shown, setShown] = useState(0); // characters of the reply already spoken
  const [conn, setConn] = useState<"on" | "off">("off");
  const [demo, setDemo] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const ws = useRef<WebSocket | null>(null);
  const cancelPlay = useRef<() => void>(() => {});
  const rec = useRef<Recognition>(null);

  const setMode = (m: OrbMode) => { signals.current.mode = m; setModeState(m); };
  const flash = (msg: string) => { setToast(msg); window.setTimeout(() => setToast(null), 5000); };

  const perform = useCallback((r: Risposta) => {
    setDemo(r.modalita === "dimostrativa");
    setReply(r.parlato);
    setShown(0);
    setStage(EMPTY_STAGE);
    setMode("speak");
    const t0 = performance.now();
    cancelPlay.current = play(r.parlato, r.scene.map((c) => c.char_index), r.tempi_stimati, {
      onCue: (i) => {
        const cue = r.scene[i];
        setStage((s) => applyCue(s, cue, performance.now() - t0));
        setShown((n) => Math.max(n, cue.char_index));
      },
      onWord: (c) => {
        signals.current.spike = 0.55 + Math.random() * 0.35;
        setShown((n) => Math.max(n, Math.floor(c)));
      },
      onEnd: () => { setShown(r.parlato.length); setMode("idle"); },
    });
  }, []);

  // WebSocket with automatic reconnection
  useEffect(() => {
    let closed = false, retry = 0;
    const connect = () => {
      const sock = new WebSocket(wsUrl(API));
      ws.current = sock;
      sock.onopen = () => { setConn("on"); retry = 0; };
      sock.onclose = () => {
        setConn("off");
        if (!closed) window.setTimeout(connect, Math.min(10000, 1000 * 2 ** retry++));
      };
      sock.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.tipo === "stato") setMode("think");
        else if (m.tipo === "risposta") perform(m as Risposta);
        else if (m.tipo === "errore") { setMode("idle"); flash(`Errore: ${m.messaggio}`); }
      };
    };
    connect();
    return () => { closed = true; ws.current?.close(); cancelPlay.current(); };
  }, [perform]);

  const ask = (text: string) => {
    text = text.trim();
    if (!text) return;
    cancelPlay.current();
    setYou(`› ${text}`);
    if (ws.current?.readyState !== WebSocket.OPEN) {
      flash(`Backend non raggiungibile su ${API}. Avvialo con make dev.`);
      return;
    }
    setMode("think");
    ws.current.send(JSON.stringify({ tipo: "domanda", testo: text }));
  };

  // ---- microphone: level for the orb + Italian speech recognition (Chrome) ----
  const stopMic = () => {
    try { rec.current?.stop(); } catch { /* already stopped */ }
    rec.current = null;
    signals.current.mic = 0;
    if (signals.current.mode === "listen") setMode("idle");
  };
  const startMic = async () => {
    stopSpeaking();
    cancelPlay.current();
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      flash("Microfono non disponibile: puoi scrivere la domanda.");
      return;
    }
    const ctx = new AudioContext();
    const an = ctx.createAnalyser();
    an.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Uint8Array(an.fftSize);
    let live = true;
    const tick = () => {
      if (!live) return;
      an.getByteTimeDomainData(buf);
      let s = 0;
      for (const v of buf) { const x = (v - 128) / 128; s += x * x; }
      signals.current.mic = Math.sqrt(s / buf.length);
      requestAnimationFrame(tick);
    };
    tick();
    const release = () => { live = false; stream.getTracks().forEach((t) => t.stop()); ctx.close(); };

    setMode("listen");
    setYou("› …");
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      flash("Il riconoscimento vocale funziona su Chrome. La sfera reagisce comunque alla tua voce.");
      window.setTimeout(() => { release(); stopMic(); }, 6000);
      return;
    }
    const r = new SR();
    rec.current = r;
    r.lang = "it-IT"; r.interimResults = true; r.continuous = false;
    let finalTxt = "";
    r.onresult = (ev: any) => {
      let s = "";
      for (const res of ev.results) { s += res[0].transcript; if (res.isFinal) finalTxt = s; }
      setYou(`› ${s}`);
    };
    r.onend = () => { release(); stopMic(); if (finalTxt) ask(finalTxt); };
    r.onerror = () => { release(); stopMic(); };
    r.start();
  };

  // While speaking, show only the sentence being said; afterwards the whole answer
  const speaking = mode === "speak";
  const sentences = splitSentences(reply);
  let start = 0, current = reply;
  for (const sen of sentences) {
    if (shown < start + sen.length) { current = sen; break; }
    start += sen.length;
  }
  const within = Math.max(0, shown - start);
  const spoken = speaking ? current.slice(0, within) : reply;
  const rest = speaking ? current.slice(within) : "";

  return (
    <div className="jarvis">
      <div className="grid-bg" />
      <header className="jhead">
        <div className="brand"><div className="brand-dot" /><div>JARVIS<small>ROYAUMONEY · MARKET INTELLIGENCE</small></div></div>
        <div className="head-right">
          {demo && <span className="tag amber" title="Cervello senza AI: domande fisse, numeri veri dal database">MODALITÀ DIMOSTRATIVA</span>}
          <Link className="tag" href="/stato">Stato dati e previsioni</Link>
          <div className={`status ${mode}`}><i />{conn === "off" ? "NON CONNESSO" : STATUS[mode]}</div>
        </div>
      </header>

      <main className="jmain">
        <section className="col left">
          {stage.charts.map((c) => <Chart key={c.key} c={c} focus={stage.focus === c.key} />)}
        </section>
        <section className="stage">
          <Orb signals={signals} />
          <div className="transcript">
            <div className="you">{you}</div>
            <div className={`reply${speaking ? "" : " full"}`}><span>{spoken}</span><span className="dim">{rest}</span></div>
          </div>
        </section>
        <section className="col right">
          {stage.cards.map((c) => <Card key={c.key} card={c} focus={stage.focus === c.key} />)}
        </section>
      </main>

      <div className="dock">
        <div className="chips">
          {CHIPS.map((c) => <button key={c} className="chip" onClick={() => ask(c)}>{c}</button>)}
        </div>
        <form className="bar-in" onSubmit={(e) => { e.preventDefault(); ask(q); setQ(""); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Chiedi a Jarvis…" autoComplete="off" aria-label="Domanda" />
          <button type="submit" className="btn send" aria-label="Invia">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </button>
          <button type="button" className={`btn mic${mode === "listen" ? " on" : ""}`} aria-label="Parla" onClick={() => (mode === "listen" ? stopMic() : startMic())}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
          </button>
        </form>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
