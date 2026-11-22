"use client";

// Macro board: one tile per metric, grouped by section, from /cabina/macro.json
// (backend: app/cabina.py, rebuilt every day). Clicking a tile opens it on the main chart.
import { itNum } from "@/lib/jarvis";

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Tile = {
  id: string; label: string; section: string; unit: string; decimals: number;
  change_kind: "diff" | "pct"; tv: string | null; value: number; date: string;
  changes: Record<string, number | null>; state: "verde" | "giallo" | "rosso" | "neutro";
  reading: string; spark: [string, number][]; errore?: string;
};
export type Spiegazione = {
  cosa_misura: string; riquadri: { label: string; significato: string }[];
  oggi: string[]; semafori: string;
};
export type Macro = {
  generato: string; sezioni: string[]; metriche: Tile[];
  spiegazioni?: Record<string, Spiegazione>; guida_semafori?: string;
  regime: any; convergenza: any; previsioni: any[];
};

// "Cosa vuol dire": under each section, today's reading first, then what it measures and
// what each tile means. Text comes from the backend (app/cabina_guide.py).
function Explain({ e }: { e: Spiegazione }) {
  return (
    <details className="macro-explain" open>
      <summary>Cosa vuol dire</summary>
      {e.oggi.length > 0 && (
        <div className="mx-block">
          <h4>Oggi{e.semafori ? <span> · {e.semafori}</span> : null}</h4>
          <ul className="mx-today">{e.oggi.map((f, i) => <li key={i}>{f}</li>)}</ul>
        </div>
      )}
      <div className="mx-block">
        <h4>Cosa misura</h4>
        <p>{e.cosa_misura}</p>
      </div>
      {e.riquadri.length > 0 && (
        <div className="mx-block">
          <h4>I riquadri</h4>
          <dl className="mx-tiles">
            {e.riquadri.map((r) => (
              <div key={r.label}><dt>{r.label}</dt><dd>{r.significato}</dd></div>
            ))}
          </dl>
        </div>
      )}
    </details>
  );
}

function Spark({ pts, state }: { pts: [string, number][]; state: string }) {
  const vals = pts.map((p) => p[1]).filter((v) => v !== null);
  if (vals.length < 2) return null;
  const W = 120, H = 30;
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const xy = vals.map((v, i) => [(i / (vals.length - 1)) * W, H - 2 - ((v - min) / span) * (H - 4)]);
  const d = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg className={`mt-spark s-${state}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden>
      <path d={`${d}L${W},${H}L0,${H}Z`} className="area" />
      <path d={d} className="line" />
      <circle cx={lx} cy={ly} r={2.2} className="dot" />
    </svg>
  );
}

function change(t: Tile, k: string) {
  const c = t.changes?.[k];
  if (c === null || c === undefined) return null;
  // percentage-point series (yields, spreads, rates) read in basis points
  const bp = t.change_kind === "diff" && (t.unit === "%" || t.unit === "punti %");
  const txt = bp ? `${c >= 0 ? "+" : ""}${itNum(c * 100)} pb`
    : t.change_kind === "pct" ? `${c >= 0 ? "+" : ""}${itNum(c, 1)}%`
    : `${c >= 0 ? "+" : ""}${itNum(c, t.decimals)}`;
  return <span key={k} className={`mt-chg ${c > 0 ? "up" : c < 0 ? "down" : ""}`}><i>{k}</i>{txt}</span>;
}

export function MacroTile({ t, onOpen }: { t: Tile; onOpen: (s: string) => void }) {
  if (t.errore) {
    return <div className="mt err"><div className="mt-label">{t.label}</div><div className="mt-read">Dato non disponibile.</div></div>;
  }
  const body = (
    <>
      <div className="mt-top">
        <span className={`mt-light l-${t.state}`} aria-label={`semaforo ${t.state}`} />
        <span className="mt-label">{t.label}</span>
        <span className="mt-date">{t.date.slice(5).split("-").reverse().join("/")}</span>
      </div>
      <div className="mt-mid">
        <div className="mt-value">{itNum(t.value, t.decimals)}<small>{t.unit}</small></div>
        <Spark pts={t.spark} state={t.state} />
      </div>
      <div className="mt-chgs">{["1g", "1m", "1a"].map((k) => change(t, k))}</div>
      {t.reading && <div className="mt-read">{t.reading}</div>}
    </>
  );
  return t.tv ? (
    <button type="button" className={`mt s-${t.state}`} onClick={() => onOpen(t.tv!)} title="Apri sul grafico principale">{body}</button>
  ) : <div className={`mt s-${t.state}`}>{body}</div>;
}

export default function MacroBoard({ data, onOpen }: { data: Macro | null; onOpen: (s: string) => void }) {
  return (
    <section className="cab-panel macro">
      <div className="cab-head">
        <span>Plancia macro</span>
        {data && <span className="cab-sub">aggiornata {data.generato.replace("T", " ")}</span>}
      </div>
      <div className="macro-scroll">
        {!data && <p className="wl-hint">Carico i dati…</p>}
        {data?.guida_semafori && (
          <details className="macro-explain legend">
            <summary>Come leggere i semafori</summary>
            <p>{data.guida_semafori}</p>
          </details>
        )}
        {data?.sezioni.map((sec) => (
          <div key={sec} className="macro-sec">
            <h3>{sec}</h3>
            <div className="macro-grid">
              {data.metriche.filter((t) => t.section === sec).map((t) => <MacroTile key={t.id} t={t} onOpen={onOpen} />)}
            </div>
            {data.spiegazioni?.[sec] && <Explain e={data.spiegazioni[sec]} />}
          </div>
        ))}
      </div>
    </section>
  );
}
