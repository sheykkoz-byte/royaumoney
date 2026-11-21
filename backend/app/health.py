"""Freshness of every series, for /health/data."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import catalog
from app.db import Observation, Series

YELLOW_FACTOR = 1.5


def status_for(age_days: int | None, max_age: int) -> str:
    if age_days is None:
        return "red"
    if age_days <= max_age:
        return "green"
    if age_days <= max_age * YELLOW_FACTOR:
        return "yellow"
    return "red"


def data_health(session: Session, today: date | None = None) -> dict:
    today = today or date.today()
    stats = {
        sid: (last_ref, n, last_pub)
        for sid, last_ref, n, last_pub in session.execute(
            select(
                Observation.series_id,
                func.max(Observation.ref_date),
                func.count(func.distinct(Observation.ref_date)),
                func.max(Observation.published_at),
            ).group_by(Observation.series_id)
        )
    }
    rows = {r.id: r for r in session.scalars(select(Series))}
    items = []
    for sdef in catalog.SERIES:
        last_ref, n, last_pub = stats.get(sdef.id, (None, 0, None))
        age = (today - last_ref).days if last_ref else None
        row = rows.get(sdef.id)
        error = None
        if row is not None:
            error = row.verify_error or row.last_fetch_error
        status = status_for(age, sdef.max_age_days)
        if error and status == "green":
            status = "yellow"  # data is recent but the last run had a problem
        items.append({
            "id": sdef.id,
            "name": sdef.name,
            "category": sdef.category,
            "source": sdef.source,
            "unit": sdef.unit,
            "frequency": sdef.frequency,
            "last_ref_date": last_ref.isoformat() if last_ref else None,
            "last_published_at": last_pub.isoformat() if last_pub else None,
            "age_days": age,
            "max_age_days": sdef.max_age_days,
            "observations": n,
            "status": status,
            "last_fetch_at": row.last_fetch_at.isoformat(timespec="seconds")
            if row and row.last_fetch_at else None,
            "error": error,
        })
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("green", "yellow", "red")}
    overall = "red" if counts["red"] else "yellow" if counts["yellow"] else "green"
    return {"status": overall, "today": today.isoformat(), "counts": counts, "series": items}
