"""What a prediction says (plan, section 5). Validated on creation, then frozen."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TargetKind = Literal["touch_above", "touch_below"]
RuleKind = Literal[
    "close_above", "close_below",
    "weekly_close_above", "weekly_close_below",
    "touch_above", "touch_below",
]


class Target(BaseModel):
    """A price zone to reach, in order. ``touch_above``: the high reaches ``zone_low``;
    ``touch_below``: the low reaches ``zone_high``."""

    label: str
    kind: TargetKind
    zone_low: float
    zone_high: float
    not_before: date | None = Field(
        None, description="Counts only from this date (and always after the previous target)")
    deadline: date

    @model_validator(mode="after")
    def _check(self):
        if self.zone_low > self.zone_high:
            raise ValueError("zone_low must be ≤ zone_high")
        if self.not_before and self.not_before > self.deadline:
            raise ValueError("not_before is after the deadline")
        return self

    @property
    def trigger(self) -> float:
        """The price that must be touched."""
        return self.zone_low if self.kind == "touch_above" else self.zone_high


class Invalidation(BaseModel):
    kind: RuleKind
    level: float
    from_date: date | None = None
    until: date | None = None
    description: str


class PredictionSpec(BaseModel):
    author: Literal["jarvis", "yousef"]
    asset: str = Field(description="e.g. XAUUSD, SPY, XLE")
    title: str
    direction: Literal["long", "short", "path"]
    entry_price: float
    probability: float | None = Field(None, ge=0, le=1)
    scenario: str | None = None
    reasoning: str
    tags: list[str] = []
    targets: list[Target] = Field(min_length=1)
    invalidations: list[Invalidation] = []
    align_to_entry: bool = Field(
        False,
        description=("Shift the verification instrument so that its last close before "
                     "creation equals entry_price. Use when the levels come from a quote "
                     "with a known, stable gap to our instrument (e.g. broker spot vs "
                     "futures-derived spot)."),
    )

    @model_validator(mode="after")
    def _check(self):
        for prev, nxt in zip(self.targets, self.targets[1:], strict=False):
            if nxt.deadline < prev.deadline and nxt.not_before is None:
                raise ValueError(f"target {nxt.label!r} ends before the previous one")
        return self

    @property
    def horizon_end(self) -> date:
        return max(t.deadline for t in self.targets)
