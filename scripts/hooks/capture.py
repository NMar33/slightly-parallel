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
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
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
    r"(?<![\w#])#(vision|rule|problem|entrypoint|skill|artifact)(?:\([^)\n]{1,80}\))?(?![\w-])(?!\s+solved\b)",
    re.IGNORECASE,
)
_ANY_TAG_RE = re.compile(
    r"(?<![\w#])#(?:prompt|vision|rule|problem|entrypoint|skill|artifact)(?:\([^)\n]{1,80}\))?(?![\w-])",
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
            "the server keeps this message as the task's text"),
    # #now-<column>: the message filed into that column, not started.
    **{f"now-{c}": ("write-a-task", f"MCP tool write_entry, lens task, status {s}, title and tags only: "
                    "the server keeps this message as the task's text. File it and go on: it is not "
                    "started in this chat")
       for c, s in (("todo", "todo"), ("to-do", "todo"), ("next", "next"), ("backlog", "backlog"),
                    ("review", "review"), ("parked", "parked"), ("done", "done"))},
    "now-doing": ("write-a-task", "MCP tool write_entry, lens task, status doing, title and tags only: "
                  "the server keeps this message as the task's text"),
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
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


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
    def open_turn(self, user_text: str) -> dict:
        """Record the user's message; the answer arrives via complete_turn.

        Returns the signals dict so context-capable adapters can surface it.
        """
        meta = self._load_meta()
        # The same message delivered twice while the previous turn is still
        # unanswered (interrupt + resend, or a retried hook event) is one
        # turn, not two — answered before any ledger is read for it.
        text_key = (user_text or "").strip()
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
        settings = _load_settings(self.data_root)

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
        evidence_for = None
        if _EVIDENCE_RE.search(user_text or ""):
            tid = named[0] if named else str(meta.get("last_task") or "")
            evidence_for = {"id": tid, "title": _task_title(self.data_root, tid) if tid else ""}

        meta["message_count"] = turn
        meta["last_active"] = now_iso()
        meta["pending_turn"] = turn
        meta["pending_user_text"] = text_key
        meta["pending_started"] = started
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
            "commands": (commands := list(dict.fromkeys(
                " ".join(m.group(1).lower().split()) for m in _COMMAND_RE.finditer(user_text or "")))),
            # #map costs a helper run: its notice asks the operator, naming
            # the model Settings give, the way the standup's does.
            "map_model": _map_model(self.data_root) if "map" in commands else None,
            # #standup by hand asks the same way. Each tool names models and
            # starts helpers its own way: the notice picks this tool's.
            "helper_models": _helper_models(self.data_root) if (standup_due or {"map", "standup"} & set(commands)) else None,
            # #task {lane} / #now {lane}: the server refuses a lane the board
            # does not have; the notice says so first, so the agent asks.
            "task_lane": _task_lane(self.data_root, self.project, user_text)
            if any(c == "task" or c.startswith("now") for c in commands) else None,
            "kept": [
                # An artifact is a folder the agent writes itself; the notice
                # names where, so the agent never guesses the data root.
                {**k, "folder": str(self.data_root / "projects" / self.project / "artifacts")}
                if k["kind"] == "artifact" else k
                for k in _kept(user_text, self.project, self.agent_name, turn)
            ],
            # Identity + clock on the first turn and every refresh: entries
            # posted with this agent_id and time line up with the captured
            # chat, which is what links a checkpoint to its conversation.
            "identity": (
                {"agent_id": self.agent_name, "project": self.project,
                 "date": _yymm_dd(datetime.now()),
                 "time": datetime.now().strftime("%H:%M")}
                if turn == 1 or refresh_due else None
            ),
        }

    def complete_turn(self, agent_text: str, *, close_if_missing: bool = False,
                      transcript: str | None = None, times: dict | None = None,
                      points: list | None = None, touched: list[str] | None = None) -> None:
        """Attach the assistant's final answer to the pending turn.

        Without a pending turn (the prompt event was skipped or lost) the
        answer is dropped — a phantom user-less turn is worse than a gap.
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
        does not.
        """
        closed = self._close_turn(agent_text, close_if_missing=close_if_missing)
        if closed is None:
            return
        # The stamps read a transcript and ask git — seconds, on a long chat
        # in a large repository. Outside the meta lock: the dashboard's
        # rename waits on it, and gives up after five seconds.
        turn, started, ended, cwd = closed
        self._stamp_time(turn, started, ended, transcript, times, points)
        self._stamp_work(turn, cwd, touched, started)

    @_with_meta_lock
    def _close_turn(self, agent_text: str, *, close_if_missing: bool) -> tuple[int, str | None, str, str] | None:
        """The answer into chat.md and the turn out of meta.json, under the
        lock. Answers what the stamps need, or None when nothing closed."""
        if not agent_text.strip():
            if not close_if_missing:
                return None
            agent_text = REPLY_MISSING
        meta = self._load_meta()
        turn = meta.pop("pending_turn", None)
        if turn is None:
            return None
        meta.pop("pending_user_text", None)
        started = meta.pop("pending_started", None)
        self._append(f"**Agent**: {escape_content(agent_text.rstrip())}\n")
        ended = now_iso()
        meta["last_active"] = ended
        _atomic_write_json(self.meta_path, meta)
        return int(turn), started, ended, str(meta.get("cwd") or "")

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
            with open(self.folder / "turns.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line) + "\n")
        except OSError as exc:
            self._lost("turn times not kept", exc)

    def _last_end(self) -> str:
        """The previous answer's end, from the end of turns.jsonl ("" if none)."""
        return str(shared.last_json(self.folder / "turns.jsonl", "end") or "")

    def _stamp_work(self, turn: int, cwd: str, touched: list[str] | None = None,
                    started: str | None = None) -> None:
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
            stamp = work_stamp(cwd, self._last_stamp_head() or str(self._load_meta().get("base_head") or ""))
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
                return
            stamp = {"head": "", "commits": [], "dirty": None, "changed": changed}
            if capped:
                stamp["changed_capped"] = True
        stamp = {"turn": turn, "at": now_iso(), **stamp, "touched": files}
        try:
            with open(self.folder / "work.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(stamp, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._lost("work stamp not kept", exc)

    def _last_stamp_at(self) -> str:
        """The previous stamp's time, from the end of work.jsonl ("" if none)."""
        return str(shared.last_json(self.folder / "work.jsonl", "at") or "")

    def _last_stamp_head(self) -> str:
        """The previous stamp's HEAD, from the end of work.jsonl ("" if none)."""
        return str(shared.last_json(self.folder / "work.jsonl", "head") or "")

    @_with_meta_lock
    def note_origin(self, tool: str = "", session_id: str = "", cwd: str = "") -> None:
        """Record where this agent runs: the tool, its full session id and
        the working directory — enough to print a resume command later.
        Written once (or when a value changes); never breaks the session.
        The directory is the one the chat started in and is kept: the tool
        reports the agent's current one, which moves when it works in a
        subfolder, and a resume there meets a different set of instructions."""
        updates = {}
        meta = self._load_meta()
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

    def full_turn(self, user_text: str, agent_text: str) -> dict:
        """One-shot capture for end-of-turn-only tools (e.g. Codex notify).

        The turn is closed even when the reply came empty (marked as a gap):
        left open, the next message wrote a second user line under it, and
        the same message again ("continue") was taken for this one."""
        signals = self.open_turn(user_text)
        self.complete_turn(agent_text, close_if_missing=True)
        return signals


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


def work_stamp(cwd: str, prev_head: str = "") -> dict | None:
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
    for name in signals.get("commands") or []:
        skill, start = _COMMANDS[name]
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
