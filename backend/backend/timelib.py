"""A time entry's clock: read one, write a change to it under the ledger's
lock, bank a pause and run again, delete it — and the state a page shows
(running, paused, done; worked and attributed seconds).

The time routes (routers/time_tracking.py) and the smart timer (timeauto)
both change entries through here, so the timer imports no router."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from . import clocktime
from .answers import not_found
from .db import ViewStore
from .entities import ENTITIES
from .rowedit import rewrite_one

ENT = ENTITIES["time_entry"]

# A timer left running this long is almost certainly forgotten, not worked.
RUNAWAY_HOURS = 8


def _now() -> datetime:
    """Now, with its UTC offset (clocktime.py): lengths are real time."""
    return clocktime.now()


def _parse(ts: str) -> datetime | None:
    """A stored moment with its offset; an old naive one reads as local."""
    return clocktime.parse(ts)


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
    edge = ended or paused_at or clocktime.aware(now or _now())
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


# ---------------------------------------------------------------------------
# The UTC offset on stored times (tk_3a363c87)
# ---------------------------------------------------------------------------

#: The columns of a time entry that hold a moment.
MOMENTS = ("started_at", "ended_at", "paused_at")


def stamp_offsets(row: dict[str, Any]) -> dict[str, Any]:
    """The moments of a row, naive ones given their local offset; the
    changed columns only. An end or a pause that would fall before the start
    in the hour the clocks go back takes the second of the two times."""
    out: dict[str, Any] = {}
    start_raw = row.get("started_at")
    start = clocktime.with_offset(start_raw) if start_raw not in (None, "") else ""
    if start != str(start_raw or ""):
        out["started_at"] = start
    floor = clocktime.parse(start)
    for col in ("ended_at", "paused_at"):
        raw = row.get(col)
        if raw in (None, ""):
            continue
        got = clocktime.with_offset(raw, floor)
        if got != str(raw):
            out[col] = got
    return out


def migrate_offsets(data_root: Path, *, backup: bool = True) -> dict[str, Any]:
    """Give every stored time entry's moments their UTC offset, once.

    Rows written before the offset hold naive local times; each such moment
    is rewritten as the same local time with the offset it had (stamp_offsets).
    Rows that have their offsets are left as they are, so a second run
    changes nothing. Before the first write the file is copied whole to
    ``time-offsets-migration-<stamp>/`` in the backup folder (beside the data
    root, never inside it). The rewrite runs under the ledger's lock, and
    after it the rows are read back: the same ids in the same order, or the
    copy is put back and the run fails. Old files work without it: a naive
    moment reads as local time everywhere."""
    from .backup import backup_root_for
    from .csvio import read_rows, rewrite_rows
    from .file_safety import atomic_write

    root = Path(data_root)
    path = root / ENT.csv
    if not path.exists():
        return {"rows": 0, "changed": 0, "backup": ""}
    if not any(clocktime.is_naive(r.get(c)) for r in read_rows(path) for c in MOMENTS):
        return {"rows": 0, "changed": 0, "backup": ""}
    kept: dict[str, Any] = {"ids": [], "changed": 0, "backup": ""}

    def mutate(rows: list[dict[str, str]]) -> bool:
        kept["ids"] = [r.get("id") for r in rows]
        plan = [(r, stamp_offsets(r)) for r in rows]
        if not any(p for _, p in plan):
            return False
        if backup:
            dest = backup_root_for(root) / f"time-offsets-migration-{time.strftime('%Y%m%d-%H%M%S')}"
            dest.mkdir(parents=True, exist_ok=True)
            atomic_write(dest / ENT.csv, path.read_bytes())
            kept["backup"] = str(dest / ENT.csv)
        for r, p in plan:
            if p:
                r.update(p)
                kept["changed"] += 1
        return True

    rewrite_rows(path, ENT.columns, mutate)
    after = [r.get("id") for r in read_rows(path)]
    if kept["changed"] and after != kept["ids"]:
        if kept["backup"]:
            atomic_write(path, Path(kept["backup"]).read_bytes())
        raise RuntimeError(f"{ENT.csv}: the rows read back are not the rows written "
                           f"({len(after)} for {len(kept['ids'])}); the copy is put back")
    return {"rows": len(after), "changed": kept["changed"], "backup": kept["backup"]}
