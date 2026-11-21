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

async function getHealth(): Promise<DataHealth | null> {
  try {
    const r = await fetch(`${API}/health/data`, { cache: "no-store" });
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

export default async function Home() {
  const h = await getHealth();
  return (
    <main>
      <h1>ROYAUMONEY · JARVIS</h1>
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
