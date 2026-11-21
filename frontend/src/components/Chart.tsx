"use client";

// "Holographic" line chart: the line draws itself with a glowing trail, key levels light up
// with a pulse when Jarvis names them, an overlay series gets its own right-hand scale.
import { useMemo } from "react";
import type { ChartState, Serie } from "@/lib/jarvis";
import { itNum } from "@/lib/jarvis";

const W = 560, H = 220, PAD = { l: 8, r: 8, t: 14, b: 22 };

function scale(values: number[], lo: number, hi: number) {
  const min = Math.min(...values), max = Math.max(...values);
  const pad = (max - min) * 0.08 || Math.abs(max) * 0.02 || 1;
  const a = min - pad, b = max + pad;
  return { f: (v: number) => hi - ((v - a) / (b - a)) * (hi - lo), min: a, max: b };
}

function path(s: Serie, x: (i: number) => number, y: (v: number) => number) {
  return s.punti.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.valore).toFixed(1)}`).join("");
}

export default function Chart({ c, focus }: { c: ChartState; focus: boolean }) {
  const { serie, overlay, levels, bands } = c;
  const geom = useMemo(() => {
    const n = serie.punti.length;
    const x = (i: number) => PAD.l + (i / Math.max(n - 1, 1)) * (W - PAD.l - PAD.r);
    const vals = [...serie.punti.map((p) => p.valore), ...levels.map((l) => l.valore)];
    const y = scale(vals, PAD.t, H - PAD.b);
    const d = path(serie, x, y.f);
    const area = `${d}L${x(n - 1)},${H - PAD.b}L${x(0)},${H - PAD.b}Z`;
    let od: string | null = null;
    if (overlay?.punti.length) {
      // Overlay on the same time axis: map its dates onto the main series' range
      const t0 = Date.parse(serie.punti[0].data), t1 = Date.parse(serie.punti[n - 1].data);
      const ox = (dt: string) => PAD.l + ((Date.parse(dt) - t0) / Math.max(t1 - t0, 1)) * (W - PAD.l - PAD.r);
      const pts = overlay.punti.filter((p) => Date.parse(p.data) >= t0 && Date.parse(p.data) <= t1);
      const oy = scale(pts.map((p) => p.valore), PAD.t, H - PAD.b);
      od = pts.map((p, i) => `${i ? "L" : "M"}${ox(p.data).toFixed(1)},${oy.f(p.valore).toFixed(1)}`).join("");
    }
    const t0 = Date.parse(serie.punti[0].data), t1 = Date.parse(serie.punti[n - 1].data);
    const bx = (dt: string) => PAD.l + ((Date.parse(dt) - t0) / Math.max(t1 - t0, 1)) * (W - PAD.l - PAD.r);
    return { x, y, d, area, od, bx, n };
  }, [serie, overlay, levels]);

  const last = serie.ultimo;
  const chg = serie.variazione_periodo_pct;
  return (
    <div className={`panel chart-panel${focus ? " focus" : ""}`}>
      <div className="p-head">
        <div className="p-title">{serie.nome}{overlay ? ` · ${overlay.nome}` : ""}</div>
        {chg !== null && <div className={`tag ${chg >= 0 ? "up" : "down"}`}>{chg >= 0 ? "+" : ""}{itNum(chg, 1)}%</div>}
      </div>
      <div className="big">{itNum(last.valore, last.valore < 100 ? 2 : 0)}<span className="unit">{serie.unita}</span></div>
      <div className="sub">ultimo dato {last.data} · fonte {serie.fonti.join(", ")}</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={serie.nome}>
        <defs>
          <linearGradient id={`area-${c.key}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="rgba(139,124,255,.35)" />
            <stop offset="1" stopColor="rgba(139,124,255,0)" />
          </linearGradient>
          <linearGradient id={`line-${c.key}`} x1="0" x2="1">
            <stop offset="0" stopColor="#8b7cff" /><stop offset=".6" stopColor="#5fe1ff" /><stop offset="1" stopColor="#e9ebff" />
          </linearGradient>
          <filter id={`glow-${c.key}`}><feGaussianBlur stdDeviation="2.2" /></filter>
        </defs>
        {bands.map((b, i) => (
          <rect key={i} className="band" x={geom.bx(b.da)} y={PAD.t} width={Math.max(2, geom.bx(b.a) - geom.bx(b.da))} height={H - PAD.t - PAD.b} />
        ))}
        <path d={geom.area} fill={`url(#area-${c.key})`} className="area" />
        <path d={geom.d} stroke={`url(#line-${c.key})`} className="line glow" filter={`url(#glow-${c.key})`} pathLength={1} />
        <path d={geom.d} stroke={`url(#line-${c.key})`} className="line" pathLength={1} />
        {geom.od && <path d={geom.od} className="line overlay" pathLength={1} />}
        {levels.map((l, i) => (
          <g key={`${l.valore}-${i}`} className="level">
            <line x1={PAD.l} x2={W - PAD.r} y1={geom.y.f(l.valore)} y2={geom.y.f(l.valore)} />
            <text x={W - PAD.r - 2} y={geom.y.f(l.valore) - 4} textAnchor="end">{l.etichetta ?? itNum(l.valore)}</text>
          </g>
        ))}
        <circle className="last-dot" cx={geom.x(geom.n - 1)} cy={geom.y.f(last.valore)} r={3.5} />
        <text className="axis" x={PAD.l} y={H - 6}>{serie.punti[0].data}</text>
        <text className="axis" x={W - PAD.r} y={H - 6} textAnchor="end">{last.data}</text>
      </svg>
    </div>
  );
}
