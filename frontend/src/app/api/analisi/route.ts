// "Chiedi a Claude" on the site: a server-side route that asks Claude to analyse the data the
// pages show (regime, calibration, institutional ideas) and streams the answer as text.
// The key stays on the server (Vercel environment variable ANTHROPIC_API_KEY); the page is
// behind the site password like everything else (middleware.ts).
import Anthropic from "@anthropic-ai/sdk";
import inst from "../../../../public/istituzionali/13f.json";
import rqe from "../../../../public/rqe/rqe.json";

export const runtime = "nodejs";
export const maxDuration = 120;

/* eslint-disable @typescript-eslint/no-explicit-any */
const I = inst as any, R = rqe as any;

const SYSTEM = `Sei l'analista di ricerca di RoyauMoney. Rispondi in italiano, chiaro e diretto, per un trader esperto.
Regole:
- Usa SOLO i dati JSON qui sotto. Non inventare numeri, prezzi, notizie o eventi. Se un dato manca, dillo.
- Il 13F è una fotografia a fine trimestre depositata fino a 45 giorni dopo: i gestori possono aver già cambiato posizione. Ricordalo quando conta.
- BlackRock e JPMorgan muovono soprattutto flussi di clienti e fondi indice: non trattare i loro movimenti come opinioni.
- Il "prezzo pagato" è una stima (media delle chiusure del trimestre).
- Lente Buffett: qualità (ROE, debito/EBITDA, margini, flusso di cassa), valore intrinseco da flussi di cassa scontati e margine di sicurezza (almeno 25%). I fondamentali vengono da Yahoo: sono un ordine di grandezza.
- Lente Dalio: regime più probabile, settori che la teoria lega a ogni regime, e come il settore è andato davvero per regime dal 1999. Se teoria e storia non concordano, dillo.
- Il tilt per regime non ha dimostrato un vantaggio statistico: non presentarlo come certezza.
- Chiudi con: "Ricerca, non consulenza personalizzata."
Formato: titoletti preceduti da "## ", elenchi con "- ", grassetto con **testo**. Massimo 400 parole.`;

function compactIdea(i: any, full: boolean) {
  const p = i.prezzi ?? {}, a = i.approfondimento ?? {}, b = a.buffett ?? {}, d = a.dalio ?? {};
  const base = {
    ticker: i.ticker, nome: a.profilo?.nome ?? i.emittente, settore: i.settore, giudizio: i.giudizio,
    gestori: i.gestori, tipo: i.tipo, valore_acquisti: i.valore_acquisti, favore_regime: i.favore_regime,
    prezzo_pagato_stima: p.prezzo_medio_trimestre, prezzo_oggi: p.prezzo_oggi, da_loro: p.da_prezzo_medio,
    margine_sicurezza_base: b.scenari?.base?.margine ?? null, controlli_buffett: `${b.superati}/${b.su}`,
    eccesso_storico_settore_pesato: d.eccesso_atteso ?? null,
  };
  if (!full) return base;
  return {
    ...base, motivi: i.motivi, dettaglio_gestori: i.dettaglio_gestori, prezzi: p, profilo: a.profilo,
    buffett: b, dalio: { favorito_in: d.favorito_in, etf: d.etf_settore, dal: d.storia_dal, per_regime: d.per_regime },
    avviso: a.avviso ?? null,
  };
}

function context(ticker?: string) {
  const r = R.regime, t = R.taratura;
  const idea = ticker ? I.idee.find((x: any) => x.ticker === ticker) : null;
  return {
    oggi: I.oggi,
    regime: { nome: r.nome, probabilita: r.probabilita, nomi: Object.fromEntries(Object.entries(R.quadranti).map(([q, v]: any) => [q, v.name])),
      crescita_p_su: r.crescita.p_su, inflazione_p_su: r.inflazione.p_su },
    settori_per_regime: R.settori,
    allocazione: R.allocazione.righe.map((x: any) => ({ nome: x.nome, base: x.base, con_regime: x.consigliato })),
    taratura_tilt: t ? { t_verifica: t.significativita_test?.t, sharpe_rp_verifica: t.risk_parity?.test?.sharpe, sharpe_scelto_verifica: t.scelto_stats?.test?.sharpe } : null,
    gestori: I.gestori.map((m: any) => ({ nome: m.nome, stile: m.stile, periodo: m.periodo, depositato: m.depositato })),
    titolo_richiesto: idea ? compactIdea(idea, true) : null,
    idee: I.idee.map((x: any) => compactIdea(x, false)),
  };
}

function apiKey() {
  return process.env.ANTHROPIC_API_KEY || process.env.JARVIS_ANTHROPIC_API_KEY || "";
}

export async function GET() {
  return Response.json({ disponibile: Boolean(apiKey()) });
}

export async function POST(req: Request) {
  const key = apiKey();
  if (!key) {
    return new Response("Analisi non disponibile: manca la chiave ANTHROPIC_API_KEY nelle impostazioni di Vercel.", { status: 503 });
  }
  let body: { domanda?: string; ticker?: string };
  try { body = await req.json(); } catch { return new Response("Richiesta non valida.", { status: 400 }); }
  const domanda = String(body.domanda ?? "").trim().slice(0, 1500);
  const ticker = body.ticker ? String(body.ticker).slice(0, 12) : undefined;
  if (!domanda) return new Response("Scrivi una domanda.", { status: 400 });

  const client = new Anthropic({ apiKey: key });
  const stream = client.beta.messages.stream({
    model: "claude-opus-5-5",
    max_tokens: 16000,
    output_config: { effort: "medium" },
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    cache_control: { type: "ephemeral" },
    system: `${SYSTEM}\n\nDATI (JSON):\n${JSON.stringify(context(ticker))}`,
    messages: [{ role: "user", content: domanda }],
  });

  const enc = new TextEncoder();
  const out = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for await (const ev of stream) {
          if (ev.type === "content_block_delta" && ev.delta.type === "text_delta") controller.enqueue(enc.encode(ev.delta.text));
        }
        const final = await stream.finalMessage();
        if (final.stop_reason === "refusal") controller.enqueue(enc.encode("\n\nClaude ha rifiutato questa richiesta."));
        if (final.stop_reason === "max_tokens") controller.enqueue(enc.encode("\n\n(Risposta interrotta: troppo lunga.)"));
      } catch (e) {
        const msg = e instanceof Anthropic.AuthenticationError ? "chiave API non valida"
          : e instanceof Anthropic.RateLimitError ? "troppe richieste, riprova tra un minuto"
          : e instanceof Anthropic.BadRequestError ? `richiesta respinta (${e.message.slice(0, 200)})`
          : e instanceof Anthropic.APIError ? `errore ${e.status ?? ""} dal servizio`
          : "errore di rete";
        controller.enqueue(enc.encode(`\n\nAnalisi non riuscita: ${msg}.`));
      } finally {
        controller.close();
      }
    },
    cancel() { stream.abort(); },
  });
  return new Response(out, { headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" } });
}
