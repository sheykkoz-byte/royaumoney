"use client";

// Market clocks: local time and whether the session is open (regular hours, weekdays;
// holidays are not taken into account).
import { useEffect, useState } from "react";

type Market = { name: string; code: string; tz: string; open: [number, number]; close: [number, number] };
const MARKETS: Market[] = [
  { name: "Tokyo", code: "TYO", tz: "Asia/Tokyo", open: [9, 0], close: [15, 0] },
  { name: "Londra", code: "LDN", tz: "Europe/London", open: [8, 0], close: [16, 30] },
  { name: "Milano", code: "MIL", tz: "Europe/Rome", open: [9, 0], close: [17, 30] },
  { name: "New York", code: "NYC", tz: "America/New_York", open: [9, 30], close: [16, 0] },
];

function parts(now: Date, tz: string) {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, hour: "2-digit", minute: "2-digit", weekday: "short", hourCycle: "h23",
  }).formatToParts(now).map((x) => [x.type, x.value]));
  return { h: Number(p.hour), m: Number(p.minute), wd: p.weekday as string, hhmm: `${p.hour}:${p.minute}` };
}

export function isOpen(now: Date, mk: Market): boolean {
  const { h, m, wd } = parts(now, mk.tz);
  if (wd === "Sat" || wd === "Sun") return false;
  const t = h * 60 + m;
  return t >= mk.open[0] * 60 + mk.open[1] && t < mk.close[0] * 60 + mk.close[1];
}

/** Forex: from Sunday 17:00 to Friday 17:00 New York time. */
export function forexOpen(now: Date): boolean {
  const { h, wd } = parts(now, "America/New_York");
  if (wd === "Sat") return false;
  if (wd === "Sun") return h >= 17;
  if (wd === "Fri") return h < 17;
  return true;
}

export default function Clocks() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 20_000);
    return () => clearInterval(t);
  }, []);
  if (!now) return <div className="clocks" />;
  return (
    <div className="clocks">
      {MARKETS.map((mk) => {
        const open = isOpen(now, mk);
        return (
          <div key={mk.name} className={`clk${open ? " open" : ""}`} title={open ? "Borsa aperta" : "Borsa chiusa"}>
            <i /><span>{mk.name}</span><em>{mk.code}</em><b>{parts(now, mk.tz).hhmm}</b>
          </div>
        );
      })}
      <div className={`clk${forexOpen(now) ? " open" : ""}`}><i /><span>Forex</span><em>FX</em><b>{forexOpen(now) ? "aperto" : "chiuso"}</b></div>
    </div>
  );
}
