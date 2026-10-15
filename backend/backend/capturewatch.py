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
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .csvio import read_rows
from .db import ViewStore
from .hookshared import NOT_OPERATOR, TRANSCRIPT_NOISE

ERRORS = Path(".capture") / "errors.jsonl"
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


def check(store: ViewStore, claude_root: Path | None = None, now: float | None = None) -> dict[str, Any]:
    """Every capture problem now: turns not recorded, hook errors of the last day."""
    now = now or time.time()
    key = f"{store.data_root}|{claude_root}"
    hit = _cache.get(key)
    if hit and now - hit[0] < 30 and claude_root is None:
        return hit[1]
    root = claude_root or Path.home() / ".claude" / "projects"
    missed: list[dict[str, Any]] = []
    watched = 0
    for row in read_rows(store.data_root / "integrations.csv"):
        code, path = str(row.get("project") or ""), str(row.get("path") or "")
        if not code or not path:
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
    out = {"ok": not missed and not errors, "missed": missed, "errors": errors[-50:],
           "errors_n": len(errors), "watched": watched, "at": now}
    if claude_root is None:
        _cache[key] = (now, out)
    return out
