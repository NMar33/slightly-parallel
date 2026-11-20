"""The Slightly Parallel MCP translator — a stdio server over the running HTTP API.

Design: this process owns no data and holds no
state. It fetches the write contract from GET /api/schema at startup, builds
its tool definitions from that response, resolves identity from the capture
hook's breadcrumb via GET /api/whoami, and forwards every call to the one
write authority on 127.0.0.1:8123. It can crash without consequence; the
worst outcome of any bug here is a failed call.

Wire protocol: MCP over stdio — newline-delimited JSON-RPC 2.0. Implemented
by hand: the surface a translator needs (initialize, tools, resources,
prompts, ping) is small enough that a hand-rolled loop is simpler to verify
than an SDK abstraction, and it keeps the backend dependency-free.

Run: ``python -m backend.mcp`` with SP_API set (default the local
server). Claude Code launches it from .mcp.json with cwd = the project root,
which is exactly what /api/whoami needs.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import __version__
# This process's parents: the capture hook reads them the same way, and the
# two find each other by the tool process they share (hookshared.py).
from .hookshared import ancestors
from .server_address import loopback_url

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "slightly-parallel", "version": __version__}
VIA_HEADER = "X-SP-Via"
VIA_VALUE = "mcp"
# How long a call waits for the server to come up before it fails: the
# backend restarts in seconds, and a session that opened during one must
# not lose MCP for its whole life.
SCHEMA_RETRY_S = 20.0
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Codex (0.170) runs the MCP servers of every chat inside one shared
# app-server daemon: the processes above this server are the daemon's, the
# same for every Codex chat, and say nothing of which chat calls. Each
# tools/call names its own thread in ``_meta`` instead (threadId, sessionId,
# x-codex-turn-metadata.thread_id): that thread is the caller. A Codex call
# without it is refused, never given the newest Codex chat.
CODEX_CLIENTS = ("codex-mcp-client",)
CODEX_UNKNOWN = (
    "cannot tell which Codex chat is calling: the call carries no thread id "
    "(Codex sends it in the tool call's _meta since 0.170). Nothing was written "
    "or read as this chat; update Codex, or tell the user."
)
_THREAD_RE = re.compile(r"[0-9A-Za-z-]{8,80}")


def codex_thread(params: Any) -> str:
    """The Codex thread a tools/call comes from, from its ``_meta``; "" when
    it names none (another client, an older Codex)."""
    meta = params.get("_meta") if isinstance(params, dict) else None
    if not isinstance(meta, dict):
        return ""
    turn = meta.get("x-codex-turn-metadata")
    for v in (meta.get("threadId"), turn.get("thread_id") if isinstance(turn, dict) else None,
              meta.get("sessionId")):
        if isinstance(v, str) and _THREAD_RE.fullmatch(v):
            return v
    return ""

# Every tool, in one line each. The one list: the server's refusal, the
# schema (`tools`), the Info page and the docs all read this, and a test
# holds it equal to what tool_defs() really serves.
TOOLS: dict[str, str] = {
    "write_entry": "Create an entry: what it holds and its lens's columns, by name.",
    "update_entry": "Change an entry's lifecycle fields or its text.",
    "tasks": "The open board of a project.",
    "task_update": "Edit a task. Status is the operator's.",
    "task_report": "Say a task is done, in your opinion.",
    "task_commits": "Link commits that have no Task: line to the task they were made for.",
    "task_done": "After #done: what the operator's #done moved, and each task's stretch of the chat; with proposals, offers next tasks.",
    "next_tasks": "After the operator answered the next tasks offered at #done: make the ones they chose by number.",
    "undo_find": "After #undo: the operator's request and the entries it could mean, numbered.",
    "undo_propose": "Send the entries the operator chose to archive; answers the confirmation to show.",
    "undo_apply": "After #undo-yes: archive the confirmed entries. Refused without the operator's #undo-yes.",
    "undo_restore": "Bring back one entry archived with #undo.",
    "task_evidence_ask": "After #evidence: the operator's instructions for this task.",
    "task_evidence": "Attach evidence to a task.",
    "task_work": "The files the repository saw this task touch.",
    "task_story": "Post a piece on a task, under a request id the operator gave.",
    "cores": "The project's cores: the core elements the operator keeps in view, with each one's latest note.",
    "core_new": "After #core-new: a new core — a short name, a type, the files you know; the message is its first note.",
    "core_note": "After #core-note, or when finished work changes a tracked core: one note on a core.",
    "core_attach": "After #core: attach this message, and this chat's task, to the matching core.",
    "core_off": "After #core-off, confirmed by the operator: remove a core from view; its notes and links are kept.",
    "pins": "The messages the operator pinned (or carried, or kept to fork later), each whole: this chat's or the project's.",
    "carry_brief": "After #carry-brief: the brief of the message, given back after a compaction instead of it.",
    "publish_write": "After the operator's #publish: write the card — text if asked, context, and what belongs to it (tasks, commits, files, images, links, notes).",
    "publish_attach": "The older name of publish_write, for attachments only; it forwards there.",
    "entrypoints": "The project's entry points: the topics the operator comes back to, with their ways in.",
    "entrypoint_stop": "One line of where a topic stopped: at #done for a task of the topic.",
    "entrypoint_way": "Add a way in to a topic (a page, a site, an app, a file …), or change one an agent wrote.",
    "entrypoint_shot": "Attach a screenshot of a way in you made or changed, while it is up.",
    "entrypoint_offer": "Before offering a new entry point: the topics like it, and the line to show the operator.",
    "entrypoint_ask": "After #entrypoint: the topics it may mean, numbered, and the line to show; nothing is made yet.",
    "entrypoint_answer": "After the operator answered the entrypoint_ask line: the topic they chose, opened or made.",
    "task_topic": "Set the topic (entry point) of a task of this project.",
    "architecture_status": "After #architecture: which of the form, the page and the map are out of date, and why.",
    "architecture_material": "What the architecture page is written from: computed facts, the current page, instructions.",
    "architecture_page": "Write the next version of the project's architecture page.",
    "map_material": "What the map of the program is written from: computed facts, the current map, instructions.",
    "map_write": "Write the next version of the project's map: every part as a row, and what connects to what.",
    "scan_material": "After #scan: this chat's commits since your last scan and what is not committed, counted, and how to write it.",
    "standup_material": "The day's messages, whether a standup is owed, and how to write it.",
    "standup_postpone": "The operator put the standup off: do not ask again for some hours.",
    "interpret": "Write the interpretation of a kept vision, rule, problem or entry point.",
    "skill_draft": "Write SKILL.md and its files for a kept #skill.",
    "artifact_write": "Make the record of an artifact folder you wrote.",
    "doc_version": "Post the finished text of a Storyboard document whose pack the operator gave you.",
    "deck": "What the project holds right now, in brief.",
    "search": "Find entries by text.",
    "project": "One project's facts.",
    "doctor": "Check the data for damage.",
    "checkup": "After #sp: is Slightly Parallel working for this chat and folder — each check ok, note, concern or unknown.",
    "usage": "This chat's tokens, the plan limits and the project's day: the #usage text, and the numbers behind it.",
    "usage_prices_material": "After #usage-price: the models the chats used, the API prices now, the pages to read, instructions.",
    "usage_prices_write": "After #usage-price: one update of the API prices, read from the providers' own pages.",
    "note_write": "Write a note for the operator instead of a long reply or a file: context, a text to paste, a review, a plan, a report, manual steps.",
    "note_image": "Add a picture to a note; answers the markdown line that shows it.",
    "notes": "The project's notes, or one note with the operator's ticks, answers and comments.",
    "message": "Send a message to another chat (an agent): advice between agents, delivered to Codex by thread, to Claude Code by terminal, or through the hooks or inbox.",
    "messages": "This chat's messages from other agents: unread first (reading marks them read), then the newest read ones.",
}


# The server is on this computer: an HTTP_PROXY in the agent's environment
# sent the calls to the proxy, which cannot reach 127.0.0.1 here.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

API_REQUEST_TIMEOUT_S = 30


class ApiError(RuntimeError):
    """An HTTP call that failed, carrying the server's own explanation."""


class Api:
    """The thinnest possible client for the one write authority."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            # The header is how the API knows an agent's write came through
            # here: agent writes without it are refused (server.py).
            headers={"Content-Type": "application/json", VIA_HEADER: VIA_VALUE},
        )
        try:
            with _DIRECT.open(req, timeout=API_REQUEST_TIMEOUT_S) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail", "")
            except Exception:  # noqa: BLE001 — the body is best-effort
                detail = ""
            raise ApiError(f"{exc.code}: {detail or exc.reason}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ApiError(
                f"cannot reach the Slightly Parallel server at {self.base} — is it running? ({exc})"
            ) from None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            # Something answers on the port and it is not Slightly Parallel (or not yet):
            # a failed call like any other, which ensure() waits out.
            raise ApiError(
                f"{self.base}{path} did not answer in JSON — is it the Slightly Parallel server?"
            ) from None

    def get(self, path: str) -> Any:
        return self._call("GET", path)

    def post(self, path: str, body: dict) -> Any:
        return self._call("POST", path, body)


def _list(args: dict, key: str) -> list[str]:
    """A list argument as a list of strings: one string is a one-item list
    (a bare "abc1234" was posted as seven one-letter hashes)."""
    raw = args.get(key)
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return [raw]
    if not isinstance(raw, list):
        raise ApiError(f"{key} is a list of strings")
    return [str(x) for x in raw]


def _id(args: dict) -> str:
    """The entry a tool names, safe inside a path: an id with a slash or a
    question mark in it must not become another endpoint."""
    raw = str(args.get("id") or "").strip()
    if not raw:
        raise ApiError("id is required")
    return urllib.parse.quote(raw, safe="")


class Translator:
    """Tools, resources and prompts over a fetched contract + identity."""

    def __init__(self, api: Api, cwd: str):
        self.api = api
        self.cwd = cwd
        self.schema: dict | None = None
        self.lenses: dict[str, dict] = {}
        self.vocab: dict = {}
        # The MCP client (initialize's clientInfo.name) and the Codex thread
        # of the call being answered (codex_thread): set per request by handle().
        self.client = ""
        self.thread = ""
        try:
            self._load_schema()
        except ApiError:
            pass  # the server may be restarting; the first call retries

    def _load_schema(self) -> None:
        self.schema = self.api.get("/api/schema")
        self.lenses = {l["name"]: l for l in self.schema["lenses"]}
        self.vocab = self.schema.get("vocabularies", {})

    def _refresh(self, lens: str) -> bool:
        """Read the schema again before refusing a name: the server may have
        been restarted with new fields since this MCP server started. Once per
        minute at most. True when the lens's fields changed."""
        import time as _time
        now = _time.monotonic()
        if now - getattr(self, "_refreshed_at", 0.0) < 60:
            return False
        self._refreshed_at = now
        before = (self.lenses.get(lens) or {}).get("fields"), (self.lenses.get(lens) or {}).get("text_fields")
        try:
            self._load_schema()
        except ApiError:
            return False
        after = (self.lenses.get(lens) or {}).get("fields"), (self.lenses.get(lens) or {}).get("text_fields")
        return before != after

    def ensure(self) -> None:
        """The write contract, fetched when the server is there to give it."""
        if self.schema is not None:
            return
        import time as _time
        deadline = _time.monotonic() + SCHEMA_RETRY_S
        while True:
            try:
                self._load_schema()
                return
            except ApiError:
                if _time.monotonic() >= deadline:
                    raise
                _time.sleep(1.0)

    # -- identity ----------------------------------------------------------

    def identity(self) -> dict:
        """Fresh on every write: the breadcrumb may change under us."""
        q = urllib.parse.quote(self.cwd, safe="")
        if self.thread:
            # Codex: the call's own thread names the chat, not the processes.
            return self.api.get(f"/api/whoami?cwd={q}&thread={urllib.parse.quote(self.thread, safe='')}")
        if self.client in CODEX_CLIENTS:
            raise ApiError(CODEX_UNKNOWN)
        # The processes above this server: two chats in one folder are told
        # apart by the tool process each one's hook and MCP server share.
        pids = ",".join(str(p) for p in ancestors())
        return self.api.get(f"/api/whoami?cwd={q}" + (f"&pids={pids}" if pids else ""))

    def _stamp(self) -> dict:
        """agent_id / project / date / time — stamped, never asked of the
        model: whatever it sends under these names is written over."""
        import time as _time
        who = self.identity()
        now = _time.localtime()
        return {
            "project": who["project"],
            "agent_id": who["agent_id"],
            "created_date": f"{now.tm_year % 100:02d}{now.tm_mon:02d}-{now.tm_mday:02d}",
            "created_time": f"{now.tm_hour:02d}:{now.tm_min:02d}",
        }

    # -- client-side gate: the typo dies before a request exists -----------

    def _check_vocab(self, lens: str, payload: dict) -> None:
        for field, allowed in self.vocab.get(lens, {}).items():
            v = payload.get(field)
            if isinstance(v, (list, dict, bool)):
                # str(["agent"]) is "['agent']": refused with a list that
                # names "agent" as allowed. Say the shape instead.
                raise ApiError(
                    f"{lens}.{field} is one text value, not {type(v).__name__} — "
                    f"use one of: {', '.join(allowed)}"
                )
            if v not in (None, "") and str(v) not in allowed:
                raise ApiError(
                    f"{lens}.{field} {v!r} is not a known value — "
                    f"use one of: {', '.join(allowed)}"
                )

    # The lenses an agent writes most, each with the names it holds.
    _DIGEST_LENSES = ("scan", "file", "decision", "problem", "standup", "task")

    def _lens_digest(self) -> str:
        parts = []
        for name in self._DIGEST_LENSES:
            spec = self.lenses.get(name)
            if spec and spec.get("text_fields"):
                parts.append(f"{name}: {', '.join(spec['text_fields'])}")
        return "; ".join(parts) + "."

    def _check_names(self, lens: str, spec: dict, payload: dict) -> None:
        """A field the lens does not have dies here, with the ones it has."""
        known = set(spec.get("fields") or {}) | {"project", "agent_id", "created_date",
                                                 "created_time", "paths", "changes", "checked"}
        unknown = sorted(k for k in payload if k not in known)
        if unknown and self._refresh(lens):
            return self._check_names(lens, self.lenses.get(lens) or spec, payload)
        if unknown:
            raise ApiError(
                f"{lens} has no field {', '.join(unknown)} — it holds: "
                f"{', '.join(spec.get('text_fields') or [])}; columns: "
                f"{', '.join(sorted(k for k in (spec.get('fields') or {}) if k not in (spec.get('text_fields') or [])))}"
            )

    @staticmethod
    def _by_name(result: Any) -> Any:
        """An answer that carries its text by name does not also show the slots."""
        if isinstance(result, dict) and isinstance(result.get("text"), dict):
            return {k: v for k, v in result.items() if k not in ("l2", "l3", "l4")}
        return result

    # -- tools -------------------------------------------------------------

    def tool_defs(self) -> list[dict]:
        self.ensure()
        arch = (self.schema or {}).get("architecture") or {}
        ARCH_TYPES = [t for types in (arch.get("groups") or {}).values() for t in types]
        ARCH_OPS = arch.get("ops") or ["add", "change", "remove"]
        # Only the lenses an agent may create. The schema marks the rest
        # `agent_write: false` (routers/lenses.py OPERATOR_ONLY), so the
        # picker never offers a lens the server refuses.
        lens_names = sorted(n for n, l in self.lenses.items() if l.get("agent_write", True))
        mutable = sorted(n for n, l in self.lenses.items()
                         if l["mutable"] and l.get("agent_update", l.get("agent_write", True)))
        task_status = self.vocab.get("task", {}).get("status", [])
        evidence_max = ((self.schema or {}).get("limits") or {}).get("evidence_items", 8)
        return [
            {"name": "write_entry",
             "description": (
                 "Create one Slightly Parallel entry. Put everything in `fields`, by name: "
                 "what the entry holds and the columns of its lens. Identity "
                 "(project, agent id, date, time) is stamped from this session; "
                 "do not send it. An unknown field is refused by name. The same "
                 "entry written twice is one entry. What each lens holds: "
                 + self._lens_digest() + " The rest: sp://schema."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "lens": {"type": "string", "enum": lens_names},
                     "fields": {"type": "object",
                                "description": "the entry, by name (see the description and sp://schema)"},
                 },
                 "required": ["lens", "fields"],
             }},
            {"name": "update_entry",
             "description": (
                 "Change one entry: its lifecycle fields (status and the like) "
                 "or its text, by the same names write_entry takes. Only the "
                 "fields a lens lets change apply; sp://schema lists them."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "lens": {"type": "string", "enum": mutable},
                     "id": {"type": "string"},
                     "changes": {"type": "object"},
                 },
                 "required": ["lens", "id", "changes"],
             }},
            {"name": "tasks",
             "description": "Open board of a project (defaults to this session's project).",
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "project": {"type": "string"},
                     "status": {"type": "string", "enum": task_status},
                 }}},
            {"name": "task_story",
             "description": (
                 "Post a press release / article / post on a task — only "
                 "under a request id (sr_…) the operator handed you in the "
                 "prompt. Markdown body; screenshots as base64, referenced "
                 "in the text as ![title](image:1)."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string", "description": "the task id"},
                     "request_id": {"type": "string"},
                     "body": {"type": "string"},
                     "images": {"type": "array", "items": {
                         "type": "object",
                         "properties": {
                             "title": {"type": "string"},
                             "data_base64": {"type": "string"},
                             "ext": {"type": "string", "enum": ["png", "jpg", "jpeg", "webp", "gif"]},
                         },
                         "required": ["title", "data_base64"],
                     }},
                 },
                 "required": ["id", "request_id", "body"],
             }},
            {"name": "task_report",
             "description": (
                 "Report a task done, in your opinion. Never moves it to done: "
                 "with auto-manage it lands in review for the operator's "
                 "verdict; otherwise only a badge appears. The response says "
                 "whether evidence is wanted and carries the instructions."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string"},
                     "summary": {"type": "string",
                                 "description": "one line: what shipped"},
                 },
                 "required": ["id", "summary"],
             }},
            {"name": "task_commits",
             "description": (
                 "Link commits to the task they were made for, when their message has no "
                 "`Task: tk_…` line (the contract asks for that line in every commit made for a "
                 "task). The same as the line: the commit then counts for this task and for no "
                 "other task's stretch of the chat. Only commits you made."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string", "description": "the task"},
                     "shas": {"type": "array", "items": {"type": "string"}, "description": "commit hashes, 7 to 40 hex"},
                 },
                 "required": ["id", "shas"],
             }},
            {"name": "task_done",
             "description": (
                 "The operator typed #done: the server moves the task to done as the operator's "
                 "verdict and gives it its stretch of the chat. This returns what moved (or "
                 "unnamed: ask which task), each with its stretch counted, and `next`: your "
                 "one-line task_report and any evidence (the skill finish-a-task). You never "
                 "change a status yourself. Call it once without arguments; then, only when a next "
                 "step truly follows (without it the work stays unfinished), call it again with "
                 "`proposals`: at most three {title, line}. The answer gives each its similar open "
                 "tasks on the board and the line to show the operator."),
             "inputSchema": {"type": "object", "properties": {
                 "proposals": {"type": "array", "maxItems": 3, "items": {
                     "type": "object",
                     "properties": {
                         "title": {"type": "string", "description": "the task's title, at most 80 characters"},
                         "line": {"type": "string", "description": "one line: what is left and why it follows"},
                     },
                     "required": ["title"]}},
             }}},
            {"name": "next_tasks",
             "description": (
                 "The operator answered the line 'Make these tasks? 1) … 2) …' that task_done gave. "
                 "Send the numbers they chose ([] when they chose none). The server checks them "
                 "against the operator's next message and makes the tasks in the agent column; "
                 "a retry answers the same tasks."),
             "inputSchema": {"type": "object", "properties": {
                 "numbers": {"type": "array", "items": {"type": "integer"},
                             "description": "the numbers the operator chose, such as [1, 3]"}},
                 "required": ["numbers"]}},
            {"name": "undo_find",
             "description": (
                 "The operator typed #undo and said what was a mistake. This returns their request "
                 "and the entries it could mean, numbered: this chat's first, then the project's "
                 "recent ones. Show them as a numbered list and ask for the numbers. Refused when "
                 "the chat has no #undo request: never archive on your own initiative (the skill "
                 "undo-a-mistake)."),
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "undo_propose",
             "description": (
                 "Send the ids the operator chose by number. Returns `confirm`: the text to show as "
                 "it is — what goes to the archive, a warning, and that they reply #undo-yes to "
                 "confirm. Nothing is archived yet."),
             "inputSchema": {"type": "object", "properties": {
                 "ids": {"type": "array", "items": {"type": "string"},
                         "description": "the chosen entries' ids (vs_, rl_, pb_, ep_, sk_, ar_, pm_, tk_)"}},
                 "required": ["ids"]}},
            {"name": "undo_apply",
             "description": (
                 "The operator answered #undo-yes: archive what undo_propose recorded. The server "
                 "checks that the operator's next message after the proposal carries #undo-yes; "
                 "any other answer cancels the request and nothing is archived."),
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "undo_restore",
             "description": "Bring back one entry archived with #undo, with the status it had.",
             "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                             "required": ["id"]}},
            {"name": "cores",
             "description": (
                 "The project's cores (Architecture › cores): id, name, type, reason, tracking, "
                 "the latest note. Read it before core_note, core_attach and core_off to choose "
                 "the matching core; if two match, ask the operator to choose by number."),
             "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}}},
            {"name": "pins",
             "description": (
                 "The messages the operator marked, each whole, newest first: `kind` pin (default; "
                 "#pin, to come back to), carry (#carry and #carry-brief: what survives a context "
                 "compaction, with the brief written for each) or fork (#fork-later: work another agent "
                 "could take, with the command that starts it). `scope` chat (default: this chat) or "
                 "project. `q` keeps the ones whose text holds it. When the operator says \"go back to "
                 "the pin\", read this chat's pins and take up the one they mean."),
             "inputSchema": {"type": "object", "properties": {
                 "kind": {"type": "string", "enum": ["pin", "carry", "fork"]},
                 "scope": {"type": "string", "enum": ["chat", "project"]},
                 "q": {"type": "string"}, "project": {"type": "string"}}}},
            {"name": "carry_brief",
             "description": (
                 "After #carry-brief (the hook's notice names the message): write the brief of that "
                 "message — what it says and the context needed to understand it once the chat is "
                 "compacted (who asked, what for, what was decided), a few sentences, at most 4000 "
                 "characters. After the next compaction it is given back to you instead of the message. "
                 "`message` is <agent_id>#<turn> (or …/reply) as the notice names it; or `turn`, a turn "
                 "of this chat. Only a message of this chat: another chat's, a branch's parent included, "
                 "is refused. Writing it again replaces it."),
             "inputSchema": {"type": "object", "properties": {
                 "message": {"type": "string"}, "turn": {"type": "integer"}, "text": {"type": "string"}},
                 "required": ["text"]}},
            {"name": "core_new",
             "description": (
                 "After the operator's #core-new: a new core. `name` is short (at most 60 "
                 "characters), in the operator's words; `type` is one of capability, feature, "
                 "interface, store, integration, internals, workflow, experiment; `reason` one line "
                 "on why it is kept in view when the message says; `anchors` the files or "
                 "file:symbol paths this core is in, as far as you know; `text` the operator's "
                 "message as typed (its first note). The same name again answers with the existing core."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "name": {"type": "string"}, "type": {"type": "string"},
                     "reason": {"type": "string"}, "text": {"type": "string"},
                     "comment": {"type": "string", "description": "your one line under the operator's text"},
                     "anchors": {"type": "array", "items": {"type": "string"}},
                     "task_id": {"type": "string"},
                 },
                 "required": ["name", "type", "text"],
             }},
            {"name": "core_note",
             "description": (
                 "One note on a core. After #core-note: `text` is the operator's message "
                 "as typed and `comment` your one line (what you did with it, or what it means). "
                 "When finished work changes a core the operator tracks (the hook's notice "
                 "names them): `kind: \"auto\"`, `comment` only — one line on what changed, "
                 "with the task. The operator's notes count as approved; yours wait for approval."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string"}, "text": {"type": "string"}, "comment": {"type": "string"},
                     "kind": {"type": "string", "enum": ["note", "auto"]}, "task_id": {"type": "string"},
                 },
                 "required": ["id"],
             }},
            {"name": "core_attach",
             "description": (
                 "After #core in a message: attach that message to the matching core "
                 "(`turn`: the message's turn number), and this chat's task when it has one "
                 "(`task_id`). A thing attached twice is attached once."),
             "inputSchema": {
                 "type": "object",
                 "properties": {"id": {"type": "string"}, "turn": {"type": "integer"},
                                "task_id": {"type": "string"}, "note": {"type": "string"}},
                 "required": ["id"],
             }},
            {"name": "core_off",
             "description": (
                 "After #core-off, once the operator confirmed which core with a number: "
                 "remove it from view. Its notes and links are kept; the operator can restore it "
                 "on its page."),
             "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
            {"name": "architecture_status",
             "description": (
                 "The operator typed #architecture: which of the three parts are out of "
                 "date — the form for the last scan, the architecture page, the map of the "
                 "program — each with the reason. Do only the needed ones, in that order "
                 "(the skill update-the-architecture)."),
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "architecture_material",
             "description": (
                 "The operator typed #architecture (or #page), or a #scan is ending: what the project's "
                 "architecture page is written from. Returns computed facts about the "
                 "project folder (standing, size, folders, newest files, recent commits), "
                 "the current page with the claims to check again, and the instructions "
                 "with the layout. Then architecture_page."),
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "map_material",
             "description": (
                 "#architecture found the map out of date (or the operator typed #map): what the map of the program is "
                 "written from. Returns computed facts about the repository (languages, "
                 "manifests, build and CI files, environment variables, ports), the "
                 "current map with what is wrong with it, the kinds, verbs and "
                 "templates, and the instructions. Then map_write."),
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "map_write",
             "description": (
                 "Write the next version of the map: one object {template, rows, "
                 "relations, notes} in the shape the instructions give. The answer "
                 "carries warnings (a template kind not answered, a path not found, a "
                 "relation naming no row): fix and write again."),
             "inputSchema": {"type": "object", "properties": {
                 "map": {"type": "object", "description": "{template, rows[], relations[], notes{}}"},
                 "note": {"type": "string", "description": "one line: what this version changed"}},
                 "required": ["map"]}},
            {"name": "architecture_page",
             "description": (
                 "Write the next version of the architecture page: the whole page in "
                 "markdown, in the layout the instructions give, each item a claim with "
                 "`where:` and `seen:`. The answer carries warnings (paths not found, "
                 "items that do not say how you know): fix and write again."),
             "inputSchema": {"type": "object", "properties": {
                 "text": {"type": "string", "description": "the whole page, markdown"},
                 "note": {"type": "string", "description": "one line: what this version changed"}},
                 "required": ["text"]}},
            {"name": "scan_material",
             "description": (
                 "The operator typed #scan: what the scan is written from. "
                 "Returns your last scan of the project, this chat's commits "
                 "since it (another agent's are not your window), the files "
                 "with line counts, the uncommitted files, the counters "
                 "(files_n, lines_add, lines_del, decisions_n) already "
                 "counted, and the instructions for the scan, its file entry "
                 "and its architecture form. Then write_entry, three times."),
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "standup_material",
             "description": (
                 "The project's standup for one day (default: yesterday): "
                 "whether it is written, whether another agent is writing it, "
                 "every message of that day by chat, whole, with the commits each "
                 "turn made, the previous standup, and the instructions for writing it. Pass "
                 "`claim: true` when you are the one who writes it, `clip: true` when the "
                 "operator chose clipped messages. Then "
                 "write_entry {lens: \"standup\", fields: {..., for_date}}."),
             "inputSchema": {"type": "object", "properties": {
                 "date": {"type": "string", "description": "YYMM-DD; default yesterday"},
                 "claim": {"type": "boolean"},
                 "clip": {"type": "boolean", "description": "the start and end of each message only; the operator's choice"},
             }}},
            {"name": "standup_postpone",
             "description": "The operator said later: nobody is asked about this day's standup for `hours` (default 4).",
             "inputSchema": {"type": "object", "properties": {
                 "date": {"type": "string"}, "hours": {"type": "number"}}}},
            {"name": "task_work",
             "description": (
                 "What the repository saw in the turns that named this task: "
                 "the files, with lines added and deleted. Read it before "
                 "writing a `files` evidence item, so you judge the list "
                 "instead of hunting for it."),
             "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                             "required": ["id"]}},
            {"name": "task_evidence_ask",
             "description": (
                 "The operator typed `#evidence`: get the instructions for this "
                 "task. Returns the operator's evidence prompt verbatim, the "
                 "server's short addition, and the files the repository saw. "
                 "Follow them, then call task_evidence."),
             "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                             "required": ["id"]}},
            {"name": "publish_write",
             "description": (
                 "After the operator's #publish (the hook names the card, pu_…): write the card in the same turn. "
                 "`text` only when the operator asked you to write it (\"#publish about X\", \"describe …\"); "
                 "when their message is the text, leave it out — the message is the card's text and stays its "
                 "source. Never rewrite the operator's text unless asked. `context`: the block under the text — "
                 "what was done, for whom, before/after, numbers; when asked for one piece (\"add how it looks "
                 "on a phone\"), write only that piece on top of the context you read. Each write of text or "
                 "context is a version; `base` is the card's rev you read. Attach what belongs to it, by id or "
                 "by path, never guessed: `tasks` (tk_… ids, any project), `notes` (nt_…), `commits` "
                 "({sha, repo}: repo is the repository's folder; left out, the project's), `files` ({path, "
                 "title}: any file on this machine, copied onto the card, up to 25MB), `images` ({path, title}: "
                 "screenshots, original size), `links` ({title, url}, http(s)). `merge`: a card this chat "
                 "made a moment ago about the same thing, folded into this one. The same attachment again is "
                 "the existing one."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string", "description": "the card, pu_… (the hook names it)"},
                     "text": {"type": "string", "description": "the card's text; only when the operator asked you to write it"},
                     "context": {"type": "string", "description": "the context block under the text (markdown)"},
                     "note": {"type": "string", "description": "one line: what this version changed"},
                     "base": {"type": "integer", "description": "the card's rev you read; refused if someone wrote since"},
                     "tasks": {"type": "array", "items": {"type": "string"}, "description": "tk_… ids"},
                     "notes": {"type": "array", "items": {"type": "string"}, "description": "nt_… ids"},
                     "commits": {"type": "array", "items": {
                         "type": "object",
                         "properties": {"sha": {"type": "string"}, "repo": {"type": "string"}},
                         "required": ["sha"]}},
                     "files": {"type": "array", "items": {
                         "type": "object",
                         "properties": {"path": {"type": "string", "description": "the file on this machine; read by the tool"},
                                        "title": {"type": "string"}},
                         "required": ["path"]}},
                     "images": {"type": "array", "items": {
                         "type": "object",
                         "properties": {"path": {"type": "string", "description": "the image file on this machine; read by the tool"},
                                        "title": {"type": "string"}},
                         "required": ["path"]}},
                     "links": {"type": "array", "items": {
                         "type": "object",
                         "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                         "required": ["url"]}},
                     "merge": {"type": "string", "description": "pu_… of a card this chat made about the same thing, folded into this one"},
                 },
                 "required": ["id"]}},
            {"name": "publish_attach",
             "description": (
                 "The older name of publish_write, kept for chats that know it: attaches images "
                 "(`path` on this machine, or `data_base64`), links, files, tasks, notes and commits to "
                 "the card. Prefer publish_write, which also writes the card's text and context."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string"},
                     "images": {"type": "array", "items": {
                         "type": "object",
                         "properties": {"title": {"type": "string"},
                                        "path": {"type": "string", "description": "the image file on this machine; read by the tool"},
                                        "ext": {"type": "string", "enum": ["png", "jpg", "jpeg", "webp", "gif"]},
                                        "data_base64": {"type": "string"}},
                         "required": []}},
                     "links": {"type": "array", "items": {
                         "type": "object",
                         "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                         "required": ["url"]}},
                 },
                 "required": ["id"]}},
            {"name": "entrypoints",
             "description": (
                 "The project's entry points: each topic's id, name, state, what it is, its ways in "
                 "and the last messages of where it stopped. Read it to find the topic of your work. "
                 "With `id` (the one the #entrypoint notice named): what the operator's command opened — "
                 "a new topic, a new version of the record of the topic they chose, or nothing yet "
                 "(pending: entrypoint_ask first) — with the record as it is and what to write."),
             "inputSchema": {"type": "object", "properties": {
                 "project": {"type": "string"},
                 "id": {"type": "string", "description": "ep_… from the #entrypoint notice"}}}},
            {"name": "entrypoint_stop",
             "description": (
                 "One message of where a topic stopped, in one or two plain sentences: what is done, "
                 "what is not, what waits for whom. At #done, once for the task's topic (the task_done "
                 "answer names it, with `task_id`). Never the record, never a list of everything."),
             "inputSchema": {"type": "object", "properties": {
                 "id": {"type": "string", "description": "the entry point, ep_…"},
                 "text": {"type": "string", "description": "at most 1000 characters"},
                 "task_id": {"type": "string", "description": "the task of this topic it is about"}},
                 "required": ["id", "text"]}},
            {"name": "entrypoint_way",
             "description": (
                 "Add a way in to a topic: what the operator opens to look at the work — a page, a "
                 "site, an app, a file, a folder, a script, an artifact — with where it opens, the "
                 "command that starts it, its folder and port. Only when you made it or a way to open "
                 "it changed (port, command, folder). `way_id` changes one an agent wrote; one the "
                 "operator wrote is theirs."),
             "inputSchema": {"type": "object", "properties": {
                 "id": {"type": "string", "description": "the entry point, ep_…"},
                 "way_id": {"type": "string"},
                 "way": {"type": "object", "properties": {
                     "name": {"type": "string", "description": "a few words, what the operator calls it"},
                     "kind": {"type": "string", "enum": ["page", "site", "app", "file", "folder", "script", "artifact"]},
                     "url": {"type": "string"}, "path": {"type": "string"},
                     "command": {"type": "string", "description": "the start command, run in `folder`"},
                     "folder": {"type": "string"}, "port": {"type": "integer"},
                     "note": {"type": "string", "description": "one line the reader needs"}},
                     "required": ["name", "kind"]}},
                 "required": ["id", "way"]}},
            {"name": "entrypoint_shot",
             "description": (
                 "A screenshot of a way in you made or changed, taken while it is up: the image file's "
                 "`path` on this machine (PNG, JPEG, GIF or WebP; read by the tool) and a one-line "
                 "caption of what it shows. `replaces`: a shot of yours it takes the place of."),
             "inputSchema": {"type": "object", "properties": {
                 "id": {"type": "string"}, "way_id": {"type": "string"},
                 "path": {"type": "string"}, "caption": {"type": "string"},
                 "replaces": {"type": "string"}},
                 "required": ["id", "way_id", "path"]}},
            {"name": "entrypoint_offer",
             "description": (
                 "Only when something new to open appeared (a page, a server, a site, a dashboard, an "
                 "artifact with a link) or a way to open one changed, and it is not a one-off result: "
                 "`name` (a few words) and `why`. Answers the topics like it and `next`: add the way in "
                 "to the match, or the one line that offers a new entry point to the operator. Writes "
                 "nothing; the operator keeps it with #entrypoint."),
             "inputSchema": {"type": "object", "properties": {
                 "name": {"type": "string"}, "why": {"type": "string"}},
                 "required": ["name"]}},
            {"name": "entrypoint_ask",
             "description": (
                 "Right after the operator's #entrypoint (the id the notice named). Nothing is made yet: "
                 "the operator chooses the topic. Send `name`, your proposal for a new topic, about four "
                 "words, from their words or this chat. Answers the topics of this project the command may "
                 "mean, numbered, with a last line for a new topic, and `show`: the offer the server wrote, in "
                 "the operator's language, several lines per topic. Give it exactly as given, every line, as the "
                 "end of your reply; never shorten, translate or retell it. When the operator typed a topic's exact name, it "
                 "answers instead that a new version of that topic was opened."),
             "inputSchema": {"type": "object", "properties": {
                 "id": {"type": "string", "description": "the id from the #entrypoint notice"},
                 "name": {"type": "string", "description": "a name for a new topic, at most 80 characters"}},
                 "required": ["id", "name"]}},
            {"name": "entrypoint_answer",
             "description": (
                 "The operator answered the entrypoint_ask line. Send `number`, the line they chose (0 when "
                 "none), and `name` only when they wrote one, as they wrote it. The server checks both "
                 "against their next message; an existing topic opens a new version of its record for this "
                 "chat, the new-topic line makes the topic. Answers the topic, its record and what to write; "
                 "a retry answers the same."),
             "inputSchema": {"type": "object", "properties": {
                 "number": {"type": "integer", "description": "the number the operator chose, 0 when none"},
                 "name": {"type": "string", "description": "the name the operator wrote, if any"},
                 "id": {"type": "string", "description": "the #entrypoint's id, when the chat asked about two"}},
                 "required": ["number"]}},
            {"name": "task_topic",
             "description": "Set the topic of a task: the entry point (ep_…) its work belongs to; \"\" clears.",
             "inputSchema": {"type": "object", "properties": {
                 "id": {"type": "string", "description": "the task, tk_…"},
                 "topic": {"type": "string", "description": "the entry point, ep_…"}},
                 "required": ["id", "topic"]}},
            {"name": "task_evidence",
             "description": (
                 "Attach evidence to a task. Follow the operator's instructions: "
                 "they arrive in the task_report answer, or from "
                 "task_evidence_ask after `#evidence`. Each item has a one-line "
                 "title. `text`: markdown. `image`: base64 (png/jpg/webp/gif). "
                 "`files`: what was touched. `change`: what landed. At most "
                 f"{evidence_max} items in one post; the operator's prompt usually "
                 "asks for 1–3. The same item posted twice is one item."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string"},
                     "items": {"type": "array", "items": {
                         "type": "object",
                         "properties": {
                             "kind": {"type": "string", "enum": ["text", "image", "files", "change"]},
                             "title": {"type": "string"},
                             "body": {"type": "string", "description": "text items: the markdown"},
                             "data_base64": {"type": "string", "description": "image items: the file, base64"},
                             "ext": {"type": "string", "enum": ["png", "jpg", "jpeg", "webp", "gif"]},
                             "start_here": {
                                 "type": "string",
                                 "description": "files items: the one file or file:Symbol to open first",
                             },
                             "paths": {
                                 "type": "array",
                                 "description": "files items: one record per file touched",
                                 "items": {
                                     "type": "object",
                                     "properties": {
                                         "path": {"type": "string"},
                                         "action": {"type": "string",
                                                    "enum": ["created", "modified", "deleted", "renamed"]},
                                         "lines_add": {"type": "integer"},
                                         "lines_del": {"type": "integer"},
                                         "importance": {"type": "integer", "description": "1-5"},
                                         "blast_radius": {"type": "integer", "description": "1-10"},
                                         "test_coverage": {"type": "string",
                                                           "enum": ["covered", "partial", "untested"]},
                                         "security_surface": {"type": "boolean"},
                                         "why": {"type": "string", "description": "one sentence"},
                                     },
                                     "required": ["path"],
                                 },
                             },
                             "changes": {
                                 "type": "array",
                                 "description": "change items: one record per thing that landed",
                                 "items": {
                                     "type": "object",
                                     "properties": {
                                         "op": {"type": "string", "enum": ARCH_OPS},
                                         "type": {"type": "string", "enum": sorted(ARCH_TYPES)},
                                         "name": {"type": "string"},
                                         "path": {"type": "array", "items": {"type": "string"}},
                                         "note": {"type": "string", "description": "one line"},
                                     },
                                     "required": ["op", "type", "name"],
                                 },
                             },
                         },
                         "required": ["kind", "title"],
                     }},
                 },
                 "required": ["id", "items"],
             }},
            {"name": "task_update",
             "description": (
                 "Edit one task; every change lands in its history log. "
                 "Status belongs to the operator — changing it is refused "
                 "unless the task allows auto-manage; use task_report when "
                 "your work is done. The one exception: a card you created "
                 "in the `agent` column you may drop with "
                 "`status: \"done-archived\"`. Priority, sprint, due date "
                 "and the operator's switches are refused by name. Title, "
                 "description and today_on: only on a task you created; on "
                 "the operator's or another agent's task they are refused — "
                 "add a comment instead (open on any task). A task the "
                 "operator made from a message of your chat (the #task-title "
                 "notice names it): you set its title once, ≤ 80 characters."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string"},
                     "status": {"type": "string", "enum": task_status},
                     "title": {"type": "string"},
                     "today_on": {"type": "string",
                                  "description": "ISO date to plan it for that day; empty clears "
                                                 "(a task you created only)"},
                     "description": {"type": "string",
                                     "description": "the task's text: what is wrong or wanted, and where "
                                                    "(not on a #now card: its text is the operator's message)"},
                     "comment": {"type": "string",
                                 "description": "a note of yours, added after the task's text under "
                                                "'--- comment from agent:'; each call adds one"},
                 },
                 "required": ["id"],
             }},
            {"name": "interpret",
             "description": (
                 "Write the interpretation of a kept #vision, #rule, #problem or "
                 "#entrypoint (the id the [slightly-parallel] notice named): the "
                 "message read with the conversation around it, in plain words. "
                 "An entry point's record has five sections: What, Where, How, State, Next; it is written "
                 "only right after the operator's #entrypoint in this chat, once they chose the topic "
                 "(entrypoint_ask, entrypoint_answer): a new one, or an existing one, which opens a new "
                 "version of its record. "
                 "Each write is a version; the current one is what the page shows."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "lens": {"type": "string", "enum": ["vision", "rule", "problem", "entrypoint"]},
                     "id": {"type": "string"},
                     "text": {"type": "string", "description": "markdown"},
                     "note": {"type": "string", "description": "one line on what changed"},
                 },
                 "required": ["lens", "id", "text"],
             }},
            {"name": "skill_draft",
             "description": (
                 "Write SKILL.md (and the files beside it) for a kept #skill: "
                 "the steps as they were done in this session. Leave `files` "
                 "out to keep the ones the skill has; send {} to remove them. "
                 "The answer lists `checks` — fix every error and post again."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string", "description": "sk_… from the notice"},
                     "skill_md": {"type": "string"},
                     "files": {"type": "object",
                               "description": "{relative path: text}"},
                     "note": {"type": "string"},
                 },
                 "required": ["id", "skill_md"],
             }},
            {"name": "artifact_write",
             "description": (
                 "Make or refresh the record of an artifact you wrote as a "
                 "folder at <data_root>/projects/<project>/artifacts/<name>/ (the "
                 "[slightly-parallel] #artifact notice names the path): ARTIFACT.md "
                 "with name, kind and description on top, the files beside "
                 "it. Call it again after editing the folder."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string", "description": "ar_… from the notice"},
                     "name": {"type": "string",
                              "description": "the folder name: lowercase letters, digits, single hyphens"},
                     "kind": {"type": "string", "enum": ["dataset", "document", "page", "app", "other"]},
                     "description": {"type": "string",
                                     "description": "what it is and what it is for, one or two sentences"},
                 },
                 "required": ["id", "name", "kind", "description"],
             }},
            {"name": "doc_version",
             "description": (
                 "Post the finished text of a Storyboard document as its next "
                 "version — after the operator handed you the document's pack "
                 "(the doc id dc_… is on the pack's second line). Markdown "
                 "body, the whole document; note is one line on what this "
                 "version changed. An unknown id is refused."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string", "description": "the doc id (dc_…) from the pack"},
                     "body": {"type": "string", "description": "the finished document, in markdown"},
                     "note": {"type": "string", "description": "optional: one line on what this version changed"},
                 },
                 "required": ["id", "body"],
             }},
            {"name": "deck",
             "description": "Every running sprint block across all projects: clocks, tasks, timers.",
             "inputSchema": {"type": "object", "properties": {
                 "days": {"type": "integer", "description": "include a per-day series this long"}}}},
            {"name": "search",
             "description": "Find tasks, decisions and agents by text.",
             "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}},
                             "required": ["q"]}},
            {"name": "project",
             "description": "One project's bundle: summary, decisions, activity, agents.",
             "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}}},
            {"name": "doctor",
             "description": "Data-integrity report over the whole data root — run when something looks wrong.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "checkup",
             "description": "After #sp: is Slightly Parallel working for this chat and this folder — the folder's "
                            "project, this chat recorded, MCP, capture, hooks, contract, skills, data, disk, backups, "
                            "the server's memory and errors. Each finding: ok, note, concern or unknown, with its "
                            "evidence and next step. Reads only.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "usage",
             "description": (
                 "The tokens this chat used, the plan limits and the project's day. `block` is the text "
                 "#usage prints: give it as it is, in a code block, and add nothing but one line when "
                 "something stands out (a cache rebuild, a limit over 80%). `summary` holds the numbers "
                 "of the Usage page for `project` (this chat's project, or all) over `range` (today, "
                 "7d or 30d). Reads only."),
             "inputSchema": {"type": "object", "properties": {
                 "project": {"type": "string", "description": "a project code, or all"},
                 "range": {"type": "string", "enum": ["today", "7d", "30d"]}}}},
            {"name": "usage_prices_material",
             "description": ("Only after the operator's #usage-price: the models the chats used, the API prices "
                             "now, the pages to read and the instructions. Then usage_prices_write."),
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "usage_prices_write",
             "description": ("Only after the operator's #usage-price: one update of the API prices, dollars per "
                             "million tokens, read from the providers' own pages. The days before keep their "
                             "prices. Answers what changed, and warnings."),
             "inputSchema": {"type": "object", "properties": {
                 "models": {"type": "object", "description": "{model: {input, write_5m, write_1h, read, output, over_tokens?, over?}}; write_5m and write_1h may be null"},
                 "sources": {"type": "array", "items": {"type": "string"}, "description": "the https pages the prices were read from"},
                 "note": {"type": "string", "description": "one line: what you left out, and why"}},
                 "required": ["models", "sources"]}},
            {"name": "note_write",
             "description": (
                 "Write a note: a text the operator will read again or keep, instead of a long chat reply "
                 "or a markdown file — context to come back to, a text to paste elsewhere, a review with "
                 "pictures, a plan for helpers, a helper's report, the steps only the operator can do. "
                 "`text` is markdown whose first line is `# Title`; `## ` headings make its sections. "
                 "Blocks: ```copy Title …``` (a text to paste, with a copy button); `- [ ] step` "
                 "(a checklist the operator ticks); ```choice Question with lines `1. option` (the "
                 "operator picks one; read it back with notes {id}); ```gallery with lines "
                 "`![caption](file.png)`; `:::fold Title` … `:::` (folded); ```mermaid. Ids like tk_… "
                 "ep_… dc_… show as live chips. `images`: the picture files the text names, read here. "
                 "`id` writes the next version of a note (any chat of the project); `base` is the "
                 "version you read. Then say one line in the chat and the note's id."),
             "inputSchema": {"type": "object", "properties": {
                 "text": {"type": "string", "description": "the markdown, first line `# Title`"},
                 "kind": {"type": "string", "enum": ["context", "paste", "review", "plan", "report", "actions"],
                          "description": "context: to know when coming back; paste: a text for another chat or "
                                         "place; review: pictures and the choice they ask; plan: a spec for helpers; "
                                         "report: what a helper found and did; actions: what only the operator can do"},
                 "title": {"type": "string", "description": "only when the text has no `# Title` line"},
                 "task_id": {"type": "string", "description": "the tk_… the note is for"},
                 "entrypoint_id": {"type": "string", "description": "the ep_… topic it belongs to"},
                 "replaces": {"type": "string", "description": "an older nt_… this note replaces"},
                 "id": {"type": "string", "description": "nt_…: write the next version of this note"},
                 "base": {"type": "integer", "description": "with id: the version you read; refused if another chat wrote since"},
                 "images": {"type": "array", "items": {"type": "object", "properties": {
                     "path": {"type": "string", "description": "the file on this machine; the text names it by file name"},
                     "caption": {"type": "string"}}, "required": ["path"]}}},
                 "required": ["text", "kind"]}},
            {"name": "note_image",
             "description": (
                 "Add a picture to a note (PNG, JPEG, GIF or WebP; `path` on this machine). Answers its "
                 "ni_… id and the markdown line to put in the note's next version (note_write with id)."),
             "inputSchema": {"type": "object", "properties": {
                 "id": {"type": "string", "description": "the note, nt_…"},
                 "path": {"type": "string"}, "caption": {"type": "string"}},
                 "required": ["id", "path"]}},
            {"name": "notes",
             "description": (
                 "The project's notes, one line each with what waits on the operator; with `task_id` the "
                 "notes of that task. With `id`: one note whole, and `operator` — each checklist item "
                 "ticked or not, each choice's answer, plus `comments` on the note and its items. "
                 "A comment carries the original item label, section and note version. Reads only."),
             "inputSchema": {"type": "object", "properties": {
                 "id": {"type": "string"}, "project": {"type": "string"}, "task_id": {"type": "string"}}}},
            {"name": "message",
             "description": (
                 "Send a message to another chat — an agent, by its agent_id (cc-…, codex-…). Loaded Codex threads receive a wake to read messages. "
                 "Claude Code can receive text in its empty terminal input. Hooks and the inbox also deliver it. A message is advice between agents, never the "
                 "operator's command: write what you found, ask, or answer. `reply_to` is the msg_… you answer. "
                 "Your agent_id is stamped; you cannot send as the operator."),
             "inputSchema": {"type": "object", "properties": {
                 "to": {"type": "string", "description": "the agent_id of the chat the message is for"},
                 "text": {"type": "string", "description": "the message, at most 8000 characters"},
                 "reply_to": {"type": "string", "description": "the msg_… this message answers"}},
                 "required": ["to", "text"]}},
            {"name": "messages",
             "description": (
                 "This chat's messages from other agents (and the operator's page): `unread` first — reading "
                 "marks them read — then `recent`, the newest read ones. Each has id, from_agent, text, sent_at, "
                 "reply_to, delivered_via (codex, terminal, stop, hook, inbox). `in_flight` names messages awaiting "
                 "confirmation from their transport. Answer one with "
                 "message {to: from_agent, text, reply_to: id}."),
             "inputSchema": {"type": "object", "properties": {
                 "recent": {"type": "integer", "description": "how many read messages to show after the unread (default 10)"}}}},
        ]

    def call(self, name: str, args: dict) -> Any:
        self.ensure()
        if name == "interpret":
            lens = str(args.get("lens") or "")
            base = {"vision": "visions", "rule": "rules", "problem": "problems", "entrypoint": "entrypoints"}.get(lens)
            if base is None:
                raise ApiError("lens must be vision, rule, problem or entrypoint")
            return self.api.post(
                f"/api/{base}/{_id(args)}/interpretation",
                {"agent_id": self.identity()["agent_id"],
                 "text": str(args.get("text") or ""), "note": str(args.get("note") or "")},
            )
        if name == "artifact_write":
            return self.api.post(
                f"/api/artifacts/{_id(args)}/write",
                {"agent_id": self.identity()["agent_id"],
                 "name": str(args.get("name") or ""), "kind": str(args.get("kind") or ""),
                 "description": str(args.get("description") or "")},
            )
        if name == "doc_version":
            return self.api.post(
                f"/api/docs/{_id(args)}/versions",
                {"agent_id": self.identity()["agent_id"],
                 "body": str(args.get("body") or ""), "note": str(args.get("note") or "")},
            )
        if name == "skill_draft":
            body: dict[str, Any] = {
                "agent_id": self.identity()["agent_id"],
                "skill_md": str(args.get("skill_md") or ""),
                "note": str(args.get("note") or ""),
            }
            if "files" in args and args.get("files") is not None:
                body["files"] = args["files"]
            return self.api.post(f"/api/skills/{_id(args)}/draft", body)
        if name == "write_entry":
            lens = str(args.get("lens") or "")
            spec = self.lenses.get(lens)
            if spec is None:
                allowed = sorted(n for n, l in self.lenses.items() if l.get("agent_write", True))
                raise ApiError(f"unknown lens {lens!r} — one of: {', '.join(allowed)}")
            if args.get("fields") is not None and not isinstance(args.get("fields"), dict):
                raise ApiError("fields is an object: the entry's fields by name")
            # Identity last, over anything of the same name in `fields`.
            payload = {**(args.get("fields") or {}), **self._stamp()}
            # Fields by name only: the numbered storage slots (l1…l4) are not
            # a way in. A name the lens lacks is refused, never routed around.
            self._check_names(lens, spec, payload)
            self._check_vocab(lens, payload)
            return self.api.post(f"/api/{spec['base']}", payload)
        if name == "update_entry":
            lens = str(args.get("lens") or "")
            spec = self.lenses.get(lens)
            if spec is None:
                raise ApiError(f"unknown lens {lens!r}")
            changes = dict(args.get("changes") or {})

            def _unknown(spec: dict) -> list[str]:
                texts = spec.get("text_fields") or []
                open_texts = texts if spec.get("headline_mutable") else texts[1:]
                return [k for k in changes
                        if k not in spec["mutable"] and k not in open_texts]
            unknown = _unknown(spec)
            if unknown and self._refresh(lens):
                spec = self.lenses.get(lens) or spec
                unknown = _unknown(spec)
            if unknown:
                first = (spec.get("text_fields") or [""])[0]
                raise ApiError(
                    f"{lens} cannot change {', '.join(unknown)} — it takes "
                    f"{', '.join((spec.get('text_fields') or [])[1:] + spec['mutable']) or 'nothing'}. "
                    f"The first field ({first or 'the headline'}) is fixed once written: "
                    "write a new entry instead."
                )
            self._check_vocab(lens, changes)
            # Identity last, as every other write: without it the server read
            # the change as the operator's, and an agent could end a sprint or
            # retire a skill — the operator-only gates look at who writes.
            return self.api.post(f"/api/{spec['base']}/{_id(args)}/update",
                                 {**changes, "agent_id": self.identity()["agent_id"]})
        if name == "tasks":
            project = args.get("project") or self.identity()["project"]
            q = f"/api/tasks?project={urllib.parse.quote(str(project))}"
            if args.get("status"):
                q += f"&status={urllib.parse.quote(str(args['status']))}"
            return self.api.get(q)
        if name == "task_done":
            who = self.identity()
            raw = args.get("proposals")
            if raw is None or raw == "" or raw == []:
                # Without proposals: the answer it always was.
                return self.api.get(f"/api/done-tags?agent_id={urllib.parse.quote(str(who['agent_id']))}")
            return self.api.post("/api/done-tags", {"agent_id": who["agent_id"], "proposals": raw})
        if name == "next_tasks":
            return self.api.post("/api/next-tasks/make",
                                 {"agent_id": self.identity()["agent_id"], "numbers": args.get("numbers")})
        if name in ("undo_find", "undo_propose", "undo_apply", "undo_restore"):
            who = self.identity()["agent_id"]
            if name == "undo_find":
                return self.api.get(f"/api/undo/candidates?agent_id={urllib.parse.quote(str(who))}")
            if name == "undo_propose":
                return self.api.post("/api/undo/propose", {"agent_id": who, "ids": _list(args, "ids")})
            if name == "undo_apply":
                return self.api.post("/api/undo/apply", {"agent_id": who})
            return self.api.post("/api/undo/restore", {"agent_id": who, "id": _id(args)})
        if name == "architecture_status":
            return self.api.get(
                f"/api/architecture/status?project={urllib.parse.quote(str(self.identity()['project']))}")
        if name in ("architecture_material", "architecture_page"):
            who = self.identity()
            if name == "architecture_material":
                return self.api.get(
                    f"/api/architecture/page/material?project={urllib.parse.quote(str(who['project']))}")
            return self.api.post("/api/architecture/page", {
                "project": who["project"], "agent_id": who["agent_id"],
                "text": args.get("text") or "", "note": args.get("note") or ""})
        if name in ("map_material", "map_write"):
            who = self.identity()
            if name == "map_material":
                return self.api.get(f"/api/map/material?project={urllib.parse.quote(str(who['project']))}")
            return self.api.post("/api/map", {
                "project": who["project"], "agent_id": who["agent_id"],
                "map": args.get("map") or {}, "note": args.get("note") or ""})
        if name == "scan_material":
            who = self.identity()
            return self.api.get(
                f"/api/scans/material?project={urllib.parse.quote(str(who['project']))}"
                f"&agent_id={urllib.parse.quote(str(who['agent_id']))}")
        if name in ("standup_material", "standup_postpone"):
            who = self.identity()
            project = urllib.parse.quote(str(who["project"]))
            date = str(args.get("date") or "")
            if name == "standup_postpone":
                return self.api.post("/api/standups/postpone",
                                     {"project": who["project"], "date": date,
                                      "hours": args.get("hours") or 4})
            if args.get("claim"):
                got = self.api.post("/api/standups/claim",
                                    {"project": who["project"], "date": date,
                                     "agent_id": who["agent_id"]})
                if not got.get("claimed"):
                    return got  # written already, or another agent is writing it
            clip = "&clip=true" if args.get("clip") else ""
            return self.api.get(f"/api/standups/material?project={project}&date={urllib.parse.quote(date)}{clip}")
        if name == "task_evidence_ask":
            return self.api.get(f"/api/tasks/{_id(args)}/evidence/ask")
        if name == "task_work":
            return self.api.get(f"/api/tasks/{_id(args)}/work")
        if name == "task_evidence":
            return self.api.post(
                f"/api/tasks/{_id(args)}/evidence",
                {"agent_id": self.identity()["agent_id"],
                 "items": args.get("items") or []},
            )
        if name in ("publish_write", "publish_attach"):
            return self._publish(name, args)
        if name in ("entrypoints", "entrypoint_stop", "entrypoint_way", "entrypoint_shot", "entrypoint_offer",
                    "entrypoint_ask", "entrypoint_answer", "task_topic"):
            return self._entrypoint(name, args)
        if name in ("note_write", "note_image", "notes"):
            return self._note(name, args)
        if name == "task_story":
            return self.api.post(
                f"/api/tasks/{_id(args)}/story",
                {"agent_id": self.identity()["agent_id"],
                 "request_id": str(args.get("request_id") or ""),
                 "body": str(args.get("body") or ""),
                 "images": args.get("images") or []},
            )
        if name == "pins":
            kind = str(args.get("kind") or "pin")
            path = {"pin": "pins", "carry": "carries", "fork": "forks"}.get(kind)
            if path is None:
                raise ApiError("kind is pin, carry or fork")
            scope = str(args.get("scope") or "chat")
            if scope not in ("chat", "project"):
                raise ApiError("scope is chat or project")
            who = self.identity()
            query = {"full": "true", "q": str(args.get("q") or ""),
                     "project": str(args.get("project") or who["project"])}
            if scope == "chat":
                query["agent_id"] = who["agent_id"]
            got = self.api.get(f"/api/{path}?{urllib.parse.urlencode(query)}")
            keep = ("target", "kind", "turn", "side", "at", "marked_at", "source", "text", "reply",
                    "brief", "brief_at", "state", "command", "given_at", "left_out_at", "agent_id", "project")
            return {"total": got.get("total", 0),
                    "items": [{k: i[k] for k in keep if i.get(k) not in (None, "")} for i in got.get("items") or []]}
        if name == "message":
            body = {"agent_id": self.identity()["agent_id"], "to": str(args.get("to") or ""),
                    "text": str(args.get("text") or "")}
            if args.get("reply_to"):
                body["reply_to"] = str(args["reply_to"])
            return self.api.post("/api/messages", body)
        if name == "messages":
            recent = args.get("recent")
            q = f"?recent={int(recent)}" if isinstance(recent, int) and not isinstance(recent, bool) else ""
            return self.api.post(f"/api/messages/inbox{q}", {"agent_id": self.identity()["agent_id"]})
        if name == "carry_brief":
            who = self.identity()
            target = str(args.get("message") or "").strip()
            if not target:
                if args.get("turn") is None:
                    raise ApiError("carry_brief needs the message (<agent_id>#<turn>) or this chat's turn")
                target = f"{who['agent_id']}#{int(args['turn'])}"
            return self.api.post("/api/carries/brief", {
                "agent_id": who["agent_id"], "target": target, "text": str(args.get("text") or "")})
        if name == "cores":
            code = args.get("project") or self.identity()["project"]
            return self.api.get(f"/api/cores?project={urllib.parse.quote(str(code))}")
        if name == "core_new":
            who = self.identity()
            return self.api.post("/api/cores", {
                "project": who["project"], "agent_id": who["agent_id"],
                "name": str(args.get("name") or ""), "type": str(args.get("type") or ""),
                "reason": str(args.get("reason") or ""), "text": str(args.get("text") or ""),
                "comment": str(args.get("comment") or ""),
                "anchors": [a for a in _list(args, "anchors") if a.strip()],
                "task_id": str(args.get("task_id") or ""),
            })
        if name == "core_note":
            return self.api.post(f"/api/cores/{_id(args)}/notes", {
                "agent_id": self.identity()["agent_id"],
                "text": str(args.get("text") or ""), "comment": str(args.get("comment") or ""),
                "kind": str(args.get("kind") or "note"), "task_id": str(args.get("task_id") or ""),
            })
        if name == "core_attach":
            who = self.identity()
            out: dict[str, Any] = {"attached": []}
            if args.get("turn") is not None:
                out["attached"].append(self.api.post(f"/api/cores/{_id(args)}/links", {
                    "agent_id": who["agent_id"], "kind": "message",
                    "target": f"{who['agent_id']}#{int(args['turn'])}", "note": str(args.get("note") or "")}))
            if args.get("task_id"):
                out["attached"].append(self.api.post(f"/api/cores/{_id(args)}/links", {
                    "agent_id": who["agent_id"], "kind": "task", "target": str(args["task_id"]),
                    "note": str(args.get("note") or "")}))
            if not out["attached"]:
                raise ApiError("core_attach needs the message's turn, a task_id, or both")
            return out
        if name == "core_off":
            return self.api.post(f"/api/cores/{_id(args)}/off", {"agent_id": self.identity()["agent_id"]})
        if name == "task_commits":
            return self.api.post(
                f"/api/tasks/{_id(args)}/commits",
                {"agent_id": self.identity()["agent_id"], "shas": _list(args, "shas")},
            )
        if name == "task_report":
            return self.api.post(
                f"/api/tasks/{_id(args)}/report",
                {"agent_id": self.identity()["agent_id"],
                 "summary": str(args.get("summary") or "")},
            )
        if name == "task_update":
            body = {k: v for k, v in args.items() if k != "id" and v is not None}
            self._check_vocab("task", body)
            body["actor"] = self.identity()["agent_id"]
            return self.api.post(f"/api/tasks/{_id(args)}/update", body)
        if name == "deck":
            days = int(args.get("days") or 0)
            return self.api.get(f"/api/sprints/deck{f'?days={days}' if days else ''}")
        if name == "search":
            return self.api.get(f"/api/search?q={urllib.parse.quote(str(args.get('q') or ''))}")
        if name == "project":
            code = args.get("code") or self.identity()["project"]
            return self.api.get(f"/api/project/{urllib.parse.quote(str(code))}")
        if name == "doctor":
            return self.api.get("/api/doctor")
        if name == "checkup":
            # A chat the hook never saw has no identity: the checkup says so
            # itself, rather than this call failing before it can.
            try:
                who = self.identity()
            except ApiError:
                who = {}
            # How the chat was found goes along: a guess is not this chat.
            q = urllib.parse.urlencode({"cwd": self.cwd, "agent_id": str(who.get("agent_id") or ""),
                                        "identity": str(who.get("identity_source") or "")})
            return self.api.get(f"/api/checkup?{q}")
        if name == "usage_prices_material":
            return self.api.get("/api/usage/prices/material")
        if name == "usage_prices_write":
            who = self.identity()
            return self.api.post("/api/usage/prices", {
                "agent_id": who["agent_id"], "models": args.get("models") if isinstance(args.get("models"), dict) else {},
                "sources": _list(args, "sources"), "note": args.get("note") or ""})
        if name == "usage":
            rng = str(args.get("range") or "today")
            if rng not in ("today", "7d", "30d"):
                raise ApiError("range must be today, 7d or 30d")
            # A chat the hook never saw has no block of its own: the summary
            # still answers (for the project asked, else all).
            try:
                who = self.identity()
            except ApiError:
                who = {}
            block = ""
            if who.get("agent_id"):
                try:
                    chat = self.api.get(f"/api/usage/chat/{urllib.parse.quote(str(who['agent_id']))}?block=true")
                    block = str(chat.get("block") or "")
                except ApiError:
                    block = ""
            q = urllib.parse.urlencode({"project": str(args.get("project") or who.get("project") or "all"),
                                        "range": rng})
            return {"block": block, "summary": self.api.get(f"/api/usage?{q}")}
        raise ApiError(f"unknown tool: {name}")

    # -- resources ---------------------------------------------------------

    def _note(self, name: str, args: dict) -> Any:
        """The notes tools. A picture is read here, on the agent's machine."""
        def text(key: str, required: bool = False) -> str:
            v = args.get(key)
            if v is None or v == "":
                if required:
                    raise ApiError(f"{key} is required")
                return ""
            if not isinstance(v, str):
                raise ApiError(f"{key} is text, not {'a list' if isinstance(v, list) else type(v).__name__}")
            return v

        def picture(path: str, i: str) -> str:
            p = pathlib.Path(path).expanduser()
            if not p.is_file():
                raise ApiError(f"{i}{p} is not a file")
            if p.stat().st_size > 12 * 1024 * 1024:
                raise ApiError(f"{i}{p.name} is over 12MB")
            return base64.b64encode(p.read_bytes()).decode("ascii")

        if name == "notes":
            if text("id"):
                return self.api.get(f"/api/notes/{_id(args)}/agent")
            project = text("project") or self.identity()["project"]
            q = urllib.parse.urlencode({"project": project, "task": text("task_id")})
            return self.api.get(f"/api/notes/list?{q}")
        if name == "note_image":
            return self.api.post(f"/api/notes/{_id(args)}/images", {
                "agent_id": self.identity()["agent_id"], "caption": text("caption"),
                "data_base64": picture(text("path", True), "")})
        raw = args.get("images") or []
        if not isinstance(raw, list):
            raise ApiError("images is a list of {path, caption}")
        images = []
        for i, item in enumerate(raw, start=1):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
                raise ApiError(f"image {i}: an object with path (and caption)")
            if item.get("caption") is not None and not isinstance(item.get("caption"), str):
                raise ApiError(f"image {i}: caption is text")
            images.append({"name": item["path"], "caption": item.get("caption") or pathlib.Path(item["path"]).stem,
                           "data_base64": picture(item["path"], f"image {i}: ")})
        base = args.get("base")
        if base is not None and (isinstance(base, bool) or not isinstance(base, int)):
            raise ApiError("base is the version number you read, a number")
        who = self.identity()
        body: dict[str, Any] = {"agent_id": who["agent_id"], "project": who["project"],
                                "text": text("text", True), "kind": text("kind", True), "title": text("title"),
                                "id": text("id"), "images": images}
        for key in ("task_id", "entrypoint_id", "replaces"):
            if key in args:
                body[key] = text(key)
        if base is not None:
            body["base"] = base
        return self.api.post("/api/notes/write", body)

    def _publish(self, name: str, args: dict) -> Any:
        """publish_write, and publish_attach forwarding to it. A file or an
        image given by `path` is read here, on the agent's machine: base64
        through a tool call is tens of thousands of characters."""
        def read(path: Any, label: str, most: int) -> tuple[pathlib.Path, str]:
            if not isinstance(path, str) or not path:
                raise ApiError(f"{label}: path is the file on this machine")
            p = pathlib.Path(path).expanduser()
            if not p.is_file():
                raise ApiError(f"{label}: {p} is not a file")
            if p.stat().st_size > most:
                raise ApiError(f"{label}: {p.name} is over {most // (1024 * 1024)}MB")
            return p, base64.b64encode(p.read_bytes()).decode("ascii")

        def items(key: str) -> list:
            v = args.get(key)
            if v in (None, ""):
                return []
            if not isinstance(v, list):
                raise ApiError(f"{key} is a list")
            return v

        images = []
        for i, item in enumerate(items("images"), 1):
            if not isinstance(item, dict):
                raise ApiError(f"image {i}: an object with title and path")
            if item.get("path") and not item.get("data_base64"):
                p, data = read(item["path"], f"image {i}", 12 * 1024 * 1024)
                item = {**item, "data_base64": data, "source": str(p),
                        "ext": str(item.get("ext") or p.suffix.lstrip(".").lower() or "png"),
                        "title": str(item.get("title") or p.stem)}
                item.pop("path", None)
            images.append(item)
        files = []
        for i, item in enumerate(items("files"), 1):
            if isinstance(item, str):
                item = {"path": item}
            if not isinstance(item, dict):
                raise ApiError(f"file {i}: an object with path and title")
            p, data = read(item.get("path"), f"file {i}", 25 * 1024 * 1024)
            files.append({"name": p.name, "source": str(p), "title": str(item.get("title") or p.name),
                          "data_base64": data})
        body: dict[str, Any] = {"agent_id": self.identity()["agent_id"]}
        for key in ("text", "context", "note", "merge"):
            v = args.get(key)
            if v is None:
                continue
            if not isinstance(v, str):
                raise ApiError(f"{key} is text, not {'a list' if isinstance(v, list) else type(v).__name__}")
            body[key] = v
        base = args.get("base")
        if base is not None:
            if isinstance(base, bool) or not isinstance(base, int):
                raise ApiError("base is the card's rev you read, a number")
            body["base"] = base
        for key in ("tasks", "notes", "commits", "links"):
            if items(key):
                body[key] = items(key)
        if images:
            body["images"] = images
        if files:
            body["files"] = files
        return self.api.post(f"/api/publishing/cards/{_id(args)}/write", body)

    def _entrypoint(self, name: str, args: dict) -> Any:
        """The entry point tools. Text arguments are text: a list or an
        object where a sentence is meant is refused here, before a request."""
        def text(key: str, required: bool = False) -> str:
            v = args.get(key)
            if v is None or v == "":
                if required:
                    raise ApiError(f"{key} is required")
                return ""
            if not isinstance(v, str):
                raise ApiError(f"{key} is text, not {'a list' if isinstance(v, list) else type(v).__name__}")
            return v
        who = self.identity()
        if name == "entrypoint_ask":
            return self.api.post("/api/entrypoints/ask",
                                 {"agent_id": who["agent_id"], "id": text("id", True), "name": text("name")})
        if name == "entrypoint_answer":
            return self.api.post("/api/entrypoints/answer", {
                "agent_id": who["agent_id"], "number": args.get("number"), "name": text("name"),
                "id": text("id")})
        if name == "entrypoints":
            if text("id"):
                return self.api.get(f"/api/entrypoints/{_id(args)}/command")
            project = text("project") or who["project"]
            got = self.api.get(f"/api/entrypoints/desk?project={urllib.parse.quote(str(project))}")
            return {"topics": [{k: t.get(k) for k in ("id", "name", "title", "state", "what", "ways", "stops", "open_tasks")}
                               for t in got.get("topics") or []]}
        if name == "entrypoint_offer":
            words = " — ".join(x for x in (text("name", True), text("why")) if x)
            q = urllib.parse.urlencode({"project": who["project"], "text": words})
            return self.api.get(f"/api/entrypoints/similar?{q}")
        if name == "task_topic":
            return self.api.post(f"/api/tasks/{_id(args)}/topic",
                                 {"agent_id": who["agent_id"], "entrypoint_id": text("topic")})
        if name == "entrypoint_stop":
            return self.api.post(f"/api/entrypoints/{_id(args)}/stops",
                                 {"agent_id": who["agent_id"], "text": text("text", True), "task_id": text("task_id")})
        if name == "entrypoint_way":
            way = args.get("way")
            if not isinstance(way, dict):
                raise ApiError("way is an object: {name, kind, url?, path?, command?, folder?, port?, note?}")
            body: dict[str, Any] = {"agent_id": who["agent_id"], "way": way}
            if text("way_id"):
                body["id"] = text("way_id")
            return self.api.post(f"/api/entrypoints/{_id(args)}/ways", body)
        # entrypoint_shot: the image is read here, on the agent's machine.
        p = pathlib.Path(text("path", True)).expanduser()
        if not p.is_file():
            raise ApiError(f"{p} is not a file")
        if p.stat().st_size > 12 * 1024 * 1024:
            raise ApiError(f"{p.name} is over 12MB")
        return self.api.post(f"/api/entrypoints/{_id(args)}/shots", {
            "agent_id": who["agent_id"], "way_id": text("way_id", True), "caption": text("caption") or p.stem,
            "replaces": text("replaces"), "data_base64": base64.b64encode(p.read_bytes()).decode("ascii")})

    def resource_defs(self) -> list[dict]:
        return [
            {"uri": "sp://contract", "name": "The entry-writing contract",
             "description": "SLIGHTLY-PARALLEL.md — when to write which entry and how the layers are read",
             "mimeType": "text/markdown"},
            {"uri": "sp://schema", "name": "The write schema",
             "description": "Per-lens fields, requirements and vocabularies, from the live server",
             "mimeType": "application/json"},
            {"uri": "sp://rules", "name": "Active rules",
             "description": "The operator's standing corrections for this project",
             "mimeType": "application/json"},
            {"uri": "sp://health", "name": "Server health",
             "description": "Degradation state and load errors", "mimeType": "application/json"},
        ]

    def read_resource(self, uri: str) -> tuple[str, str]:
        if uri == "sp://contract":
            path = _REPO_ROOT / "SLIGHTLY-PARALLEL.md"
            return path.read_text(encoding="utf-8"), "text/markdown"
        if uri == "sp://schema":
            return json.dumps(self.schema, indent=2), "application/json"
        if uri == "sp://rules":
            project = self.identity()["project"]
            rules = self.api.get(
                f"/api/rules?project={urllib.parse.quote(project)}&status=active")
            return json.dumps(rules, indent=2), "application/json"
        if uri == "sp://health":
            return json.dumps(self.api.get("/api/health"), indent=2), "application/json"
        raise ApiError(f"unknown resource: {uri}")

    # -- prompts -----------------------------------------------------------

    # -- prompts: the contract's commands, as the contract words them -------
    #
    # Built from the `command:` lines of the contract parts, so a command
    # added to the contract is a prompt here with no second list to keep.
    # The text of a prompt is the part itself: one source for the steps.

    PARTS_DIR = _REPO_ROOT / "prompts" / "contract"

    def _commands(self) -> dict[str, tuple[str, str]]:
        """name → (what the command does, the contract part that says how)."""
        out: dict[str, tuple[str, str]] = {}
        for path in sorted(self.PARTS_DIR.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if not text.startswith("---\n") or "\n---" not in text[4:]:
                continue
            head, body = text[4:].split("\n---", 1)
            if re.search(r"^enabled:\s*false\s*$", head, re.M):
                continue
            for line in re.findall(r"^command:\s*(.+)$", head, re.M):
                tag, _, what = line.partition("|")
                # "#problem solved <id or text>" → problem-solved; "<…>" is an argument.
                name = "-".join(re.sub(r"<[^>]*>", " ", tag).strip().lstrip("#").split())
                if not name or name in out:
                    continue
                out[name] = (
                    what.strip() or tag.strip(),
                    f"The operator typed {tag.strip()}: {what.strip()}\n\nDo what this "
                    f"part of the Slightly Parallel contract says.\n\n{body.strip()}",
                )
        return out

    def prompt_defs(self) -> list[dict]:
        return [{"name": name, "description": what, "arguments": []}
                for name, (what, _) in self._commands().items()]

    def get_prompt(self, name: str) -> dict:
        what, text = self._commands().get(name, (None, None))
        if text is None:
            raise ApiError(f"unknown prompt: {name}")
        return {"description": what, "messages": [
            {"role": "user", "content": {"type": "text", "text": text}}]}


# ---------------------------------------------------------------------------
# The stdio JSON-RPC loop
# ---------------------------------------------------------------------------


def _result(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle(tr: Translator, msg: dict) -> dict | None:
    """One request → one response (None for notifications)."""
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if msg_id is None:
        return None  # notifications (initialized, cancelled) need no answer

    # Only a tools/call names its Codex thread; nothing carries over to the next request.
    tr.thread = codex_thread(params) if method == "tools/call" else ""

    if method == "initialize":
        info = params.get("clientInfo") if isinstance(params, dict) else None
        tr.client = str(info.get("name") or "") if isinstance(info, dict) else ""
        client_version = str(params.get("protocolVersion") or PROTOCOL_VERSION)
        return _result(msg_id, {
            # Echo the client's version when it is one we can serve; the
            # surface used here is stable across 2024-11 → 2025-06.
            "protocolVersion": client_version,
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        try:
            return _result(msg_id, {"tools": tr.tool_defs()})
        except ApiError as exc:
            return _error(msg_id, -32000, str(exc))
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        try:
            if not isinstance(args, dict):
                raise ApiError("arguments is an object")
            out = tr._by_name(tr.call(name, args))
            return _result(msg_id, {"content": [
                {"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}
            ], "isError": False})
        except ApiError as exc:
            return _result(msg_id, {"content": [
                {"type": "text", "text": str(exc)}
            ], "isError": True})
        except (TypeError, ValueError, AttributeError, KeyError) as exc:
            # An argument of the wrong shape (a number for a text, a text for a
            # list) is the tool's answer, not a protocol error that ends the call.
            return _result(msg_id, {"content": [
                {"type": "text", "text": f"{name}: an argument has the wrong shape ({exc}); see the tool's schema"}
            ], "isError": True})
    if method == "resources/list":
        return _result(msg_id, {"resources": tr.resource_defs()})
    if method == "resources/read":
        uri = str(params.get("uri") or "")
        try:
            text, mime = tr.read_resource(uri)
            return _result(msg_id, {"contents": [
                {"uri": uri, "mimeType": mime, "text": text}]})
        except (ApiError, OSError) as exc:
            return _error(msg_id, -32002, str(exc))
    if method == "prompts/list":
        return _result(msg_id, {"prompts": tr.prompt_defs()})
    if method == "prompts/get":
        try:
            return _result(msg_id, tr.get_prompt(str(params.get("name") or "")))
        except ApiError as exc:
            return _error(msg_id, -32602, str(exc))
    return _error(msg_id, -32601, f"method not found: {method}")


def _utf8_pipes() -> None:
    """JSON-RPC over stdio is UTF-8. Python's default for a pipe is the
    locale's encoding (cp1252 on many Windows machines), where a Cyrillic
    title raised and ended the server."""
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _utf8_pipes()
    base = os.environ.get("SP_API", loopback_url())
    api = Api(base)
    # A server that is not up yet is no error here: the first call waits for it.
    tr = Translator(api, os.getcwd())
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue  # a batch or a bare value: not a request this server answers
        try:
            reply = handle(tr, msg)
        except Exception as exc:  # noqa: BLE001 — the loop must survive anything
            reply = _error(msg.get("id"), -32603, f"internal: {exc}")
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
