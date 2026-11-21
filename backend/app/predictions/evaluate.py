"""Verification of one prediction against daily bars. Pure and deterministic: the whole
state is recomputed from the creation date each time, so re-running never drifts.

Rules with daily bars (we do not know the order of events inside a day):
- a target counts from the first bar *after* the creation date, and the next target only
  from the bar after the previous one was hit;
- on a day where both a target and an invalidation are touched, the invalidation wins
  (the prudent reading); close-based invalidations are checked after the targets of the
  same day, since a close comes after the intraday high/low;
- a weekly close is the last bar of a calendar week, known once the week is over.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from app.predictions.spec import Invalidation, PredictionSpec, Target


@dataclass
class Event:
    key: str
    on_date: date
    kind: str  # target_hit | target_missed | invalidated | hit | expired
    message: str
    data: dict = field(default_factory=dict)


@dataclass
class Result:
    status: str  # aperta | colpita | invalidata | scaduta
    resolved_on: date | None
    targets: list[dict]
    rules: list[dict]
    events: list[Event]
    last_bar: date | None
    extremes: dict  # highest high / lowest low since creation


def fmt(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _weekly_closes(bars: pd.DataFrame, as_of: date) -> set[date]:
    """Dates whose bar is the last of its week, and the week is over on ``as_of``."""
    out = set()
    dates = list(bars.index)
    for i, d in enumerate(dates):
        nxt = dates[i + 1] if i + 1 < len(dates) else None
        week_end = d + timedelta(days=6 - d.weekday())  # Sunday
        if nxt is not None and nxt.isocalendar()[:2] != d.isocalendar()[:2]:
            out.add(d)
        elif nxt is None and as_of > week_end - timedelta(days=2) and d.weekday() == 4:
            out.add(d)  # Friday bar, and as_of is Saturday or later
    return out


def _rule_hit(rule: Invalidation, bar, is_week_close: bool) -> tuple[bool, float]:
    hit, price = _rule_hit_raw(rule, bar, is_week_close)
    return bool(hit), float(price)


def _rule_hit_raw(rule: Invalidation, bar, is_week_close: bool):
    k = rule.kind
    if k == "close_above":
        return bar.close > rule.level, bar.close
    if k == "close_below":
        return bar.close < rule.level, bar.close
    if k == "weekly_close_above":
        return is_week_close and bar.close > rule.level, bar.close
    if k == "weekly_close_below":
        return is_week_close and bar.close < rule.level, bar.close
    if k == "touch_above":
        return bar.high >= rule.level, bar.high
    if k == "touch_below":
        return bar.low <= rule.level, bar.low
    raise ValueError(k)  # pragma: no cover


def _target_hit(t: Target, bar) -> tuple[bool, float]:
    if t.kind == "touch_above":
        return bool(bar.high >= t.trigger), float(bar.high)
    return bool(bar.low <= t.trigger), float(bar.low)


def evaluate(spec: PredictionSpec, created: date, bars: pd.DataFrame, as_of: date,
             offset: float = 0.0) -> Result:
    """``bars``: DataFrame indexed by date with open/high/low/close. ``offset`` is added
    to every price (see ``PredictionSpec.align_to_entry``)."""
    b = bars[(bars.index > created) & (bars.index <= as_of)].sort_index() + offset
    b.index = [d if isinstance(d, date) else d.date() for d in b.index]
    week_closes = _weekly_closes(b, as_of)

    tstate = [{"label": t.label, "status": "in attesa", "trigger": t.trigger,
               "deadline": t.deadline.isoformat(), "hit_on": None, "hit_price": None}
              for t in spec.targets]
    rstate = [{"description": r.description, "kind": r.kind, "level": r.level,
               "triggered_on": None, "price": None} for r in spec.invalidations]
    events: list[Event] = []
    current = 0  # index of the target being chased
    earliest = created + timedelta(days=1)  # first day the current target may count
    if spec.targets:
        tstate[0]["status"] = "attiva"

    def resolve(status: str, d: date) -> Result:
        return Result(status, d, tstate, rstate, events, b.index[-1] if len(b) else None,
                      _extremes(b))

    for d, bar in b.iterrows():
        # 1. Deadline of the current target passed without a hit → expired
        t = spec.targets[current]
        if d > t.deadline:
            tstate[current]["status"] = "mancata"
            events.append(Event(f"missed:{current}", t.deadline, "target_missed",
                                f"{t.label}: non raggiunta entro il {t.deadline:%d/%m/%Y}."))
            events.append(Event("expired", t.deadline, "expired",
                                "Previsione scaduta: obiettivo non raggiunto in tempo."))
            return resolve("scaduta", t.deadline)

        # 2. Intraday: touch invalidations and the current target
        touch_rules = [(i, r) for i, r in enumerate(spec.invalidations)
                       if r.kind.startswith("touch") and _active(r, d, created)]
        close_rules = [(i, r) for i, r in enumerate(spec.invalidations)
                       if not r.kind.startswith("touch") and _active(r, d, created)]
        hit_rule = _first_hit(touch_rules, bar, d in week_closes)
        hit_target, price = (False, None)
        if d >= earliest and (t.not_before is None or d >= t.not_before):
            hit_target, price = _target_hit(t, bar)

        if hit_rule is not None:
            return _invalidate(hit_rule, spec, rstate, events, d, bar, d in week_closes,
                               ambiguous=hit_target, resolve=resolve)

        if hit_target:
            tstate[current] |= {"status": "raggiunta", "hit_on": d.isoformat(),
                                "hit_price": round(price, 2)}
            events.append(Event(
                f"hit:{current}", d, "target_hit",
                f"{t.label} raggiunta il {d:%d/%m/%Y}: "
                f"{'massimo' if t.kind == 'touch_above' else 'minimo'} {fmt(price)} "
                f"({'≥' if t.kind == 'touch_above' else '≤'} {fmt(t.trigger)}).",
                {"price": round(price, 2)}))
            if current == len(spec.targets) - 1:
                events.append(Event("hit", d, "hit",
                                    "Previsione colpita: tutti gli obiettivi raggiunti."))
                return resolve("colpita", d)
            current += 1
            tstate[current]["status"] = "attiva"
            earliest = d + timedelta(days=1)

        # 3. End of day: close-based invalidations
        hit_rule = _first_hit(close_rules, bar, d in week_closes)
        if hit_rule is not None:
            return _invalidate(hit_rule, spec, rstate, events, d, bar, d in week_closes,
                               ambiguous=False, resolve=resolve)

    # No bar decided it: still open unless the current deadline is already over
    t = spec.targets[current]
    if as_of > t.deadline:
        tstate[current]["status"] = "mancata"
        events.append(Event(f"missed:{current}", t.deadline, "target_missed",
                            f"{t.label}: non raggiunta entro il {t.deadline:%d/%m/%Y}."))
        events.append(Event("expired", t.deadline, "expired",
                            "Previsione scaduta: obiettivo non raggiunto in tempo."))
        return resolve("scaduta", t.deadline)
    return Result("aperta", None, tstate, rstate, events, b.index[-1] if len(b) else None,
                  _extremes(b))


def _active(r: Invalidation, d: date, created: date) -> bool:
    return (r.from_date is None or d >= r.from_date) and (r.until is None or d <= r.until) \
        and d > created


def _first_hit(rules, bar, is_week_close: bool):
    for i, r in rules:
        hit, _ = _rule_hit(r, bar, is_week_close)
        if hit:
            return i
    return None


def _invalidate(i, spec, rstate, events, d, bar, is_week_close, ambiguous, resolve):
    r = spec.invalidations[i]
    _, price = _rule_hit(r, bar, is_week_close)
    rstate[i] |= {"triggered_on": d.isoformat(), "price": round(price, 2)}
    note = (" Nello stesso giorno è stato toccato anche l'obiettivo: con barre giornaliere "
            "l'ordine non è noto, per prudenza vale l'invalidazione.") if ambiguous else ""
    events.append(Event("invalidated", d, "invalidated",
                        f"Previsione invalidata il {d:%d/%m/%Y}: {r.description} "
                        f"(prezzo {fmt(price)}).{note}",
                        {"rule": i, "price": round(price, 2), "ambiguous": ambiguous}))
    return resolve("invalidata", d)


def _extremes(b: pd.DataFrame) -> dict:
    if b.empty:
        return {}
    return {
        "high": round(float(b["high"].max()), 2), "high_on": b["high"].idxmax().isoformat(),
        "low": round(float(b["low"].min()), 2), "low_on": b["low"].idxmin().isoformat(),
        "last_close": round(float(b["close"].iloc[-1]), 2),
    }
