"use client";

// Deep dive on one stock bought by the managers: price since their entry, Buffett's lens
// (quality, value, margin of safety) and Dalio's lens (how the sector behaves by regime).
import AskClaude from "@/components/AskClaude";
import Sheet from "@/components/ui/Sheet";
import { itNum } from "@/lib/jarvis";

/* eslint-disable @typescript-eslint/no-explicit-any */
const pct = (x: number | null | undefined, nd = 0, sign = false) =>
  x === null || x === undefined ? "—" : `${sign && x > 0 ? "+" : ""}${itNum(x * 100, nd)}%`;
const usd = (v: number | null | undefined, nd = 2) => (v == null ? "—" : `$${itNum(v, nd)}`);
const big = (v: number | null | undefined) => {
  if (v == null) return "—";
  const a = Math.abs(v);
  return `${v < 0 ? "−" : ""}$${a >= 1e12 ? `${itNum(a / 1e12, 2)} mila mld` : a >= 1e9 ? `${itNum(a / 1e9, 1)} mld` : `${itNum(a / 1e6, 0)} mln`}`;
};
const QN: Record<string, string> = { A: "Goldilocks", B: "Reflazione", C: "Stagflazione", D: "Deflazione / recessione" };
const QC: Record<string, string> = { A: "#5fe1ff", B: "#ffc35a", C: "#ff5d73", D: "#8b7cff" };
const VERDICT: Record<string, [string, string]> = {
  margine: ["C'è margine", "ok"], "da seguire": ["Da seguire", "mid"],
  "treno passato": ["Treno passato", "bad"], "contro il regime": ["Contro il regime", "bad"],
};

function PriceChart({ pts, p, b }: { pts: any[]; p: any; b: any }) {
  if (!pts?.length) return <p className="rq-muted">Grafico non disponibile.</p>;
  const W = 900, H = 230, L = 46, R = 10, T = 10, B = 24;
  const base = b?.scenari?.base?.valore;
  const vals = [...pts.map((x) => x.c), p?.minimo_trimestre, p?.massimo_trimestre].filter((v) => v != null) as number[];
  if (base && base < Math.max(...vals) * 2 && base > Math.min(...vals) / 2) vals.push(base);
  const lo = Math.min(...vals) * 0.97, hi = Math.max(...vals) * 1.03;
  const t0 = +new Date(pts[0].d), t1 = +new Date(pts[pts.length - 1].d);
  const x = (d: string) => L + ((+new Date(d) - t0) / Math.max(t1 - t0, 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const path = pts.map((q, i) => `${i ? "L" : "M"}${x(q.d).toFixed(1)},${y(q.c).toFixed(1)}`).join("");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => lo + f * (hi - lo));
  const qEnd = p?.data_prezzo ? null : null; void qEnd;
  const last = pts[pts.length - 1];
  const months = pts.filter((q, i) => i === 0 || q.d.slice(5, 7) !== pts[i - 1].d.slice(5, 7)).filter((_, i) => i % 2 === 0);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="ia-chart" role="img" aria-label="Prezzo nell'ultimo anno">
      {ticks.map((v) => <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="ia-grid" /><text x={L - 6} y={y(v) + 3} textAnchor="end" className="ia-lab">{itNum(v, v < 20 ? 1 : 0)}</text></g>)}
      {months.map((m) => <text key={m.d} x={x(m.d)} y={H - 6} className="ia-lab">{m.d.slice(5, 7)}/{m.d.slice(2, 4)}</text>)}
      {p && <rect x={L} width={W - L - R} y={y(p.massimo_trimestre)} height={Math.max(1, y(p.minimo_trimestre) - y(p.massimo_trimestre))} className="ia-band" />}
      {p && <line x1={L} x2={W - R} y1={y(p.prezzo_medio_trimestre)} y2={y(p.prezzo_medio_trimestre)} className="ia-avg" />}
      {base && base >= lo && base <= hi && <line x1={L} x2={W - R} y1={y(base)} y2={y(base)} className="ia-iv" />}
      <path d={path} className="ia-line" />
      <circle cx={x(last.d)} cy={y(last.c)} r={4.5} className="ia-dot" />
    </svg>
  );
}

function Check({ ok }: { ok: boolean | null }) {
  return ok === null ? <i className="sh-na">n.d.</i> : ok ? <i className="sh-ok">✓ sì</i> : <i className="sh-no">✗ no</i>;
}

function checkValue(nome: string, v: number | null) {
  if (v == null) return "—";
  if (nome.startsWith("Debito")) return itNum(v, 2) + "×";
  if (nome.startsWith("Flusso")) return big(v);
  return pct(v, 1);
}

export default function IdeaSheet({ idea, onClose }: { idea: any | null; onClose: () => void }) {
  if (!idea) return null;
  const a = idea.approfondimento ?? {}, p = idea.prezzi, b = a.buffett, dl = a.dalio, pf = a.profilo ?? {};
  const v = VERDICT[idea.giudizio] ?? [idea.giudizio, "mid"];
  const fav: string[] = dl?.favorito_in ?? [];
  const favProb = fav.reduce((s: number, q: string) => s + (dl?.probabilita?.[q] ?? 0), 0);
  const exp = dl?.eccesso_atteso;
  // A plain-language synthesis built only from the numbers above
  const sintesi: string[] = [];
  if (p) sintesi.push(p.da_prezzo_medio <= 0.1
    ? `Rispetto al prezzo medio a cui l'hanno comprato (${usd(p.prezzo_medio_trimestre)}) oggi è a ${usd(p.prezzo_oggi)} (${pct(p.da_prezzo_medio, 1, true)}): si può ancora entrare vicino al loro prezzo.`
    : `Oggi è a ${usd(p.prezzo_oggi)}, ${pct(p.da_prezzo_medio, 1, true)} sopra il loro prezzo medio stimato: si entrerebbe più cari di loro.`);
  if (b?.scenari?.base?.margine != null) sintesi.push(`Lente Buffett: valore intrinseco stimato ${usd(b.scenari.base.valore)} nello scenario base, margine di sicurezza ${pct(b.scenari.base.margine, 0)} (ne serve almeno il 25%). ${b.sintesi}`);
  else if (b) sintesi.push(`Lente Buffett: ${b.sintesi} Controlli superati ${b.superati} su ${b.su}.`);
  if (dl?.settore) sintesi.push(`Lente Dalio: la teoria lega ${dl.settore} a ${fav.length ? fav.map((q) => QN[q]).join(" e ") : "nessun regime in particolare"} (probabilità oggi ${pct(favProb)}); nella storia dal 2000, pesata con i regimi di oggi, il settore ha reso ${exp == null ? "—" : pct(exp, 1, true)} l'anno rispetto all'S&P 500.`);
  return (
    <Sheet open onClose={onClose} accent={v[1] === "ok" ? "#3ddc97" : v[1] === "bad" ? "#ff5d73" : "#ffc35a"}
      eyebrow={<>{idea.settore ?? "Settore n.d."} · {pf.paese ?? ""} <span className={`in-chip ${v[1]}`}>{v[0]}</span></>}
      title={<>{idea.ticker} <span className="rq-muted" style={{ fontSize: 16 }}>{pf.nome ?? idea.emittente}</span></>}>
      <div className="sh-kpis">
        <div className="sh-kpi"><span>Prezzo oggi</span><b>{usd(p?.prezzo_oggi)}</b></div>
        <div className="sh-kpi"><span>Pagato da loro (stima)</span><b>{usd(p?.prezzo_medio_trimestre)}</b><small className="rq-muted"> {usd(p?.minimo_trimestre)}–{usd(p?.massimo_trimestre)}</small></div>
        <div className="sh-kpi"><span>Da loro a oggi</span><b className={p?.da_prezzo_medio > 0 ? "up" : "down"}>{pct(p?.da_prezzo_medio, 1, true)}</b></div>
        <div className="sh-kpi"><span>Valore intrinseco (base)</span><b>{usd(b?.scenari?.base?.valore)}</b></div>
        <div className="sh-kpi"><span>Margine di sicurezza</span><b className={(b?.scenari?.base?.margine ?? -1) >= 0.25 ? "up" : "down"}>{pct(b?.scenari?.base?.margine)}</b></div>
        <div className="sh-kpi"><span>Il regime favorisce il settore</span><b>{pct(idea.favore_regime)}</b></div>
      </div>

      <div>
        <h3>In sintesi</h3>
        <ul className="sh-list">{sintesi.map((t) => <li key={t}>{t}</li>)}</ul>
        {a.avviso && <p className="in-warn">{a.avviso}</p>}
      </div>

      <div className="ac-box">
        <h3>Chiedi a Claude un&apos;analisi di {idea.ticker}</h3>
        <AskClaude ticker={idea.ticker} placeholder={`Es. «Conviene entrare su ${idea.ticker} adesso o aspettare?»`} quick={[
          { label: "Analisi completa", domanda: `Analizza ${idea.ticker} incrociando le due lenti: chi l'ha comprato e quanto, prezzo pagato stimato rispetto a oggi, qualità e valore alla Buffett (margine di sicurezza), regime macro e storia del settore alla Dalio. C'è ancora margine per entrare come hanno fatto loro? Dammi una conclusione chiara.` },
          { label: "Cosa può andare storto", domanda: `Quali sono i rischi principali nel seguire i gestori su ${idea.ticker} adesso? Considera ritardo dei dati, prezzo, valutazione, regime che potrebbe cambiare.` },
          { label: "A che prezzo entrerei", domanda: `In base al valore intrinseco stimato, al prezzo pagato dai gestori e al margine di sicurezza richiesto da Buffett, quale fascia di prezzo renderebbe ${idea.ticker} interessante? Spiega il calcolo usando solo i dati.` },
        ]} />
      </div>

      <div>
        <h3>Prezzo nell&apos;ultimo anno</h3>
        <PriceChart pts={a.grafico} p={p} b={b} />
        <div className="rq-legend">
          <span><i style={{ background: "rgba(255,195,90,.35)" }} />Intervallo del trimestre dell&apos;acquisto</span>
          <span><i style={{ background: "#ffc35a" }} />Prezzo medio stimato pagato</span>
          <span><i style={{ background: "#3ddc97" }} />Valore intrinseco (scenario base)</span>
          <span>52 settimane: {usd(pf.min_52s)} – {usd(pf.max_52s)} · obiettivo medio di {pf.analisti ?? "—"} analisti: {usd(pf.prezzo_obiettivo)}</span>
        </div>
      </div>

      <div>
        <h3>Chi l&apos;ha comprato</h3>
        <div className="scroll"><table className="rq-table">
          <thead><tr><th>Gestore</th><th>Mossa</th><th>Quote prima → dopo</th><th>Valore mosso</th><th>Peso nel suo portafoglio</th></tr></thead>
          <tbody>{(idea.dettaglio_gestori ?? []).map((g: any) => (
            <tr key={g.nome}><td><b>{g.nome}</b><div className="rq-muted">{g.nota}</div></td><td>{g.tipo}{g.variazione_pct != null ? ` (${pct(g.variazione_pct, 0, true)})` : ""}</td>
              <td className="num">{itNum(g.quote_prima)} → {itNum(g.quote_dopo)}</td><td>{big(g.variazione_valore)}</td><td>{pct(g.peso, 1)}</td></tr>
          ))}</tbody>
        </table></div>
      </div>

      <div className="sh-cols">
        <div>
          <h3>Lente Buffett · qualità e valore</h3>
          {b ? <>
            {b.controlli.map((c: any) => <div key={c.nome} className="sh-check"><span>{c.nome}</span><span className="rq-muted">{checkValue(c.nome, c.valore)}</span><Check ok={c.ok} /></div>)}
            <p className="rq-note">Superati {b.superati} su {b.su}. Tasso di sconto {pct(b.tasso_sconto, 1)} = il maggiore tra 8% e Treasury 10 anni ({pct(b.treasury_10a, 2)}) + 5% di premio per il rischio azionario. Rendimento degli utili {pct(b.rendimento_utili, 1)}.</p>
          </> : <p className="rq-muted">Dati non disponibili.</p>}
        </div>
        <div>
          <h3>Valore intrinseco (flussi di cassa scontati)</h3>
          {b && Object.keys(b.scenari).length ? <div className="scroll"><table className="rq-table">
            <thead><tr><th>Scenario</th><th>Crescita del flusso di cassa</th><th>Valore per azione</th><th>Margine di sicurezza</th></tr></thead>
            <tbody>{(["prudente", "base", "ottimista"] as const).filter((k) => b.scenari[k]).map((k) => {
              const sc = b.scenari[k];
              const capped = k === "ottimista" && b.scenari.base && sc.crescita === b.scenari.base.crescita;
              return <tr key={k}><td>{k}{capped && <div className="rq-muted">uguale al base: crescita già al tetto del 12%</div>}</td><td>{pct(sc.crescita, 1)}</td><td>{usd(sc.valore)}</td><td className={sc.margine >= 0.25 ? "up" : "down"}>{pct(sc.margine)}</td></tr>;
            })}</tbody>
          </table></div> : <p className="rq-muted">Non calcolabile: manca il flusso di cassa libero o la crescita attesa (o è negativo).</p>}
          <p className="rq-note">Flusso di cassa libero degli ultimi 12 mesi che cresce come gli utili (massimo 12%) per 10 anni scendendo fino al 2,5%, più cassa meno debito. Margine richiesto da Buffett: almeno 25%. Dati Yahoo, non bilanci verificati: è un ordine di grandezza.</p>
          <div className="sh-kpis" style={{ marginTop: 10 }}>
            <div className="sh-kpi"><span>Margine lordo</span><b>{pct(pf.margine_lordo)}</b></div>
            <div className="sh-kpi"><span>Margine operativo</span><b>{pct(pf.margine_operativo)}</b></div>
            <div className="sh-kpi"><span>Crescita ricavi a/a</span><b>{pct(pf.crescita_ricavi, 1, true)}</b></div>
            <div className="sh-kpi"><span>Crescita utili a/a</span><b>{pct(pf.crescita_utili, 1, true)}</b></div>
            <div className="sh-kpi"><span>Capitalizzazione</span><b>{big(pf.capitalizzazione)}</b></div>
            <div className="sh-kpi"><span>Beta</span><b>{pf.beta == null ? "—" : itNum(pf.beta, 2)}</b></div>
          </div>
        </div>
      </div>

      <div>
        <h3>Lente Dalio · il settore {dl?.settore ?? ""} nei quattro regimi</h3>
        <p className="rq-muted" style={{ marginBottom: 8 }}>Teoria: favorito in {fav.length ? fav.map((q) => QN[q]).join(", ") : "nessun regime"} (probabilità oggi {pct(favProb)}). Dati: rendimento in più del fondo settoriale {dl?.etf_settore ?? "—"} rispetto all&apos;S&P 500 nel mese dopo ogni mese in cui quel regime era il più probabile, dal {dl?.storia_dal?.slice(0, 4) ?? "—"}.</p>
        {dl && Object.keys(dl.per_regime ?? {}).length ? <div className="scroll"><table className="rq-table">
          <thead><tr><th>Regime</th><th>Probabilità oggi</th><th>Teoria</th><th>Rendimento in più all&apos;anno</th><th>Mesi positivi</th><th>Mesi osservati</th></tr></thead>
          <tbody>{["A", "B", "C", "D"].map((q) => {
            const h = dl.per_regime[q];
            return <tr key={q}><td><i className="rq-dot" style={{ background: QC[q] }} />{QN[q]}</td><td>{pct(dl.probabilita?.[q])}</td><td>{fav.includes(q) ? "favorito" : "—"}</td>
              <td className={h ? (h.eccesso_annuo > 0 ? "up" : "down") : ""}>{h ? pct(h.eccesso_annuo, 1, true) : "—"}</td><td>{h ? pct(h.quota_positivi) : "—"}</td><td>{h?.mesi ?? "—"}</td></tr>;
          })}
            <tr><td><b>Pesato con i regimi di oggi</b></td><td>100%</td><td></td><td className={exp > 0 ? "up" : "down"}><b>{pct(exp, 1, true)}</b></td><td></td><td></td></tr>
          </tbody>
        </table></div> : <p className="rq-muted">Storico del settore non disponibile.</p>}
        <p className="rq-note">Se teoria e dati non concordano, prevale la prudenza: medie su pochi anni sono rumorose e un settore può cambiare natura (la tecnologia del 2000 non è quella di oggi).</p>
      </div>

      <div>
        <h3>I motivi del giudizio</h3>
        <ul className="sh-list">{idea.motivi.map((m: string) => <li key={m}>{m}</li>)}</ul>
        <p className="rq-note">Le posizioni sono quelle di fine trimestre depositate alla SEC fino a 45 giorni dopo: oggi i gestori possono averle già cambiate. Ricerca, non consulenza personalizzata.</p>
      </div>
    </Sheet>
  );
}
