"use client";

// Watchlist: favourites on top (starred, in the user's order), then every market by
// category, with search. Any TradingView symbol can be added from the search box.
import { useMemo, useState } from "react";
import { CATEGORIES, nameOf, search, type Sym } from "@/lib/symbols";

type Props = {
  active: string;
  favorites: string[];
  onSelect: (s: string) => void;
  onToggleFavorite: (s: string) => void;
};

function Row({ item, active, fav, onSelect, onToggle }: {
  item: Sym; active: boolean; fav: boolean; onSelect: () => void; onToggle: () => void;
}) {
  return (
    <div className={`wl-row${active ? " on" : ""}`}>
      <button type="button" className="wl-main" onClick={onSelect} title={item.s}>
        <span className="wl-name">{item.n}</span>
        <span className="wl-sym">{item.s.split(":").pop()}</span>
      </button>
      <button type="button" className={`wl-star${fav ? " fav" : ""}`} onClick={onToggle}
        aria-label={fav ? `Togli ${item.n} dai preferiti` : `Aggiungi ${item.n} ai preferiti`}>
        {fav ? "★" : "☆"}
      </button>
    </div>
  );
}

export default function Watchlist({ active, favorites, onSelect, onToggleFavorite }: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const results = useMemo(() => search(q), [q]);
  const favSet = new Set(favorites);
  const custom = q.includes(":") && !results.some((r) => r.s === q.trim().toUpperCase());

  const row = (item: Sym) => (
    <Row key={item.s} item={item} active={item.s === active} fav={favSet.has(item.s)}
      onSelect={() => onSelect(item.s)} onToggle={() => onToggleFavorite(item.s)} />
  );

  return (
    <aside className="cab-panel wl">
      <div className="cab-head"><span>Watchlist</span></div>
      <input id="wl-search" className="wl-search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Cerca: oro, EURUSD, DAX…" autoComplete="off" aria-label="Cerca un mercato" />
      <div className="wl-scroll">
        {q.trim() ? (
          <div className="wl-group">
            {results.map(row)}
            {custom && row({ s: q.trim().toUpperCase(), n: "Simbolo TradingView" })}
            {!results.length && !custom && (
              <p className="wl-hint">Nessun risultato. Puoi scrivere un simbolo TradingView completo,
                per esempio <b>NASDAQ:AMD</b>.</p>
            )}
          </div>
        ) : (
          <>
            <div className="wl-group">
              <div className="wl-cat fav">★ Preferiti</div>
              {favorites.length ? favorites.map((s) => row({ s, n: nameOf(s) }))
                : <p className="wl-hint">Tocca ☆ accanto a un mercato per aggiungerlo qui.</p>}
            </div>
            {CATEGORIES.map((c) => (
              <div key={c.id} className="wl-group">
                <button type="button" className="wl-cat" aria-expanded={!!open[c.id]}
                  onClick={() => setOpen((o) => ({ ...o, [c.id]: !o[c.id] }))}>
                  <span>{c.name}</span><span className="wl-count">{c.items.length} {open[c.id] ? "▾" : "▸"}</span>
                </button>
                {open[c.id] && c.items.map(row)}
              </div>
            ))}
          </>
        )}
      </div>
    </aside>
  );
}
