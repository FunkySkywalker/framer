"""Pure data models — no GTK/GObject imports (core layer law)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .framing import (
    ASPECT_MAX,
    ASPECT_MIN,
    FRAME_PERCENT_MAX,
    FRAME_PERCENT_MIN,
    SHORT_EDGE_MAX,
    SHORT_EDGE_MIN,
)


class ItemState(str, Enum):
    """Lifecycle state of a single queue item."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class QueueItem:
    """One image queued for framing.

    Written by the worker thread only; the UI reads state via dispatcher
    events, never while the worker is mid-mutation of the same field.
    """

    path: Path
    uri: str
    width: int | None = None
    height: int | None = None
    format: str | None = None
    size_bytes: int | None = None
    state: ItemState = ItemState.QUEUED
    fraction: float = 0.0
    output_path: Path | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = lo
    return max(lo, min(hi, v))


def _clamp_float(value: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = lo
    return max(lo, min(hi, v))


@dataclass(frozen=True)
class OutputSpec:
    """Immutable snapshot of the user's output/frame settings for one batch.

    The UI controls are insensitive while a batch runs, so the snapshot
    taken at job start is stable for its whole lifetime. Inputs are
    clamped to the valid ranges here (and again in ``core.framing``).
    """

    aspect_num: int
    aspect_den: int
    portrait: bool
    short_edge: int
    frame_percent: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "aspect_num", _clamp_int(self.aspect_num, ASPECT_MIN, ASPECT_MAX))
        object.__setattr__(self, "aspect_den", _clamp_int(self.aspect_den, ASPECT_MIN, ASPECT_MAX))
        object.__setattr__(self, "short_edge", _clamp_int(self.short_edge, SHORT_EDGE_MIN, SHORT_EDGE_MAX))
        object.__setattr__(self, "frame_percent", _clamp_float(self.frame_percent, FRAME_PERCENT_MIN, FRAME_PERCENT_MAX))


@dataclass
class JobSummary:
    """Counts for one finished batch."""

    total: int
    done: int
    failed: int
    cancelled: int
