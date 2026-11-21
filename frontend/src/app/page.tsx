// Phase 0 placeholder: shows the data engine's health. The immersive UI arrives in phases 4–6
// (see prototype/index.html for the target look).

type SeriesHealth = {
  id: string;
  name: string;
  category: string;
  last_ref_date: string | null;
  age_days: number | null;
  max_age_days: number;
  status: "green" | "yellow" | "red";
  error: string | null;
};
type DataHealth = {
  status: string;
  counts: Record<string, number>;
  series: SeriesHealth[];
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

type Target = { label: string; status: string; trigger: number; deadline: string; hit_on: string | null; hit_price: number | null };
type Prediction = {
  id: string; title: string; asset: string; status: string; entry_price: number;
  created_at: string; resolved_on: string | null; last_bar_date: string | null;
  targets: Target[]; extremes: { high?: number; low?: number; last_close?: number } | null;
};
type Group = { total: number; open: number; resolved: number; hit: number; hit_rate: number | null };
type TrackRecord = { overall: Group; brier: { score: number | null; n: number } };

async function get<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${API}${path}`, { cache: "no-store" });
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

const STATUS_CLASS: Record<string, string> = {
  aperta: "yellow", colpita: "green", invalidata: "red", scaduta: "red",
  raggiunta: "green", attiva: "yellow", mancata: "red", "in attesa": "idle",
};

function TrackRecordPanel({ tr, preds }: { tr: TrackRecord; preds: Prediction[] }) {
  const o = tr.overall;
  return (
    <section className="block">
      <h2>TRACK RECORD</h2>
      <p className="sub">
        {o.total} previsioni · {o.open} aperte · {o.resolved} chiuse
        {o.hit_rate !== null && <> · successo {(o.hit_rate * 100).toFixed(0)}%</>}
        {tr.brier.score !== null && <> · Brier {tr.brier.score.toFixed(3)} (su {tr.brier.n})</>}
      </p>
      {preds.map((p) => (
        <div key={p.id} className="pred">
          <div className="pred-head">
            <span className={`dot ${STATUS_CLASS[p.status] ?? ""}`} />
            <b className="num">{p.id}</b> <span>{p.title}</span>
            <span className="tag">{p.status}</span>
          </div>
          <div className="sub">
            {p.asset} · ingresso {p.entry_price} · registrata {p.created_at.slice(0, 10)}
            {p.extremes?.last_close !== undefined && <> · ultima chiusura {p.extremes.last_close} (max {p.extremes.high}, min {p.extremes.low})</>}
            {p.last_bar_date ? <> · verificata al {p.last_bar_date}</> : <> · in attesa del primo prezzo</>}
          </div>
          <ol>
            {p.targets.map((t) => (
              <li key={t.label}>
                <span className={`dot ${STATUS_CLASS[t.status] ?? ""}`} /> {t.label}: {t.trigger} entro {t.deadline}
                {t.hit_on && <> → {t.hit_on} a {t.hit_price}</>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}

export default async function Home() {
  const [h, tr, preds] = await Promise.all([
    get<DataHealth>("/health/data"),
    get<TrackRecord>("/track-record"),
    get<Prediction[]>("/previsioni"),
  ]);
  return (
    <main>
      <h1>ROYAUMONEY · JARVIS</h1>
      {tr && preds && <TrackRecordPanel tr={tr} preds={preds} />}
      {!h ? (
        <p className="sub">Backend non raggiungibile su {API}. Avvialo con <code>make dev</code>.</p>
      ) : (
        <>
          <p className="sub">
            Stato dei dati: <span className={`dot ${h.status}`} /> {h.counts.green} aggiornate ·{" "}
            {h.counts.yellow} in ritardo · {h.counts.red} mancanti
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th></th><th>Serie</th><th>Nome</th><th>Ultimo dato</th><th>Età</th><th>Nota</th></tr>
              </thead>
              <tbody>
                {h.series.map((s) => (
                  <tr key={s.id}>
                    <td><span className={`dot ${s.status}`} /></td>
                    <td className="num">{s.id}</td>
                    <td>{s.name}</td>
                    <td className="num">{s.last_ref_date ?? "—"}</td>
                    <td className="num">{s.age_days ?? "—"}g / {s.max_age_days}g</td>
                    <td className="err">{s.error ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
