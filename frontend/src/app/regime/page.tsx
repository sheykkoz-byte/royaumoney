"use client";

// Regime & Quality Engine dashboard (data: /rqe/rqe.json, written by `python -m app.cli rqe`).
// Dalio's four seasons with probabilities, the growth × inflation map, regime history since
// 2000, All Weather allocation with the regime tilt, backtest against a 60/40, alerts.
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { itNum } from "@/lib/jarvis";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Q = "A" | "B" | "C" | "D";
const QS: Q[] = ["A", "B", "C", "D"];
const QCOLOR: Record<Q, string> = { A: "#5fe1ff", B: "#ffc35a", C: "#ff5d73", D: "#8b7cff" };
const pct = (x: number | null | undefined, nd = 0) => (x === null || x === undefined ? "—" : `${itNum(x * 100, nd)}%`);

function Bar({ v, color }: { v: number; color: string }) {
  return <div className="rq-bar"><i style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%`, background: color }} /></div>;
}

// Growth × inflation map: quadrants, last 12 months as a trail, today pulsing
function QuadrantMap({ hist, now }: { hist: any[]; now: any }) {
  const S = 260, M = 1.5; // most readings sit within ±1.5; beyond that the point stays on the edge
  const x = (g: number) => S / 2 + (Math.max(-M, Math.min(M, g)) / M) * (S / 2 - 14);
  const y = (i: number) => S / 2 - (Math.max(-M, Math.min(M, i)) / M) * (S / 2 - 14);
  const trail = hist.slice(-12);
  const g = now.crescita.punteggio, inf = now.inflazione.punteggio;
  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="rq-map" role="img" aria-label="Mappa crescita e inflazione">
      <rect x={S / 2} y={0} width={S / 2} height={S / 2} fill={QCOLOR.B} opacity=".08" />
      <rect x={S / 2} y={S / 2} width={S / 2} height={S / 2} fill={QCOLOR.A} opacity=".08" />
      <rect x={0} y={0} width={S / 2} height={S / 2} fill={QCOLOR.C} opacity=".08" />
      <rect x={0} y={S / 2} width={S / 2} height={S / 2} fill={QCOLOR.D} opacity=".08" />
      <line x1={S / 2} x2={S / 2} y1={0} y2={S} className="rq-axis" />
      <line y1={S / 2} y2={S / 2} x1={0} x2={S} className="rq-axis" />
      <text x={S - 6} y={14} textAnchor="end" fill={QCOLOR.B}>Reflazione</text>
      <text x={S - 6} y={S - 8} textAnchor="end" fill={QCOLOR.A}>Goldilocks</text>
      <text x={6} y={14} fill={QCOLOR.C}>Stagflazione</text>
      <text x={6} y={S - 8} fill={QCOLOR.D}>Deflazione</text>
      <text x={S - 6} y={S / 2 + 12} textAnchor="end" className="rq-axis-label">crescita →</text>
      <text x={S / 2 + 4} y={30} className="rq-axis-label">↑ inflazione</text>
      <polyline points={trail.map((h) => `${x(h.crescita)},${y(h.inflazione)}`).join(" ")} className="rq-trail" />
      {trail.map((h, i) => <circle key={h.data} cx={x(h.crescita)} cy={y(h.inflazione)} r={2 + (i / trail.length) * 2} fill={QCOLOR[h.dominante as Q]} opacity={0.3 + (i / trail.length) * 0.6} />)}
      <circle cx={x(g)} cy={y(inf)} r={7} fill={QCOLOR[now.dominante as Q]} className="rq-now" />
      <circle cx={x(g)} cy={y(inf)} r={7} fill="none" stroke={QCOLOR[now.dominante as Q]} className="rq-ping" />
    </svg>
  );
}

// Stacked probabilities since 2000
function History({ hist }: { hist: any[] }) {
  const W = 900, H = 160;
  const n = hist.length;
  const x = (i: number) => (i / Math.max(n - 1, 1)) * W;
  const layers = useMemo(() => {
    const acc = new Array(n).fill(0);
    return QS.map((q) => {
      const lo = acc.slice();
      hist.forEach((h, i) => { acc[i] += h[q]; });
      const hi = acc.slice();
      const top = hi.map((v, i) => `${x(i).toFixed(1)},${(H - v * H).toFixed(1)}`);
      const bot = lo.map((v, i) => `${x(i).toFixed(1)},${(H - v * H).toFixed(1)}`).reverse();
      return { q, d: `M${top.join("L")}L${bot.join("L")}Z` };
    });
  }, [hist, n]);
  const years = hist.map((h, i) => [h.data.slice(0, 4), i] as const).filter(([y], i, a) => i === 0 || y !== a[i - 1][0]).filter(([y]) => +y % 5 === 0);
  return (
    <svg viewBox={`0 0 ${W} ${H + 16}`} className="rq-hist" role="img" aria-label="Probabilità dei regimi dal 2000">
      {layers.map((l) => <path key={l.q} d={l.d} fill={QCOLOR[l.q]} opacity=".75" />)}
      {years.map(([y, i]) => <text key={y} x={x(i)} y={H + 12} className="rq-axis-label">{y}</text>)}
    </svg>
  );
}

function Curves({ curve, names }: { curve: any[]; names: Record<string, string> }) {
  const W = 900, H = 220, keys = Object.keys(names);
  const colors: Record<string, string> = { rp: "#5fe1ff", rp_tilt: "#3ddc97", bench: "#8a8fb4" };
  const vals = curve.flatMap((c) => keys.map((k) => Math.log(c[k])));
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const x = (i: number) => (i / Math.max(curve.length - 1, 1)) * W;
  const y = (v: number) => 8 + (1 - (Math.log(v) - lo) / (hi - lo)) * (H - 16);
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="rq-curves" role="img" aria-label="Crescita di 100 investiti">
        {keys.map((k) => <path key={k} d={curve.map((c, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(c[k]).toFixed(1)}`).join("")} stroke={colors[k]} className="rq-curve" pathLength={1} />)}
      </svg>
      <div className="rq-legend">{keys.map((k) => <span key={k}><i style={{ background: colors[k] }} />{names[k]} · {itNum(curve[curve.length - 1][k])}</span>)}</div>
    </>
  );
}

const ASSET_SHORT: Record<string, string> = {
  equity: "Azioni", long_tsy: "Tsy lunghi", int_tsy: "Tsy interm.", tips: "TIPS",
  gold: "Oro", commodities: "Materie p.", cash: "Liquidità",
};

// Preferences heat map: −1 red … +1 green
function Prefs({ prefs, quadranti }: { prefs: Record<string, Record<string, number>>; quadranti: any }) {
  const assets = Object.keys(ASSET_SHORT);
  const bg = (v: number) => v >= 0 ? `rgba(61,220,151,${Math.min(1, Math.abs(v)) * 0.55})` : `rgba(255,93,115,${Math.min(1, Math.abs(v)) * 0.55})`;
  return (
    <table className="rq-table rq-heat">
      <thead><tr><th>Regime</th>{assets.map((a) => <th key={a}>{ASSET_SHORT[a]}</th>)}</tr></thead>
      <tbody>
        {QS.filter((q) => prefs[q]).map((q) => (
          <tr key={q}><td><i className="rq-dot" style={{ background: QCOLOR[q] }} />{quadranti[q].name}</td>
            {assets.map((a) => <td key={a} style={{ background: bg(prefs[q][a] ?? 0) }}>{itNum(prefs[q][a] ?? 0, 2)}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

function candLabel(c: any): string {
  if (c.tipo !== "imparato") return "teorico";
  return c.solo_regime ? "imparato, solo regime" : "imparato";
}

function Calibration({ t, tilt, quadranti }: { t: any; tilt: any; quadranti: any }) {
  const sig = t.significativita_test;
  const rpT = t.risk_parity.test, chT = t.scelto_stats.test;
  const significant = Math.abs(sig.t) >= 2;
  return (
    <section className="rq-card">
      <h2>Taratura del tilt</h2>
      <div className={`rq-verdict${significant ? " ok" : ""}`}>
        <b>{significant ? "Il tilt aggiunge valore in modo distinguibile dal caso." : "Il tilt non ha ancora dimostrato un vantaggio reale."}</b>{" "}
        Scelto guardando solo il periodo {t.periodi.taratura}: {t.scelto.tipo === "imparato" ? `preferenze imparate dai mesi precedenti${t.scelto.solo_regime ? " (solo la parte che cambia col regime)" : ""}` : "preferenze teoriche"}, decisione tenuta {t.scelto.orizzonte ?? 1} {(t.scelto.orizzonte ?? 1) === 1 ? "mese" : "mesi"}, probabilità medie su {t.scelto.media_mesi} mesi, forza {itNum(t.scelto.forza, 2)}.
        Nel periodo mai visto ({t.periodi.verifica}) Sharpe {itNum(chT.sharpe, 2)} contro {itNum(rpT.sharpe, 2)} del risk parity puro, rendimento annuo {pct(chT.cagr, 1)} contro {pct(rpT.cagr, 1)},
        perdita massima {pct(chT.max_drawdown, 1)} contro {pct(rpT.max_drawdown, 1)}. Statistica t {itNum(sig.t, 1)} (serve circa 2): {significant ? "" : "la differenza può essere rumore."}
      </div>
      <div className="rq-grid two">
        <div>
          <h3>Preferenze in uso ({tilt.modo === "imparato" ? "imparate dai dati, solo dal passato" : "teoriche"})</h3>
          <Prefs prefs={tilt.preferenze} quadranti={quadranti} />
        </div>
        <div>
          <h3>Preferenze teoriche (Dalio)</h3>
          <Prefs prefs={tilt.preferenze_teoriche} quadranti={quadranti} />
        </div>
      </div>
      <h3>Per orizzonte: il migliore sul periodo di taratura</h3>
      <table className="rq-table">
        <thead><tr><th>Decisione tenuta</th><th>Tipo</th><th>Forza</th><th>Sharpe taratura</th><th>Sharpe verifica</th><th>Perdita max verifica</th><th>t verifica</th></tr></thead>
        <tbody>
          {[1, 3, 6, 12].map((h) => {
            const c = t.candidati.find((x: any) => (x.orizzonte ?? 1) === h && x.forza > 0);
            if (!c) return null;
            return (
              <tr key={h}><td>{h} {h === 1 ? "mese" : "mesi"}</td><td>{candLabel(c)}</td><td>{itNum(c.forza, 2)}</td>
                <td>{itNum(c.sharpe_train, 2)}</td><td>{itNum(c.sharpe_test, 2)}</td><td className="down">{pct(c.dd_test, 1)}</td><td>{c.t_test == null ? "–" : itNum(c.t_test, 1)}</td></tr>
            );
          })}
          <tr><td>–</td><td>risk parity puro</td><td>0</td><td>{itNum(t.risk_parity.train.sharpe, 2)}</td><td>{itNum(rpT.sharpe, 2)}</td><td className="down">{pct(rpT.max_drawdown, 1)}</td><td>–</td></tr>
        </tbody>
      </table>
      <h3>Candidati provati (ordinati sul periodo di taratura)</h3>
      <table className="rq-table">
        <thead><tr><th>Tipo</th><th>Orizzonte</th><th>σ</th><th>Media mesi</th><th>Forza</th><th>Sharpe taratura</th><th>Sharpe verifica</th><th>Perdita max verifica</th></tr></thead>
        <tbody>
          {t.candidati.slice(0, 10).map((c: any, i: number) => (
            <tr key={i} className={i === 0 ? "rq-best" : ""}><td>{c.forza === 0 ? "risk parity puro" : candLabel(c)}</td><td>{c.orizzonte ?? 1} m</td><td>{itNum(c.sigma, 1)}</td><td>{c.media_mesi}</td><td>{itNum(c.forza, 2)}</td>
              <td>{itNum(c.sharpe_train, 2)}</td><td>{itNum(c.sharpe_test, 2)}</td><td className="down">{pct(c.dd_test, 1)}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="rq-note">Con un orizzonte di h mesi la decisione di ogni mese resta in portafoglio per h mesi (si tiene la media delle ultime h decisioni) e le preferenze imparate si stimano sui rendimenti a h mesi, solo da finestre già chiuse. «Solo regime» toglie la parte comune a tutti i regimi (per esempio «più oro sempre»), così resta solo il vero tempismo. Le differenze di Sharpe sotto 0,27 stanno dentro l&apos;errore statistico. Si rifà con <code>python -m app.cli rqe-taratura</code>.</p>
    </section>
  );
}

export default function RegimePage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    fetch("/rqe/rqe.json", { cache: "no-store" }).then((r) => r.json()).then(setD).catch(() => setErr(true));
  }, []);
  if (err) return <main className="rq"><p>Dati non disponibili: esegui <code>python -m app.cli rqe</code>.</p></main>;
  if (!d) return <main className="rq"><p className="rq-muted">Carico il motore dei regimi…</p></main>;
  const r = d.regime, al = d.allocazione, bt = d.backtest;
  return (
    <main className="rq">
      <header className="rq-head">
        <div>
          <div className="rq-eyebrow">Regime &amp; Quality Engine · Dalio × Buffett</div>
          <h1>{r.nome}</h1>
          <p className="rq-muted">{r.descrizione} Dati al {d.as_of.split("-").reverse().join("/")}.</p>
        </div>
        <Link href="/" className="rq-back">← Cabina</Link>
      </header>

      <section className="rq-grid">
        <div className="rq-card">
          <h2>Probabilità dei quattro regimi</h2>
          {QS.map((q) => (
            <div key={q} className={`rq-prob${q === r.dominante ? " on" : ""}`}>
              <span>{d.quadranti[q].name}</span>
              <Bar v={r.probabilita[q]} color={QCOLOR[q]} />
              <b>{pct(r.probabilita[q])}</b>
            </div>
          ))}
          <p className="rq-note">P(crescita sopra il trend) {pct(r.crescita.p_su)} · P(inflazione sopra il trend) {pct(r.inflazione.p_su)}. Le probabilità dei regimi sono i prodotti.</p>
        </div>
        <div className="rq-card rq-center">
          <h2>Dove siamo</h2>
          <QuadrantMap hist={d.storico} now={r} />
          <p className="rq-note">Punto pieno: oggi. Scia: gli ultimi 12 mesi.</p>
        </div>
        <div className="rq-card">
          <h2>I segnali</h2>
          {(["crescita", "inflazione"] as const).map((k) => (
            <div key={k} className="rq-signal">
              <div className="rq-signal-head"><b>{k === "crescita" ? "Crescita" : "Inflazione"}</b><span>{itNum(r[k].punteggio, 2)}</span></div>
              {r[k].componenti.map((c: any) => (
                <div key={c.serie} className="rq-comp">
                  <span>{c.nome}</span>
                  <i className={c.segnale > 0 ? "up" : c.segnale < 0 ? "down" : ""}>{c.segnale === null ? "—" : itNum(c.segnale, 2)}</i>
                </div>
              ))}
            </div>
          ))}
          <p className="rq-note">Ogni segnale: variazione a 3–6 mesi rispetto agli ultimi 5 anni (z-score robusto). Positivo = sopra il trend.</p>
        </div>
      </section>

      <section className="rq-card">
        <h2>Storico dei regimi dal 2000</h2>
        <History hist={d.storico} />
        <div className="rq-legend">{QS.map((q) => <span key={q}><i style={{ background: QCOLOR[q] }} />{d.quadranti[q].name}</span>)}</div>
        <p className="rq-note">Ogni mese usa solo i dati pubblicati entro quel mese, revisioni comprese.</p>
      </section>

      <section className="rq-card">
        <h2>Allocazione modello · All Weather con tilt per regime</h2>
        <table className="rq-table">
          <thead><tr><th>Asset</th><th>Base (risk parity)</th><th>Consigliata</th><th>Scostamento</th><th>Perché</th></tr></thead>
          <tbody>
            {al.righe.map((x: any) => (
              <tr key={x.asset}>
                <td>{x.nome}</td>
                <td><div className="rq-cell"><Bar v={x.base * 2} color="#8a8fb4" />{pct(x.base, 1)}</div></td>
                <td><div className="rq-cell"><Bar v={x.consigliato * 2} color="#5fe1ff" />{pct(x.consigliato, 1)}</div></td>
                <td className={x.scostamento > 0.004 ? "up" : x.scostamento < -0.004 ? "down" : ""}>{x.scostamento >= 0 ? "+" : ""}{itNum(x.scostamento * 100, 1)} pt</td>
                <td className="rq-muted">{x.motivo}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="rq-note">Pesi di base inversamente proporzionali alla volatilità degli ultimi 12 mesi; tilt con probabilità medie su {al.tilt.media_mesi} mesi, decisione tenuta {al.tilt.orizzonte_mesi ?? 1} mesi e preferenze {al.tilt.modo === "imparato" ? "imparate dai dati (vedi Taratura)" : "teoriche"}; scostamento massimo ±{itNum(al.limiti.scostamento_massimo * 100)} punti. Allocazione modello a scopo di ricerca, non consulenza personalizzata.</p>
      </section>

      {d.taratura && <Calibration t={d.taratura} tilt={al.tilt} quadranti={d.quadranti} />}

      <section className="rq-card">
        <h2>Backtest dal {bt.statistiche.rp.dal.slice(0, 4)}</h2>
        <Curves curve={bt.curve} names={bt.strategie} />
        <table className="rq-table">
          <thead><tr><th>Strategia</th><th>Rendimento annuo</th><th>Volatilità</th><th>Sharpe</th><th>Perdita massima</th></tr></thead>
          <tbody>
            {Object.entries(bt.statistiche).map(([k, s]: [string, any]) => (
              <tr key={k}><td>{bt.strategie[k]}</td><td>{pct(s.cagr, 1)}</td><td>{pct(s.volatilita, 1)}</td><td>{itNum(s.sharpe, 2)}</td><td className="down">{pct(s.max_drawdown, 1)}</td></tr>
            ))}
          </tbody>
        </table>
        <h3>Rendimento medio mensile per regime</h3>
        <table className="rq-table">
          <thead><tr><th>Regime</th><th>Mesi</th>{Object.keys(bt.strategie).map((k) => <th key={k}>{bt.strategie[k]}</th>)}</tr></thead>
          <tbody>
            {QS.filter((q) => bt.per_regime[q]).map((q) => (
              <tr key={q}><td><i className="rq-dot" style={{ background: QCOLOR[q] }} />{d.quadranti[q].name}</td><td>{bt.per_regime[q].mesi}</td>
                {Object.keys(bt.strategie).map((k) => <td key={k}>{pct(bt.per_regime[q].strategie[k], 2)}</td>)}</tr>
            ))}
          </tbody>
        </table>
        <ul className="rq-notes">{bt.note.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
      </section>

      <section className="rq-grid two">
        <div className="rq-card">
          <h2>Alert: cambi di regime</h2>
          <ul className="rq-alerts">
            {[...d.alert.cambi_di_regime].reverse().map((e: any) => (
              <li key={e.data}><span>{e.data.split("-").reverse().join("/")}</span>
                <i style={{ color: QCOLOR[e.da as Q] }}>{d.quadranti[e.da].name}</i> → <b style={{ color: QCOLOR[e.a as Q] }}>{d.quadranti[e.a].name}</b> ({pct(e.probabilita)})</li>
            ))}
          </ul>
          <p className="rq-note">Scatta quando il regime più probabile cambia e il nuovo supera il {pct(d.alert.soglia)}.</p>
        </div>
        <div className="rq-card">
          <h2>Screener Buffett</h2>
          <p className="rq-muted">In arrivo: titoli dei settori favoriti dal regime, con ROE, debito/EBITDA, free cash flow, margini, valore intrinseco (DCF) e margine di sicurezza. Serve la chiave dei dati fondamentali (FMP).</p>
        </div>
      </section>
    </main>
  );
}
