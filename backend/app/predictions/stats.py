"""Track record: hit rates and calibration (Brier score)."""

import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Prediction

RESOLVED = ("colpita", "invalidata", "scaduta")
CALIBRATION_BINS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001)]


def horizon_bucket(days: int) -> str:
    if days <= 7:
        return "fino a 1 settimana"
    if days <= 31:
        return "fino a 1 mese"
    if days <= 92:
        return "fino a 3 mesi"
    return "oltre 3 mesi"


def brier(pairs: list[tuple[float, int]]) -> float | None:
    """Mean squared error between probability and outcome (0 best, 0.25 = always 50%)."""
    if not pairs:
        return None
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def _group(rows: list[dict]) -> dict:
    resolved = [r for r in rows if r["status"] in RESOLVED]
    hits = sum(1 for r in resolved if r["status"] == "colpita")
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r["status"] == "aperta"),
        "resolved": len(resolved),
        "hit": hits,
        "invalidated": sum(1 for r in resolved if r["status"] == "invalidata"),
        "expired": sum(1 for r in resolved if r["status"] == "scaduta"),
        "hit_rate": round(hits / len(resolved), 3) if resolved else None,
    }


def summarize(rows: list[dict]) -> dict:
    """``rows``: dicts with status, probability, asset, author, horizon_days, tags,
    targets_hit, targets_total."""
    out = {"overall": _group(rows)}
    for key in ("asset", "author", "horizon"):
        groups = defaultdict(list)
        for r in rows:
            groups[r[key]].append(r)
        out[f"by_{key}"] = {k: _group(v) for k, v in sorted(groups.items())}
    tags = defaultdict(list)
    for r in rows:
        for t in r["tags"]:
            tags[t].append(r)
    out["by_event"] = {k: _group(v) for k, v in sorted(tags.items())}

    resolved = [r for r in rows if r["status"] in RESOLVED]
    pairs = [(r["probability"], int(r["status"] == "colpita"))
             for r in resolved if r["probability"] is not None]
    b = brier(pairs)
    out["brier"] = {
        "score": None if b is None else round(b, 4),
        "n": len(pairs),
        "reference_50_50": 0.25,
        "note": "0 = perfetto; 0,25 = come dire sempre 50%. Contano solo le previsioni "
                "chiuse con una probabilità dichiarata.",
    }
    out["calibration"] = []
    for lo, hi in CALIBRATION_BINS:
        sel = [(p, o) for p, o in pairs if lo <= p < hi]
        if sel:
            out["calibration"].append({
                "range": f"{lo:.0%}–{min(hi, 1):.0%}", "n": len(sel),
                "avg_probability": round(sum(p for p, _ in sel) / len(sel), 3),
                "hit_frequency": round(sum(o for _, o in sel) / len(sel), 3),
            })
    th = sum(r["targets_hit"] for r in rows)
    tt = sum(r["targets_decided"] for r in rows)
    out["targets"] = {"hit": th, "decided": tt,
                      "hit_rate": round(th / tt, 3) if tt else None}
    return out


def track_record(session: Session) -> dict:
    rows = []
    for p in session.scalars(select(Prediction)):
        state = json.loads(p.state or "{}")
        spec = json.loads(p.spec)
        targets = state.get("targets", [])
        rows.append({
            "status": p.status, "probability": p.probability, "asset": p.asset,
            "author": p.author,
            "horizon": horizon_bucket((p.horizon_end - p.created_at.date()).days),
            "tags": spec.get("tags", []),
            "targets_hit": sum(1 for t in targets if t["status"] == "raggiunta"),
            "targets_decided": sum(1 for t in targets if t["status"] in ("raggiunta",
                                                                          "mancata")),
        })
    return summarize(rows)
