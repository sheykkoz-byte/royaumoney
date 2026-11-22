"use client";

// Two always-visible entry points in the cockpit's top bar: macro regimes and institutional
// holdings, each with today's headline so the reason to click is visible at a glance.
import Link from "next/link";
import { useEffect, useState } from "react";
import { itNum } from "@/lib/jarvis";

/* eslint-disable @typescript-eslint/no-explicit-any */
const QC: Record<string, string> = { A: "#5fe1ff", B: "#ffc35a", C: "#ff5d73", D: "#8b7cff" };

function RegimeIcon({ dom }: { dom?: string }) {
  const cells: [string, number, number][] = [["C", 0, 0], ["B", 13, 0], ["D", 0, 13], ["A", 13, 13]];
  return (
    <svg viewBox="0 0 25 25" className="sec-icon" aria-hidden="true">
      {cells.map(([q, x, y]) => <rect key={q} x={x} y={y} width="12" height="12" rx="2.5" fill={QC[q]} opacity={q === dom ? 1 : 0.28} />)}
    </svg>
  );
}

function InstIcon() {
  return (
    <svg viewBox="0 0 25 25" className="sec-icon" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M3 9 12.5 3 22 9" /><path d="M5 10v9M10 10v9M15 10v9M20 10v9" /><path d="M3 22h19" />
    </svg>
  );
}

export default function Sections() {
  const [rq, setRq] = useState<any>(null);
  const [inst, setInst] = useState<any>(null);
  useEffect(() => {
    fetch("/rqe/rqe.json", { cache: "no-store" }).then((r) => r.json()).then((d) => setRq(d.regime)).catch(() => {});
    fetch("/istituzionali/13f.json", { cache: "no-store" }).then((r) => r.json()).then((d) => {
      const ok = d.idee.filter((i: any) => i.giudizio === "margine").length;
      const g = d.gestori.find((m: any) => m.periodo);
      setInst({ ok, tot: d.idee.length, periodo: g?.periodo });
    }).catch(() => {});
  }, []);
  const dom = rq?.dominante;
  return (
    <nav className="sec-dock" aria-label="Sezioni di analisi">
      <Link href="/regime" className="sec-tile" style={{ "--sec": dom ? QC[dom] : "#5fe1ff" } as React.CSSProperties}>
        <RegimeIcon dom={dom} />
        <span className="sec-txt">
          <b>Regimi macro</b>
          <small>{rq ? `${rq.nome} · ${itNum(rq.probabilita[dom] * 100)}%` : "Dalio · All Weather"}</small>
        </span>
      </Link>
      <Link href="/istituzionali" className="sec-tile" style={{ "--sec": "#3ddc97" } as React.CSSProperties}>
        <InstIcon />
        <span className="sec-txt">
          <b>Istituzionali</b>
          <small>{inst ? `${inst.ok} idee con margine su ${inst.tot}` : "13F × regime"}</small>
        </span>
      </Link>
    </nav>
  );
}
