"""Database schema and session handling.

SQLite for the prototype; the schema is plain SQLAlchemy so it moves to
Postgres/TimescaleDB by changing DATABASE_URL (observations becomes a hypertable then).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class Series(Base):
    """One row per catalog entry, plus what the source told us at verification time."""

    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[str | None] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(60))
    frequency: Mapped[str] = mapped_column(String(10))

    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verified_title: Mapped[str | None] = mapped_column(Text)
    verified_unit: Mapped[str | None] = mapped_column(String(120))
    verified_frequency: Mapped[str | None] = mapped_column(String(60))
    verify_error: Mapped[str | None] = mapped_column(Text)

    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_fetch_error: Mapped[str | None] = mapped_column(Text)


class Observation(Base):
    """A value of a series for a reference date, as known from ``published_at``.

    A revision never overwrites: it adds a row with a later ``published_at``.
    ``pub_method`` says how reliable ``published_at`` is:
      - ``alfred``        exact vintage date from ALFRED (FRED real-time API)
      - ``first_seen``    the day our job first saw this value (upper bound, ±1 day)
      - ``estimated_lag`` history loaded in bulk: ref_date + typical release lag
      - ``market_close``  market prices, known at the close of ref_date
      - ``derived``       latest publication date among the inputs
    """

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("series_id", "ref_date", "published_at", name="uq_obs_version"),
        Index("ix_obs_series_ref", "series_id", "ref_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"))
    ref_date: Mapped[date] = mapped_column(Date)
    published_at: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    raw_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(20))
    pub_method: Mapped[str] = mapped_column(String(20))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, future=True)
        _SessionLocal = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def init_db(engine: Engine | None = None) -> None:
    Base.metadata.create_all(engine or get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
