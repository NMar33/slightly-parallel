"""When each turn of a chat ended — the agent's working time.

``chat.md`` stamps when a turn *starts* (the prompt). When the agent's
answer *ended* is kept beside it, from three sources, best first:

- ``turns.jsonl`` — the capture hook writes ``{turn, start, end}`` at every
  answer (source ``hook``), and the backfill below writes the same for
  older chats (source ``transcript``);
- ``work.jsonl`` — the git stamp, written at every answer in a repository
  (its ``at`` is the answer's end), for chats older than the hook's line.

A turn's *working* time is not its span: ``active_sec`` sums the
stretches between the turn's messages and tool results, leaving out any
silence over ``ACTIVE_GAP_SEC`` — a laptop asleep, or the agent waiting on
a helper, is not working. The hook writes it; the backfill computes it.
A turn with no end anywhere is unknown; sessions.py counts it as an
estimate and says so.

**Backfill.** Claude Code keeps its own transcript of every session, one
JSON record per message with a timestamp. For every turn the hook did not
time, the answer's end is the last assistant record after the turn's prompt
and before whatever came next — the next captured turn, or a prompt in the
transcript the capture skipped (a task notification): work the agent does
for a notification is not the turn's (background helpers are agents of
their own). The backfill's own lines are recomputed each run; the hook's
are never touched.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

log = logging.getLogger("sp.turntimes")

FILE = "turns.jsonl"
#: The one number: the capture hook loads this file by path and reads it here.
ACTIVE_GAP_SEC = 20 * 60


def _parse(ts: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


def _lines(path: Path) -> Iterator[dict[str, Any]]:
    """Each JSON object of a JSON-lines file, read one line at a time. A
    Claude Code transcript runs to hundreds of MB: read whole and parsed into
    one list it took the server from 200 MB to 2.5 GB at every start, and
    glibc kept most of it after (docs/performance.md)."""
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


class Timed:
    """What is known of one turn's answer."""
    __slots__ = ("end", "active_sec", "busy", "helper_sec")

    def __init__(self, end: datetime, active_sec: int | None = None,
                 busy: list[tuple[datetime, datetime]] | None = None, helper_sec: int = 0):
        self.end, self.active_sec, self.busy, self.helper_sec = end, active_sec, busy, helper_sec


def times(chat_dir: Path) -> dict[int, Timed]:
    """turn → what is known of its answer, from the best source there is."""
    out: dict[int, Timed] = {}
    for rec in _lines(chat_dir / "work.jsonl"):
        at = _parse(rec.get("at"))
        if at is not None and isinstance(rec.get("turn"), int):
            out[rec["turn"]] = Timed(at)
    for rec in _lines(chat_dir / FILE):   # the hook's own stamp wins
        at = _parse(rec.get("end"))
        if at is None or not isinstance(rec.get("turn"), int):
            continue
        active = rec.get("active_sec")
        busy = None
        if isinstance(rec.get("busy"), list):
            pairs = ((_parse(x[0]), _parse(x[1])) for x in rec["busy"] if isinstance(x, list) and len(x) == 2)
            busy = [(a, b) for a, b in pairs if a and b]
        out[rec["turn"]] = Timed(at, int(active) if isinstance(active, (int, float)) else None,
                                 busy, int(rec.get("helper_sec") or 0))
    return out


def active_seconds(points: list[datetime], start: datetime, end: datetime) -> int:
    """Seconds between the turn's message times, long silences left out."""
    inside = sorted(p for p in points if start <= p <= end)
    edge = [start, *inside, end]
    return int(sum(g for g in ((b - a).total_seconds() for a, b in zip(edge, edge[1:])) if g <= ACTIVE_GAP_SEC))


def signature(chat_dir: Path) -> tuple:
    """Changes when an end is added — part of a chat's cache key."""
    sig = []
    for name in (FILE, "work.jsonl"):
        try:
            st = (chat_dir / name).stat()
            sig.append((st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append(None)
    return tuple(sig)


# ---------------------------------------------------------------------------
# Busy: the main agent and its helpers
# ---------------------------------------------------------------------------
#
# A chat is busy for the person while its agent works — and while the
# helpers it started work (Claude Code keeps each helper's transcript in
# <session>/subagents/agent-*.jsonl). ``measure`` reads both and answers,
# for the window since the chat's previous answer:
#   busy        — the merged stretches when anyone was active (a silence
#                 over ACTIVE_GAP_SEC splits them: a laptop asleep is not
#                 busy); three helpers in the same hour are one hour;
#   helper_sec  — each helper's own active time, added up: the work done;
#   active_sec  — the main agent's own working time inside the turn.
# The capture hook loads this file by path, so it stays standard-library.


Interval = tuple[datetime, datetime]


_points_cache: dict[str, tuple[tuple[int, int], list[datetime]]] = {}
# Kept by the number of times held, not of files: a chat had 174 helper
# transcripts, each asked for on every turn, and a cache of fewer files than
# that is emptied in a cycle. 500 000 times is about 30 MB; a 330 MB
# transcript holds about 5 000.
POINTS_KEPT = 500_000
#: And at most this many files, so files with no times in them pile up too.
FILES_KEPT = 2_000


def points_of(transcript: Path) -> list[datetime]:
    """The time of every message and tool result in a transcript (read once
    per file version: the backfill asks for the same helpers turn after turn)."""
    try:
        st = transcript.stat()
    except OSError:
        return []
    key, version = str(transcript), (st.st_mtime_ns, st.st_size)
    hit = _points_cache.pop(key, None)
    if hit and hit[0] == version:
        _points_cache[key] = hit       # asked for again: kept longest
        return hit[1]
    out = []
    for rec in _lines(transcript):
        if rec.get("type") in _ACTIVITY:
            at = _parse(rec.get("timestamp"))
            if at is not None:
                out.append(at)
    if len(out) > POINTS_KEPT // 4:
        return out          # one file this large is read again when asked, not kept
    _points_cache[key] = (version, out)
    held = sum(len(v[1]) for v in _points_cache.values())
    while (held > POINTS_KEPT or len(_points_cache) > FILES_KEPT) and len(_points_cache) > 1:
        held -= len(_points_cache.pop(next(iter(_points_cache)))[1])
    return out


#: Record types that are activity: Claude Code's messages and tool results,
#: Codex's rollout items and events (its session file, one line per event).
_ACTIVITY = frozenset({"user", "assistant", "response_item", "event_msg"})


def helper_transcripts(transcript: Path) -> list[Path]:
    """The helpers' transcripts of a Claude Code session."""
    folder = transcript.with_suffix("") / "subagents"
    return sorted(folder.glob("agent-*.jsonl")) if folder.is_dir() else []


def stretches(points: Iterable[datetime]) -> list[Interval]:
    """Points closer than ACTIVE_GAP_SEC joined into stretches."""
    out: list[list[datetime]] = []
    for p in sorted(points):
        if out and (p - out[-1][1]).total_seconds() <= ACTIVE_GAP_SEC:
            out[-1][1] = p
        else:
            out.append([p, p])
    return [(a, b) for a, b in out]


def union(ivs: Iterable[Interval]) -> list[Interval]:
    out: list[list[datetime]] = []
    for a, b in sorted(ivs):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def length(ivs: Iterable[Interval]) -> float:
    return sum((b - a).total_seconds() for a, b in ivs)


def clip(ivs: Iterable[Interval], lo: datetime, hi: datetime) -> list[Interval]:
    return [(max(a, lo), min(b, hi)) for a, b in ivs if b > lo and a < hi]


def measure(transcript: Path, start: datetime, end: datetime, since: datetime | None = None,
            main: Iterable[datetime] | None = None) -> dict[str, Any]:
    """Busy stretches, helper seconds and the turn's own working seconds for
    the window from the previous answer (``since``) to this one's ``end``,
    read from a Claude Code or Codex session file and its helpers'.
    ``main``: the session file's own activity times, from a caller that has
    read them already (the capture hook reads the end of the file once) —
    the file is then not read again here."""
    lo = min(since, start) if since else start
    helpers = []
    for f in helper_transcripts(transcript):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < lo:
                continue   # finished before this window: nothing of it here
        except OSError:
            continue
        helpers.append(points_of(f))
    return measure_points(points_of(transcript) if main is None else main, helpers, start, end, since)


def measure_points(main: Iterable[datetime], helpers: Iterable[Iterable[datetime]],
                   start: datetime, end: datetime, since: datetime | None = None) -> dict[str, Any]:
    """The same, from activity times a tool hands over itself (OpenCode's
    plugin reads its messages' and child sessions' times)."""
    lo = min(since, start) if since else start
    main = [p for p in main if lo <= p <= end]
    ivs = stretches([start, *main, end])
    helper = 0.0
    for points in helpers:
        mine = stretches(p for p in points if lo <= p <= end)
        helper += length(mine)
        ivs += mine
    return {
        "active_sec": active_seconds(main, start, end),
        "helper_sec": int(helper),
        "busy": [[a.replace(microsecond=0).isoformat(), b.replace(microsecond=0).isoformat()]
                 for a, b in union(ivs) if b > a],
    }


# ---------------------------------------------------------------------------
# Backfill from Claude Code's transcripts
# ---------------------------------------------------------------------------

def _is_prompt(rec: dict[str, Any], noise: tuple[str, ...]) -> bool:
    """A user record that starts a new exchange: typed text or a task
    notification — not a tool result, not the tool's own bookkeeping
    (``noise``: hookshared.TRANSCRIPT_NOISE)."""
    if rec.get("type") != "user" or rec.get("isMeta"):
        return False
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return not content.lstrip().startswith(noise)
    if isinstance(content, list):
        return not any(isinstance(p, dict) and p.get("type") == "tool_result" for p in content)
    return False


def from_transcript(transcript: Path, starts: dict[int, datetime],
                    every_start: Iterable[datetime] = ()) -> dict[int, tuple[datetime, int]]:
    """turn → (end, working seconds), for the turns whose start is given.
    ``every_start``: all the chat's turn starts — a turn ends before the next."""
    # Imported here, not at the top: the hook loads this file by path, with
    # no package around it, and never comes this way.
    from .hookshared import TRANSCRIPT_NOISE

    prompts: list[datetime] = []
    answers: list[datetime] = []
    points: list[datetime] = []
    for rec in _lines(transcript):
        at = _parse(rec.get("timestamp"))
        if at is None or rec.get("type") not in ("user", "assistant"):
            continue
        points.append(at)
        if _is_prompt(rec, TRANSCRIPT_NOISE):
            prompts.append(at)
        elif rec.get("type") == "assistant":
            answers.append(at)
    prompts.sort()
    answers.sort()
    captured = sorted(set(every_start) | set(starts.values()))
    out: dict[int, tuple[datetime, int]] = {}
    for turn, start in starts.items():
        # The prompt behind this turn is stamped a moment before the hook's
        # header; the next prompt after it bounds the answer.
        nxt_prompt = next((p for p in prompts if (p - start).total_seconds() > 2), None)
        nxt_turn = next((s for s in captured if s > start), None)
        nxt = min((x for x in (nxt_prompt, nxt_turn) if x is not None), default=None)
        last = None
        for a in answers:
            if a < start:
                continue
            if nxt is not None and a >= nxt:
                break
            last = a
        if last is not None:
            out[turn] = (last, active_seconds(points, start, last))
    return out


def _transcript_of(meta: dict[str, Any], claude_dir: Path) -> Path | None:
    ref = str(meta.get("session_ref") or "")
    if not ref or not claude_dir.is_dir():
        return None
    hits = list(claude_dir.glob(f"*/{ref}.jsonl"))
    return hits[0] if hits else None


def _current(folder: Path, transcript: Path) -> bool:
    """turns.jsonl written after the transcript and its helpers last moved:
    nothing new to read (the backfill runs at every start)."""
    try:
        mine = (folder / FILE).stat().st_mtime
        theirs = max([transcript.stat().st_mtime, *(f.stat().st_mtime for f in helper_transcripts(transcript))])
    except OSError:
        return False
    return mine > theirs


def backfill(data_root: Path, claude_dir: Path | None = None) -> int:
    """Time every Claude Code turn the hook did not, from its transcript.
    Rewrites a chat's turns.jsonl only when its answer changed; answers how
    many turns were written."""
    from .file_safety import acquire_flock, lock_path, replace_file
    from .sessions import parse_turns

    claude_dir = claude_dir or Path.home() / ".claude" / "projects"
    written = 0
    for chat_md in Path(data_root).glob("projects/*/chats/*/chat.md"):
        folder = chat_md.parent
        try:
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("tool", "claude-code") != "claude-code":
            continue
        transcript = _transcript_of(meta, claude_dir)
        if transcript is None:
            continue
        lines = list(_lines(folder / FILE))
        # A hook line from before busy stretches were measured is measured again.
        hook = [r for r in lines if r.get("source") == "hook" and "busy" in r]
        timed = {r.get("turn") for r in hook}
        pending = meta.get("pending_turn")
        turns = parse_turns(chat_md)
        measured = timed | {r.get("turn") for r in lines if r.get("source") == "transcript" and "busy" in r}
        if all(t.number in measured or t.number == pending for t in turns) and _current(folder, transcript):
            continue   # every turn timed, and nothing has moved since
        starts = {t.number: t.at for t in turns if t.number not in timed and t.number != pending}
        got = from_transcript(transcript, starts, (t.at for t in turns)) if starts else {}
        # Each answer's window opens at the previous answer's end: helpers
        # still working between turns land in the next one.
        ended = {int(r["turn"]): _parse(r.get("end")) for r in hook if isinstance(r.get("turn"), int)}
        ended.update({n: e for n, (e, _) in got.items()})
        fresh = []
        for n in sorted(got):
            end = got[n][0]
            since = ended.get(n - 1)
            m = measure(transcript, starts[n], end, since if since and since < starts[n] else None)
            fresh.append({"turn": n, "start": starts[n].isoformat(),
                          "end": end.replace(microsecond=0).isoformat(), **m, "source": "transcript"})
        old = [r for r in lines if r.get("source") == "transcript" or (r.get("source") == "hook" and "busy" not in r)]
        if fresh == old:
            continue
        # The hook may have timed a turn meanwhile: take its lines as they are
        # now, under the lock its append takes, so none lands between the
        # read and the replace.
        try:
            with acquire_flock(lock_path(folder / FILE), timeout_s=2.0):
                now = [r for r in _lines(folder / FILE) if r.get("source") == "hook"]
                hook = [r for r in now if "busy" in r]
                fresh = [r for r in fresh if r["turn"] not in {h.get("turn") for h in hook}]
                # A hook line without busy stretches is measured again from
                # the transcript; where the transcript has nothing for its
                # turn, the hook's end is still the only one and is kept.
                replaced = {r["turn"] for r in fresh}
                kept = [r for r in now if "busy" not in r and r.get("turn") not in replaced]
                body = "".join(json.dumps(r) + "\n" for r in [*hook, *kept, *fresh])
                tmp = folder / (FILE + ".tmp")
                tmp.write_text(body, encoding="utf-8")
                replace_file(tmp, folder / FILE)
        except OSError as exc:   # FileSafetyError too: the hook holds it, next start
            log.info("turn times for %s: %s", folder, exc)
            continue
        written += len(fresh)
    return written
