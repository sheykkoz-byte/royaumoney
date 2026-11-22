"use client";

// Institutional holdings (SEC 13F) crossed with the macro regime.
// Data: /istituzionali/13f.json, written by `python -m app.cli istituzionali`.
import Link from "next/link";
import { useEffect, useState } from "react";
import AskClaude from "@/components/AskClaude";
import IdeaSheet from "@/components/IdeaSheet";
import { itNum } from "@/lib/jarvis";

/* eslint-disable @typescript-eslint/no-explicit-any */
const pct = (x: number | null | undefined, nd = 0, sign = false) =>
  x === null || x === undefined ? "—" : `${sign && x > 0 ? "+" : ""}${itNum(x * 100, nd)}%`;
const usd = (v: number) => {
  const a = Math.abs(v);
  const s = a >= 1e9 ? `${itNum(a / 1e9, 1)} mld` : a >= 1e6 ? `${itNum(a / 1e6, 0)} mln` : `${itNum(a / 1e3, 0)} mila`;
  return `${v < 0 ? "−" : ""}$${s}`;
};
const date = (s?: string) => (s ? s.split("-").reverse().join("/") : "—");
const VERDICT: Record<string, { label: string; cls: string }> = {
  margine: { label: "C'è margine", cls: "ok" },
  "da seguire": { label: "Da seguire", cls: "mid" },
  "treno passato": { label: "Treno passato", cls: "bad" },
  "contro il regime": { label: "Contro il regime", cls: "bad" },
};
const KIND: Record<string, string> = {
  nuova: "nuova", aumentata: "aumentata", "aumentata poco": "aumentata poco", ridotta: "ridotta",
  "ridotta poco": "ridotta poco", venduta: "venduta tutta", invariata: "invariata", "cambio di codice": "cambio di codice",
};

// Where today's price sits against the quarter's range (estimated price paid)
function PriceBar({ p }: { p: any }) {
  if (!p) return <span className="in-muted">prezzo n.d.</span>;
  const lo = Math.min(p.minimo_trimestre, p.prezzo_oggi), hi = Math.max(p.massimo_trimestre, p.prezzo_oggi);
  const x = (v: number) => `${((v - lo) / Math.max(hi - lo, 1e-9)) * 100}%`;
  return (
    <div className="in-pbar" title={`Trimestre: ${itNum(p.minimo_trimestre, 2)}–${itNum(p.massimo_trimestre, 2)}, media ${itNum(p.prezzo_medio_trimestre, 2)}; oggi ${itNum(p.prezzo_oggi, 2)}`}>
      <i className="range" style={{ left: x(p.minimo_trimestre), width: `calc(${x(p.massimo_trimestre)} - ${x(p.minimo_trimestre)})` }} />
      <i className="avg" style={{ left: x(p.prezzo_medio_trimestre) }} />
      <i className="now" style={{ left: x(p.prezzo_oggi) }} />
    </div>
  );
}

function Ideas({ ideas }: { ideas: any[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const [deep, setDeep] = useState<any>(null);
  return (
    <>
    <IdeaSheet idea={deep} onClose={() => setDeep(null)} />
    <table className="rq-table in-ideas">
      <thead><tr><th>Titolo</th><th>Chi l&apos;ha comprato</th><th>Settore</th><th>Regime</th><th>Prezzo medio trim.</th><th>Oggi</th><th>Da loro</th><th>Prezzo vs trimestre</th><th>Giudizio</th></tr></thead>
      <tbody>
        {ideas.map((i) => {
          const v = VERDICT[i.giudizio] ?? { label: i.giudizio, cls: "mid" };
          const p = i.prezzi;
          return [
            <tr key={i.ticker} className="in-row" tabIndex={0} onClick={() => setDeep(i)} onKeyDown={(e) => { if (e.key === "Enter") setDeep(i); }}>
              <td><b>{i.ticker}</b><div className="in-muted">{i.emittente}</div></td>
              <td>{i.gestori.join(", ")}<div className="in-muted">{KIND[i.tipo] ?? i.tipo} · {usd(i.valore_acquisti)}</div></td>
              <td>{i.settore ?? "—"}</td>
              <td>{pct(i.favore_regime)}</td>
              <td>{p ? `$${itNum(p.prezzo_medio_trimestre, 2)}` : "—"}</td>
              <td>{p ? `$${itNum(p.prezzo_oggi, 2)}` : "—"}</td>
              <td className={p && p.da_prezzo_medio > 0 ? "up" : "down"}>{pct(p?.da_prezzo_medio, 1, true)}</td>
              <td><PriceBar p={p} /></td>
              <td><span className={`in-chip ${v.cls}`}>{v.label}</span>
                <button type="button" className="in-more" onClick={(e) => { e.stopPropagation(); setOpen(open === i.ticker ? null : i.ticker); }}>{open === i.ticker ? "meno" : "motivi"}</button></td>
            </tr>,
            open === i.ticker && (
              <tr key={`${i.ticker}-why`} className="in-why"><td colSpan={9}>
                <ul>{i.motivi.map((m: string) => <li key={m}>{m}</li>)}</ul>
                {i.fondamentali && <div className="in-muted">ROE {pct(i.fondamentali.roe)} · debito/patrimonio {i.fondamentali.debito_patrimonio == null ? "—" : itNum(i.fondamentali.debito_patrimonio, 2)} · P/E atteso {i.fondamentali.pe_atteso == null ? "—" : itNum(i.fondamentali.pe_atteso, 1)}</div>}
              </td></tr>
            ),
          ];
        })}
      </tbody>
    </table>
    </>
  );
}

function Manager({ m }: { m: any }) {
  const [tab, setTab] = useState<"acquisti" | "vendite" | "posizioni">("acquisti");
  if (m.errore) return <div className="rq-card"><h2>{m.nome}</h2><p className="in-muted">Non disponibile: {m.errore}</p></div>;
  const rows: any[] = m[tab] ?? [];
  return (
    <div className="rq-card">
      <div className="in-mhead">
        <div>
          <h2>{m.nome} <span className={`in-chip ${m.stile === "discrezionale" ? "ok" : "mid"}`}>{m.stile === "discrezionale" ? "opinioni" : "flussi clienti"}</span></h2>
          <p className="in-muted">{m.nota}</p>
        </div>
        <div className="in-facts">
          <span>{usd(m.valore_totale)}</span><span>{itNum(m.numero_posizioni)} titoli</span>
          <span>al {date(m.periodo)}, depositato il {date(m.depositato)}</span>
        </div>
      </div>
      {m.avviso && <p className="in-warn">{m.avviso}</p>}
      <div className="in-tabs">
        {(["acquisti", "vendite", "posizioni"] as const).map((t) => (
          <button key={t} className={t === tab ? "on" : ""} onClick={() => setTab(t)}>{t === "posizioni" ? "più grandi" : t} ({(m[t] ?? []).length})</button>
        ))}
      </div>
      {rows.length === 0 ? <p className="in-muted">Nessun movimento rilevante (sopra lo 0,2% del portafoglio).</p> : (
        <table className="rq-table">
          <thead><tr><th>Titolo</th><th>Cosa</th><th>Quote</th><th>{tab === "posizioni" ? "Valore" : "Valore mosso"}</th><th>Peso</th><th>Da fine trim.</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.cusip}>
                <td><b>{r.ticker ?? "—"}</b> <span className="in-muted">{r.emittente}</span></td>
                <td>{KIND[r.tipo] ?? r.tipo}{r.frazionamento ? ` (split ${r.frazionamento}:1)` : ""}</td>
                <td>{r.variazione_pct == null ? itNum(r.quote_dopo) : pct(r.variazione_pct, 0, true)}</td>
                <td>{usd(tab === "posizioni" ? r.valore : r.variazione_valore)}</td>
                <td>{pct(r.peso, 1)}</td>
                <td className={r.prezzi && r.prezzi.da_fine_trimestre > 0 ? "up" : "down"}>{pct(r.prezzi?.da_fine_trimestre, 1, true)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function IstituzionaliPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    fetch("/istituzionali/13f.json", { cache: "no-store" }).then((r) => r.json()).then(setD).catch(() => setErr(true));
  }, []);
  if (err) return <main className="rq"><p>Dati non disponibili: esegui <code>python -m app.cli istituzionali</code>.</p></main>;
  if (!d) return <main className="rq"><p className="rq-muted">Carico i depositi 13F…</p></main>;
  const g = d.gestori.find((m: any) => m.periodo) ?? {};
  const counts = d.idee.reduce((a: any, i: any) => ({ ...a, [i.giudizio]: (a[i.giudizio] ?? 0) + 1 }), {});
  return (
    <main className="rq">
      <header className="rq-head">
        <div>
          <div className="rq-eyebrow">Istituzionali · SEC 13F × regime macro</div>
          <h1>Cosa hanno comprato i grandi</h1>
          <p className="rq-muted">Posizioni al {date(g.periodo)}, depositate entro il {date(g.depositato)}: oggi sono passati {g.giorni_dalla_fine_trimestre} giorni dalla fotografia. Regime attuale: <b>{d.regime.nome}</b>.</p>
        </div>
        <div className="in-links"><Link href="/regime" className="rq-back">Regimi →</Link><Link href="/" className="rq-back">← Cabina</Link></div>
      </header>

      <section className="rq-grid">
        <div className="rq-card">
          <h2>Il ritardo</h2>
          <p className="in-big">{g.giorni_di_ritardo_deposito} giorni</p>
          <p className="rq-muted">tra la fine del trimestre e il deposito (il limite di legge è 45). I movimenti possono essere avvenuti in qualsiasi giorno del trimestre: oggi un acquisto può essere vecchio da {g.giorni_dalla_fine_trimestre} a circa {g.giorni_dalla_fine_trimestre + 91} giorni.</p>
        </div>
        <div className="rq-card">
          <h2>Le idee di questo trimestre</h2>
          {Object.entries(VERDICT).map(([k, v]) => (
            <div key={k} className="in-count"><span className={`in-chip ${v.cls}`}>{v.label}</span><b>{counts[k] ?? 0}</b></div>
          ))}
          <p className="rq-note">Solo acquisti dei gestori discrezionali. Clicca un titolo per l&apos;analisi completa alla Buffett e alla Dalio.</p>
        </div>
        <div className="rq-card">
          <h2>Come si giudica</h2>
          <ul className="rq-notes">
            <li>Prezzo pagato stimato = media delle chiusure del trimestre. Entro +{pct(d.regole.vicino_al_prezzo)}: c&apos;è margine; oltre +{pct(d.regole.treno_passato)}: treno passato.</li>
            <li>Regime: probabilità che il regime sia uno di quelli che favoriscono il settore (da {pct(d.regole.regime_favorevole)} favorevole, sotto {pct(d.regole.regime_sfavorevole)} contrario).</li>
            <li>Qualità alla Buffett: ROE ≥ {pct(d.regole.roe_minimo)}, debito/patrimonio ≤ {itNum(d.regole.debito_massimo, 1)}, P/E atteso ≤ {itNum(d.regole.pe_massimo)}.</li>
            <li>Comprato da più gestori nello stesso trimestre: punto in più.</li>
          </ul>
        </div>
      </section>

      <section className="rq-card ac-box">
        <h2>Chiedi a Claude un&apos;analisi</h2>
        <AskClaude placeholder="Es. «Ha senso seguire Berkshire su Lennar?»" quick={[
          { label: "Conclusione complessiva", domanda: "Dammi la conclusione complessiva: in che regime siamo e quali posizioni dei gestori discrezionali hanno ancora margine di ingresso, buona qualità alla Buffett e un settore coerente con il regime (teoria e storia). Elenca le 3-5 idee migliori e le 3 da evitare, con il motivo." },
          { label: "Dove c'è ancora margine?", domanda: "Tra le idee, dove c'è ancora margine rispetto al prezzo pagato dai gestori E margine di sicurezza alla Buffett E un regime favorevole al settore? Ordina dalla più solida alla meno solida." },
          { label: "Cosa può andare storto?", domanda: "Cosa può andare storto nel seguire queste posizioni adesso? Considera ritardo dei dati, regime che potrebbe cambiare, titoli scesi molto dal loro ingresso, concentrazione in un settore." },
        ]} />
      </section>

      <section className="rq-card">
        <h2>Le idee, incrociate con il regime</h2>
        <Ideas ideas={d.idee} />
        <p className="rq-note">Barra: grigio = intervallo di prezzo del trimestre, trattino = prezzo medio (stima di quanto hanno pagato), punto = oggi.</p>
      </section>

      <section className="in-managers">
        {d.gestori.map((m: any) => <Manager key={m.nome} m={m} />)}
      </section>

      <section className="rq-card">
        <h2>Limiti da tenere a mente</h2>
        <ul className="rq-notes">{d.note.map((n: string) => <li key={n}>{n}</li>)}</ul>
      </section>
    </main>
  );
}
