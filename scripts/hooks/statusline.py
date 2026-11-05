#!/usr/bin/env python3
"""Claude Code status line — the plan limits and the open chat's state for
Slightly Parallel, then the operator's own status line.

Installed by the Setup page into a project's ``.claude/settings.local.json``
as ``statusLine``. Claude Code runs it after each assistant message (and on
a few other events) with the session's JSON on stdin and shows what it
prints (https://code.claude.com/docs/en/statusline). Of that JSON this
keeps:

- ``rate_limits`` (Pro, Max and Ultra plans, after the first reply): one
  line in ``<data root>/.usage/limits.jsonl`` when it tells something new
  for the account (a later reset, a higher percentage) or the account's
  last line is older than five minutes (hookshared.limits_append). The
  line names the config folder's key (``CLAUDE_CONFIG_DIR`` of this
  process, else ``~/.claude``), and as data the ``model.id`` and the
  session's first 8 characters;
- ``context_window`` and ``prompt_cache``: the chat's state in
  ``<data root>/.usage/sessions/claude-code-<session>.json`` (overwritten;
  files a week old are removed).

Nothing else is kept: no folder, no prompt, no cost. Then the operator's
own status line runs with the same input and its output is shown; without
one, one short line of the limits. Which one is the operator's: with
``--then-key``, the side file Setup wrote (hookshared, "The status line's
wrapped command") — the command kept from the same settings file, or the
one the project's shared settings or the user's give now; ``--then
<command>`` is how Setup wrote it before.

Usage (as written by Setup):
    statusline.py --data-root <path> [--then-key <key>]

Fast and quiet by rule: Claude Code cancels a status line still running when
the next update comes, and a status line that fails shows nothing. Every
failure is swallowed; the exit code is 0.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

#: The operator's own status line gets this long; then its output is dropped.
THEN_TIMEOUT_S = 10.0
#: The session folder is swept (old state files, temp files a killed run
#: left) at most this often.
SWEEP_S = 3600
#: A temp file older than this was left by a run that was killed.
TMP_STALE_S = 60


@functools.lru_cache(maxsize=1)
def _shared():
    """The backend's hookshared.py, loaded by path (standard library only)."""
    path = Path(__file__).resolve().parents[2] / "backend" / "backend" / "hookshared.py"
    spec = importlib.util.spec_from_file_location("sp_hookshared_statusline", path)
    assert spec is not None and spec.loader is not None, path
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _now(shared=None) -> str:
    return (shared.now_dt() if shared is not None else datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")


def _finite(value):
    """A number the status line gave, if it is a finite one (else None)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _cause(value) -> str | None:
    """Claude Code's last cache miss cause as text: a list or an object of
    causes joined with commas."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = [str(k) if v is True else f"{k}: {v}" for k, v in value.items() if v not in (None, False, "")]
        return ", ".join(parts)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v not in (None, ""))
    return str(value)


def session_state(data: dict, shared) -> dict | None:
    """The open chat's state from the status line JSON: only the fields it
    gave. None when it gave neither the context window nor the cache."""
    ctx = data.get("context_window") if isinstance(data.get("context_window"), dict) else None
    cache = data.get("prompt_cache") if isinstance(data.get("prompt_cache"), dict) else None
    if ctx is None and cache is None:
        return None
    out: dict = {"at": _now(shared), "session_id": str(data.get("session_id") or "")}
    model = data.get("model")
    if isinstance(model, dict) and model.get("id"):
        out["model"] = str(model["id"])
    if ctx is not None:
        c: dict = {}
        if _finite(ctx.get("used_percentage")) is not None:
            c["used_pct"] = ctx["used_percentage"]
        if _finite(ctx.get("context_window_size")) is not None:
            c["size"] = ctx["context_window_size"]
        cur = ctx.get("current_usage") if isinstance(ctx.get("current_usage"), dict) else {}
        for key, field in (("input", "input_tokens"), ("output", "output_tokens"),
                           ("cache", "cache_read_input_tokens"), ("cache_write", "cache_creation_input_tokens")):
            if _finite(cur.get(field)) is not None:
                c[key] = cur[field]
        if c:
            out["context"] = c
    if cache is not None:
        p: dict = {}
        if isinstance(cache.get("warm"), bool):
            p["warm"] = cache["warm"]
        if "hit_ratio" in cache:
            p["hit_ratio"] = _finite(cache["hit_ratio"])
        if "last_miss_cause" in cache:
            p["last_miss_cause"] = _cause(cache["last_miss_cause"])
        for key in ("expires_at", "last_miss_at"):
            if key in cache:
                p[key] = shared.epoch_local(cache[key]) or None
        if p:
            out["prompt_cache"] = p
    return out


def write_session(data_root: Path, state: dict, shared) -> None:
    """Overwrite this chat's state file."""
    folder = data_root / ".usage" / "sessions"
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", state.get("session_id") or "")[:80] or "session"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"claude-code-{safe}.json"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        shared.replace_file(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    sweep(folder, shared)


def sweep(folder: Path, shared, now: float | None = None) -> bool:
    """At most once an hour (the folder's ``.swept`` mark): remove the state
    files a week old, and the temp files a killed run left. True when it swept."""
    now = time.time() if now is None else now
    mark = folder / ".swept"
    try:
        if now - mark.stat().st_mtime < SWEEP_S:
            return False
    except OSError:
        pass
    try:
        mark.touch()
        os.utime(mark, (now, now))
    except OSError:
        return False
    cutoff = now - shared.SESSION_FILE_DAYS * 86400
    for old in folder.iterdir():
        try:
            age = old.stat().st_mtime
            if (old.suffix == ".json" and age < cutoff) or \
                    (old.name.startswith(".") and old.name.endswith(".tmp") and now - age > TMP_STALE_S):
                old.unlink()
        except OSError:
            continue
    return True


def own_line(data: dict, shared=None) -> str:
    """``SP · 5-hour 62% · week 31%`` (the percent by the Usage page's rule,
    hookshared.pct_whole); empty without the limits."""
    shared = shared or _shared()
    limits = data.get("rate_limits") if isinstance(data.get("rate_limits"), dict) else {}
    parts = []
    for key, label in (("five_hour", "5-hour"), ("seven_day", "week")):
        w = limits.get(key)
        used = shared.pct_whole(w.get("used_percentage")) if isinstance(w, dict) else None
        if used is not None:
            parts.append(f"{label} {used}%")
    return "SP · " + " · ".join(parts) if parts else ""


def keep(raw: bytes, data_root: Path) -> None:
    """What this status line keeps of one update. Writes only under the
    data root, and only when it exists. Never raises."""
    try:
        if not data_root.is_dir():
            return
        data = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        if not isinstance(data, dict):
            return
        shared = _shared()
        model = data.get("model")
        line = shared.limits_line_claude(
            data.get("rate_limits"), _now(shared),
            account=shared.config_key(shared.claude_config_dir()),
            model=str(model.get("id") or "") if isinstance(model, dict) else "",
            session=str(data.get("session_id") or ""))
        shared.limits_append(data_root, line, now=shared.now_epoch())
        state = session_state(data, shared)
        if state is not None and state.get("session_id"):
            write_session(data_root, state, shared)
    except Exception:  # noqa: BLE001 — a status line must never fail
        pass


def then_command(data_root: str, key: str, then: str) -> str:
    """The operator's own status line: from the side file of ``key``, else
    the ``--then`` an older Setup wrote. Never raises."""
    if key and data_root:
        try:
            shared = _shared()
            return shared.statusline_then_command(shared.read_statusline_then(Path(data_root).expanduser(), key))
        except Exception:  # noqa: BLE001
            return ""
    return then


def run_then(command: str, raw: bytes) -> bytes:
    """The operator's own status line, with the same input; its output. A
    status line of ours inside it (the operator's script calls this one)
    keeps nothing and runs nothing more."""
    env = {**os.environ, "SP_STATUSLINE_ACTIVE": "1"}
    try:
        got = subprocess.run(command, shell=True, input=raw, capture_output=True, timeout=THEN_TIMEOUT_S,
                             check=False, env=env)
    except (OSError, subprocess.SubprocessError):
        return b""
    return got.stdout


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    data_root, then, key = "", "", ""
    while args:
        a = args.pop(0)
        if a == "--data-root" and args:
            data_root = args.pop(0)
        elif a == "--then" and args:
            then = args.pop(0)
        elif a == "--then-key" and args:
            key = args.pop(0)
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        raw = b""
    nested = bool(os.environ.get("SP_STATUSLINE_ACTIVE"))
    if data_root and not nested:
        keep(raw, Path(data_root).expanduser())
    try:
        command = "" if nested else then_command(data_root, key, then)
        out = run_then(command, raw) if command.strip() else b""
        if out.strip():
            sys.stdout.buffer.write(out)
        else:
            # No status line of the operator's, or it printed nothing: ours.
            try:
                data = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            except ValueError:
                data = {}
            line = own_line(data) if isinstance(data, dict) else ""
            if line:
                sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
        sys.stdout.flush()
    except Exception:  # noqa: BLE001 — a status line must never fail
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
