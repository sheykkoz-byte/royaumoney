"use client";

// TradingView's free embeddable widgets (charts with every market, ticker tape).
// The chart is TradingView's own; it is not linked to the user's TradingView account.
import { useEffect, useId, useRef } from "react";

/* eslint-disable @typescript-eslint/no-explicit-any */
let tvLoad: Promise<void> | null = null;
function loadTv(): Promise<void> {
  if ((window as any).TradingView) return Promise.resolve();
  tvLoad ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/tv.js";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => { tvLoad = null; reject(new Error("TradingView non raggiungibile")); };
    document.head.appendChild(s);
  });
  return tvLoad;
}

const BG = "rgba(8, 9, 18, 1)";

export function TvChart({ symbol, interval = "60", compact = false }: {
  symbol: string; interval?: string; compact?: boolean;
}) {
  const id = "tv" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const failed = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    loadTv().then(() => {
      if (cancelled || !document.getElementById(id)) return;
      new (window as any).TradingView.widget({
        container_id: id, symbol, interval, autosize: true,
        timezone: "Europe/Rome", theme: "dark", style: "1", locale: "it",
        backgroundColor: BG, gridColor: "rgba(150, 140, 255, 0.06)",
        allow_symbol_change: !compact, hide_top_toolbar: compact, hide_side_toolbar: compact,
        hide_legend: false, withdateranges: !compact, save_image: false, details: false,
        enable_publishing: false, studies: [],
      });
    }).catch(() => { if (failed.current) failed.current.hidden = false; });
    return () => {
      cancelled = true;
      const el = document.getElementById(id);
      if (el) el.innerHTML = "";
    };
  }, [id, symbol, interval, compact]);
  return (
    <div className="tv-wrap">
      <div id={id} className="tv-host" />
      <div ref={failed} className="tv-failed" hidden>
        Grafico TradingView non raggiungibile: controlla la connessione.
      </div>
    </div>
  );
}

export function TickerTape({ symbols }: { symbols: { s: string; n: string }[] }) {
  const host = useRef<HTMLDivElement>(null);
  const key = symbols.map((x) => x.s).join(",");
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    el.innerHTML = '<div class="tradingview-widget-container__widget"></div>';
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbols: symbols.map((x) => ({ proName: x.s, title: x.n })),
      showSymbolLogo: true, isTransparent: true, displayMode: "adaptive",
      colorTheme: "dark", locale: "it",
    });
    el.appendChild(s);
    return () => { el.innerHTML = ""; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return <div ref={host} className="tradingview-widget-container tape" />;
}
