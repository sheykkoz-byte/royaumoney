"use client";

// The trader's cockpit: a viewing platform (no orders). Laid out for a 49" 32:9 monitor,
// it folds down to normal screens and phones.
//   watchlist · main TradingView chart · 2×2 secondary charts · macro board · Jarvis
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Card from "@/components/Cards";
import Clocks from "@/components/cabina/Clocks";
import MacroBoard, { type Macro } from "@/components/cabina/MacroBoard";
import { TickerTape, TvChart } from "@/components/cabina/Tv";
import Watchlist from "@/components/cabina/Watchlist";
import type { OrbSignals } from "@/components/Orb";
import { DEFAULT_FAVORITES, DEFAULT_MINI, nameOf } from "@/lib/symbols";

const Orb = dynamic(() => import("@/components/Orb"), { ssr: false });

const INTERVALS: [string, string][] = [
  ["1", "1m"], ["5", "5m"], ["15", "15m"], ["60", "1h"], ["240", "4h"], ["D", "G"], ["W", "S"],
];

// Per-viewer preferences in the browser (favourites, chart, slots)
function usePref<T>(key: string, initial: T): [T, (v: T | ((x: T) => T)) => void] {
  const [v, setV] = useState<T>(initial);
  const loaded = useRef(false);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(`cabina.${key}`);
      if (raw) setV(JSON.parse(raw));
    } catch { /* first visit or storage blocked */ }
    loaded.current = true;
  }, [key]);
  useEffect(() => {
    if (!loaded.current) return;
    try { localStorage.setItem(`cabina.${key}`, JSON.stringify(v)); } catch { /* ignore */ }
  }, [key, v]);
  return [v, setV];
}

export default function Cabina() {
  const [symbol, setSymbol] = usePref("simbolo", "OANDA:XAUUSD");
  const [interval, setInterval_] = usePref("intervallo", "60");
  const [favorites, setFavorites] = usePref<string[]>("preferiti", DEFAULT_FAVORITES);
  const [mini, setMini] = usePref<string[]>("mini", DEFAULT_MINI);
  const [macro, setMacro] = useState<Macro | null>(null);
  const signals = useRef<OrbSignals>({ mode: "idle", mic: 0, spike: 0, voice: -1, cue: 0 });

  useEffect(() => {
    fetch("/cabina/macro.json", { cache: "no-store" }).then((r) => r.json()).then(setMacro).catch(() => {});
  }, []);

  const toggleFavorite = useCallback((s: string) => {
    setFavorites((f) => (f.includes(s) ? f.filter((x) => x !== s) : [...f, s]));
  }, [setFavorites]);
  const tape = useMemo(() => favorites.map((s) => ({ s, n: nameOf(s) })), [favorites]);
  const regime = macro?.regime;
  const openPred = macro?.previsioni?.[0];

  return (
    <div className="cabina">
      <header className="cab-top">
        <Link href="/jarvis" className="brand" title="Apri Jarvis">
          <div className="brand-dot" /><div>CABINA<small>ROYAUMONEY · USO PERSONALE</small></div>
        </Link>
        <div className="cab-tape"><TickerTape symbols={tape} /></div>
        <Clocks />
      </header>

      <main className="cab-grid">
        <Watchlist active={symbol} favorites={favorites} onSelect={setSymbol} onToggleFavorite={toggleFavorite} />

        <section className="cab-panel chart-main">
          <div className="cab-head">
            <span className="cm-title">{nameOf(symbol)} <em>{symbol}</em></span>
            <div className="cm-tools">
              {INTERVALS.map(([v, l]) => (
                <button key={v} type="button" className={`seg${interval === v ? " on" : ""}`} onClick={() => setInterval_(v)}>{l}</button>
              ))}
              <button type="button" className={`seg star${favorites.includes(symbol) ? " on" : ""}`}
                onClick={() => toggleFavorite(symbol)} aria-label="Preferito">★</button>
            </div>
          </div>
          <TvChart symbol={symbol} interval={interval} />
        </section>

        <section className="cab-panel minis">
          <div className="cab-head"><span>Grafici di controllo</span><span className="cab-sub">giornaliero</span></div>
          <div className="mini-grid">
            {mini.map((s, i) => (
              <div key={i} className="mini">
                <div className="mini-head">
                  <button type="button" className="mini-name" onClick={() => setSymbol(s)} title="Apri sul grafico principale">{nameOf(s)}</button>
                  <button type="button" className="mini-swap" title="Metti qui il grafico principale"
                    onClick={() => setMini((m) => m.map((x, j) => (j === i ? symbol : x)))}>⇄</button>
                </div>
                <TvChart symbol={s} interval="D" compact />
              </div>
            ))}
          </div>
        </section>

        <MacroBoard data={macro} onOpen={setSymbol} />

        <aside className="cab-panel jarvis-col">
          <div className="cab-head"><span>Jarvis</span><span><Link href="/regime" className="cab-link">Regimi →</Link> · <Link href="/istituzionali" className="cab-link">Istituzionali →</Link> · <Link href="/jarvis" className="cab-link">Parla con Jarvis →</Link></span></div>
          <div className="jc-orb"><Orb signals={signals} /></div>
          <div className="jc-scroll">
            {regime && <Card card={{ key: "r", kind: "regime", data: { regime }, born: 0 }} focus={false} />}
            {macro?.convergenza && <Card card={{ key: "s", kind: "scenari", data: { scenari: macro.convergenza }, born: 0 }} focus={false} />}
            {openPred && <Card card={{ key: "p", kind: "previsione", data: { previsione: openPred }, born: 0 }} focus={false} />}
          </div>
        </aside>
      </main>
    </div>
  );
}
