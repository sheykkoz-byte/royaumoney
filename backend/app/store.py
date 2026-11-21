"""Reading and writing observations with revision history (point-in-time safe)."""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalog
from app.catalog import SeriesDef
from app.db import Observation, Series
from app.sources import RawPoint


def sync_catalog(session: Session) -> None:
    """Make sure every catalog entry has a row in ``series`` (and keep labels current)."""
    existing = {s.id: s for s in session.scalars(select(Series))}
    for d in catalog.SERIES:
        row = existing.get(d.id) or Series(id=d.id)
        row.name, row.category, row.source = d.name, d.category, d.source
        row.source_id, row.unit, row.frequency = d.source_id, d.unit, d.frequency
        session.add(row)
    session.flush()


@dataclass
class SaveReport:
    inserted: int = 0  # first value for a ref_date
    revised: int = 0  # new version of an existing ref_date
    updated: int = 0  # same (ref_date, published_at) seen again with a new value
    unchanged: int = 0


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def save_points(
    session: Session,
    sdef: SeriesDef,
    points: list[RawPoint],
    pub_method: str,
    today: date | None = None,
    scale: float | None = None,
) -> SaveReport:
    """Store points, adding a version only when a value really changes.

    Points without ``published_at`` get one assigned here:
      - ref_dates newer than anything stored: ``today`` (first_seen);
      - otherwise (bulk history, or revisions of an old date): history gets
        ref_date + release lag (estimated_lag), revisions get ``today`` (first_seen).
    """
    today = today or date.today()
    scale = sdef.scale if scale is None else scale
    now = datetime.now(UTC).replace(tzinfo=None)

    rows = session.scalars(
        select(Observation).where(Observation.series_id == sdef.id)
    ).all()
    versions: dict[date, list[Observation]] = {}
    for r in rows:
        versions.setdefault(r.ref_date, []).append(r)
    for vs in versions.values():
        vs.sort(key=lambda r: r.published_at)
    latest_ref = max(versions) if versions else None

    rep = SaveReport()
    for p in sorted(points, key=lambda p: (p.ref_date, p.published_at or date.min)):
        value = p.value * scale
        vs = versions.setdefault(p.ref_date, [])

        method = pub_method
        pub = p.published_at
        if pub is None:
            if vs:
                if _same(vs[-1].value, value):
                    rep.unchanged += 1
                    continue
                pub, method = today, "first_seen"
            elif latest_ref is not None and p.ref_date > latest_ref:
                pub, method = today, "first_seen"
            else:
                pub = min(today, p.ref_date + timedelta(days=sdef.release_lag_days))
                method = "estimated_lag"

        pubs = [v.published_at for v in vs]
        i = bisect_right(pubs, pub)
        if i and vs[i - 1].published_at == pub:
            row = vs[i - 1]
            if _same(row.value, value):
                rep.unchanged += 1
            else:
                row.value, row.raw_value, row.fetched_at = value, p.value, now
                rep.updated += 1
            continue
        if i and _same(vs[i - 1].value, value):
            rep.unchanged += 1  # same as the version already in force at that date
            continue
        row = Observation(
            series_id=sdef.id, ref_date=p.ref_date, published_at=pub, value=value,
            raw_value=p.value, unit=sdef.unit, source=sdef.source, pub_method=method,
            fetched_at=now,
        )
        session.add(row)
        vs.insert(i, row)
        if len(vs) == 1:
            rep.inserted += 1
        else:
            rep.revised += 1
    session.flush()
    return rep


def load_frame(
    session: Session,
    series_id: str,
    as_of: date | None = None,
    start: date | None = None,
) -> pd.DataFrame:
    """Values known on ``as_of`` (default: latest), one row per ref_date.

    Columns: value, published_at. Index: ref_date (Timestamp), sorted.
    """
    q = select(Observation.ref_date, Observation.published_at, Observation.value).where(
        Observation.series_id == series_id
    )
    if as_of is not None:
        q = q.where(Observation.published_at <= as_of)
    if start is not None:
        q = q.where(Observation.ref_date >= start)
    df = pd.DataFrame(session.execute(q).all(), columns=["ref_date", "published_at", "value"])
    if df.empty:
        return pd.DataFrame(
            {"value": pd.Series(dtype=float), "published_at": pd.Series(dtype="datetime64[ns]")},
            index=pd.DatetimeIndex([], name="ref_date"),
        )
    df["ref_date"] = pd.to_datetime(df["ref_date"])
    df["published_at"] = pd.to_datetime(df["published_at"])
    df = df.sort_values(["ref_date", "published_at"]).groupby("ref_date").last()
    return df[["value", "published_at"]]
