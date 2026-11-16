"""Codex's plan limits read without a Codex chat (``codex app-server``).

The rollout path (hookshared.codex_turn_usage) records Codex's limits only
when a Codex turn ends in an integrated folder. The operator runs Codex
rarely, so the Usage page's Codex row stayed empty for days. ``codex
app-server`` — stdio, newline-delimited JSON-RPC 2.0 — answers
``account/rateLimits/read`` in about a second: no session, no tokens spent.

What this module writes, all under ``<data root>/.usage/``:

- ``limits.jsonl`` — a reading as one more line of the account's series
  (hookshared.limits_append dedups: a line goes in only when it tells
  something new, the plan changed, or the series' last line is older than
  five minutes), ``source: "app-server"``. The series key is the one the
  rollout lines use (CODEX_HOME's key); Codex's own ``accountId`` is kept on
  the line as data.
- ``codex-account.json`` — the account's own daily tokens
  (``account/usage/read``), kept as given for a later look at what the
  hooks did not record.
- ``codex-poll.json`` — the poll's state: last attempt, last success, next
  attempt (local time for the page, and ``next_epoch``, the same moment in
  epoch seconds, which ``due`` reads: in the hour the clocks go back a local
  time names two moments), the cause of the last failure, how many failures
  in a row. Kept
  apart from the readings so a failing poll keeps its backoff instead of
  retrying every minute.

The Poller is a daemon thread of the served app (server.py's lifespan): it
wakes every minute and reads the settings each time (``usage.codex_poll``,
``usage.codex_poll_hours``). The Usage page may ask for a reading now
(``POST /api/usage/limits/refresh``); agents may not.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any

from . import app_settings, file_safety, hookshared

log = logging.getLogger("backend.codexlimits")

USAGE_DIR = ".usage"
ACCOUNT_FILE = "codex-account.json"
POLL_FILE = "codex-poll.json"
SOURCE = "app-server"
READ_TIMEOUT_S = 15.0
WAKE_S = 60
#: After the machine wakes, the network needs a moment: no poll for this long.
SETTLE_S = 120
#: After a failure: 15 min, then 1 h, then 6 h (never past the setting's interval).
BACKOFF_S = (15 * 60, 60 * 60, 6 * 3600)
CLIENT = {"name": "slightly-parallel", "title": "Slightly Parallel", "version": "1"}

_inflight = threading.Lock()
_logged_causes: set[str] = set()


# ---------------------------------------------------------------------------
# Detection and one reading
# ---------------------------------------------------------------------------


def _version_key(folder: Path) -> tuple[int, ...]:
    digits = "".join(c if c.isdigit() else " " for c in folder.parent.name).split()
    return tuple(int(d) for d in digits)


def find_codex() -> str:
    """The codex program; "" when there is none. A server started at login
    or as a service often has a shorter PATH than the operator's terminal,
    so the usual install folders are looked in as well."""
    got = shutil.which("codex")
    if got:
        return got
    home = Path.home()
    folders = [home / ".local" / "bin", home / ".npm-global" / "bin", home / ".volta" / "bin", home / ".bun" / "bin",
               Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    # The newest Node version first, as nvm would choose.
    folders += sorted((home / ".nvm" / "versions" / "node").glob("*/bin"), key=_version_key, reverse=True)
    if os.name == "nt" and os.environ.get("APPDATA"):
        folders.insert(0, Path(os.environ["APPDATA"]) / "npm")
    for folder in folders:
        hit = shutil.which("codex", path=str(folder))
        if hit:
            return hit
    return ""


def detect() -> dict[str, Any]:
    """Is Codex on this machine: ``{found, exe, home}``. No network."""
    exe = find_codex()
    return {"found": bool(exe), "exe": exe, "home": str(hookshared.codex_home())}


def _stop(proc: subprocess.Popen[str]) -> None:
    """End the program and what it started. On npm's install ``codex`` is a
    wrapper around the real program (on Windows a .cmd around node around
    it), and ending only the wrapper leaves the real one running."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _rpc(exe: str, timeout: float) -> dict[int, Any]:
    """Run the handshake and the three reads; the answers by id. Raises
    TimeoutError when the answers do not come in time, OSError when the
    process cannot start, ValueError on an unreadable answer."""
    calls = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"clientInfo": CLIENT, "capabilities": {"experimentalApi": True}}},
        {"jsonrpc": "2.0", "method": "initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "account/read", "params": {"refreshToken": False}},
        {"jsonrpc": "2.0", "id": 3, "method": "account/rateLimits/read",
         "params": {"excludeResetCreditDetails": True}},
        {"jsonrpc": "2.0", "id": 4, "method": "account/usage/read", "params": None},
    ]
    want = {1, 2, 3, 4}
    answers: dict[int, Any] = {}
    # npm's wrapper needs node from the same folder when the PATH lacks it.
    env = {**os.environ, "PATH": os.pathsep.join((str(Path(exe).parent), os.environ.get("PATH", "")))}
    proc = subprocess.Popen([exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", env=env,
                            start_new_session=os.name != "nt",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    done = threading.Event()

    def pump() -> None:
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(msg, dict) and isinstance(msg.get("id"), int):
                    answers[msg["id"]] = msg
                    if want <= answers.keys():
                        break
        finally:
            done.set()

    reader = threading.Thread(target=pump, name="codex-limits-read", daemon=True)
    reader.start()
    try:
        assert proc.stdin is not None
        for call in calls:
            proc.stdin.write(json.dumps(call) + "\n")
        proc.stdin.flush()
    except (OSError, ValueError):
        pass  # the process ended first: the answers say what came
    finished = done.wait(timeout)
    _stop(proc)
    reader.join(timeout=2)
    for pipe in (proc.stdin, proc.stdout):
        # The reader may still be in stdout, if something holds it open: then it stays.
        if pipe is not None and (pipe is proc.stdin or not reader.is_alive()):
            try:
                pipe.close()
            except (OSError, ValueError):
                pass
    # The limits are what matters: a hung usage read does not lose them.
    if not finished and 3 not in answers:
        raise TimeoutError(f"no answer in {timeout:g} s")
    return answers


def _bucket(result: dict[str, Any]) -> dict[str, Any]:
    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict) and isinstance(by_id.get("codex"), dict):
        return by_id["codex"]
    got = result.get("rateLimits")
    return got if isinstance(got, dict) else {}


def _windows(bucket: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The bucket's windows by name: ``five_hour`` (300 min), ``seven_day``
    (10 080 min), any other by its own ``<minutes>m`` name."""
    out: dict[str, dict[str, Any]] = {}
    for pos in ("primary", "secondary"):
        w = bucket.get(pos)
        if not isinstance(w, dict):
            continue
        minutes = w.get("windowDurationMins")
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            continue
        name = {300: "five_hour", 10080: "seven_day"}.get(minutes, f"{minutes}m")
        used = w.get("usedPercent")
        if isinstance(used, bool) or not isinstance(used, (int, float)):
            continue
        out[name] = {"used": float(used), "resets_at": hookshared.epoch_local(w.get("resetsAt")),
                     "span_s": minutes * 60}
    return out


def limits_line(result: dict[str, Any], at: str) -> dict[str, Any] | None:
    """A limits line from an ``account/rateLimits/read`` result; None
    without a 5-hour or a weekly window."""
    bucket = _bucket(result)
    windows = _windows(bucket)
    line: dict[str, Any] = {"at": at, "tool": "codex", "account": hookshared.config_key(hookshared.codex_home()),
                            "model": "", "session": ""}
    for name in ("five_hour", "seven_day"):
        if name in windows:
            line[name] = windows[name]
    if "five_hour" not in line and "seven_day" not in line:
        return None
    if bucket.get("planType"):
        line["plan"] = str(bucket["planType"])
    if result.get("accountId"):
        line["account_id"] = str(result["accountId"])
    line["source"] = SOURCE
    return line


def account_usage(result: dict[str, Any], at: str, account_id: str) -> dict[str, Any]:
    """``account/usage/read``'s result as the file keeps it: the summary as
    given, the days as ``[{date, tokens}]`` (null stays null)."""
    days = []
    for b in result.get("dailyUsageBuckets") or []:
        if isinstance(b, dict) and b.get("startDate"):
            days.append({"date": str(b["startDate"]), "tokens": b.get("tokens")})
    summary = result.get("summary")
    return {"read_at": at, "account_id": account_id,
            "summary": summary if isinstance(summary, dict) else {}, "days": days}


def _error_text(answer: Any) -> str:
    """The server's own sentence from an error answer, short, with no address in it."""
    err = answer.get("error") if isinstance(answer, dict) else None
    msg = str(err.get("message") or "") if isinstance(err, dict) else ""
    return re.sub(r"\S+@\S+", "<address>", " ".join(msg.split()))[:160]


def read(timeout: float = READ_TIMEOUT_S, exe: str | None = None, at: str | None = None) -> dict[str, Any]:
    """One reading: ``{ok: True, limits_line, account_id, usage}`` or
    ``{ok: False, cause}`` — the cause a short plain sentence."""
    exe = find_codex() if exe is None else exe
    if not exe:
        return {"ok": False, "cause": "codex is not on this machine"}
    stamp = at or hookshared.epoch_local(hookshared.now_epoch())
    try:
        answers = _rpc(exe, timeout)
    except TimeoutError as exc:
        return {"ok": False, "cause": str(exc)}
    except OSError as exc:
        return {"ok": False, "cause": f"codex could not start: {exc.strerror or exc}"}
    init = answers.get(1)
    if not isinstance(init, dict) or "result" not in init:
        return {"ok": False, "cause": "codex has no app-server (older version)"}
    # Signed out: account/read answers {account: null}. An error on it (an
    # older shape) decides nothing: the limits read does.
    account = answers.get(2) or {}
    acc = account.get("result") if isinstance(account, dict) else None
    if isinstance(acc, dict) and "account" in acc and acc.get("account") is None:
        return {"ok": False, "cause": "not signed in"}
    limits = answers.get(3)
    if not isinstance(limits, dict) or not isinstance(limits.get("result"), dict):
        msg = _error_text(limits)
        if "auth" in msg.lower() or "login" in msg.lower():
            return {"ok": False, "cause": "not signed in"}
        return {"ok": False, "cause": msg or "unreadable answer"}
    line = limits_line(limits["result"], stamp)
    if line is None:
        return {"ok": False, "cause": "unreadable answer"}
    account_id = str(limits["result"].get("accountId") or "")
    usage = answers.get(4)
    usage_result = usage.get("result") if isinstance(usage, dict) else None
    return {"ok": True, "limits_line": line, "account_id": account_id,
            "usage": account_usage(usage_result, stamp, account_id) if isinstance(usage_result, dict) else None}


# ---------------------------------------------------------------------------
# The poll and its state
# ---------------------------------------------------------------------------


def _state_path(data_root: Path) -> Path:
    return Path(data_root) / USAGE_DIR / POLL_FILE


def _read_state(data_root: Path) -> dict[str, Any]:
    try:
        got = json.loads(_state_path(data_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        got = {}
    return got if isinstance(got, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    file_safety.atomic_write(path, json.dumps(value, ensure_ascii=False, indent=1))


def interval_s(values: dict[str, Any] | None = None) -> int:
    values = values if values is not None else app_settings.defaults()
    try:
        hours = int(values.get("usage.codex_poll_hours", 6))
    except (TypeError, ValueError):
        hours = 6
    return max(1, hours) * 3600


def enabled(values: dict[str, Any]) -> bool:
    return bool(values.get("usage.codex_poll", True))


def poll(data_root: Path, values: dict[str, Any] | None = None, now: float | None = None,
         reader: Any = read) -> dict[str, Any]:
    """One attempt, under the in-flight lock (a second caller meanwhile gets
    ``{skipped: "running"}``). Writes the reading, the account file and the
    state; returns the state with ``written`` (a limits line went in)."""
    if not _inflight.acquire(blocking=False):
        return {"skipped": "running"}
    try:
        values = values if values is not None else app_settings.load(Path(data_root))
        at = now if now is not None else hookshared.now_epoch()
        stamp = hookshared.epoch_local(at)
        state = _read_state(data_root)
        got = reader(at=stamp) if reader is read else reader()
        state["last_attempt"] = stamp
        written = False
        if got.get("ok"):
            written = hookshared.limits_append(data_root, got["limits_line"], now=at)
            if got.get("usage"):
                _write_json(Path(data_root) / USAGE_DIR / ACCOUNT_FILE, got["usage"])
            nxt = at + interval_s(values)
            state.update({"last_success": stamp, "cause": "", "failures": 0,
                          "next_attempt": hookshared.epoch_local(nxt), "next_epoch": round(nxt, 3)})
        else:
            cause = str(got.get("cause") or "unreadable answer")
            # Another cause is another trouble: its backoff starts over.
            n = int(state.get("failures") or 0) + 1 if cause == state.get("cause") else 1
            wait = min(BACKOFF_S[min(n, len(BACKOFF_S)) - 1], interval_s(values))
            state.update({"cause": cause, "failures": n, "next_attempt": hookshared.epoch_local(at + wait),
                          "next_epoch": round(at + wait, 3)})
            if cause not in _logged_causes:
                _logged_causes.add(cause)
                log.warning("codex limits not read: %s (next try in %d min)", cause, wait // 60)
        _write_json(_state_path(data_root), state)
        return {**state, "written": written}
    finally:
        _inflight.release()


def state(data_root: Path, values: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the page needs beside the readings: ``{found, exe, home,
    enabled, every_hours, last_attempt, last_success, next_attempt, cause,
    failures}``."""
    values = values if values is not None else app_settings.load(Path(data_root))
    st = _read_state(data_root)
    return {**detect(), "enabled": enabled(values), "every_hours": interval_s(values) // 3600,
            "last_attempt": str(st.get("last_attempt") or ""), "last_success": str(st.get("last_success") or ""),
            "next_attempt": str(st.get("next_attempt") or ""), "cause": str(st.get("cause") or ""),
            "failures": int(st.get("failures") or 0)}


def due(data_root: Path, values: dict[str, Any], now: float | None = None) -> bool:
    """Whether the scheduled poll should run now: on, Codex found, and the
    state's ``next_attempt`` passed (or none yet)."""
    if not enabled(values) or not detect()["found"]:
        return False
    st = _read_state(data_root)
    # Epoch seconds on both sides: in the hour the clocks go back a local
    # time names two moments. ``next_epoch`` is the moment itself; a state
    # written before it has the local time only.
    nxt = st.get("next_epoch")
    if isinstance(nxt, bool) or not isinstance(nxt, (int, float)):
        nxt = hookshared.epoch_of(st.get("next_attempt"))
    if nxt is None:
        return True
    return nxt <= (now if now is not None else hookshared.now_epoch())


def newest_reading_age_s(data_root: Path, now: float | None = None) -> float | None:
    """Seconds since the newest Codex limits line; None without one."""
    from . import usagelib
    rows, _bad = usagelib.limit_history(Path(data_root))
    lines = rows.get("codex") or []
    if not lines:
        return None
    read_at = hookshared.epoch_of(lines[-1].get("at"))
    if read_at is None:
        return None
    return max(0.0, (now if now is not None else hookshared.now_epoch()) - read_at)


def refresh_wanted(data_root: Path, now: float | None = None) -> bool:
    """The page's ask: a reading now when the newest is older than the
    page's own stale threshold, or there is none."""
    from . import usagelib
    age = newest_reading_age_s(data_root, now)
    return age is None or age > usagelib.STALE_MIN * 60


class Poller:
    """The served app's scheduled poll: a daemon thread that wakes every
    minute, reads the settings and polls when due."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = Path(data_root)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_wall: float | None = None
        self._not_before = 0.0
        self._settle_until = 0.0

    def _settled(self, wall: float) -> bool:
        """False for a while after the wall clock jumped between two wakes:
        the machine slept, the poll is overdue, and the network is not up yet."""
        if self._last_wall is not None and wall - self._last_wall > WAKE_S * 3:
            self._settle_until = wall + SETTLE_S
        self._last_wall = wall
        return wall >= self._settle_until

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="codex-limits", daemon=True)
            self._thread.start()

    def stop(self, wait: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=wait)

    def _run(self) -> None:
        # The first look comes a few seconds after the start, not at it.
        if self._stop.wait(5):
            return
        while not self._stop.is_set():
            self.tick()
            if self._stop.wait(WAKE_S):
                return

    def tick(self) -> bool:
        """One wake: poll when settled and due; whether it polled. Never raises."""
        try:
            values = app_settings.load(self.data_root)
            wall = hookshared.now_epoch()
            if self._settled(wall) and wall >= self._not_before and due(self.data_root, values):
                poll(self.data_root, values)
                return True
        except Exception as exc:  # noqa: BLE001 — the poll must never end the thread
            # Its state may not have been written (a file held open): no new try each minute.
            self._not_before = hookshared.now_epoch() + BACKOFF_S[0]
            log.warning("codex limits poll failed: %s", exc)
        return False


__all__ = ["Poller", "detect", "due", "limits_line", "poll", "read", "refresh_wanted", "state"]
