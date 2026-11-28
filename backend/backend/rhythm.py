"""A chat's rhythm for the terminal window's tabs (tk_d2e11125, «f1 · ритм»).

Six dots on each tab are the chat's last six clock hours, oldest first; the
current hour, still running, is the last. For each hour this counts what
Slightly Parallel already keeps for the chat, read cheaply:

* ``msgs`` — messages: the operator's (a turn's start) and the agent's
  answers (a turn's end), from ``turns.jsonl`` (the capture hook's stamp);
  an answer only ``work.jsonl`` timed counts its end;
* ``commits`` — commits in the chat's repository tied to the chat: signed
  ``Agent: <this chat>``, or unsigned and naming one of the chat's tasks in
  ``Task:``, or listed in the chat's own per-turn stamps (``work.jsonl``)
  and signed by no other agent; by author time;
* ``tasks`` — the chat's tasks (named in its turns) moved to done in the
  hour (``task_events``: a status change to done);
* ``tokens`` — the main agent's new input + output of the turns whose last
  message fell in the hour (``usage.jsonl``, the Usage page's sums).

What the dots draw from these (the weights) is the page's business. Files
are read once per change: every answer is kept per file version, the
commits per HEAD (gitwork's log cache), so a poll every 5 s costs a stat
per file.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from . import gitwork, turntimes, usagelib
from .entities import DONE_STATUSES
from .hookshared import ping_turn_numbers
from .viewrows import rows_or_empty

#: How many periods, and how long each is.
PERIODS = 6
PERIOD = timedelta(hours=1)

_lock = threading.Lock()
# folder → (file versions, [(kind, moment)]) — kind "msg" or "tok:<n>".
_points: dict[str, tuple[tuple, list[tuple[str, datetime, int]]]] = {}


def _moment(v: Any) -> datetime | None:
    return usagelib._moment(v)


def periods(now: datetime) -> list[datetime]:
    """The starts of the six periods, oldest first: clock hours, the last
    the hour ``now`` is in."""
    top = now.replace(minute=0, second=0, microsecond=0)
    return [top - PERIOD * (PERIODS - 1 - i) for i in range(PERIODS)]


def slot(starts: list[datetime], at: datetime | None) -> int | None:
    """The period ``at`` falls in, or None (before the first, or after the last's end)."""
    if at is None or at < starts[0] or at >= starts[-1] + PERIOD:
        return None
    return min(int((at - starts[0]) / PERIOD), PERIODS - 1)


def _version(folder: Path) -> tuple:
    out = []
    for name in ("chat.md", turntimes.FILE, "work.jsonl", usagelib.USAGE_FILE):
        try:
            st = (folder / name).stat()
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


def _folder_points(folder: Path) -> list[tuple[str, datetime, int]]:
    """Every message moment and every turn's tokens of a chat folder, kept per file version."""
    key = str(folder)
    ver = _version(folder)
    with _lock:
        hit = _points.get(key)
    if hit is not None and hit[0] == ver:
        return hit[1]
    pts: list[tuple[str, datetime, int]] = []
    hooked: set[int] = set()
    pings = ping_turn_numbers(folder / "chat.md")
    for rec in turntimes._lines(folder / turntimes.FILE):
        n = rec.get("turn")
        if not isinstance(n, int) or n in hooked:
            continue          # a second stamp of a turn (a helper's report): one answer
        hooked.add(n)
        if rec.get("ping"):
            pings.add(n)
        if n in pings:
            continue
        for k in ("start", "end"):
            at = _moment(rec.get(k))
            if at is not None:
                pts.append(("msg", at, 1))
    for rec in turntimes._lines(folder / "work.jsonl"):
        n = rec.get("turn")
        if isinstance(n, int) and n not in hooked and n not in pings:
            hooked.add(n)
            at = _moment(rec.get("at"))
            if at is not None:
                pts.append(("msg", at, 1))
    cu = usagelib.chat_usage(folder / usagelib.USAGE_FILE)
    for n, t in (cu.get("turns") or {}).items():
        if n in pings:
            continue
        at = _moment(t.get("at"))
        main = t.get("main") or {}
        tok = int(main.get("new") or 0) + int(main.get("output") or 0)
        if at is not None and tok > 0:
            pts.append(("tok", at, tok))
    with _lock:
        _points[key] = (ver, pts)
        if len(_points) > 2000:
            _points.pop(next(iter(_points)))
    return pts


def _commits(chat_path: Path, aid: str, tasks: set[str], since: datetime) -> list[datetime]:
    """When each commit tied to the chat was made, since ``since``."""
    repo = gitwork.repo_for_chat(chat_path)
    if repo is None:
        return []
    stamped: set[str] = set()
    for st in gitwork.read_stamps(chat_path).values():
        for sha in st.get("commits") or []:
            if isinstance(sha, str) and sha:
                stamped.add(sha)
    out: list[datetime] = []
    for c in gitwork.commits(repo):   # newest first
        if c.at < since:
            break
        if c.agent:
            mine = c.agent == aid
        else:
            mine = bool(tasks & set(c.tasks)) or any(c.sha.startswith(s) or s.startswith(c.sha) for s in stamped)
        if mine:
            out.append(c.at)
    return out


def closed_at(store: Any, task_ids: Iterable[str], since: datetime) -> dict[str, list[datetime]]:
    """task → the moments it was moved to done since ``since``. One query for every chat."""
    ids = sorted({t for t in task_ids if t})
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    done = ",".join("?" * len(DONE_STATUSES))
    out: dict[str, list[datetime]] = {}
    for r in rows_or_empty(
        store,
        "SELECT task_id, timestamp FROM task_events_mutual WHERE field = 'status' "
        f"AND lower(trim(new_value)) IN ({done}) AND timestamp >= ? AND task_id IN ({ph})",
        (*DONE_STATUSES, since.strftime("%Y-%m-%dT%H:%M:%S"), *ids),
    ):
        at = _moment(r.get("timestamp"))
        if at is not None:
            out.setdefault(str(r["task_id"]), []).append(at)
    return out


def rhythm(agent: dict[str, Any], tasks: set[str], closed: dict[str, list[datetime]], now: datetime) -> dict[str, Any]:
    """``{period_min, periods: [{start, end, msgs, commits, tasks, tokens}] × 6}``, oldest first."""
    starts = periods(now)
    rows = [{"start": usagelib._iso(s), "end": usagelib._iso(s + PERIOD), "msgs": 0, "commits": 0, "tasks": 0, "tokens": 0}
            for s in starts]
    folder = usagelib.chat_folder(agent)
    if folder is not None:
        for kind, at, n in _folder_points(folder):
            i = slot(starts, at)
            if i is None:
                continue
            if kind == "msg":
                rows[i]["msgs"] += n
            else:
                rows[i]["tokens"] += n
        for at in _commits(folder / "chat.md", str(agent.get("agent_id") or ""), tasks, starts[0]):
            i = slot(starts, at)
            if i is not None:
                rows[i]["commits"] += 1
    for tid in tasks:
        # A task moved to done twice in the window (reopened, closed again) counts once, at its last close.
        moments = [at for at in closed.get(tid, []) if slot(starts, at) is not None]
        if moments:
            rows[slot(starts, max(moments))]["tasks"] += 1  # type: ignore[index]
    return {"period_min": int(PERIOD.total_seconds() // 60), "periods": rows}


def forget() -> None:
    """Drop the cache — for tests."""
    with _lock:
        _points.clear()
