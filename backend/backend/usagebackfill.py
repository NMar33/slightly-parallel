"""Usage for the chats recorded before the hooks kept it — once, at start.

The hooks write a chat's tokens (usage.jsonl) since 2026-11-01. A chat
recorded before has none, and a chat that ran across that day has them from
the turn the hook first closed. The tool's own transcript still holds every
API message (Claude Code: ``~/.claude/projects/<folder>/<session>.jsonl`` and
its ``subagents/``; Codex: the rollout of the thread). This module reads it
with the import's parser (sessionimport.claude_usage_parts /
codex_usage_parts, hookshared's rules) and gives each line the turn of the
chat's own chat.md — so the hook, the import and the backfill agree.

What the hooks wrote is never touched: only lines of turns before the first
turn the hook kept a main-agent line for are added, never an id the file
holds, each with ``"source": "log"``. The read, the filter and the append are
one step under usage.jsonl's lock.

Turns are matched one by one (``align``): a chat.md turn takes the
transcript prompt recorded within seconds of it. A turn the transcript has
no prompt for gets no lines (its stretch stays with the prompt before it,
as the transcript has it); a prompt the chat has no turn for keeps its
tokens out (never given to a neighbour). A chat where fewer than half of the
turns match, or where two prompts could be one turn's, is refused, nothing
written: never guessed.

Each chat once: meta.json ``usage_backfill`` says what was done
(``{"at", "result": "done", "lines", "turns": [lo, hi], "matched",
"unmatched_turns", "unmatched_prompts", "version": 2}``) or why not
(``"no transcript"``, ``"turns do not match"``, ``"no turns"``, with
``version``). A refusal of an older version is tried again; a done chat
never. A chat active in the last hour is left for the next start (the hook
may be writing). Nothing raises into the server: each chat on its own,
logged with its id.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from . import capturewatch, sessionimport
from .csvio import read_rows
from .file_safety import acquire_flock, atomic_write_json, lock_path
from .hookshared import HISTORY_SLACK_S, _append_bytes, codex_home, codex_rollout
from .sessions import parse_chat

log = logging.getLogger("sp.usagebackfill")

MARKER = "usage_backfill"
#: A chat touched this recently may still be going on.
ACTIVE_SECONDS = 3600
#: A chat.md turn header and the transcript's prompt record are the same
#: moment, give or take the hook's start and the header's whole seconds.
ALIGN_SECONDS = 10.0
TOOLS = ("claude-code", "codex")
#: The marker's version: a refusal of an older one is tried again (the
#: first version refused every chat whose prompt count differed by more
#: than one); a done chat is never run again.
VERSION = 2


class Refused(Exception):
    """The chat cannot be backfilled; the message is the marker's result."""


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _local_epoch(value: Any) -> float | None:
    try:
        d = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    try:
        return d.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def _mtime(p: Path | None) -> float:
    try:
        return p.stat().st_mtime if p is not None else 0.0
    except OSError:
        return 0.0


def _fingerprint(paths: list[Path]) -> tuple:
    out = []
    for p in paths:
        try:
            st = p.stat()
            out.append((str(p), st.st_size, st.st_mtime_ns))
        except OSError:
            out.append((str(p), -1, -1))
    return tuple(out)


def _tool_of(meta: dict[str, Any], agent_id: str) -> str:
    tool = str(meta.get("tool") or "")
    if tool:
        return tool
    return "claude-code" if agent_id.startswith("cc-") else "codex" if agent_id.startswith("codex-") else ""


def find_transcript(meta: dict[str, Any], tool: str, claude_root: Path, codex_dir: Path,
                    project_path: str = "") -> Path | None:
    """The tool's own log of this chat's session, as sessionimport and
    capturewatch find it; None when there is none."""
    ref = str(meta.get("session_ref") or "")
    if not ref or "/" in ref or "\\" in ref or ".." in ref:
        return None
    if tool == "codex":
        return codex_rollout(ref, home=str(codex_dir))
    folders = [str(meta.get("cwd") or ""), project_path]
    for folder in dict.fromkeys(f.rstrip("/\\") for f in folders if f):
        hit = claude_root / capturewatch.folder_slug(folder) / f"{ref}.jsonl"
        if hit.is_file():
            return hit
    try:
        hits = sorted(claude_root.glob(f"*/{ref}.jsonl")) if claude_root.is_dir() else []
    except OSError:
        hits = []
    return hits[0] if len(hits) == 1 else None


def chat_turns(folder: Path, meta: dict[str, Any]) -> list[tuple[int, float | None, bool, str]]:
    """(turn, started epoch, quiet, the person's text) of each turn in
    chat.md. The hook's own epoch (meta.json ``turns``) where it kept one;
    else the header's local time."""
    hist: dict[int, tuple[float | None, bool]] = {}
    for h in meta.get("turns") or []:
        try:
            n, t = int(h[0]), h[1]
            quiet = bool(h[2]) if len(h) > 2 else False
        except (TypeError, ValueError, IndexError):
            continue
        hist[n] = (float(t) if isinstance(t, (int, float)) and t > 0 else None, quiet)
    turns, _n = parse_chat(folder / "chat.md")
    out = []
    for t in turns:
        epoch, quiet = hist.get(t.number, (None, False))
        out.append((t.number, epoch if epoch is not None else _local_epoch(t.at.isoformat()), quiet, t.user_summary))
    return out


def _same(a: str, b: str) -> bool:
    """The same message, as the hook kept it and as the transcript has it."""
    na, nb = " ".join(str(a).split())[:120].casefold(), " ".join(str(b).split())[:120].casefold()
    return bool(na) and na == nb


def align(chat: Sequence[tuple[int, float | None, bool, str]],
          prompts: Sequence[tuple[float | None, str]]) -> tuple[list[list[Any]], dict[str, int]]:
    """(the turn history for hookshared.assign_turns, the counts): turn by
    turn, in order, each turn the model saw takes the one transcript prompt
    within ALIGN_SECONDS after the last one taken, and starts at its time.

    A turn with no prompt there gets nothing: the hook kept it, the
    transcript did not (a message absorbed mid-turn, another session's
    message, a helper's hand-back); what was written meanwhile stays with
    the prompt before it, as in the transcript. A prompt with no turn opens a window of
    its own numbered 0, so its tokens are dropped, never given to a
    neighbour (history copied in from a branched session, prompts from
    before the hooks were wired, or that the hook skipped). Two prompts for
    one turn that the text does not tell apart (the same text twice is
    taken in order), prompts out of order or
    without a time, or fewer than half of the turns matched raise Refused.
    A prompt two turns could claim that the text does not settle is given
    to neither."""
    talk = [c for c in chat if not c[2]]
    times = [p[0] for p in prompts]
    numbers = [c[0] for c in chat]
    if not talk or not prompts or len(set(numbers)) != len(numbers) or numbers != sorted(numbers):
        raise Refused("turns do not match")
    if any(not isinstance(t, (int, float)) for t in times):
        raise Refused("turns do not match")
    at = [float(t) for t in times if isinstance(t, (int, float))]
    if any(b < a for a, b in zip(at, at[1:])):
        raise Refused("turns do not match")
    owner: dict[int, int] = {}
    ptr = 0
    for k, (n, t, _q, text) in enumerate(talk):
        if t is None:
            continue
        cand = [i for i in range(ptr, len(at)) if abs(at[i] - t) <= ALIGN_SECONDS]
        if len(cand) > 1:
            # The text tells them apart; the same text twice (a message
            # sent again) is taken in order, the earlier first.
            cand = [i for i in cand if _same(prompts[i][1], text)][:1]
            if not cand:
                raise Refused("turns do not match")
        if not cand:
            continue
        i = cand[0]
        nxt = talk[k + 1] if k + 1 < len(talk) else None
        if nxt is not None and nxt[1] is not None and abs(at[i] - nxt[1]) <= ALIGN_SECONDS \
                and not _same(prompts[i][1], text):
            if not _same(prompts[i][1], nxt[3]):
                ptr = i + 1          # either turn's: neither gets it
            continue                 # else the next turn's own
        owner[i] = n
        ptr = i + 1
    if len(owner) * 2 < len(talk):
        raise Refused("turns do not match")
    history = [[owner.get(i, 0), at[i], False] for i in range(len(at))]
    return history, {"matched": len(owner), "unmatched_turns": len(talk) - len(owner),
                     "unmatched_prompts": len(at) - len(owner)}


def _due(mark: Any) -> bool:
    """Whether a chat with this marker is (still) to be backfilled."""
    if not isinstance(mark, dict):
        return mark is None
    if mark.get("result") == "done":
        return False
    v = mark.get("version")
    return not (isinstance(v, int) and not isinstance(v, bool) and v >= VERSION)


def _helpers(transcript: Path | None, tool: str) -> list[Path]:
    """A Claude Code session's helper transcripts (``<session>/subagents``)."""
    base = transcript.with_suffix("") / "subagents" if transcript is not None and tool == "claude-code" else None
    try:
        return sorted(base.rglob("*.jsonl")) if base is not None and base.is_dir() else []
    except OSError:
        return []


def _inputs(folder: Path, transcript: Path, tool: str) -> tuple:
    """What the backfill of a chat read, as sizes and times (the helpers
    found again: a new one changes it too)."""
    return _fingerprint([folder / "chat.md", folder / "meta.json", transcript, *_helpers(transcript, tool)])


def _read_meta(folder: Path) -> Any:
    return json.loads((folder / "meta.json").read_text(encoding="utf-8"))


def _append_missing(path: Path, lines: list[dict[str, Any]],
                    unchanged: Callable[[], bool]) -> tuple[list[dict[str, Any]], int] | None:
    """Under usage.jsonl's lock: read every line, keep of ``lines`` those of
    a turn before the first turn with a main-agent line not from the log,
    whose id the file does not hold, and append them. Answers (the lines
    written, the lines from the log the file held already); None, nothing
    written, when ``unchanged()`` says the chat moved since it was read. A
    file that cannot be read raises (nothing is written)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with acquire_flock(lock_path(path), timeout_s=5.0):
        if not unchanged():
            return None
        ids: set[str] = set()
        first: int | None = None
        before = 0
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except FileNotFoundError:
            fh = None
        if fh is not None:
            with fh:
                for raw in fh:
                    try:
                        rec = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    if rec.get("id"):
                        ids.add(str(rec["id"]))
                    if rec.get("source") == "log":
                        before += 1
                        continue
                    turn = rec.get("turn")
                    if not rec.get("helper") and isinstance(turn, int) and not isinstance(turn, bool):
                        first = turn if first is None else min(first, turn)
        fresh = []
        for ln in lines:
            key = str(ln.get("id") or "")
            if not key or key in ids or (first is not None and int(ln["turn"]) >= first):
                continue
            ids.add(key)
            fresh.append({**ln, "source": "log"})
        if fresh:
            _append_bytes(path, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in fresh))
    return fresh, before


def _mark(folder: Path, value: dict[str, Any], used: dict[str, Any]) -> bool:
    """Set meta.json ``usage_backfill`` under the lock the hook takes for
    meta.json — only when meta.json is still the one the backfill read
    (``used``): False, nothing written, when it changed."""
    meta_path = folder / "meta.json"
    with acquire_flock(meta_path.with_name("meta.json.lock"), timeout_s=5.0):
        meta = _read_meta(folder)
        if meta != used:
            return False
        meta[MARKER] = value
        atomic_write_json(meta_path, meta)
    return True


def backfill_chat(folder: Path, claude_root: Path, codex_dir: Path, now: float,
                  project_path: str = "") -> dict[str, Any] | None:
    """Backfill one chat. Answers the marker written, or None when the chat
    was left for later (active, another tool, marked already, moved while
    it was read)."""
    meta = _read_meta(folder)
    if not isinstance(meta, dict) or not _due(meta.get(MARKER)):
        return None
    tool = _tool_of(meta, folder.name)
    if tool not in TOOLS:
        return None
    transcript = find_transcript(meta, tool, claude_root, codex_dir, project_path)
    touched = max([_local_epoch(meta.get("last_active")) or 0.0, _mtime(folder / "chat.md"),
                   _mtime(folder / "usage.jsonl"), _mtime(transcript),
                   *(_mtime(h) for h in _helpers(transcript, tool))])
    if now - touched < ACTIVE_SECONDS:
        return None
    marker: dict[str, Any]
    if transcript is None:
        marker = {"at": _now_iso(), "result": "no transcript", "version": VERSION}
        return marker if _mark(folder, marker, meta) else None
    seen = _inputs(folder, transcript, tool)

    def unchanged() -> bool:
        # meta.json as it was read (a write before ``seen`` was taken
        # included), and nothing else read since moved.
        return _inputs(folder, transcript, tool) == seen and _read_meta(folder) == meta

    try:
        chat = chat_turns(folder, meta)
        if not chat:
            raise Refused("no turns")
        session = str(meta.get("session_ref") or "")
        parts = sessionimport.claude_usage_parts if tool == "claude-code" else sessionimport.codex_usage_parts
        times, texts, assign = parts(transcript, session)
        history, counts = align(chat, list(zip(times, texts)))
    except Refused as why:
        if not unchanged():
            return None
        marker = {"at": _now_iso(), "result": str(why), "version": VERSION}
        return marker if _mark(folder, marker, meta) else None
    # A line with no time would go to some turn: not guessed. Turn 0 is a
    # prompt the chat has no turn for: assign_turns drops it.
    lines = [ln for ln in assign(history, history[0][1] - HISTORY_SLACK_S, 0) if ln.get("at")]
    got_back = _append_missing(folder / "usage.jsonl", lines, unchanged)
    if got_back is None:
        return None          # it moved while it was read: the next start
    fresh, before = got_back
    got = sorted({int(x["turn"]) for x in fresh})
    # ``lines``: the file's lines from the log — a run cut off between its
    # append and this mark wrote them, and the next one finds them there.
    marker = {"at": _now_iso(), "result": "done", "lines": len(fresh) + before,
              "turns": [got[0], got[-1]] if got else [], **counts, "version": VERSION}
    return marker if _mark(folder, marker, meta) else None


def backfill(data_root: Path, claude_root: Path | None = None, codex_dir: Path | None = None,
             now: float | None = None) -> dict[str, int]:
    """Backfill every chat of every project in integrations.csv. Answers
    {result: chats} of this run (``lines``: lines written)."""
    data_root = Path(data_root)
    claude_root = claude_root or Path.home() / ".claude" / "projects"
    codex_dir = codex_dir or codex_home()
    now = time.time() if now is None else now
    counts: dict[str, int] = {}
    paths: dict[str, str] = {}
    for row in read_rows(data_root / "integrations.csv"):
        code = str(row.get("project") or "").strip()
        if code and code not in paths:
            paths[code] = str(row.get("path") or "").strip()
    for code, project_path in paths.items():
        if "/" in code or "\\" in code or code in ("", ".", ".."):
            continue
        chats = data_root / "projects" / code / "chats"
        try:
            folders = sorted(p for p in chats.iterdir() if p.is_dir() and not p.is_symlink()) if chats.is_dir() else []
        except OSError:
            continue
        for folder in folders:
            if not (folder / "meta.json").is_file():
                continue
            try:
                marker = backfill_chat(folder, claude_root, codex_dir, now, project_path)
            except Exception:  # noqa: BLE001 — one chat never stops the rest, nor the server
                log.exception("usage backfill: %s/%s not filled", code, folder.name)
                continue
            if marker is None:
                continue
            counts[marker["result"]] = counts.get(marker["result"], 0) + 1
            if marker["result"] == "done":
                counts["lines"] = counts.get("lines", 0) + int(marker.get("lines") or 0)
    return counts


def run_once(data_root: Path) -> None:
    """The server's start (a daemon thread): never raises."""
    try:
        got = backfill(Path(data_root))
        if got:
            log.info("usage backfill: %s", ", ".join(f"{k} {v}" for k, v in sorted(got.items())))
    except Exception:  # noqa: BLE001 — usage missing is said on the Usage page
        log.exception("usage not backfilled")


__all__ = ["backfill", "backfill_chat", "run_once", "align", "chat_turns", "find_transcript", "MARKER"]
