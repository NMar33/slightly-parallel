"""Is capture working? — the watchdog behind the top bar's warning.

Capture fails in two ways, and neither says much on its own:

- **loudly**: the hook runs and throws. It prints the failure into the
  agent's chat and exits 0 (a session must never break), and records it in
  ``<data root>/.capture/errors.jsonl`` (scripts/hooks/capture.py
  ``record_failure``). Here: every error of the last day.
- **silently**: the hook never runs — not installed in that folder, Python
  missing, a path moved. Nothing is written anywhere. Claude Code keeps its
  own log of every session in ``~/.claude/projects/<folder>/<session>.jsonl``;
  for each project folder registered in Setup, a session whose last message
  from the person is newer than Slightly Parallel's last captured turn of that session
  (or that Slightly Parallel never saw at all) is a turn that was not recorded.

Only sessions active in the last hour are judged, and only the person's own
messages count — a turn that runs for an hour is not a gap. Read-only: the
home folder is read, never written; tests pass their own ``claude_root``.

**Lost** (``lost``): a session of the last week, in a registered folder,
after its integration, with a message from the person, that Slightly
Parallel never recorded at all — Claude Code's log as above, Codex's in
``~/.codex/sessions/<y>/<m>/<d>/rollout-*.jsonl`` (its first line names the
session and the folder it ran in). A missed turn is gone from the top bar an
hour later; a lost session stays until the operator connects the tool or
says it is not needed (``.capture/ignored.json``, project:tool).
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .csvio import read_rows
from .db import ViewStore
from .hookshared import NOT_OPERATOR, TRANSCRIPT_NOISE, codex_home, session_key

ERRORS = Path(".capture") / "errors.jsonl"
IGNORED = Path(".capture") / "ignored.json"
WEEK_SECONDS = 7 * 86400       # how far back a session never recorded is looked for
ACTIVE_SECONDS = 3600          # a session untouched this long is not judged
GRACE_SECONDS = 120            # a prompt this much newer than the capture is a missed turn
# What the hook does not capture (a helper's report handed back into the
# chat included: without it here, every such report was "a turn that was
# not recorded"), and the tool's own bookkeeping in its transcript.
_SYSTEM = tuple(dict.fromkeys(NOT_OPERATOR + TRANSCRIPT_NOISE))
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def folder_slug(path: str) -> str:
    """Claude Code's name for a working folder: every other character a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _utc(ts: str) -> float | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def _local(ts: str) -> float | None:
    """A captured time: local, without a zone."""
    try:
        d = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    return d.timestamp() if d.tzinfo is None else d.astimezone(timezone.utc).timestamp()


def last_prompt(transcript: Path, tail_bytes: int = 400_000) -> float | None:
    """When the person last wrote in this session, from the end of its log."""
    try:
        with open(transcript, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - tail_bytes))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"type":"user"' not in line.replace(" ", ""):
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
            continue
        msg = rec.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
                continue
            text = " ".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
        else:
            text = str(content or "")
        if not text.strip() or text.lstrip().startswith(_SYSTEM):
            continue
        return _utc(str(rec.get("timestamp") or ""))
    return None


def errors_since(data_root: Path, since: float) -> list[dict[str, Any]]:
    path = Path(data_root) / ERRORS
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue  # valid JSON, not a record: a hand edit or a torn line
        at = _local(str(e.get("at") or ""))
        if at is not None and at >= since:
            out.append({**e, "ts": at})
    return out


def ignored(data_root: Path) -> set[str]:
    """The project:tool pairs the operator said need no recording."""
    try:
        got = json.loads((Path(data_root) / IGNORED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(x) for x in got} if isinstance(got, list) else set()


def set_ignored(data_root: Path, project: str, tool: str, on: bool) -> set[str]:
    from .file_safety import atomic_write
    pairs = ignored(data_root)
    key = f"{project}:{tool}"
    (pairs.add if on else pairs.discard)(key)
    path = Path(data_root) / IGNORED
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(sorted(pairs)))
    _cache.clear()
    return pairs


def _since(created_date: str) -> float:
    """The start of an integration's day, from its YYMM-DD; 0 when unreadable."""
    m = re.fullmatch(r"(\d\d)(\d\d)-(\d\d)", created_date.strip())
    if not m:
        return 0.0
    try:
        return datetime(2000 + int(m[1]), int(m[2]), int(m[3])).timestamp()
    except ValueError:
        return 0.0


def _codex_prompt(rollout: Path, tail_bytes: int = 400_000) -> float | None:
    """When the person last wrote in a Codex session: its last user message
    that is not the context Codex adds itself (those start with '<')."""
    try:
        with open(rollout, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - tail_bytes))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"role":"user"' not in line.replace(" ", ""):
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        pl = rec.get("payload") if isinstance(rec, dict) else None
        if not isinstance(pl, dict) or pl.get("type") != "message" or pl.get("role") != "user":
            continue
        text = " ".join(str(c.get("text") or "") for c in pl.get("content") or [] if isinstance(c, dict))
        # What Codex adds itself: context in tags, and the AGENTS.md it read.
        if not text.strip() or text.lstrip().startswith(("<", "# AGENTS.md instructions")):
            continue
        return _utc(str(rec.get("timestamp") or ""))
    return None


def codex_sessions(root: Path, since: float) -> list[dict[str, Any]]:
    """Codex sessions touched since ``since``: id, folder, last prompt."""
    out: list[dict[str, Any]] = []
    for rollout in sorted(root.glob("*/*/*/rollout-*.jsonl")):
        try:
            if rollout.stat().st_mtime < since:
                continue
            with open(rollout, encoding="utf-8", errors="replace") as fh:
                first = json.loads(fh.readline() or "{}")
        except (OSError, ValueError):
            continue
        pl = first.get("payload") if isinstance(first, dict) else None
        if not isinstance(pl, dict) or not pl.get("id") or not pl.get("cwd"):
            continue
        if pl.get("thread_source", "user") != "user":
            continue  # a helper thread Codex started, not the person's chat
        out.append({"session": str(pl["id"]), "cwd": str(pl["cwd"]), "rollout": rollout})
    return out


def _norm(path: str) -> str:
    """A folder as one string to compare: resolved, case folded where the system folds it."""
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except (OSError, ValueError):
        return os.path.normcase(path.rstrip("/\\"))


def _owner(cwd: str, folders: dict[str, str]) -> str:
    """The project whose folder holds cwd, the longest folder winning — as the hook decides."""
    c = _norm(cwd)
    best, size = "", -1
    for code, folder in folders.items():
        if (c == folder or c.startswith(folder.rstrip(os.sep) + os.sep)) and len(folder) > size:
            best, size = code, len(folder)
    return best


#: The file each tool's capture lives in, in a project folder: once it is
#: written, only sessions after it count as lost — older ones were before the fix.
_WIRED = {"claude": Path(".claude") / "settings.local.json", "codex": Path(".codex") / "hooks.json"}


def _wired_at(path: str, tool: str) -> float:
    try:
        return (Path(path) / _WIRED[tool]).stat().st_mtime
    except OSError:
        return 0.0


def unrecorded(store: ViewStore, claude_root: Path, codex_root: Path, now: float) -> list[dict[str, Any]]:
    """Every session of the last week, in an integrated folder, after its
    integration, with a message from the person, that nothing recorded: one
    row each — project, tool, session id, its log file, the folder it ran
    in, its last message, and whether it ran after the tool was wired there
    (``after_wiring``; before it, the session was lost for want of a hook)."""
    since = now - WEEK_SECONDS
    codex = codex_sessions(codex_root, since) if codex_root.is_dir() else []
    rows_ = [r for r in read_rows(store.data_root / "integrations.csv") if r.get("project") and r.get("path")]
    folders = {str(r["project"]): _norm(str(r["path"])) for r in rows_}
    out: list[dict[str, Any]] = []
    for row in rows_:
        code, path = str(row.get("project") or ""), str(row.get("path") or "").rstrip("/\\")
        base = max(since, _since(str(row.get("created_date") or "")))
        wired = {tool: _wired_at(path, tool) for tool in _WIRED}
        chats = store.data_root / "projects" / code / "chats"
        folder = claude_root / folder_slug(path)
        for transcript in folder.glob("*.jsonl") if folder.is_dir() else []:
            try:
                if transcript.stat().st_mtime < base:
                    continue
            except OSError:
                continue
            if (chats / f"cc-{transcript.stem[:8]}" / "meta.json").exists():
                continue
            at = last_prompt(transcript)
            if at is not None and at >= base:
                out.append({"project": code, "tool": "claude", "session": transcript.stem, "file": transcript,
                            "cwd": path, "last_at": at, "wired": wired["claude"] > 0, "after_wiring": at >= wired["claude"] > 0})
        for c in codex:
            if _owner(c["cwd"], folders) != code:
                continue
            # Recorded under its name now, or under the first 8 characters of
            # its id as it was before 17 October 2026.
            names = (f"codex-{session_key('codex', c['session'])}", f"codex-{c['session'][:8]}")
            if any((chats / n / "meta.json").exists() for n in names):
                continue
            at = _codex_prompt(c["rollout"])
            if at is not None and at >= base:
                out.append({"project": code, "tool": "codex", "session": c["session"], "file": c["rollout"],
                            "cwd": c["cwd"], "last_at": at, "wired": wired["codex"] > 0, "after_wiring": at >= wired["codex"] > 0})
    return out


def lost(store: ViewStore, claude_root: Path, codex_root: Path, now: float) -> list[dict[str, Any]]:
    """Per project and tool: the sessions nothing recorded. ``sessions``
    counts what warns (all of them while the tool is not wired there; once
    it is, only those after); ``earlier`` the ones before the wiring, which
    no longer warn but can still be imported."""
    skip = ignored(store.data_root)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for r in unrecorded(store, claude_root, codex_root, now):
        g = groups.setdefault((r["project"], r["tool"]), {"project": r["project"], "tool": r["tool"], "sessions": 0,
                                                          "earlier": 0, "last_at": 0.0,
                                                          "ignored": f"{r['project']}:{r['tool']}" in skip})
        g["sessions" if r["after_wiring"] or not r["wired"] else "earlier"] += 1
        g["last_at"] = max(g["last_at"], r["last_at"])
    return list(groups.values())


def check(store: ViewStore, claude_root: Path | None = None, now: float | None = None,
          codex_root: Path | None = None) -> dict[str, Any]:
    """Every capture problem now: turns not recorded, hook errors of the last day."""
    now = now or time.time()
    key = f"{store.data_root}|{claude_root}"
    hit = _cache.get(key)
    if hit and now - hit[0] < 30 and claude_root is None:
        return hit[1]
    root = claude_root or Path.home() / ".claude" / "projects"
    missed: list[dict[str, Any]] = []
    watched = 0
    skip = ignored(store.data_root)
    for row in read_rows(store.data_root / "integrations.csv"):
        code, path = str(row.get("project") or ""), str(row.get("path") or "").rstrip("/\\")
        if not code or not path or f"{code}:claude" in skip:
            continue
        folder = root / folder_slug(path)
        if not folder.is_dir():
            continue
        chats = store.data_root / "projects" / code / "chats"
        for transcript in folder.glob("*.jsonl"):
            try:
                if now - transcript.stat().st_mtime > ACTIVE_SECONDS:
                    continue
            except OSError:
                continue
            watched += 1
            prompt = last_prompt(transcript)
            if prompt is None or now - prompt > ACTIVE_SECONDS:
                continue
            session = transcript.stem
            meta = chats / f"cc-{session[:8]}" / "meta.json"
            captured: float | None = None
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
                captured = _local(str(m.get("last_active") or "")) if isinstance(m, dict) else None
            except (OSError, ValueError):
                captured = None
            if captured is None or prompt - captured > GRACE_SECONDS:
                missed.append({
                    "project": code, "session": session, "agent_id": f"cc-{session[:8]}",
                    "prompt_at": prompt, "captured_at": captured,
                    "why": "this session was never captured" if captured is None
                           else "its latest messages were not captured",
                })
    errors = errors_since(store.data_root, now - 86400)
    # A test passes its own Claude root and no Codex one: then there is none.
    croot = codex_root or (codex_home() / "sessions" if claude_root is None else root / "__no_codex__")
    gone = lost(store, root, croot, now)
    out = {"ok": not missed and not errors and not any(g["sessions"] and not g["ignored"] for g in gone),
           "missed": missed, "lost": gone, "errors": errors[-50:],
           "errors_n": len(errors), "watched": watched, "at": now}
    if claude_root is None:
        _cache[key] = (now, out)
    return out
