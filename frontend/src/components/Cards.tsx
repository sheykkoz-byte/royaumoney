"use client";

// Cards Jarvis brings up while talking: regime, scenarios (with divergence alarm),
// a prediction, a single value, a correlation.
import type { CardState } from "@/lib/jarvis";
import { itNum } from "@/lib/jarvis";

/* eslint-disable @typescript-eslint/no-explicit-any */

function Regime({ r }: { r: any }) {
  const axes: [string, string][] = [["liquidity", "Liquidità"], ["growth", "Crescita"], ["inflation", "Inflazione"]];
  return (
    <>
      <div className="p-head"><div className="p-title">Regime macro</div><div className="tag">{r.as_of}</div></div>
      <div className="regime-name">{r.regime}</div>
      {axes.map(([k, label]) => {
        const a = r.assi[k];
        const v = Math.max(-3, Math.min(3, a.punteggio ?? 0));
        return (
          <div key={k} className="axis-row">
            <span>{label}{a.al_confine ? " · al confine" : ""}</span>
            <div className="axis-bar"><i style={{ left: v < 0 ? `${50 + (v / 3) * 50}%` : "50%", width: `${(Math.abs(v) / 3) * 50}%` }} className={v >= 0 ? "pos" : "neg"} /></div>
            <b>{itNum(a.punteggio, 2)}</b>
          </div>
        );
      })}
      {r.storico_regime?.mesi && (
        <div className="sub">In {r.storico_regime.mesi} mesi in questo regime: meglio {r.storico_regime.meglio.map((x: any) => x.asset).join(", ")}; peggio {r.storico_regime.peggio.map((x: any) => x.asset).join(", ")}.</div>
      )}
    </>
  );
}

function Scenari({ s }: { s: any }) {
  return (
    <>
      <div className="p-head"><div className="p-title">Convergenza macro ↔ mercato</div><div className="tag">{s.as_of}</div></div>
      <div className="sub verdict">{s.verdetto}</div>
      {s.scenari.map((x: any) => (
        <div key={x.id} className={`scen${x.allarme_divergenza ? " alarm" : ""}`}>
          <div className="scen-head"><b>{x.nome}</b><span className="num">{x.punteggio}</span></div>
          <div className="voices">
            <span>macro {itNum(x.voce_macro, 2)}</span>
            <span>mercato {itNum(x.voce_mercato, 2)}</span>
            <span>convergenza {x.convergenza ?? "—"}</span>
          </div>
          {x.allarme_divergenza && <div className="alarm-text">⚠ {x.allarme_divergenza.text}</div>}
        </div>
      ))}
    </>
  );
}

function Previsione({ p }: { p: any }) {
  return (
    <>
      <div className="p-head"><div className="p-title">Previsione {p.id}</div><div className="tag">{p.status}</div></div>
      <div className="sub">{p.title}</div>
      <div className="steps">
        {p.targets.map((t: any) => (
          <div key={t.label} className={`st ${t.status === "raggiunta" ? "done" : t.status === "attiva" ? "active" : ""}`}>
            <b>{t.label}</b>
            <p>{itNum(t.trigger)} entro {t.deadline}{t.hit_on ? ` · raggiunta il ${t.hit_on}` : ""}</p>
          </div>
        ))}
      </div>
      {p.invalidations?.length > 0 && <div className="inv">Smentite: {p.invalidations.map((r: any) => r.description).join(" · ")}</div>}
    </>
  );
}

function Valore({ v }: { v: any }) {
  return (
    <>
      <div className="p-head"><div className="p-title">{v.etichetta}</div></div>
      <div className="big">{itNum(v.valore as number)}<span className="unit">{v.unita}</span></div>
    </>
  );
}

function Correlazione({ c }: { c: any }) {
  const r = c.valore as number | null;
  return (
    <>
      <div className="p-head"><div className="p-title">Correlazione</div><div className="tag">{c.mesi} mesi</div></div>
      <div className="big">{r === null ? "—" : itNum(r, 2)}</div>
      <div className="sub">{c.metodo}{c.sfasamento_mesi ? `, sfasamento ${c.sfasamento_mesi} mesi` : ""}. {r !== null && Math.abs(r) < 0.3 ? "Legame debole." : ""}</div>
    </>
  );
}

export default function Card({ card, focus }: { card: CardState; focus: boolean }) {
  const d = card.data;
  let body = null;
  if (card.kind === "regime" && d.regime) body = <Regime r={d.regime} />;
  else if (card.kind === "scenari" && d.scenari) body = <Scenari s={d.scenari} />;
  else if (card.kind === "previsione" && d.previsione) body = <Previsione p={d.previsione} />;
  else if (card.kind === "valore") body = <Valore v={d} />;
  else if (card.kind === "correlazione" && d.correlazione) body = <Correlazione c={d.correlazione} />;
  if (!body) return null;
  return <div className={`panel card-in${focus ? " focus" : ""}`}>{body}</div>;
}
