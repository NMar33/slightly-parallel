#!/usr/bin/env python3
"""Slightly Parallel capture core — the one writer of chat turns.

Tool adapters (Claude Code hooks, the OpenCode plugin, the Codex notify
script) all funnel through here. A turn is captured in one of two shapes:

- two-phase: ``open_turn`` when the user's message arrives (verbatim),
  ``complete_turn`` when the assistant's final answer is known;
- one-shot:  ``full_turn`` for tools that only report at end of turn.

Writes per turn: a multiline entry in the agent's ``chat.md`` (the ground
truth the dashboard derives sessions from) and a refreshed ``meta.json``.
Also computes the operator signals (standup due, decision hint, contract
refresh) from ``settings.json`` at the data root; adapters that can inject
context surface them to the model.

Standard library only — must run anywhere Python 3.11+ exists.
"""

from __future__ import annotations

import csv
import functools
import hashlib
import json
import os
import subprocess
import re
import tempfile
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover — not a POSIX platform
    fcntl = None  # type: ignore[assignment]
try:
    import msvcrt  # Windows: the same advisory lock, on the first byte
except ImportError:  # pragma: no cover
    msvcrt = None  # type: ignore[assignment]

# The tools send and read UTF-8 (JSON on stdin and stdout). Windows would
# use its own code page here: a Cyrillic prompt was stored garbled and the
# "·" in a notice broke the reader. Every hook imports this module first.
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass


def record_failure(data_root: str | Path, project: str, agent: str, tool: str, error: str) -> None:
    """Keep a hook's failure where the dashboard reads it (backend
    capturewatch.py): <data root>/.capture/errors.jsonl, one line each, the
    older half dropped past 256 KB. Never raises: this runs because
    something already went wrong."""
    try:
        path = Path(data_root) / ".capture" / "errors.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "project": project,
                                 "agent_id": agent, "tool": tool, "error": error[:500]}, ensure_ascii=False) + "\n")
        if path.stat().st_size > 256 * 1024:
            # At the newline only: an error text may hold U+2028 unescaped.
            lines = [ln for ln in path.read_text(encoding="utf-8", errors="replace").split("\n") if ln]
            path.write_text("\n".join(lines[len(lines) // 2:]) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


@functools.lru_cache(maxsize=None)
def _backend_module(name: str):
    """A standard-library-only module of the backend, loaded by path: the
    hook cannot import the backend package, and one copy of a rule is
    better than two (hookshared.py, turntimes.py)."""
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "backend" / "backend" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"sp_{name}", path)
    assert spec is not None and spec.loader is not None, path
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# What the hooks and the server both need: who is speaking, the skills in a
# transcript, the end of a growing file (backend/backend/hookshared.py).
shared = _backend_module("hookshared")
# os.replace, patient on Windows, where a file open elsewhere refuses a moment.
_replace = shared.replace_file


META_LOCK = "meta.json.lock"


def _with_meta_lock(fn):
    """Read-modify-write of meta.json under the sidecar lock the backend takes
    too (routers/core.py rename, agents_extra group). Without it a rename
    landing mid-turn reverts pending_turn and the reply is dropped."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._meta_lock():
            return fn(self, *args, **kwargs)
    return wrapper

# Defaults mirror backend/backend/app_settings.py (this file cannot import
# the backend package).
_SETTING_DEFAULTS = {
    "contract_refresh_turns": 25,   # 0 disables
    "standup_enabled": True,
    "decision_hint_enabled": True,
    "files_due_enabled": True,
    "architecture_due_enabled": True,
    # Show each reply's tokens after it (recording is always on); a chat's
    # #usage-on / #usage-off outranks it (meta.json usage_show).
    "usage_show": False,
}
# The settings of the ``usage`` section the hook reads (app_settings.py too):
# warnings under a reply when a chat costs much of the 5-hour limit; a chat's
# #usage-warnings-on / #usage-warnings-off outranks it (meta.json usage_warn).
_USAGE_SETTING_DEFAULTS = {
    "warnings": True,
}

# What a turn's Agent line says when the tool never handed us the reply.
REPLY_MISSING = "(reply not in transcript)"

_DECISION_RE = re.compile(
    r"\b(decided to|decide to|chose\b|chosen\b|opting for|opted for|"
    r"went with|settled on|we will use|let's use)\b",
    re.IGNORECASE,
)

# Messages the server keeps by their tag (backend/backend/keeplib.py). The
# hook names the id the moment the message arrives, so the agent can write
# its interpretation in the same turn. ``#problem solved <id>`` is a command.
_KEEP_TAG_RE = re.compile(
    r"(?<![\w#])#(vision|rule|problem|entrypoint|skill|artifact|publish)(?:\([^)\n]{1,80}\))?(?![\w-])(?!\s+solved\b)",
    re.IGNORECASE,
)
_ANY_TAG_RE = re.compile(
    r"(?<![\w#])#(?:prompt|vision|rule|problem|entrypoint|skill|artifact|publish)(?:\([^)\n]{1,80}\))?(?![\w-])",
    re.IGNORECASE,
)
# ``#evidence`` is a command, not a kept message: nothing is stored for it.
# The notice names the task so the agent does not have to guess — the one in
# the message, else the last one named in this chat.
_EVIDENCE_RE = re.compile(r"(?<![\w#])#evidences?(?![\w-])", re.IGNORECASE)
# Every command of the contract gets a notice, so the agent never has to
# recognise a tag by itself. One shape for all of them:
# ``[slightly-parallel] #<command> — <lower case, what to do>``; a notice with no
# command of its own (the identity line, the refresh) names itself instead. The kept tags and #evidence have their own
# notices above; these are the rest: command → (skill, where to start).
# tests/test_hook_parity.py holds this table equal to the contract's
# `command:` lines.
_COMMANDS: dict[str, tuple[str, str]] = {
    "scan": ("make-a-scan", "MCP tool scan_material"),
    "page": ("keep-the-architecture-page", "MCP tool architecture_material"),
    "map": ("map-the-program", "asking the operator, then MCP tool map_material"),
    "architecture": ("update-the-architecture", "MCP tool architecture_status"),
    "task": ("write-a-task", "MCP tool write_entry, lens task, status agent"),
    # The task the chat starts on: the server puts it in doing, in the lane
    # the message names or #now's own (backend/routers/tasks_extra.py). Its
    # text is the operator's message, kept by the server: the agent titles it.
    "now": ("write-a-task", "MCP tool write_entry, lens task, status doing, title and tags only: "
            "the server keeps this message as the task's text. Write it first, before the work"),
    # #now-<column>: the message filed into that column, not started.
    **{f"now-{c}": ("write-a-task", f"MCP tool write_entry, lens task, status {s}, title and tags only: "
                    "the server keeps this message as the task's text. File it and go on: it is not "
                    "started in this chat")
       for c, s in (("todo", "todo"), ("to-do", "todo"), ("next", "next"), ("backlog", "backlog"),
                    ("review", "review"), ("parked", "parked"), ("done", "done"))},
    "now-doing": ("write-a-task", "MCP tool write_entry, lens task, status doing, title and tags only: "
                  "the server keeps this message as the task's text. Write it first, before the work"),
    "decision": ("log-a-decision", "MCP tool write_entry, lens decision, with a weight"),
    "standup": ("daily-standup", "MCP tool standup_material"),
    "prompt": ("", "nothing to write: the server keeps the message in the prompt library"),
    "help": ("sp-help", "answering with its list, as it is"),
    # The operator's verdict: the server moves the task (backend donelib.py).
    "done": ("finish-a-task", "MCP tool task_done"),
    "problem solved": ("", "MCP tool update_entry, lens problem, changes {status: \"resolved\"}"),
    # Archiving entries made by mistake: the operator asks, chooses by number
    # and confirms; the server checks both in the chat (backend undolib.py).
    "undo": ("undo-a-mistake", "MCP tool undo_find"),
    "undo-yes": ("undo-a-mistake", "MCP tool undo_apply"),
    # Is it working: the server's checks for this chat and folder (backend checkup.py).
    "sp": ("sp-checkup", "MCP tool checkup; report in the skill's shape, change nothing without a yes"),
    # Cores: the program's core elements the operator keeps in view (backend corelib.py).
    "core-new": ("keep-a-core", "MCP tool core_new with a short name, a type and the files you know; "
                 "the server saves this message as the first note"),
    "core-note": ("keep-a-core", "MCP tool cores, choose the matching core, then core_note with this message as text "
                  "and your one-line comment; if two match, ask the operator to choose by number first"),
    "core": ("keep-a-core", "MCP tool core_attach: this message, and this chat's task when it has one, to the matching "
             "core; if two match, ask the operator to choose by number first"),
    "core-off": ("keep-a-core", "MCP tool cores, choose the matching core, ask the operator to confirm its number, "
                 "then core_off"),
    # The operator silenced the message: every other tag in it is text (hookshared.command_text).
    "mute": ("", "nothing to do: #mute turned every other command in this message off; its tags are plain text"),
    # Usage: the hook answers these itself (TurnCapture.usage_answer); on
    # Claude Code a message of only these never reaches the model.
    **{k: ("", "nothing to do: the hook answered") for k in (
        "usage", "usage-on", "usage-off", "usage-warnings-on", "usage-warnings-off")},
    # The API prices the Usage page counts dollars with: a helper reads the providers' pages.
    "usage-price": ("update-usage-prices", "say in one line which pages you are going to, then a helper agent (Claude "
                    "Code: on opus; with no helpers, you) calls MCP tool usage_prices_material, then usage_prices_write"),
    # A star: the server marks it from the chat log (backend marklib.py).
    **{k: ("", "nothing to write: the server stars it") for k in (
        "important", "important-agent", "important-task", "important-message")},
}
# Built from the table, so a command is added in one place. Longest first,
# so `#important-task` is not read as `#important`; a space in a command
# ("problem solved") matches any run of spaces.
_COMMAND_RE = re.compile(
    r"(?<![\w#])#("
    + "|".join(re.escape(k).replace(r"\ ", r"\s+") for k in sorted(_COMMANDS, key=len, reverse=True))
    + r")(?![\w-])",
    re.IGNORECASE,
)

# The server's pattern for a task id (backend/backend/sessions.py), tasks only;
# tests/test_hook_parity.py holds the two equal.
_TASK_ID_RE = re.compile(r"\b(tk_[a-z0-9][a-z0-9_-]{2,40})(?:\.\d{1,3})?\b")
# ``#task {ui} …`` and ``#now {ui} …`` name the board lane in braces. The
# server's pattern (backend/backend/sessions.py TASK_CMD_RE); the parity
# test holds the two equal.
_TASK_CMD_RE = re.compile(r"(?<![\w#])#(task|now(?:-(?:to-?do|next|backlog|doing|review|parked|done))?)(?![\w-])(?:[ \t]*\{([^}\n]{1,80})\})?", re.IGNORECASE)


#: The commands the hook answers itself (format_signals, usage_answer).
_USAGE_COMMANDS = ("usage", "usage-on", "usage-off", "usage-warnings-on", "usage-warnings-off")


def _apply_usage(meta: dict, commands: list[str]) -> None:
    """#usage-on / #usage-off show the line after each reply or not;
    #usage-warnings-on / #usage-warnings-off the warnings (meta.json)."""
    for c in commands:
        if c in ("usage-on", "usage-off"):
            meta["usage_show"] = c == "usage-on"
        elif c in ("usage-warnings-on", "usage-warnings-off"):
            meta["usage_warn"] = c == "usage-warnings-on"


def usage_only(text: str) -> list[str]:
    """The usage commands of a message that holds nothing else (no other
    command, no other text): Claude Code's hook answers it without the
    model. Empty when the message says anything more."""
    said = shared.command_text(text or "")
    found = [" ".join(m.group(1).lower().split()) for m in _COMMAND_RE.finditer(said)]
    if not found or any(c not in _USAGE_COMMANDS for c in found):
        return []
    if _COMMAND_RE.sub("", said).strip():
        return []
    return list(dict.fromkeys(found))


def server_url() -> str:
    """Where the operator's own pages are: the port the server takes
    (backend/backend/config.py reads SP_PORT, 8123 by default)."""
    port = (os.environ.get("SP_PORT") or "8123").strip()
    return f"http://127.0.0.1:{port if port.isdigit() else '8123'}"


def _round_half_down(n: int, unit: int, decimals: int) -> tuple[int, int]:
    """n / unit to ``decimals`` places as (whole, tenths), half rounded down."""
    scale = 10 ** decimals
    q, rem = divmod(n * scale, unit)
    if rem * 2 > unit:
        q += 1
    return divmod(q, scale) if decimals else (q, 0)


def format_tokens(n: int) -> str:
    """A token count as the Usage page writes it: 512 · 2.4k · 108k · 4.1M ·
    41M; a value that would round up into the next step is cut instead
    (999 950 is 999k). The backend's usagelib.format_tokens is the rule;
    this copy answers when that module cannot be loaded."""
    n = max(0, int(n or 0))
    if n < 1000:
        return str(n)
    for unit, decimals, cap, suffix in ((1000, 1, 10, "k"), (1000, 0, 1000, "k"),
                                        (1_000_000, 1, 10, "M"), (1_000_000, 0, None, "M")):
        if cap is not None and n >= cap * unit:
            continue
        whole, tenth = _round_half_down(n, unit, decimals)
        if cap is not None and whole >= cap:
            # Down at the boundary: the shown value never reaches the next step.
            whole, tenth = divmod(n * 10 ** decimals // unit, 10) if decimals else (n // unit, 0)
        return f"{whole}.{tenth}{suffix}" if decimals and tenth else f"{whole}{suffix}"
    return f"{n // 1_000_000}M"  # pragma: no cover — the last step has no cap


def _usagelib():
    """The backend's usagelib (zone of the server), loaded by path; None when
    it is not there or does not load."""
    try:
        return _backend_module("usagelib")
    except Exception:  # noqa: BLE001 — a missing module is an answer
        return None


def _task_lane(data_root: Path, project: str, user_text: str) -> dict | None:
    """The lane the operator's #task / #now names in braces, and whether the
    board has it: ``{"named": "ui", "lane": "UI" or None, "lanes": [...]}``;
    None when the message names no lane (the server picks the default)."""
    hits = list(_TASK_CMD_RE.finditer(user_text or ""))
    named = " ".join((hits[-1].group(2) or "").split()) if hits else ""
    if not named:
        return None
    lanes: dict[str, str] = {}
    for r in _read_csv(data_root / "tasks.csv"):
        if r.get("project") != project or (r.get("archived_at") or "").strip():
            continue
        name = (r.get("lane") or r.get("assignee") or "").strip()
        if name:
            lanes.setdefault(name.lower(), name)
    return {"named": named, "lane": lanes.get(named.lower()), "lanes": sorted(lanes.values(), key=str.lower)}


def _task_title(data_root: Path, task_id: str) -> str:
    """The task's title from the ledger; '' when it cannot be read."""
    try:
        with open(data_root / "tasks.csv", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("id") == task_id:
                    return str(row.get("title") or "").strip()
    except (OSError, csv.Error):
        pass
    return ""


# kind → (id prefix, API route); mirrors backend/backend/entities.py.
_KEEP_ROUTES = {
    "vision": ("vs_", "visions"),
    "rule": ("rl_", "rules"),
    "problem": ("pb_", "problems"),
    "entrypoint": ("ep_", "entrypoints"),
    "skill": ("sk_", "skills"),
    "artifact": ("ar_", "artifacts"),
    "publish": ("pu_", "publish"),
}


def keep_id(kind: str, project: str, agent_id: str, turn: int) -> str:
    """The same hash as backend keeplib.keep_id — a test holds them equal."""
    seed = f"{kind}|{project}|{agent_id}|{turn}"
    return _KEEP_ROUTES[kind][0] + hashlib.sha256(seed.encode()).hexdigest()[:8]


# The evidence request the board staples under a task's text. The server
# strips it before deciding whether a tagged message says anything
# (backend/backend/sessions.py:_BOILERPLATE_RE); the hook must agree, or it
# hands out an id the server never adopts.
_BOILERPLATE_RE = re.compile(
    r"^Evidence required — collect it as you work.*", re.MULTILINE | re.DOTALL
)


def _kept(text: str, project: str, agent_id: str, turn: int) -> list[dict]:
    """The kept entries a message makes; none when the tag is all it says."""
    kinds: list[str] = []
    for m in _KEEP_TAG_RE.finditer(text or ""):
        kind = m.group(1).lower()
        if kind not in kinds:
            kinds.append(kind)
    body = _BOILERPLATE_RE.sub("", _ANY_TAG_RE.sub("", text or ""))
    if not kinds or not body.strip():
        return []
    return [
        {"kind": k, "id": keep_id(k, project, agent_id, turn), "route": _KEEP_ROUTES[k][1]}
        for k in kinds
    ]


def now_iso() -> str:
    # SP_NOW fixes the clock for tests (hookshared.now_dt).
    return shared.now_dt().strftime("%Y-%m-%dT%H:%M:%S")


# One escape for the chat format, shared with the server's import (hookshared.py).
escape_content = shared.escape_content


def _load_settings(data_root: Path) -> dict:
    values = dict(_SETTING_DEFAULTS)
    try:
        stored = json.loads(
            (data_root / "settings.json").read_text(encoding="utf-8")
        ).get("agent", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return values
    for key, default in _SETTING_DEFAULTS.items():
        v = stored.get(key, default)
        if isinstance(default, bool):
            values[key] = bool(v) if isinstance(v, bool) else default
        else:
            values[key] = (
                v
                if isinstance(v, int) and not isinstance(v, bool) and v >= 0
                else default
            )
    return values


def _usage_setting(data_root: Path, key: str):
    """A setting of the ``usage`` section (``_USAGE_SETTING_DEFAULTS``)."""
    default = _USAGE_SETTING_DEFAULTS[key]
    try:
        stored = json.loads((data_root / "settings.json").read_text(encoding="utf-8")).get("usage", {})
        v = stored.get(key, default)
    except (OSError, json.JSONDecodeError, AttributeError):
        return default
    return v if isinstance(v, type(default)) else default


def _atomic_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        _replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class TurnCapture:
    """Capture state for one agent in one project."""

    def __init__(self, data_root: str | Path, project: str, agent_name: str):
        self.data_root = Path(data_root).expanduser()
        self.project = project
        self.agent_name = agent_name
        self.folder = (
            self.data_root / "projects" / project / "chats" / agent_name
        )
        self.chat_path = self.folder / "chat.md"
        self.meta_path = self.folder / "meta.json"
        # Set by record_usage: the usage of the last call was not kept (the
        # caller then keeps its read positions, so the next one reads again).
        self.usage_failed = False

    def _lost(self, what: str, exc: BaseException) -> None:
        """A part of the turn not kept: the turn goes on, and the failure
        lands where the dashboard reads hook errors."""
        record_failure(self.data_root, self.project, self.agent_name, "capture",
                       f"{what}: {type(exc).__name__}: {exc}")

    # -- meta ---------------------------------------------------------------

    @contextmanager
    def _meta_lock(self, timeout_s: float = 5.0):
        """The lock is advisory and must never hang the session it observes:
        after ``timeout_s`` the write goes ahead without it."""
        if (fcntl is None and msvcrt is None) or not self.folder.is_dir():
            # Nothing to race over until the first turn has made the folder;
            # a note on a session that never wrote must not create one.
            yield
            return
        fh = open(self.folder / META_LOCK, "a", encoding="utf-8")
        held = False
        deadline = time.monotonic() + timeout_s
        try:
            while True:
                try:
                    if fcntl is not None:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    else:
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # pyright: ignore[reportAttributeAccessIssue] — Windows only
                    held = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.01)
            yield
        finally:
            if held:
                try:
                    if fcntl is not None:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    else:
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # pyright: ignore[reportAttributeAccessIssue] — Windows only
                except OSError:
                    pass
            fh.close()

    def _load_meta(self) -> dict:
        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                meta = {}
        except (OSError, json.JSONDecodeError):
            meta = {}
        meta.setdefault("agent_id", self.agent_name)
        meta.setdefault("agent_name", self.agent_name)
        meta.setdefault("project", self.project)
        meta.setdefault("created_date", _yymm_dd(datetime.now()))
        meta.setdefault("message_count", 0)
        meta.setdefault("l1_headline", "")
        meta.setdefault("schema_version", 2)
        meta.setdefault("capture", "hooks")
        return meta

    # -- chat.md ------------------------------------------------------------

    def _append(self, text: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        fresh = not self.chat_path.exists()
        with open(self.chat_path, "a", encoding="utf-8") as fh:
            if fresh:
                fh.write(
                    f"# Chat log — {self.agent_name}\n"
                    f"*Started {now_iso()}. Verbatim captured turns.*\n\n---\n"
                )
            fh.write(text)

    # -- public API ---------------------------------------------------------

    @_with_meta_lock
    def open_turn(self, user_text: str, *, quiet: bool = False) -> dict:
        """Record the user's message; the answer arrives via complete_turn.

        Returns the signals dict so context-capable adapters can surface it.
        ``quiet``: a turn the hook answers itself (#usage on Claude Code):
        the model never sees it, so nothing that is told once (the standup,
        a scan's reminders, the commits with no task) is spent on it.
        """
        # A lone surrogate (half of an emoji pasted from a terminal) is no
        # UTF-8: meta.json and chat.md both refused it, and the turn was lost.
        user_text = (user_text or "").encode("utf-8", "replace").decode("utf-8")
        meta = self._load_meta()
        # The same message delivered twice while the previous turn is still
        # unanswered (interrupt + resend, or a retried hook event) is one
        # turn, not two — answered before any ledger is read for it.
        text_key = user_text.strip()
        if (
            meta.get("pending_turn") is not None
            and meta.get("pending_user_text") == text_key
        ):
            return {
                "turn_number": int(meta["pending_turn"]),
                "standup_due": False,
                "decision_hint": None,
                "contract_refresh_due": False,
                "files_due": None,
                "architecture_due": None,
                "kept": [],
                "identity": None,
            }
        # A #usage answered while the turn before was still open is written
        # now, after it (answer_usage).
        self._flush_deferred(meta)
        settings = _load_settings(self.data_root)
        # A helper chat (a codex exec, a claude -p another chat started): its
        # messages are recorded, and nothing in them acts — no command, no
        # kept entry, no notice that asks for work (the standup, a scan's
        # reminders). Its prompt was written by an agent, not the operator.
        helper = bool(meta.get("helper"))
        if quiet or helper:
            settings = {**settings, "standup_enabled": False, "decision_hint_enabled": False,
                        "contract_refresh_turns": 0, "files_due_enabled": False, "architecture_due_enabled": False}

        # Once per agent per day, on its first message — a new chat included:
        # the standup is the project's, so the first agent to show up is told.
        today = now_iso()[:10]
        standup_due = None
        if settings["standup_enabled"] and meta.get("standup_asked") != today:
            standup_due = _standup_owed(self.data_root, self.project)
            meta["standup_asked"] = today
        hint = (
            _DECISION_RE.search(user_text or "")
            if settings["decision_hint_enabled"]
            else None
        )
        turn = int(meta.get("message_count", 0)) + 1
        step = settings["contract_refresh_turns"]
        refresh_due = step > 0 and turn % step == 0
        # Both notices hang off the latest scan: scans.csv is read once.
        scans = (
            _read_csv(self.data_root / "scans.csv")
            if settings["files_due_enabled"] or settings["architecture_due_enabled"]
            else []
        )
        files_due = (
            _scan_without_files(self.data_root, self.project, meta, scans)
            if settings["files_due_enabled"]
            else None
        )
        architecture_due = (
            _scan_without_entry(
                self.data_root, self.project, meta,
                ledger="architecture.csv", notified_key="architecture_notified", scans=scans,
            )
            if settings["architecture_due_enabled"]
            else None
        )

        started = now_iso()
        self._append(
            f"\n## Turn {turn} · {started}\n"
            f"**User**: {escape_content(user_text.rstrip())}\n"
        )

        named = _TASK_ID_RE.findall(user_text or "")
        if named:
            meta["last_task"] = named[-1]
        # The message as the commands read it: a ###command silences the
        # other tags (hookshared.command_text, the server reads the same).
        said = "" if helper else shared.command_text(user_text or "")
        evidence_for = None
        if _EVIDENCE_RE.search(said):
            tid = named[0] if named else str(meta.get("last_task") or "")
            evidence_for = {"id": tid, "title": _task_title(self.data_root, tid) if tid else ""}

        # Commits of the last turn that said no task: told once, here.
        unsigned = None if quiet or helper else meta.pop("unsigned_commits", None)
        unsigned_sure = False if quiet or helper else bool(meta.pop("unsigned_sure", False))
        # #usage-on / #usage-off: this chat shows each reply's tokens, or not.
        commands = list(dict.fromkeys(" ".join(m.group(1).lower().split()) for m in _COMMAND_RE.finditer(said)))
        usage_cmds = [c for c in commands if c in _USAGE_COMMANDS]
        _apply_usage(meta, usage_cmds)
        # The identity line goes to the model once, on the first turn it
        # sees: a chat whose first message the hook answered itself (#usage)
        # would otherwise never show it, and AGENTS.md reads that as
        # "capture is not active".
        tell_identity = (not quiet and not meta.get("identity_told")) or refresh_due
        if tell_identity:
            meta["identity_told"] = True
        meta["message_count"] = turn
        meta["last_active"] = now_iso()
        meta["pending_turn"] = turn
        meta["pending_user_text"] = text_key
        meta["pending_started"] = started
        # When each turn began (epoch, UTC): the tokens of an interrupted turn,
        # read at a later Stop, go to the turn whose window holds them, and
        # never to one the hook answered itself (quiet).
        self._note_turn(meta, turn, shared.now_epoch(), quiet)
        if files_due:
            # One notice per scan per agent — the response warning and the
            # contract carry the rest; nagging every turn would be noise.
            notified = list(meta.get("files_notified") or [])
            notified.append(files_due)
            meta["files_notified"] = notified[-20:]
        if architecture_due:
            notified = list(meta.get("architecture_notified") or [])
            notified.append(architecture_due)
            meta["architecture_notified"] = notified[-20:]
        _atomic_write_json(self.meta_path, meta)

        return {
            "turn_number": turn,
            "standup_due": standup_due,
            "decision_hint": hint.group(0) if hint else None,
            "contract_refresh_due": refresh_due,
            "files_due": files_due,
            "architecture_due": architecture_due,
            "evidence_for": evidence_for,
            "unsigned_commits": {"commits": unsigned, "sure": unsigned_sure} if unsigned else None,
            "commands": commands,
            # The hook's own answer to #usage, #usage-on and #usage-off.
            "usage_answer": self.usage_answer(usage_cmds, str(meta.get("tool") or "")) if usage_cmds else None,
            # #map costs a helper run: its notice asks the operator, naming
            # the model Settings give, the way the standup's does.
            "map_model": _map_model(self.data_root) if "map" in commands else None,
            # #standup by hand asks the same way. Each tool names models and
            # starts helpers its own way: the notice picks this tool's.
            "helper_models": _helper_models(self.data_root) if (standup_due or {"map", "standup"} & set(commands)) else None,
            # #task {lane} / #now {lane}: the server refuses a lane the board
            # does not have; the notice says so first, so the agent asks.
            "task_lane": _task_lane(self.data_root, self.project, said)
            if any(c == "task" or c.startswith("now") for c in commands) else None,
            "kept": [
                # An artifact is a folder the agent writes itself; the notice
                # names where, so the agent never guesses the data root.
                {**k, "folder": str(self.data_root / "projects" / self.project / "artifacts")}
                if k["kind"] == "artifact" else k
                for k in _kept(said, self.project, self.agent_name, turn)
            ],
            # Identity + clock on the first turn and every refresh: entries
            # posted with this agent_id and time line up with the captured
            # chat, which is what links a checkpoint to its conversation.
            "identity": (
                {"agent_id": self.agent_name, "project": self.project,
                 "date": _yymm_dd(datetime.now()),
                 "time": datetime.now().strftime("%H:%M")}
                if tell_identity else None
            ),
            # The cores the operator tracks right now: the agent may write a
            # one-line note when work it finishes changes one (corelib.py).
            "cores_tracking": shared.tracked_cores(self.data_root, self.project)
            if tell_identity else None,
        }

    def complete_turn(self, agent_text: str, *, close_if_missing: bool = False,
                      transcript: str | None = None, times: dict | None = None,
                      points: list | None = None, touched: list[str] | None = None,
                      committed: bool | None = None, commit_calls: list | None = None,
                      turn_started: str | None = None, continuation: bool = False) -> None:
        """Attach the assistant's final answer to the pending turn.

        Without a pending turn (the prompt event was skipped or lost) the
        answer is dropped — a phantom user-less turn is worse than a gap.
        Except with ``continuation``: the tool woke the agent itself (a
        helper's report, a background task's notice; no prompt event comes
        for those) and the reply goes on the operator's last turn, after
        the answer already there. A whole run of autonomous work — three
        hours of helpers and commits — used to leave only the agent's first
        reply in chat.md; the report at the end was dropped.
        With ``close_if_missing`` an empty answer still closes the turn,
        marked as a gap: the reply was not in the transcript, and the next
        turn must not inherit whatever is. ``transcript`` — Claude Code's or
        Codex's session file — times the answer and its helpers; a tool with
        no such file hands ``times`` over itself: {"points": [epoch ms],
        "helpers": [[epoch ms], …]} (see _stamp_time). ``points`` — the
        transcript's own activity times, from an adapter that has read
        them already: the file is then not read again. ``touched`` — the
        files this turn's tools changed, by path, from the transcript: the
        work stamp carries them, so a scan knows what moved even where git
        does not. ``commit_calls`` — the turn's shell calls that may make a
        commit, [start, end] in local time, from a tool that can tell (None
        when it cannot): the server gives a commit several chats saw to the
        one whose call was running when it was made. ``turn_started`` — when
        the turn really began, from a tool that reports the turn only at its
        end (Codex): its stamp then carries the true window.
        """
        closed = self._close_turn(agent_text, close_if_missing=close_if_missing, continuation=continuation)
        if closed is None:
            return
        # The stamps read a transcript and ask git — seconds, on a long chat
        # in a large repository. Outside the meta lock: the dashboard's
        # rename waits on it, and gives up after five seconds.
        turn, started, ended, cwd = closed
        self._stamp_time(turn, started, ended, transcript, times, points)
        commits = self._stamp_work(turn, cwd, touched, started, commit_calls, turn_started)
        # A tool that tells (Claude Code) said whether this turn ran a git
        # commit; without that word every new commit is checked, and the
        # notice says "if you made it".
        if commits and committed is not False:
            self._note_unsigned(cwd, commits, sure=committed is True)

    def _note_unsigned(self, cwd: str, commits: list[str], *, sure: bool) -> None:
        """The turn's commits that say no task (no ``Task:`` line) and no
        other agent: kept in meta, for one notice on the next turn."""
        try:
            raw = _git(cwd, "log", "--no-walk=unsorted",
                       "--format=%H%x1f%(trailers:key=Task,valueonly,separator=%x2C)%x1f%(trailers:key=Agent,valueonly,separator=%x2C)%x1f%s",
                       *commits[-10:])
        except Exception as exc:  # noqa: BLE001 — capture must never break the tool
            self._lost("commit lines not read", exc)
            return
        unsigned = []
        for line in (raw or "").splitlines():
            parts = line.split("\x1f")
            if len(parts) < 4:
                continue
            sha, task, agent, subject = parts[0], parts[1], parts[2].strip(), parts[3]
            if "tk_" in task or (agent and agent != self.agent_name):
                continue
            unsigned.append({"sha": sha[:7], "subject": subject[:80]})
        if unsigned:
            self._keep_unsigned(unsigned, sure)

    @_with_meta_lock
    def _keep_unsigned(self, unsigned: list[dict], sure: bool) -> None:
        meta = self._load_meta()
        kept = [u for u in (meta.get("unsigned_commits") or []) if isinstance(u, dict)]
        seen = {u.get("sha") for u in kept}
        kept += [u for u in unsigned if u["sha"] not in seen]
        meta["unsigned_commits"] = kept[-10:]
        meta["unsigned_sure"] = bool(meta.get("unsigned_sure")) or sure
        _atomic_write_json(self.meta_path, meta)

    @_with_meta_lock
    def _close_turn(self, agent_text: str, *, close_if_missing: bool,
                    continuation: bool = False) -> tuple[int, str | None, str, str] | None:
        """The answer into chat.md and the turn out of meta.json, under the
        lock. Answers what the stamps need, or None when nothing closed."""
        if not agent_text.strip():
            if not close_if_missing:
                return None
            agent_text = REPLY_MISSING
        meta = self._load_meta()
        turn = meta.pop("pending_turn", None)
        if turn is None:
            return self._continue_turn(agent_text, meta) if continuation and agent_text != REPLY_MISSING else None
        meta.pop("pending_user_text", None)
        started = meta.pop("pending_started", None)
        self._append(f"**Agent**: {escape_content(agent_text.rstrip())}\n")
        self._flush_deferred(meta)
        ended = now_iso()
        meta["last_active"] = ended
        _atomic_write_json(self.meta_path, meta)
        return int(turn), started, ended, str(meta.get("cwd") or "")

    def _continue_turn(self, agent_text: str, meta: dict) -> tuple[int, str | None, str, str] | None:
        """The reply after the tool woke the agent (no prompt, no pending
        turn): appended to the last turn's answer in chat.md, once per text
        (a Stop that comes again for the same reply adds nothing)."""
        turn = int(meta.get("message_count") or 0)
        if turn <= 0 or not self.chat_path.exists():
            return None
        fp = hashlib.sha256(agent_text.strip().encode("utf-8", "replace")).hexdigest()[:16]
        if meta.get("continued_fp") == fp:
            return None
        started = str(meta.get("last_active") or "") or None
        self._append(f"\n{escape_content(agent_text.rstrip())}\n")
        ended = now_iso()
        meta["continued_fp"] = fp
        meta["last_active"] = ended
        _atomic_write_json(self.meta_path, meta)
        return turn, started, ended, str(meta.get("cwd") or "")

    @_with_meta_lock
    def record_skills(self, uses: list[dict]) -> None:
        """Append the skills that ran in the pending turn to ``skills.jsonl``."""
        if not uses:
            return
        meta = self._load_meta()
        turn = int(meta.get("pending_turn") or meta.get("message_count") or 0)
        path = self.folder / "skills.jsonl"
        # A retried Stop event hands us the same transcript again; a use is
        # one (time, skill) pair however many times the tool reports it. A
        # repeat is of the latest uses, so the end of the file is enough.
        known: set[tuple[str, str]] = set()
        for line in shared.tail_lines(path):
            try:
                rec = json.loads(line)
                known.add((str(rec.get("at") or ""), str(rec.get("skill") or "")))
            except (ValueError, AttributeError):
                continue
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                for u in uses:
                    at = str(u.get("at") or now_iso())
                    if (at, str(u["skill"])) in known:
                        continue
                    known.add((at, str(u["skill"])))
                    fh.write(json.dumps({
                        "turn": turn, "at": at, "skill": u["skill"], "how": u.get("how") or "auto",
                    }) + "\n")
        except OSError as exc:
            self._lost("skill uses not kept", exc)

    # -- work: what the turn changed, stamped from git ----------------------

    def _stamp_time(self, turn: int, started: str | None, ended: str,
                    transcript: str | None = None, times: dict | None = None,
                    points: list | None = None) -> None:
        """Append the turn's start and end to ``turns.jsonl`` — and, given the
        transcript, what the backend's turntimes.measure reads from it: the
        busy stretches of the agent and its helpers since the previous
        answer, the helpers' own seconds, the agent's working seconds in the
        turn. Never raises; a failed measure leaves the start and end."""
        line: dict = {"turn": turn, "start": started or "", "end": ended, "source": "hook"}
        if (transcript or times) and started:
            try:
                tt = _turntimes()
                since = self._last_end()
                window = (datetime.fromisoformat(started), datetime.fromisoformat(ended),
                          datetime.fromisoformat(since) if since else None)
                if transcript:
                    line.update(tt.measure(Path(transcript), *window, main=points))
                else:
                    ms = lambda xs: [datetime.fromtimestamp(float(x) / 1000) for x in xs or [] if x]  # noqa: E731
                    line.update(tt.measure_points(
                        ms(times.get("points")), [ms(h) for h in times.get("helpers") or []], *window))
            except Exception as exc:  # noqa: BLE001 — timing must never cost the turn
                self._lost("turn timing not measured", exc)
        try:
            # Under the lock the server's backfill rewrites the file with.
            shared.append_locked(self.folder / "turns.jsonl", json.dumps(line) + "\n")
        except OSError as exc:
            self._lost("turn times not kept", exc)

    def _last_end(self) -> str:
        """The previous answer's end, from the end of turns.jsonl ("" if none)."""
        return str(shared.last_json(self.folder / "turns.jsonl", "end") or "")

    def _stamp_work(self, turn: int, cwd: str, touched: list[str] | None = None,
                    started: str | None = None, commit_calls: list | None = None,
                    turn_started: str | None = None) -> list[str]:
        """Append one line to ``work.jsonl``: HEAD, the commits since the
        previous stamp, the uncommitted change in the working tree, and the
        files the turn's tools touched. Without git the line still goes in
        when the turn touched something: ``head`` empty, ``touched`` filled.
        Without git the folder itself is walked for files changed since the
        previous stamp (or the turn's start): ``changed`` catches what no
        tool call names — a shell command, a helper, another tool's agent.

        Two git calls and a few bytes, so the dashboard can say what a
        turn changed without guessing from the clock: commits are this
        turn's by ancestry (the previous stamp's HEAD to this one), and
        edits that were never committed are visible at all. Never raises
        and never delays the turn: no git, no repo, no cwd — no line.
        """
        try:
            first = not self._last_stamp_head()
            stamp = work_stamp(cwd, self._last_stamp_head() or str(self._load_meta().get("base_head") or ""),
                               since=(started or "") if first else "")
        except Exception as exc:  # noqa: BLE001 — capture must never break the tool
            self._lost("git stamp failed", exc)
            stamp = None
        files = _relative_to(cwd, touched or [])
        if stamp is None:
            changed, capped = [], False
            if cwd and os.path.isdir(cwd):
                since = _epoch(self._last_stamp_at()) or _epoch(started)
                if since:
                    try:
                        changed, capped = changed_since(cwd, since)
                    except Exception as exc:  # noqa: BLE001 — capture must never break the tool
                        self._lost("changed files not found", exc)
                        changed, capped = [], False
            elif not files:
                return []
            stamp = {"head": "", "commits": [], "dirty": None, "changed": changed}
            if capped:
                stamp["changed_capped"] = True
        stamp = {"turn": turn, "at": now_iso(), **stamp, "touched": files}
        # The turn's window and its commit calls: which chat made a commit
        # several chats saw (backend gitwork.owns_commit).
        if turn_started or started:
            stamp["started"] = str(turn_started or started)
        if commit_calls is not None:
            stamp["commit_calls"] = [[str(a), str(b)] for a, b in commit_calls]
        try:
            with open(self.folder / "work.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(stamp, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._lost("work stamp not kept", exc)
        return [str(c) for c in stamp.get("commits") or []]

    def _last_stamp_at(self) -> str:
        """The previous stamp's time, from the end of work.jsonl ("" if none)."""
        return str(shared.last_json(self.folder / "work.jsonl", "at") or "")

    def _last_stamp_head(self) -> str:
        """The previous stamp's HEAD, from the end of work.jsonl ("" if none)."""
        return str(shared.last_json(self.folder / "work.jsonl", "head") or "")

    @_with_meta_lock
    def note_origin(self, tool: str = "", session_id: str = "", cwd: str = "",
                    helper_kind: str = "", helper_of: str = "", helper_of_by: str = "") -> None:
        """Record where this agent runs: the tool, its full session id and
        the working directory — enough to print a resume command later.
        Written once (or when a value changes); never breaks the session.
        The directory is the one the chat started in and is kept: the tool
        reports the agent's current one, which moves when it works in a
        subfolder, and a resume there meets a different set of instructions.

        ``helper_kind``: this chat is a run another program started
        (hookshared.HELPER_KINDS): ``helper``, ``helper_kind`` and
        ``helper_of`` (the chat that started it, when known; ``helper_of_by``
        says how it was found) are written. A chat once a helper stays one;
        a parent found later fills an empty ``helper_of``."""
        updates = {}
        meta = self._load_meta()
        if helper_kind:
            parent = shared.helper_of_clean(self.agent_name, helper_of)
            if not meta.get("helper"):
                updates.update({"helper": True, "helper_kind": helper_kind, "helper_of": parent})
                if parent and helper_of_by:
                    updates["helper_of_by"] = helper_of_by
            elif parent and not meta.get("helper_of"):
                updates["helper_of"] = parent
                if helper_of_by:
                    updates["helper_of_by"] = helper_of_by
        if meta.get("cwd"):
            cwd = ""
        elif cwd and not meta.get("base_head"):
            # HEAD before the chat's first turn: the first stamp counts its
            # commits from here. Without it a commit made in the first turn
            # (#now build it and commit) was in no turn, and #scan saw none.
            head = (_git(cwd, "rev-parse", "HEAD") or "").strip() if os.path.isdir(cwd) else ""
            if head:
                updates["base_head"] = head
        # SP_TERMINAL: the Slightly Parallel terminal this tool was started in (the
        # terminal sets it), so the page can tie the agent to its terminal.
        for key, val in (("tool", tool), ("session_ref", session_id), ("cwd", cwd),
                         ("terminal", os.environ.get("SP_TERMINAL", ""))):
            v = str(val or "").strip()
            if v and meta.get(key) != v:
                updates[key] = v
        if not updates:
            return
        meta.update(updates)
        _atomic_write_json(self.meta_path, meta)

    @_with_meta_lock
    def note_stop(self, payload_keys: list[str], *, found_text: bool,
                  transcript: tuple[str, int] | None = None) -> None:
        """Record the shape of the last Stop event: which keys the tool sent
        and whether a reply was found for the turn — diagnostics. And, with
        ``transcript`` (path, bytes read), how far into the tool's own
        transcript this Stop read: the next one reads on from there."""
        if not self.meta_path.exists():
            return  # no chat here yet — a Stop with no turn behind it leaves no trace
        try:
            meta = self._load_meta()
            meta["last_stop"] = {
                "at": now_iso(), "keys": list(payload_keys), "found_text": bool(found_text),
            }
            if transcript is not None:
                meta["transcript_pos"] = {"path": str(transcript[0]), "pos": int(transcript[1])}
            _atomic_write_json(self.meta_path, meta)
        except OSError as exc:
            self._lost("transcript position not kept", exc)

    def is_helper(self) -> bool:
        """This chat is a helper run (note_origin marked it): nothing in its
        messages acts."""
        try:
            return bool(json.loads(self.meta_path.read_text(encoding="utf-8")).get("helper"))
        except (OSError, ValueError, AttributeError):
            return False

    def transcript_pos(self, path: str) -> int:
        """Where the previous Stop stopped reading this transcript (0: read
        it from the top — a first Stop, or another file)."""
        try:
            got = json.loads(self.meta_path.read_text(encoding="utf-8")).get("transcript_pos") or {}
            return max(0, int(got.get("pos") or 0)) if got.get("path") == path else 0
        except (OSError, ValueError, AttributeError, TypeError):
            return 0

    @_with_meta_lock
    def note_chat_title(self, title: str) -> None:
        """Record the name the user gave this chat in their tool (Claude Code
        ``/rename``, ``/branch <name>``). Presentation only — ``agent_id``
        stays the key, and an operator rename in the dashboard outranks it.
        """
        title = (title or "").strip()
        if not title:
            return
        meta = self._load_meta()
        if meta.get("chat_title") == title:
            return
        meta["chat_title"] = title
        _atomic_write_json(self.meta_path, meta)

    def full_turn(self, user_text: str, agent_text: str, *, turn_started: str | None = None,
                  commit_calls: list | None = None, quiet: bool = False,
                  usage: list[dict] | None = None) -> dict:
        """One-shot capture for end-of-turn-only tools (e.g. Codex notify).

        The turn is closed even when the reply came empty (marked as a gap):
        left open, the next message wrote a second user line under it, and
        the same message again ("continue") was taken for this one.
        ``usage``: the turn's usage lines (record_usage), kept before the
        turn closes. ``quiet``: see open_turn."""
        signals = self.open_turn(user_text, quiet=quiet)
        if usage:
            # Opened at its end: every line given is this turn's.
            self.record_usage(usage, this_turn=True)
        self.complete_turn(agent_text, close_if_missing=True, turn_started=turn_started, commit_calls=commit_calls)
        return signals

    # -- usage: tokens per API message (usage.jsonl), shown on demand --------

    @staticmethod
    def _note_turn(meta: dict, turn: int, started: float, quiet: bool = False) -> None:
        """Add a turn to the history in meta.json (``turns``: [turn, started
        epoch, quiet], the last TURN_HISTORY of them)."""
        hist = [h for h in (meta.get("turns") or []) if isinstance(h, list) and len(h) >= 2]
        hist = [h for h in hist if h[0] != turn]
        hist.append([int(turn), round(float(started), 3), bool(quiet)])
        meta["turns"] = hist[-shared.TURN_HISTORY:]

    @staticmethod
    def _history(meta: dict) -> list:
        """The turn history to give usage its turns. A chat whose meta.json
        predates it has its pending turn alone; the turn before stands in
        front of the first one known (an interrupted turn's tokens go to it,
        as they always did)."""
        hist = [h for h in (meta.get("turns") or []) if isinstance(h, list) and len(h) >= 2]
        if not hist:
            pend = meta.get("pending_turn")
            start = _epoch(meta.get("pending_started"))
            if pend is not None and start:
                hist = [[int(pend), start, False]]
            elif int(meta.get("message_count") or 0) > 0:
                hist = [[int(meta["message_count"]), 0.0, False]]
        if hist and int(hist[0][0]) > 1:
            hist = [[int(hist[0][0]) - 1, 0.0, False], *hist]
        return hist

    def _flush_deferred(self, meta: dict) -> None:
        """Write the #usage exchanges answered while a turn was open, each as
        a quiet turn of its own (the caller holds the lock and saves meta)."""
        for d in meta.pop("usage_deferred", None) or []:
            if not isinstance(d, dict):
                continue
            n = int(meta.get("message_count") or 0) + 1
            self._append(f"\n## Turn {n} · {d.get('at') or now_iso()}\n"
                         f"**User**: {escape_content(str(d.get('user') or '').rstrip())}\n"
                         f"**Agent**: {escape_content(str(d.get('answer') or REPLY_MISSING).rstrip())}\n")
            meta["message_count"] = n
            self._note_turn(meta, n, float(d.get("t") or shared.now_epoch()), quiet=True)

    def answer_usage(self, user_text: str) -> str:
        """A message of only #usage commands, answered by the hook: the turn
        is recorded with the answer as the reply, and nothing else is told.
        While a turn is still open (interrupted, or the agent still working)
        no turn is opened or closed: the exchange is written after it."""
        commands = usage_only(user_text)
        tool = self._defer_usage(commands)
        if tool is None:
            answer = str(self.open_turn(user_text, quiet=True).get("usage_answer") or "")
            self.complete_turn(answer, close_if_missing=True)
            return answer
        answer = self.usage_answer(commands, tool)
        self._keep_deferred(user_text, answer)
        return answer

    @_with_meta_lock
    def _defer_usage(self, commands: list[str]) -> str | None:
        """With a turn open: apply #usage-on / #usage-off and answer the tool
        name; None when no turn is open (the exchange is a turn of its own)."""
        if not self.meta_path.exists():
            return None
        meta = self._load_meta()
        if meta.get("pending_turn") is None:
            return None
        _apply_usage(meta, commands)
        _atomic_write_json(self.meta_path, meta)
        return str(meta.get("tool") or "")

    @_with_meta_lock
    def _keep_deferred(self, user_text: str, answer: str) -> None:
        meta = self._load_meta()
        kept = [d for d in meta.get("usage_deferred") or [] if isinstance(d, dict)]
        kept.append({"user": user_text, "answer": answer, "at": now_iso(), "t": round(shared.now_epoch(), 3)})
        meta["usage_deferred"] = kept[-10:]
        if meta.get("pending_turn") is None:
            self._flush_deferred(meta)     # the turn closed meanwhile
        _atomic_write_json(self.meta_path, meta)

    def usage_answer(self, commands: list[str], tool: str = "") -> str:
        """The hook's answer to #usage, #usage-on, #usage-off,
        #usage-warnings-on and #usage-warnings-off, in order."""
        url = server_url()
        parts: list[str] = []
        name = "Codex" if tool == "codex" else "OpenCode" if tool == "opencode" else tool
        for c in commands:
            if c in ("usage-warnings-on", "usage-warnings-off") and tool not in ("", "claude-code"):
                # The warnings and the facts log are made by Claude Code's Stop hook only.
                parts.append("[slightly-parallel] Usage warnings are shown in Claude Code only. "
                             f"{name} does not show them, so this command changes nothing in this chat.")
            elif c == "usage-on":
                shows = ("each reply shows: → new tokens ↑ output tokens ↓ (cache tokens)." if tool in ("", "claude-code")
                         else "the chat viewer shows each reply: → new tokens ↑ output tokens ↓ (cache tokens). "
                              f"{name} does not show them in the terminal.")
                parts.append(
                    "[slightly-parallel] Usage is on.\n"
                    f"From now on, {shows}\n"
                    "Tokens are recorded for every reply in any case. This setting only shows them.\n"
                    "Type #usage-off to hide them. Type #usage for this chat and your plan limits.\n"
                    f"Usage page: {url}/usage")
            elif c == "usage-off":
                parts.append("[slightly-parallel] Usage is off. Tokens are still recorded. Type #usage-on to show them.")
            elif c == "usage-warnings-on":
                parts.append("[slightly-parallel] Usage warnings are on in this chat.")
            elif c == "usage-warnings-off":
                parts.append("[slightly-parallel] Usage warnings are off in this chat. Tokens are still recorded.")
            else:
                parts.append(self._usage_block(url))
        return "\n\n".join(parts)

    def _usage_block(self, url: str) -> str:
        """The #usage block, from the server's usagelib; when it cannot be
        loaded or fails, the line that says so."""
        lib = _usagelib()
        if lib is not None:
            try:
                return str(lib.usage_block(self.data_root, self.project, self.agent_name, url))
            except Exception as exc:  # noqa: BLE001 — the turn goes on without the block
                self._lost("usage block not built", exc)
        return f"[slightly-parallel] #usage — the server's module is not available; open {url}/usage."

    def usage_shown(self) -> bool:
        """Whether this chat shows each reply's tokens: its #usage-on /
        #usage-off, else the setting (agent.usage_show)."""
        try:
            own = json.loads(self.meta_path.read_text(encoding="utf-8")).get("usage_show")
        except (OSError, ValueError, AttributeError):
            own = None
        return own if isinstance(own, bool) else bool(_load_settings(self.data_root)["usage_show"])

    @_with_meta_lock
    def line_due(self, turn: int) -> bool:
        """Whether the line after this turn's reply is still to be shown: a
        Stop that comes again for the same turn (``stop_hook_active``, a
        retried event) shows it once."""
        if turn < 1 or not self.meta_path.exists():
            return False
        meta = self._load_meta()
        if meta.get("usage_line_turn") == turn:
            return False
        meta["usage_line_turn"] = turn
        _atomic_write_json(self.meta_path, meta)
        return True

    def usage_warned(self) -> bool:
        """Whether this chat shows the usage warnings: its #usage-warnings-on /
        #usage-warnings-off, else the setting (usage.warnings)."""
        try:
            own = json.loads(self.meta_path.read_text(encoding="utf-8")).get("usage_warn")
        except (OSError, ValueError, AttributeError):
            own = None
        return own if isinstance(own, bool) else bool(_usage_setting(self.data_root, "warnings"))

    @_with_meta_lock
    def usage_warning(self, turn: int) -> tuple[str, str] | None:
        """(kind, text) of the warning under this turn's reply, or None: at
        most one per reply, each shown once (backend usagewarn.py; what was
        shown is kept in meta.json ``usage_warned``). Never raises."""
        if turn < 1 or not self.meta_path.exists():
            return None
        lib = _usagelib()
        try:
            warn = _backend_module("usagewarn")
        except Exception as exc:  # noqa: BLE001
            self._lost("usage warning module not loaded", exc)
            return None
        if lib is None:
            return None
        meta = self._load_meta()
        raw = meta.get("usage_warned")
        state: dict = dict(raw) if isinstance(raw, dict) else {}
        if state.get("turn") == turn:
            return None          # a Stop again for the same turn: one warning per reply
        try:
            got = warn.due(lib, self.data_root, self.folder, turn, state)
        except Exception as exc:  # noqa: BLE001 — a warning never costs the turn
            self._lost("usage warning not built", exc)
            return None
        if got is None:
            return None
        state["turn"] = turn
        meta["usage_warned"] = state
        _atomic_write_json(self.meta_path, meta)
        return got

    def record_facts(self, turn: int, appended: dict, tools: dict, warnings: list[str],
                     effort: str = "") -> None:
        """One line per turn in ``facts.jsonl``: what was added to the chat's
        context since the last Stop, by kind (characters; images counted),
        the tool calls by name, the warnings shown, and the reasoning effort
        of the turn's last reply ("" when the log does not say). Never raises."""
        if turn < 1 or not self.folder.is_dir():
            return
        line = {"turn": int(turn), "at": now_iso(), "appended": appended, "tools": tools, "warnings": warnings,
                "effort": effort}
        try:
            with open(self.folder / "facts.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._lost("facts not kept", exc)

    def codex_read_at(self) -> float | None:
        """Up to when (epoch) the Codex session file's calls are kept; None
        before the first Stop that kept any."""
        try:
            got = json.loads(self.meta_path.read_text(encoding="utf-8")).get("codex_read_t")
        except (OSError, ValueError, AttributeError):
            return None
        return float(got) if isinstance(got, (int, float)) and not isinstance(got, bool) else None

    @_with_meta_lock
    def note_codex_read(self, lines: list[dict]) -> None:
        """Move the Codex mark to the newest call kept (after it is kept)."""
        times = [x["_t"] for x in lines if isinstance(x.get("_t"), (int, float))]
        if not times or not self.meta_path.exists():
            return
        meta = self._load_meta()
        prev = meta.get("codex_read_t")
        meta["codex_read_t"] = max(max(times), prev) if isinstance(prev, (int, float)) else max(times)
        _atomic_write_json(self.meta_path, meta)

    def record_usage(self, lines: list[dict], starts: dict | None = None,
                     *, this_turn: bool = False, compacts: list[float] | None = None,
                     whole: bool = False) -> tuple[int, list[dict]]:
        """Append the API messages read at a turn's end to ``usage.jsonl``.

        ``lines``: hookshared usage lines (``at``, ``id``, ``_t`` …); a helper's
        carry ``helper`` and ``tool_use`` (the Agent call that started it).
        ``starts``: {Agent call id: {"t": epoch, "parent": call}} seen in this
        read, kept in meta.json (``helper_turns``) so a helper's tokens go to
        the turn that started it, at whatever Stop they are read. Each line
        goes to the turn whose window holds its time (hookshared.assign_turns,
        with the history in meta.json): an interrupted turn has no Stop of
        its own. What was written more than a minute before the chat's first
        recorded prompt (``usage_from_t``) is history, not this chat's: a
        transcript read from its first byte (a resumed or branched session,
        hooks installed mid-session) holds it. ``compacts``: the times of the
        compactions read (the first line after each is marked). ``whole``:
        the log was read again from its start — the ids already kept are
        looked for in all of usage.jsonl. ``this_turn``: every line is the
        pending turn's (a tool that reports a turn only at its end).
        Answers (the turn, the lines written); ``usage_failed`` says whether
        they were kept. Never raises."""
        self.usage_failed = False
        try:
            turn, out = self._usage_turns(lines, starts or {}, this_turn, compacts or [])
            if not out:
                return turn, []
            return turn, shared.usage_append(self.folder / "usage.jsonl", out, whole=whole)
        except Exception as exc:  # noqa: BLE001 — usage must never cost the turn
            self.usage_failed = True
            self._lost("usage not kept", exc)
            return 0, []

    @_with_meta_lock
    def _usage_turns(self, lines: list[dict], starts: dict, this_turn: bool = False,
                     compacts: list[float] | None = None) -> tuple[int, list[dict]]:
        if not self.meta_path.exists():
            return 0, []      # no chat here: a Stop with no turn behind it leaves no trace
        meta = self._load_meta()
        pending = meta.get("pending_turn")
        turn = int(pending or meta.get("message_count") or 0)
        if turn < 1:
            return 0, []
        if this_turn:
            return turn, [{"turn": turn, **{k: v for k, v in ln.items() if k not in ("_t", "tool_use", "turn")}}
                          for ln in lines]
        history = self._history(meta)
        cutoff = meta.get("usage_from_t") if isinstance(meta.get("usage_from_t"), (int, float)) else None
        if cutoff is None and meta.get("usage_from"):
            cutoff = _epoch(str(meta["usage_from"])) or None     # written by an older hook, local time
        first = False
        if cutoff is None and pending is not None:
            # The chat's first prompt on record (not the pending one: an
            # interrupted first turn is this chat's too).
            begun = [h[1] for h in history if isinstance(h[1], (int, float)) and h[1] > 0]
            if begun:
                cutoff, first = float(min(begun)) - shared.HISTORY_SLACK_S, True
        got = meta.get("helper_turns")
        calls: dict[str, int] = {str(k): v for k, v in got.items() if isinstance(v, int)} if isinstance(got, dict) else {}
        before = dict(calls)
        waiting = [c for c in meta.get("usage_compacts") or [] if isinstance(c, (int, float))]
        given = sorted({*waiting, *(c for c in compacts or [] if isinstance(c, (int, float)))})
        out, left = shared.assign_turns(lines, history, calls=calls, starts=starts, compacts=given,
                                        cutoff=cutoff, default=turn)
        changed = first
        if calls != before:
            meta["helper_turns"] = dict(list(calls.items())[-shared.TURN_HISTORY:])
            changed = True
        if first:
            meta["usage_from_t"] = cutoff
        if left != waiting:
            if left:
                meta["usage_compacts"] = left[-20:]
            else:
                meta.pop("usage_compacts", None)
            changed = True
        if changed:
            _atomic_write_json(self.meta_path, meta)
        return turn, out

    def usage_line(self, turn: int) -> str:
        """The line shown after a reply: ``→ new ↑ output ↓ (cache)``, with the
        helpers' share apart. From the server's usagelib (which adds the
        event words); a sum of usage.jsonl when it cannot be loaded, by the
        server's rules: the last line of an id wins, and the leading number
        is the main agent's alone."""
        if turn < 1:
            return ""
        lib = _usagelib()
        if lib is not None:
            try:
                turns = lib.chat_turns(self.data_root, self.project, self.agent_name)
                tu = turns.get(turn) if isinstance(turns, dict) else None
                if not tu:
                    return ""
                # The server's own line, with its event words (it compares
                # the limit with the last turn that had a reading).
                if tu.get("line"):
                    return str(tu["line"])
                earlier = [k for k in turns if isinstance(k, int) and k < turn]
                return str(lib.turn_line(tu, turns[max(earlier)] if earlier else None) or "")
            except Exception as exc:  # noqa: BLE001 — fall back to the plain sum
                self._lost("usage line not built", exc)
        last: dict[str, dict] = {}
        for raw in shared.tail_lines(self.folder / "usage.jsonl"):
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("id"):
                last[str(rec["id"])] = rec
        new = out = cache = helpers = 0
        found = False
        for rec in last.values():
            if rec.get("turn") != turn:
                continue
            found = True
            if rec.get("helper"):
                helpers += shared._n(rec.get("new")) + shared._n(rec.get("output"))
            else:
                new += shared._n(rec.get("new"))
                out += shared._n(rec.get("output"))
                cache += shared._n(rec.get("cache"))
        if not found:
            return ""
        line = f"→ {format_tokens(new)} ↑ {format_tokens(out)} ↓ ({format_tokens(cache)})"
        return line + (f" + helpers {format_tokens(helpers)}" if helpers else "")


_GIT_TIMEOUT = 3.0
_UNTRACKED_MAX_BYTES = 1_000_000
# Lines are counted in this many untracked files — as many as a stamp lists —
# and in this many bytes of them: a folder of ten thousand files nobody
# ignored must not be read through at every answer.
_UNTRACKED_MAX_FILES = 200
_UNTRACKED_MAX_TOTAL = 8_000_000


def _turntimes():
    """The backend's turntimes.py, loaded by path: one set of timing rules
    for the hook and the server (it is standard-library only)."""
    return _backend_module("turntimes")


def _git(cwd: str, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *shared.GIT_PLAIN_PATHS, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_GIT_TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _epoch(iso: str | None) -> float:
    """A local ISO time as epoch seconds; 0 when there is none."""
    try:
        return datetime.fromisoformat(str(iso)[:19]).timestamp() if iso else 0.0
    except ValueError:
        return 0.0


# Folders a walk for changed files never enters: tools' caches, dependencies,
# version control. A walk is cut at either limit and says so.
_WALK_SKIP = {"node_modules", "__pycache__", "venv", "dist", "build", "target", "site-packages"}
_WALK_MAX_ENTRIES = 20_000
_WALK_MAX_SECONDS = 1.0
_WALK_MAX_LISTED = 200


def changed_since(cwd: str, since: float) -> tuple[list[str], bool]:
    """Files under ``cwd`` modified after ``since`` (epoch seconds), relative
    and newest first — the folder's own record of a turn where there is no
    git. Hidden folders and dependency folders are skipped; the walk stops
    at a number of entries or a time budget, and says it was capped."""
    root = os.path.abspath(cwd)
    found: list[tuple[float, str]] = []
    stack, seen, t0, capped = [root], 0, time.monotonic(), False
    while stack:
        if seen >= _WALK_MAX_ENTRIES or time.monotonic() - t0 > _WALK_MAX_SECONDS:
            capped = True
            break
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            seen += 1
            name = e.name
            try:
                if e.is_dir(follow_symlinks=False):
                    if not name.startswith(".") and name not in _WALK_SKIP:
                        stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    m = e.stat(follow_symlinks=False).st_mtime
                    if m > since:
                        found.append((m, os.path.relpath(e.path, root).replace(os.sep, "/")))
            except OSError:
                continue
    found.sort(reverse=True)
    if len(found) > _WALK_MAX_LISTED:
        capped = True
    return [p for _, p in found[:_WALK_MAX_LISTED]], capped


def _relative_to(cwd: str, paths: list[str]) -> list[str]:
    """Paths as the project knows them: relative to the chat's folder when
    they are under it, else as given. Order kept, duplicates dropped."""
    out: list[str] = []
    base = os.path.abspath(cwd) if cwd else ""
    for p in paths:
        q = str(p)
        if base and os.path.isabs(q):
            try:
                rel = os.path.relpath(q, base)
                if not rel.startswith(".."):
                    q = rel.replace(os.sep, "/")
            except ValueError:
                pass
        if q and q not in out:
            out.append(q)
    return out


def work_stamp(cwd: str, prev_head: str = "", since: str = "") -> dict | None:
    """What the working tree at ``cwd`` looks like right now, for one turn.

    ``head`` — the commit HEAD points at. ``commits`` — the shas reachable
    from HEAD but not from ``prev_head``, oldest first: exactly the commits
    made since the last stamp, whoever else was committing to the same
    repo. ``dirty`` — the uncommitted change: tracked files by numstat,
    untracked files by their line count (text, under a megabyte; the first
    ``_UNTRACKED_MAX_FILES`` of them, the rest are listed and counted as
    files only, and the stamp says ``capped``). ``dirty`` is None when git
    did not answer: unknown, which is not the same as clean.
    """
    if not cwd or not os.path.isdir(cwd):
        return None
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return None
    root = top.strip()
    head = (_git(root, "rev-parse", "HEAD") or "").strip()
    if not head:
        return None

    commits: list[str] = []
    if prev_head and prev_head != head:
        listed = _git(root, "rev-list", "--reverse", f"{prev_head}..{head}")
        if listed is not None:
            commits = [x.strip() for x in listed.splitlines() if x.strip()]
        else:
            # The previous HEAD is gone (rebase, reset): this one commit at
            # least is new; the rest is unknowable, and we say so.
            commits = [head]
    if since:
        # A chat's first stamp: the commits made since its first turn began
        # count too, whatever HEAD was noted before it (a hook that first
        # saw the chat after the turn noted the HEAD the turn had made). From
        # a second after the start: git's --since is to the second and
        # inclusive, and a commit made just before the message is not this turn's.
        try:
            after = (datetime.fromisoformat(since) + timedelta(seconds=1)).isoformat(timespec="seconds")
        except ValueError:
            after = since
        dated = _git(root, "rev-list", "--reverse", f"--since={after}", head)
        for sha in (x.strip() for x in (dated or "").splitlines()):
            if sha and sha not in commits:
                commits.append(sha)

    numstat = _git(root, "diff", "--numstat", "HEAD")
    others = _git(root, "ls-files", "--others", "--exclude-standard")
    if numstat is None or others is None:
        return {"head": head, "commits": commits, "dirty": None}

    files: list[dict] = []
    for line in numstat.splitlines():
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        a, d, path = cols
        files.append({"path": shared.numstat_path(path), "add": int(a) if a.isdigit() else 0,
                      "del": int(d) if d.isdigit() else 0})
    looked, budget, capped = 0, _UNTRACKED_MAX_TOTAL, False
    for path in others.splitlines():
        path = path.strip()
        if not path:
            continue
        add = 0
        if looked >= _UNTRACKED_MAX_FILES or budget <= 0:
            capped = True
        else:
            looked += 1
            try:
                full = os.path.join(root, path)
                size = os.path.getsize(full)
                if size <= min(_UNTRACKED_MAX_BYTES, budget):
                    with open(full, "rb") as fh:
                        add = fh.read().count(b"\n")
                    budget -= size
            except OSError:
                add = 0
        files.append({"path": path, "add": add, "del": 0, "new": True})

    dirty = {
        "files": len(files),
        "add": sum(f["add"] for f in files),
        "del": sum(f["del"] for f in files),
        "paths": files[:200],
    }
    if capped:
        dirty["capped"] = True
    return {"head": head, "commits": commits, "dirty": dirty}


_yymm_dd = shared.yymm_dd


STANDUP_STATE = "standup_state.json"
STANDUP_CLAIM_S = 45 * 60   # mirrors backend/backend/standuplib.py


def _standup_owed(data_root: Path, project: str) -> dict | None:
    """Yesterday's standup for this project, if it is owed and nobody has it.

    The standup is the project's, not the agent's: one per day, written from
    every chat of that day (backend/backend/standuplib.py). Read from files,
    because the hook runs with no server: the chat logs for the messages,
    standups.csv for one already written, standup_state.json for a claim by
    another agent or a postpone by the operator.
    """
    now = datetime.now()
    then = now - timedelta(days=1)
    day = _yymm_dd(then)
    stamp = re.compile(rf"^## Turn \d+ · {then:%Y-%m-%d}T", re.M)
    # A log nobody wrote to since before yesterday began holds none of
    # yesterday's turns: it is not read. (Every chat of the project used to
    # be, in full, on each agent's first message of the day.)
    day_start = datetime(then.year, then.month, then.day).timestamp()
    messages = chats = chars = 0
    for chat in (data_root / "projects" / project / "chats").glob("*/chat.md"):
        try:
            if chat.stat().st_mtime < day_start:
                continue
            text = chat.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = len(stamp.findall(text))
        if found:
            messages += found
            chats += 1
            # The day's size, for the operator's choice of whole or clipped messages.
            for part in re.split(r"(?m)^(?=## Turn )", text):
                if stamp.match(part):
                    chars += len(part)
    if not messages:
        return None
    for row in _read_csv(data_root / "standups.csv"):
        if str(row.get("project") or "") != project:
            continue
        covers = str(row.get("for_date") or "")
        if not covers:
            # An older standup names no day: it covers the day before it was written.
            try:
                made = datetime.strptime(str(row.get("created_date") or ""), "%y%m-%d")
                covers = f"{(made - timedelta(days=1)):%y%m-%d}"
            except ValueError:
                covers = ""
        if covers == day:
            return None
    try:
        state = json.loads((data_root / STANDUP_STATE).read_text(encoding="utf-8")).get(f"{project}|{day}") or {}
    except (OSError, ValueError, AttributeError):
        state = {}
    claim = state.get("claim") or {}
    if claim and time.time() - float(claim.get("at") or 0) < STANDUP_CLAIM_S:
        return None
    if float(state.get("postponed_until") or 0) > time.time():
        return None
    try:
        settings = json.loads((data_root / "settings.json").read_text(encoding="utf-8"))
        prefs = settings.get("standup") or {}
        map_model = str((settings.get("map") or {}).get("model") or "opus")
    except (OSError, ValueError, AttributeError):
        prefs, map_model = {}, "opus"
    model = str(prefs.get("model") or "opus")
    return {"date": day, "messages_n": messages, "chats_n": chats, "chars": chars,
            "model": model if _MODEL_NAME.match(model) else "opus",
            "map_model": map_model if _MODEL_NAME.match(map_model) else "opus",
            "ask": prefs.get("ask") is not False}


# A model the operator chose: one of the names offered, or one they typed
# (OpenCode's carry the provider: openai/gpt-6-luna).
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")

#: "chat": the helper runs on the model of the chat that starts it.
CHAT_MODEL = "chat"
#: The setting for each tool under standup.* and map.*, and its default.
_HELPER_KEYS = {"claude": ("model", "opus"), "codex": ("model_codex", CHAT_MODEL), "opencode": ("model_opencode", CHAT_MODEL)}


def _helper_models(data_root: Path) -> dict[str, dict[str, str]]:
    """The model Settings give each helper, per tool (Settings › Agents):
    {"standup": {"claude": "opus", "codex": "chat", …}, "map": {…}}."""
    try:
        settings = json.loads((Path(data_root) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    out: dict[str, dict[str, str]] = {}
    for job in ("standup", "map"):
        section = settings.get(job) if isinstance(settings, dict) and isinstance(settings.get(job), dict) else {}
        out[job] = {}
        for tool, (key, default) in _HELPER_KEYS.items():
            model = str(section.get(key) or default)
            out[job][tool] = model if _MODEL_NAME.match(model) else default
    return out


def _map_model(data_root: Path) -> str:
    """The model Settings give the map helper in Claude Code."""
    return _helper_models(data_root)["map"]["claude"]


def _tool_key(tool: str) -> str:
    return "codex" if tool == "codex" else "opencode" if tool == "opencode" else "claude"


def helper_offer(tool: str, job: str, model: str) -> tuple[str, str]:
    """How this tool starts the helper for a job ("standup" or "map") on the
    model Settings give, and what else the user may pick: (on, other).
    Claude Code names a model per helper (the Agent tool's model); Codex too
    (spawn_agent's model); OpenCode runs a subagent on the model its config
    gives — the plugin defines sp-standup and sp-map from Settings."""
    t = _tool_key(tool)
    if t == "codex":
        on = ("a helper agent on this chat's model (spawn_agent without model)" if model == CHAT_MODEL
              else f"a helper agent on {model} (spawn_agent with model \"{model}\")")
        return on, "another model your spawn_agent lists"
    if t == "opencode":
        if model == CHAT_MODEL:
            return "a helper agent on this chat's model (the task tool, subagent_type general)", ""
        return (f"a helper agent on {model} (the task tool, subagent_type sp-{job})",
                "this chat's model (subagent_type general)")
    return f"a helper agent on {model} (the Agent tool with model)", "another model: haiku, sonnet or opus"


def _read_csv(path: Path) -> list[dict]:
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except (OSError, csv.Error):
        return []


def _scan_without_files(data_root: Path, project: str, meta: dict, scans: list[dict] | None = None) -> str | None:
    """Id of the project's latest recent scan that no file entry references."""
    return _scan_without_entry(data_root, project, meta, ledger="files.csv", notified_key="files_notified",
                               scans=scans)


def _scan_without_entry(
    data_root: Path, project: str, meta: dict, *, ledger: str, notified_key: str,
    scans: list[dict] | None = None,
) -> str | None:
    """Id of the project's latest recent scan that no row of ``ledger`` references.

    "Recent" = today or yesterday, so an old forgotten scan does not haunt
    every new session; ``meta[notified_key]`` makes it one notice per scan
    per agent. Files and architecture entries both hang off a scan this way.
    ``scans``: the rows of scans.csv, from a caller that asks twice.
    """
    scans = [
        r for r in (_read_csv(data_root / "scans.csv") if scans is None else scans)
        if r.get("project") == project and r.get("id")
    ]
    if not scans:
        return None
    latest = max(scans, key=lambda r: (r.get("created_date") or "", r.get("created_time") or ""))
    now = datetime.now()
    recent = {_yymm_dd(now), _yymm_dd(now - timedelta(days=1))}
    if (latest.get("created_date") or "") not in recent:
        return None
    sid = latest["id"]
    if sid in (meta.get(notified_key) or []):
        return None
    covered = {
        r.get("trigger_id") for r in _read_csv(data_root / ledger)
    }
    return None if sid in covered else sid


def format_signals(signals: dict, tool: str = "claude-code") -> str:
    """Human-readable context notice; empty when nothing is due. ``tool``:
    the one the notice is for, so a helper is offered the way it starts one."""
    notes = []
    models = signals.get("helper_models") or {}
    def offer(job: str, fallback: str) -> tuple[str, str]:
        return helper_offer(tool, job, (models.get(job) or {}).get(_tool_key(tool)) or fallback)
    ident = signals.get("identity")
    if ident:
        notes.append(
            f"[slightly-parallel] project {ident['project']} · your agent_id is "
            f"{ident['agent_id']} · now {ident['date']} {ident['time']}. The "
            "MCP tools stamp these for you; they are here for reference."
        )
    usage_told = False
    for name in signals.get("commands") or []:
        skill, start = _COMMANDS[name]
        if name in _USAGE_COMMANDS:
            # The hook answered: the agent shows the answer as it is.
            if not usage_told and signals.get("usage_answer"):
                usage_told = True
                notes.append(
                    f"[slightly-parallel] #{name} — the hook's answer is below; show it to the user as it is "
                    "and add nothing to it.\n" + str(signals["usage_answer"]))
            continue
        if name == "map":
            on, other = offer("map", signals.get("map_model") or "opus")
            notes.append(
                "[slightly-parallel] #map — ask the user now, before any other work, in one line: "
                f"\"Map the program now with {on}{', or ' + other if other else ''}, or later?\" Then stop and wait for "
                "the answer. Do not call map_material and do not start a helper before it. "
                f"Now: the skill {skill} holds the steps (from its step 2). Later: nothing more."
            )
            continue
        if name == "standup":
            on, other = offer("standup", "opus")
            notes.append(
                "[slightly-parallel] #standup — ask the user now, before any other work, in one line: "
                f"\"Write the standup now with {on}{', or ' + other if other else ''}, or later?\" "
                "Then stop and wait for the answer. Do not call standup_material and do not start a helper "
                f"before it. Then: the skill {skill} holds the steps (from its step 2), on the model the user named."
            )
            continue
        notes.append(
            f"[slightly-parallel] #{name} — " + (f"the skill {skill} holds the steps. Start with {start}."
                                      if skill else f"{start}.")
        )
        lane = signals.get("task_lane")
        if (name == "task" or name.startswith("now")) and lane:
            if lane.get("lane"):
                notes[-1] += f" The lane: {lane['lane']} (the server sets it from the message)."
            else:
                notes[-1] += (
                    f" The lane {lane['named']!r} is not on the board"
                    + (f" (its lanes: {', '.join(lane['lanes'])})" if lane.get("lanes") else " (it has no lanes yet)")
                    + ": ask the operator which, in one line, before writing."
                )
    ev = signals.get("evidence_for")
    if ev is not None:
        if ev.get("id"):
            title = f" · {ev['title']}" if ev.get("title") else ""
            notes.append(
                f"[slightly-parallel] #evidence for {ev['id']}{title}. Call MCP tool "
                f"task_evidence_ask {{id: \"{ev['id']}\"}} and follow its instructions. "
                "If this is the wrong task, ask the user."
            )
        else:
            notes.append(
                "[slightly-parallel] #evidence: no task named in this chat. "
                "Ask the user which task, then call MCP tool task_evidence_ask {id}."
            )
    due = signals.get("standup_due")
    if due:
        what = (
            f"[slightly-parallel] #standup — no standup for {due['date']}: {due['messages_n']} messages in "
            f"{due['chats_n']} chat{'' if due['chats_n'] == 1 else 's'}. "
        )
        s_on, s_other = offer("standup", due["model"])
        m_on, _ = offer("map", due.get("map_model") or "opus")
        if due.get("ask"):
            size = int(due.get("chars") or 0)
            clipped = min(size, int(due.get("messages_n") or 0) * 2400)
            what += (
                f"Ask the user now, before other work, with numbered choices: "
                f"1 write it with {s_on} and map the program with {m_on} · 2 write only · 3 postpone"
                f"{'; or ' + s_other if s_other else ''}; "
                f"messages whole (about {max(1, round(size / 1000))}k characters) or clipped to the start and end of each "
                f"(about {max(1, round(clipped / 1000))}k). Whole is the default. "
            )
        else:
            what += f"Write it now with {s_on}. "
        notes.append(what + "The skill daily-standup has the steps "
                            "(MCP tools standup_material, standup_postpone).")
    if signals.get("decision_hint"):
        notes.append(
            f"[slightly-parallel] #decision — this sounds like a decision "
            f"(\"{signals['decision_hint']}\") — offer to log it "
            "(MCP tool write_entry, lens decision)."
        )
    if signals.get("contract_refresh_due"):
        notes.append(
            "[slightly-parallel] refresh — long chat: re-read SLIGHTLY-PARALLEL.md and the rules in "
            "this project's AGENTS.md."
        )
    unsigned = signals.get("unsigned_commits")
    if unsigned and unsigned.get("commits"):
        listed = ", ".join(f"{c['sha']} \"{c['subject']}\"" for c in unsigned["commits"][:5])
        more = len(unsigned["commits"]) - 5
        notes.append(
            f"[slightly-parallel] commits — {listed}{f' and {more} more' if more > 0 else ''} "
            f"{'have' if len(unsigned['commits']) > 1 else 'has'} no `Task:` line. "
            + ("" if unsigned.get("sure") else "If you made them: ")
            + "link each to its task with MCP tool task_commits {id, shas}; a commit for no task needs nothing. "
            "In the next commits, end the message with `Task: tk_…` and `Agent: <your agent_id>`."
        )
    tracked = signals.get("cores_tracking")
    if tracked:
        named = ", ".join(f"{c['name']} ({c['id']}{', until ' + c['until'] if c.get('until') else ''})" for c in tracked)
        notes.append(
            f"[slightly-parallel] cores tracked in this project: {named}. When finished work changes one, "
            "call MCP tool core_note {id, comment, kind: \"auto\", task_id} with one line on what changed. "
            "Only finished work; at most one note per task."
        )
    if signals.get("files_due"):
        notes.append(
            f"[slightly-parallel] #scan — scan {signals['files_due']} has no file entry. MCP tool "
            "write_entry, lens file, with fields.trigger_lens \"scan\", "
            f"fields.trigger_id \"{signals['files_due']}\" and fields.paths: one "
            "record per file you modified (importance, blast_radius, "
            "test_coverage, why)."
        )
    if signals.get("architecture_due"):
        notes.append(
            f"[slightly-parallel] #architecture — scan {signals['architecture_due']} has no "
            "architecture answer. MCP tool write_entry, lens architecture, with "
            f"fields.trigger_id \"{signals['architecture_due']}\": the eight-group "
            "form (does · owes · runs · stores · talks · built with · faces · "
            "holds), each group in `checked` or with its changes. See SLIGHTLY-PARALLEL.md §4."
        )
    for k in signals.get("kept") or []:
        if k["kind"] == "publish":
            notes.append(
                f"[slightly-parallel] #publish — the server keeps this message as {k['id']} on the "
                "Publish page (what shipped, worth telling). The text is the operator's: write nothing. "
                "Attach what they may need to tell about it: 1–3 screenshots of what it is about (the "
                "page or the product, as you can render it) and the links, with MCP tool "
                f"publish_attach {{id: \"{k['id']}\", images, links}}."
            )
            continue
        if k["kind"] == "skill":
            notes.append(
                f"[slightly-parallel] #skill — the server keeps this message as {k['id']}. "
                "Write the skill from what was done in this session (SLIGHTLY-PARALLEL.md §4, "
                f"Skill): MCP tool skill_draft {{id: \"{k['id']}\", skill_md, files}}."
            )
            continue
        if k["kind"] == "artifact":
            notes.append(
                f"[slightly-parallel] #artifact — the server keeps this message as {k['id']}. "
                "The skill make-an-artifact holds the steps. "
                f"Write the folder at {k.get('folder') or '<data_root>/projects/<project>/artifacts'}/<name>/ — "
                "ARTIFACT.md with name, kind and description on top, the files beside it — "
                f"then MCP tool artifact_write {{id: \"{k['id']}\", name, kind, description}} "
                "(SLIGHTLY-PARALLEL.md §4, Artifact)."
            )
            continue
        notes.append(
            f"[slightly-parallel] #{k['kind']} — the server keeps this message as "
            f"{k['id']}; do not post an entry for it. Write its interpretation "
            f"(SLIGHTLY-PARALLEL.md §4, Kept messages): MCP tool interpret "
            f"{{lens: \"{k['kind']}\", id: \"{k['id']}\", text}}."
        )
    if any("MCP tool " in n for n in notes):
        # Claude Code loads MCP tools only when searched for: a small model
        # searched ten times, or gave up and said it had written. One exact
        # query finds the tool at once.
        m = re.search(r"MCP tool (\w+)", "\n".join(notes))
        notes.append(
            "[slightly-parallel] tools — the MCP tools may need loading first: in Claude Code, ToolSearch "
            f"\"select:mcp__slightly-parallel__{m.group(1) if m else 'write_entry'}\". A write that did not "
            "answer with an id did not happen: never say it did."
        )
    return "\n".join(notes)
