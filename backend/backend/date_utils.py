"""YYMM-DD date utilities for PDR dashboard (canonical, C3).

Slightly Parallel's convention: ``2608-06`` means year 2026, month 08, day 06.
Format: ``YYMM-DD`` where YY is the 2-digit year within the 21st century,
MM is the 2-digit month, DD is the 2-digit day.

The primary format is ``YYMM-DD``. Also accepted are ``YYMM-DDTHH:MM:SS`` and
``YYMM-DDTHH:MM:SS±HH:MM`` for ``last_active`` timestamps.

This module is the one place YYMM-DD is read and written. Every other
backend module imports from here; ``tests/test_one_of_each.py`` fails when a
module parses a Slightly Parallel date itself, which is how the rule is kept.

Backward-compat: exports both ``parse_yymm_dd`` (canonical, per architecture
spec) and ``parse_yymmdd`` (placeholder shim from C2 scaffold).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional, Union

__all__ = [
    "parse_yymm_dd",
    "day_of",
    "iso_of",
    "day_before",
    "format_yymm_dd",
    "days_ago",
    "relative_time",
    "parse_iso_local",
    "today_yymm_dd",
    # backward-compat aliases used by earlier scaffolds
    "parse_yymmdd",
    "format_yymmdd",
    "today_yymmdd",
    "InvalidYYMMDD",
]


# Strict: 4 digits, dash, 2 digits. Anchored at start; end-or-time-delim after.
# Does NOT accept ``YY-MM-DD`` (extra dash) — that ambiguous foreign format is
# out of scope. Does NOT accept negative years.
_YYMM_DD_RE = re.compile(r"^(\d{4})-(\d{2})(?:$|[T ])")

# Century base for the two-digit year. Explicit is better than clever.
_CENTURY_BASE = 2000


class InvalidYYMMDD(ValueError):
    """Raised when a YYMM-DD string cannot be parsed (strict mode)."""


# ---------------------------------------------------------------------------
# Core parsers
# ---------------------------------------------------------------------------


def parse_yymm_dd(s: Union[str, None]) -> date:
    """Parse a YYMM-DD string into a ``datetime.date`` (strict).

    Accepts:
      - ``"2608-06"``                       → ``date(2026, 8, 6)``
      - ``"2608-06T14:30:00"``              → ``date(2026, 8, 6)``  (time stripped)
      - ``"2608-06T14:30:00+03:00"``        → ``date(2026, 8, 6)``
      - ``"2608-06 14:30:00"``              → ``date(2026, 8, 6)``

    Raises ``InvalidYYMMDD`` on invalid input (None, wrong shape, bad calendar
    values like month 13 or Feb 30, non-string input).

    Performance: hot path — called per activity row when building the heatmap.
    Compiled regex + one ``date()`` construction. ~1 µs typical.
    """
    if not isinstance(s, str):
        raise InvalidYYMMDD(f"expected string, got {type(s).__name__}: {s!r}")

    m = _YYMM_DD_RE.match(s)
    if not m:
        raise InvalidYYMMDD(f"not YYMM-DD format: {s!r}")

    yymm_str, dd_str = m.group(1), m.group(2)
    yy = int(yymm_str[:2])
    mm = int(yymm_str[2:4])
    dd = int(dd_str)

    try:
        return date(_CENTURY_BASE + yy, mm, dd)
    except ValueError as exc:
        # month 13, Feb 30, etc.
        raise InvalidYYMMDD(f"invalid calendar date in {s!r}: {exc}") from exc


def format_yymm_dd(d: Union[date, datetime, None]) -> str:
    """Format a ``date`` (or ``datetime``) as a YYMM-DD string.

    Returns ``""`` for ``None`` (loose contract for CSV cells that may be empty).

    >>> format_yymm_dd(date(2026, 8, 6))
    '2608-06'
    """
    if d is None:
        return ""
    if isinstance(d, datetime):
        d = d.date()
    if not isinstance(d, date):
        raise TypeError(f"expected date, got {type(d).__name__}")

    yy = d.year - _CENTURY_BASE
    if yy < 0 or yy > 99:
        raise ValueError(
            f"year {d.year} out of range for YYMM-DD "
            f"(must be {_CENTURY_BASE}..{_CENTURY_BASE + 99})"
        )
    return f"{yy:02d}{d.month:02d}-{d.day:02d}"


def today_yymm_dd(*, today: Optional[date] = None) -> str:
    """Return today's date as a YYMM-DD string."""
    return format_yymm_dd(today or date.today())


# ---------------------------------------------------------------------------
# ISO-local timestamps (meta.json ``last_active``)
# ---------------------------------------------------------------------------


def parse_iso_local(s: Union[str, None]) -> datetime:
    """Parse the ``last_active`` field: ``YYMM-DDTHH:MM:SS[±HH:MM]``.

    The YYMM-DD prefix is the Slightly Parallel convention; the time portion is standard ISO.
    Returns a naive ``datetime`` in local time. Any trailing timezone is
    stripped — MVP is single-user-single-machine, no timezone math.
    """
    if not isinstance(s, str):
        raise InvalidYYMMDD(f"expected string, got {type(s).__name__}: {s!r}")

    if "T" in s:
        date_part, time_part = s.split("T", 1)
    elif " " in s:
        date_part, time_part = s.split(" ", 1)
    else:
        d = parse_yymm_dd(s)
        return datetime(d.year, d.month, d.day)

    d = parse_yymm_dd(date_part)

    # Strip trailing timezone (Z, +HH:MM, -HHMM, ...)
    tz_match = re.search(r"([+-]\d{2}:?\d{2}|Z)$", time_part)
    if tz_match:
        time_part = time_part[: tz_match.start()]

    parts = time_part.split(":")
    try:
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        ss_str = parts[2] if len(parts) > 2 else "0"
        if "." in ss_str:
            ss_int_str, us_str = ss_str.split(".", 1)
            ss = int(ss_int_str)
            us = int((us_str + "000000")[:6])
        else:
            ss = int(ss_str)
            us = 0
        return datetime(d.year, d.month, d.day, hh, mm, ss, us)
    except (ValueError, IndexError) as exc:
        raise InvalidYYMMDD(f"invalid time portion in {s!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# Derived helpers
# ---------------------------------------------------------------------------


def days_ago(
    s: Union[str, date, datetime, None],
    *,
    today: Optional[date] = None,
) -> int:
    """Return integer days between ``today`` and the given date.

    Positive = past, negative = future, 0 = today.

    ``s`` may be a YYMM-DD string, an ISO-local timestamp, a ``date``, or a
    ``datetime``. Raises ``InvalidYYMMDD`` on invalid input.
    """
    if today is None:
        today = date.today()

    if isinstance(s, str):
        # accept both bare YYMM-DD and ISO-local timestamps
        try:
            d = parse_yymm_dd(s)
        except InvalidYYMMDD:
            d = parse_iso_local(s).date()
    elif isinstance(s, datetime):
        d = s.date()
    elif isinstance(s, date):
        d = s
    else:
        raise InvalidYYMMDD(f"expected string or date, got {type(s).__name__}")

    return (today - d).days


def relative_time(
    iso: Union[str, datetime, date, None],
    *,
    now: Optional[datetime] = None,
) -> str:
    """Return a human-readable relative-time string.

    Buckets (single-scale, no compound labels — matches the TS mirror):

    ==================  ==================
    delta               output
    ==================  ==================
    <  45 s             ``just now``
    <  90 s             ``1m ago``
    <  60 min           ``Nm ago``
    <  24 h             ``Nh ago``
    <   7 d             ``Nd ago``
    <   5 w             ``Nw ago``
    <  12 mo            ``Nmo ago``
    else                ``Ny ago``
    ==================  ==================

    Future timestamps mirror as ``in Nd`` for symmetry.

    Accepts YYMM-DD, ISO-local timestamp, ``datetime``, or ``date``.
    """
    if now is None:
        now = datetime.now()

    if isinstance(iso, str):
        try:
            dt = parse_iso_local(iso)
        except InvalidYYMMDD:
            d = parse_yymm_dd(iso)
            dt = datetime(d.year, d.month, d.day)
    elif isinstance(iso, datetime):
        dt = iso
    elif isinstance(iso, date):
        dt = datetime(iso.year, iso.month, iso.day)
    else:
        raise InvalidYYMMDD(f"expected string or datetime, got {type(iso).__name__}")

    seconds = int((now - dt).total_seconds())
    future = seconds < 0
    seconds = abs(seconds)

    def fmt(value: int, unit: str) -> str:
        core = f"{value}{unit}"
        return f"in {core}" if future else f"{core} ago"

    if seconds < 45:
        return "in a moment" if future else "just now"
    if seconds < 90:
        return fmt(1, "m")
    minutes = seconds // 60
    if minutes < 60:
        return fmt(minutes, "m")
    hours = minutes // 60
    if hours < 24:
        return fmt(hours, "h")
    days = hours // 24
    if days < 7:
        return fmt(days, "d")
    weeks = days // 7
    if weeks < 5:
        return fmt(weeks, "w")
    months = days // 30
    if months < 12:
        return fmt(months, "mo")
    years = days // 365
    return fmt(years, "y")


# ---------------------------------------------------------------------------
# Backward-compat aliases for pre-C3 call sites (loose contract: None-safe).
# ---------------------------------------------------------------------------


def parse_yymmdd(value: Union[str, None]) -> Optional[date]:
    """Legacy alias — returns ``None`` on invalid input instead of raising.

    Prefer ``parse_yymm_dd`` for new code.
    """
    if not value:
        return None
    try:
        return parse_yymm_dd(value.strip())
    except InvalidYYMMDD:
        # Best-effort ISO fallback (matches the pre-C3 placeholder behavior)
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None


def format_yymmdd(d: Union[date, datetime, None]) -> str:
    """Legacy alias — returns ``""`` on None (matches pre-C3 behavior)."""
    return format_yymm_dd(d)


def today_yymmdd() -> str:
    """Legacy alias."""
    return today_yymm_dd()


def day_of(value: Union[str, date, datetime, None]) -> str:
    """Any day Slightly Parallel knows, as ``YYMM-DD``: a date, a datetime, an ISO day
    (``2026-09-21``), or a YYMM-DD that comes back unchanged. '' when it is
    not a day at all."""
    if value is None or value == "":
        return ""
    if isinstance(value, (date, datetime)):
        return format_yymm_dd(value)
    text = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if m:                                   # an ISO day, with or without a time
        # A day that is not one (Feb 30), or a year YYMM-DD cannot hold
        # (1999 read back as 2099), is not a day.
        try:
            d = date(*(int(g) for g in m.groups()))
        except ValueError:
            return ""
        return format_yymm_dd(d) if 2000 <= d.year <= 2099 else ""
    try:
        return format_yymm_dd(parse_yymm_dd(text))
    except InvalidYYMMDD:
        return ""


def iso_of(yymm_dd: Union[str, None]) -> str:
    """``2609-21`` → ``2026-09-21``. '' when it is not a Slightly Parallel day."""
    try:
        return parse_yymm_dd(yymm_dd).strftime("%Y-%m-%d")
    except InvalidYYMMDD:
        return ""


def day_before(yymm_dd: Union[str, None]) -> str:
    """The day before this one, as ``YYMM-DD``. '' when it is not a day."""
    try:
        return format_yymm_dd(parse_yymm_dd(yymm_dd) - timedelta(days=1))
    except InvalidYYMMDD:
        return ""


def as_local(value: Union[str, datetime, None]) -> Optional[datetime]:
    """A moment as naive local time, the way every ledger and chat writes it.
    A naive value is taken as local already; one with a zone (an event
    stamped ``…+02:00`` or ``…Z``) is converted to local first, not cut —
    cutting the zone off would move it by the offset. None when unreadable."""
    if isinstance(value, datetime):
        d = value
    else:
        try:
            d = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d.astimezone().replace(tzinfo=None) if d.tzinfo is not None else d


def now_iso() -> str:
    """This moment, local, to the second: ``2026-09-27T14:02:05`` — how every
    ledger stamps what it writes."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
