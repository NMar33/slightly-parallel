"""A time entry's clock: read one, write a change to it under the ledger's
lock, bank a pause and run again, delete it — and the state a page shows
(running, paused, done; worked and attributed seconds).

The time routes (routers/time_tracking.py) and the smart timer (timeauto)
both change entries through here, so the timer imports no router."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import HTTPException

from .answers import not_found
from .db import ViewStore
from .entities import ENTITIES
from .rowedit import rewrite_one

ENT = ENTITIES["time_entry"]

# A timer left running this long is almost certainly forgotten, not worked.
RUNAWAY_HOURS = 8


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):   # "inf" is a float too
        return 0


def elapsed_seconds(row: dict, now: datetime | None = None) -> int:
    """Worked seconds so far: wall time minus everything spent paused."""
    started = _parse(str(row.get("started_at") or ""))
    if started is None:
        return 0
    ended = _parse(str(row.get("ended_at") or ""))
    paused_at = _parse(str(row.get("paused_at") or ""))
    edge = ended or paused_at or (now or _now())
    gross = int((edge - started).total_seconds())
    return max(0, gross - _int(row.get("paused_total_sec")))


def decorate(row: dict, now: datetime | None = None) -> dict:
    """Add derived state the UI needs but the CSV must not duplicate."""
    ended = str(row.get("ended_at") or "")
    paused = str(row.get("paused_at") or "")
    status = "done" if ended else ("paused" if paused else "running")
    secs = (
        _int(row.get("duration_min")) * 60
        if status == "done"
        else elapsed_seconds(row, now)
    )
    share = _int(row.get("share_pct")) or 100
    return {
        **row,
        "status": status,
        "elapsed_sec": secs,
        "attributed_sec": round(secs * share / 100),
        "runaway": status != "done" and secs > RUNAWAY_HOURS * 3600,
    }


def _load(store: ViewStore, entry_id: str) -> dict:
    row = store.query_one(
        f"SELECT * FROM {ENT.view} WHERE id = ?", (entry_id,)
    )
    if row is None:
        raise not_found("time entry", entry_id)
    return row


def _patch(store: ViewStore, entry_id: str,
           updates: "dict[str, Any] | Callable[[dict[str, str]], dict[str, Any]]") -> dict:
    """Write columns straight to the CSV row, then rebuild the views.

    ``updates`` is the columns, or a function of the row as it stands under
    the lock that returns them. A clock change is worked out that way: the
    smart timer pauses entries from its own thread, and a stop computed
    from a row read before that pause counted the away stretch as work.
    """
    def change(rows: list[dict[str, str]], r: dict[str, str]) -> bool:
        patch = updates(r) if callable(updates) else updates
        if not patch:
            return False
        r.update(patch)
        return True

    rewrite_one(store, ENT.csv, ENT.columns, entry_id, change, "time entry")
    return decorate(_load(store, entry_id))


def time_resume_row(store: ViewStore, row: dict, now: datetime, *, refuse_stopped: bool = False) -> dict:
    """Bank the paused stretch of the entry up to `now` and run again."""

    def resume(r: dict) -> dict:
        if refuse_stopped and str(r.get("ended_at") or ""):
            raise HTTPException(status_code=409, detail="entry is already stopped")
        paused_at = _parse(str(r.get("paused_at") or ""))
        if paused_at is None:
            return {}  # not paused — idempotent
        banked = _int(r.get("paused_total_sec")) + max(
            0, int((now - paused_at).total_seconds())
        )
        return {"paused_at": "", "paused_total_sec": str(banked)}

    return _patch(store, str(row["id"]), resume)


def _delete(store: ViewStore, entry_id: str) -> None:
    def drop(rows: list[dict[str, str]], _row: dict[str, str]) -> bool:
        rows[:] = [r for r in rows if r.get("id") != entry_id]
        return True

    rewrite_one(store, ENT.csv, ENT.columns, entry_id, drop, "time entry")
