"""The moments the timer keeps, with their offset from UTC.

A time entry (started_at, ended_at, paused_at) and the smart timer's own
state (an auto span's last signal, an away notice's from and to) are
written as ISO moments *with* their UTC offset: ``2026-11-01T01:30:00-07:00``.
In the hour the clocks go back a local time comes twice; without the offset
a later moment read earlier, an away notice came out negative and an auto
span closed with a negative length and was dropped (tk_3a363c87). Lengths
are worked out from moments that carry their offset, so they are lengths of
real time whatever the clock on the wall did.

Rows written before the offset (and times typed by hand) are naive local
times: they read as the local time they say, the first of the two in the
hour that comes twice. ``migrate_offsets`` (timelib) gives the stored ones
their offset once.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now() -> datetime:
    """This moment, local, with its offset, to the second."""
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0)


def at(ts: float) -> datetime:
    """A Unix time as a local moment with its offset, to the second."""
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().replace(microsecond=0)


def aware(dt: datetime) -> datetime:
    """A moment with its offset: a naive one is the local time it says."""
    return dt if dt.tzinfo is not None else dt.astimezone()


def parse(value: Any) -> datetime | None:
    """A stored moment (with an offset or naive local), or None."""
    try:
        dt = datetime.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return None
    return aware(dt)


def iso(dt: datetime) -> str:
    """The stored form: local time with the offset it had then, to the second."""
    return aware(dt).astimezone().replace(microsecond=0).isoformat()


def is_naive(value: Any) -> bool:
    """A stored moment written without an offset (before tk_3a363c87)."""
    try:
        return datetime.fromisoformat(str(value or "")).tzinfo is None
    except (TypeError, ValueError):
        return False


def with_offset(value: Any, not_before: datetime | None = None) -> str:
    """A stored moment with its offset; anything else as it was.

    A naive time in the hour that comes twice reads as the first of the
    two, unless that falls before ``not_before`` (an end before its start)
    and the second does not."""
    s = str(value or "")
    try:
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return s
    if dt.tzinfo is not None:
        return s
    first = dt.replace(fold=0).astimezone()
    if not_before is not None and first < not_before:
        second = dt.replace(fold=1).astimezone()
        if second >= not_before:
            return second.isoformat()
    return first.isoformat()
