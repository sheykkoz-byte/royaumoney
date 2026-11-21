from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class RawPoint:
    """A value as returned by a source, before scaling.

    ``published_at`` is set only when the source tells us (ALFRED vintages, market closes).
    """

    ref_date: date
    value: float
    published_at: date | None = None


@dataclass(frozen=True)
class SourceMeta:
    title: str
    unit: str
    frequency: str
    last_updated: str | None = None
