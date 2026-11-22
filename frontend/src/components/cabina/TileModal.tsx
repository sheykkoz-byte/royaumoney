"use client";

// Explanation window for one macro tile: opens from the clicked tile, the value counts up,
// the one-year chart draws itself (hover shows date and value), a coloured scale shows where
// today's reading sits between the traffic-light thresholds, then the words: what it means,
// what it says today, why it matters. ← → browse the section, Esc closes.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { itNum } from "@/lib/jarvis";
import { playOpen, prefs } from "@/lib/sfx";
import type { Spiegazione, Tile } from "./MacroBoard";

const STATE_LABEL: Record<string, string> = {
  verde: "Tranquillo", giallo: "Da osservare", rosso: "Tensione", neutro: "Informativo",
};

// Indicators where a rise is bad news: their "up" is coloured red
const RISE_IS_BAD = new Set(["VIX", "BAMLH0A0HYM2", "ICSA", "UNRATE", "CPIAUCSL", "PCEPILFE"]);

// "Animazioni ridotte" (button in the window, or the system setting) turns motion off
const reduced = () => typeof window !== "undefined" && !prefs.fullMotion();

const PERIODS = [["1a", "1 anno"], ["3a", "3 anni"], ["5a", "5 anni"]] as const;
type Period = (typeof PERIODS)[number][0];

// A short burst of particles in the traffic-light colour when the window opens
function Burst({ color }: { color: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || reduced()) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = c.clientWidth, h = c.clientHeight;
    c.width = w * dpr; c.height = h * dpr;
    const g = c.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    const parts = Array.from({ length: 90 }, () => {
      const a = Math.random() * Math.PI * 2, v = 2 + Math.random() * 7;
      return { vx: Math.cos(a) * v * 60, vy: Math.sin(a) * v * 60, r: 0.8 + Math.random() * 2.2,
               span: 700 + Math.random() * 500 };
    });
    // Time-based (not frame-based): the burst lasts about a second on any machine
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = (now - t0) / 1000;
      g.clearRect(0, 0, w, h);
      let alive = false;
      const travel = (1 - Math.exp(-3 * t)) / 3; // decelerating distance factor
      for (const p of parts) {
        const life = 1 - (now - t0) / p.span;
        if (life <= 0) continue;
        alive = true;
        const x = w / 2 + p.vx * travel, y = h / 2 + p.vy * travel;
        g.globalAlpha = life;
        g.fillStyle = color;
        g.shadowColor = color; g.shadowBlur = 8;
        g.beginPath(); g.arc(x, y, p.r, 0, Math.PI * 2); g.fill();
      }
      if (alive) raf = requestAnimationFrame(tick);
      else g.clearRect(0, 0, w, h);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [color]);
  return <canvas ref={ref} className="tm-burst" aria-hidden />;
}

const COLORS: Record<string, string> = { verde: "#3ddc97", giallo: "#ffc35a", rosso: "#ff5d73", neutro: "#8b7cff" };

function useCountUp(target: number, ms = 1100) {
  const [v, setV] = useState(reduced() ? target : target * 0.82);
  useEffect(() => {
    if (reduced()) { setV(target); return; }
    const from = target * 0.82, t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      setV(from + (target - from) * e);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

const W = 640, H = 210, PAD = { l: 6, r: 6, t: 16, b: 22 };

function BigChart({ t, points, period }: { t: Tile; points: [string, number][]; period: string }) {
  const pts = points.filter((p) => p[1] !== null);
  const [hover, setHover] = useState<number | null>(null);
  const g = useMemo(() => {
    if (pts.length < 2) return null;
    const vals = pts.map((p) => p[1]);
    const min = Math.min(...vals), max = Math.max(...vals), pad = (max - min) * 0.1 || 1;
    const lo = min - pad, hi = max + pad;
    const x = (i: number) => PAD.l + (i / (pts.length - 1)) * (W - PAD.l - PAD.r);
    const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
    const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
    return { x, y, d, area: `${d}L${x(pts.length - 1)},${H - PAD.b}L${x(0)},${H - PAD.b}Z`, min, max };
  }, [pts]);
  if (!g) return null;
  const last = pts.length - 1;
  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const fx = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((fx - PAD.l) / (W - PAD.l - PAD.r)) * last);
    setHover(Math.max(0, Math.min(last, i)));
  };
  const hi = hover ?? null;
  const fmt = (d: string) => d.split("-").reverse().join("/");
  return (
    <div className="tm-chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseMove={onMove} onMouseLeave={() => setHover(null)}
        role="img" aria-label={`${t.label}: ${period}`}>
        <defs>
          <linearGradient id="tm-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="var(--tm-color)" stopOpacity=".32" />
            <stop offset="1" stopColor="var(--tm-color)" stopOpacity="0" />
          </linearGradient>
          <filter id="tm-glow"><feGaussianBlur stdDeviation="3" /></filter>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} className="tm-grid" x1={PAD.l} x2={W - PAD.r}
            y1={PAD.t + f * (H - PAD.t - PAD.b)} y2={PAD.t + f * (H - PAD.t - PAD.b)} />
        ))}
        <path d={g.area} fill="url(#tm-area)" className="tm-area" />
        <path d={g.d} className="tm-line glow" filter="url(#tm-glow)" pathLength={1} />
        <path d={g.d} className="tm-line" pathLength={1} />
        <circle cx={g.x(last)} cy={g.y(pts[last][1])} r={4} className="tm-dot" />
        <circle cx={g.x(last)} cy={g.y(pts[last][1])} r={4} className="tm-ping" />
        <text className="tm-axis" x={PAD.l} y={H - 6}>{fmt(pts[0][0])}</text>
        <text className="tm-axis" x={W - PAD.r} y={H - 6} textAnchor="end">{fmt(pts[last][0])}</text>
        <text className="tm-axis" x={W - PAD.r} y={12} textAnchor="end">max {itNum(g.max, t.decimals)}</text>
        {hi !== null && (
          <g className="tm-hover">
            <line x1={g.x(hi)} x2={g.x(hi)} y1={PAD.t} y2={H - PAD.b} />
            <circle cx={g.x(hi)} cy={g.y(pts[hi][1])} r={4.5} />
          </g>
        )}
      </svg>
      <div className="tm-tip" aria-live="polite">
        {hi !== null
          ? <><b>{itNum(pts[hi][1], t.decimals)}</b> {t.unit} · {fmt(pts[hi][0])}</>
          : <>Passa sul grafico per leggere ogni punto</>}
      </div>
    </div>
  );
}

function Gauge({ t }: { t: Tile }) {
  const sc = t.scala;
  const [on, setOn] = useState(reduced());
  useEffect(() => { const h = setTimeout(() => setOn(true), 380); return () => clearTimeout(h); }, [t.id]);
  if (!sc || sc.valore === null) return null;
  const pos = (v: number) => Math.max(0, Math.min(100, ((v - sc.min) / (sc.max - sc.min)) * 100));
  const fmt = (v: number) => itNum(v, Math.abs(v) < 10 ? 2 : Math.abs(v) < 100 ? 1 : 0);
  const edges = Array.from(new Set(sc.zone.flatMap((z) => [z.da, z.a]).filter((x): x is number => x !== null)));
  return (
    <div className="tm-gauge">
      <div className="tm-gauge-head">
        <span>Dove siamo · {sc.misura}</span>
        <b>{fmt(sc.valore)}{sc.unita ? ` ${sc.unita}` : ""}</b>
      </div>
      <div className="tm-bar">
        {sc.zone.map((z, i) => {
          const a = pos(z.da ?? sc.min), b = pos(z.a ?? sc.max);
          return <i key={i} className={`z-${z.stato}`} style={{ left: `${a}%`, width: `${Math.max(0, b - a)}%` }} />;
        })}
        <span className="tm-marker" style={{ left: on ? `${pos(sc.valore)}%` : "0%" }} />
      </div>
      <div className="tm-ticks">
        {edges.map((e) => <span key={e} style={{ left: `${pos(e)}%` }}>{fmt(e)}</span>)}
      </div>
      {sc.nota && <p className="tm-note">{sc.nota}</p>}
    </div>
  );
}

export default function TileModal({
  tiles, index, origin, guide, onIndex, onClose, onOpenChart,
}: {
  tiles: Tile[]; index: number; origin: { x: number; y: number } | null;
  guide: Spiegazione | undefined;
  onIndex: (i: number) => void; onClose: () => void; onOpenChart: (tv: string) => void;
}) {
  const t = tiles[index];
  const closeRef = useRef<HTMLButtonElement>(null);
  const [period, setPeriod] = useState<Period>("1a");
  const [sound, setSound] = useState(prefs.sound());
  const [full, setFull] = useState(prefs.fullMotion());
  const points = period === "1a" ? t.spark : (t.storico?.[period] ?? t.spark);
  useEffect(() => { playOpen(t.state); }, [t.id, t.state]);
  const value = useCountUp(t.value ?? 0);
  const meaning = guide?.riquadri.find((r) => r.label === t.label)?.significato;
  const summary = guide?.oggi.filter((f) => f.startsWith("In sintesi")) ?? [];

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onIndex((index + 1) % tiles.length);
      if (e.key === "ArrowLeft") onIndex((index - 1 + tiles.length) % tiles.length);
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [index, tiles.length, onClose, onIndex]);

  // The window grows out of the clicked tile
  const from = origin && typeof window !== "undefined"
    ? { "--tm-dx": `${origin.x - window.innerWidth / 2}px`, "--tm-dy": `${origin.y - window.innerHeight / 2}px` }
    : {};

  const chg = (k: string) => {
    const c = t.changes?.[k];
    if (c === null || c === undefined) return null;
    const bp = t.change_kind === "diff" && (t.unit === "%" || t.unit === "punti %");
    const txt = bp ? `${c >= 0 ? "+" : ""}${itNum(c * 100)} pb`
      : t.change_kind === "pct" ? `${c >= 0 ? "+" : ""}${itNum(c, 1)}%`
      : `${c >= 0 ? "+" : ""}${itNum(c, t.decimals)}`;
    const good = RISE_IS_BAD.has(t.id) ? c < 0 : c > 0;
    return <span key={k} className={`tm-chip ${c === 0 ? "" : good ? "up" : "down"}`}><i>{{ "1g": "1 giorno", "1m": "1 mese", "1a": "1 anno" }[k]}</i>{txt}</span>;
  };

  return createPortal(
    <div className="tm-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`tm-panel st-${t.state}${full ? "" : " tm-calm"}`} role="dialog" aria-modal="true"
        aria-labelledby="tm-title" style={from as React.CSSProperties} key={t.id}>
        <div className="tm-aura" aria-hidden />
        {full && <Burst color={COLORS[t.state] ?? COLORS.neutro} />}
        <header className="tm-head">
          <span className={`tm-light l-${t.state}`} aria-hidden><i /></span>
          <div className="tm-titles">
            <div className="tm-section">{t.section} · {index + 1}/{tiles.length}</div>
            <h2 id="tm-title">{t.label}</h2>
          </div>
          <span className="tm-badge">{STATE_LABEL[t.state]}</span>
          <button ref={closeRef} className="tm-x" onClick={onClose} aria-label="Chiudi">×</button>
        </header>

        <div className="tm-value-row">
          <div className="tm-value">{itNum(value, t.decimals)}<small>{t.unit}</small></div>
          <div className="tm-chips">{["1g", "1m", "1a"].map(chg)}</div>
          <div className="tm-date">ultimo dato {t.date.split("-").reverse().join("/")}</div>
        </div>

        <div className="tm-periods" role="group" aria-label="Periodo del grafico">
          {PERIODS.map(([k, label]) => (
            <button key={k} type="button" aria-pressed={period === k} onClick={() => setPeriod(k)}>{label}</button>
          ))}
        </div>
        <BigChart key={`${t.id}-${period}`} t={t} points={points} period={period} />
        <Gauge t={t} />

        <div className="tm-text">
          {t.reading && (
            <section className="tm-card today">
              <h3>Oggi</h3>
              <p className="tm-reading">{t.reading}</p>
              {summary.map((s, i) => <p key={i}>{s}</p>)}
            </section>
          )}
          {meaning && (
            <section className="tm-card">
              <h3>Cosa vuol dire</h3>
              <p>{meaning}</p>
            </section>
          )}
          {guide?.cosa_misura && (
            <section className="tm-card">
              <h3>Perché conta · {t.section}</h3>
              <p>{guide.cosa_misura}</p>
            </section>
          )}
        </div>

        <footer className="tm-foot">
          <button onClick={() => onIndex((index - 1 + tiles.length) % tiles.length)} aria-label="Riquadro precedente">←</button>
          <button onClick={() => onIndex((index + 1) % tiles.length)} aria-label="Riquadro successivo">→</button>
          <button type="button" aria-pressed={sound} title={sound ? "Spegni i suoni" : "Accendi i suoni"}
            onClick={() => { prefs.setSound(!sound); setSound(!sound); }}>{sound ? "🔊 Suoni" : "🔇 Suoni"}</button>
          <button type="button" aria-pressed={full}
            onClick={() => { prefs.setFullMotion(!full); setFull(!full); }}>
            {full ? "Animazioni piene" : "Animazioni ridotte"}</button>
          <span className="tm-hint">← → per scorrere · Esc per chiudere</span>
          {t.tv && <button className="tm-primary" onClick={() => { onOpenChart(t.tv!); onClose(); }}>Apri sul grafico principale</button>}
        </footer>
      </div>
    </div>,
    document.body,
  );
}
