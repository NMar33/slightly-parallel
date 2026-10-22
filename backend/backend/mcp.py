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

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# This process's parents: the capture hook reads them the same way, and the
# two find each other by the tool process they share (hookshared.py).
from .hookshared import ancestors

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "slightly-parallel", "version": "1.2.0"}
VIA_HEADER = "X-SP-Via"
VIA_VALUE = "mcp"
# How long a call waits for the server to come up before it fails: the
# backend restarts in seconds, and a session that opened during one must
# not lose MCP for its whole life.
SCHEMA_RETRY_S = 20.0
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Every tool, in one line each. The one list: the server's refusal, the
# schema (`tools`), the Info page and the docs all read this, and a test
# holds it equal to what tool_defs() really serves.
TOOLS: dict[str, str] = {
    "write_entry": "Create an entry: what it holds and its lens's columns, by name.",
    "update_entry": "Change an entry's lifecycle fields or its text.",
    "tasks": "The open board of a project.",
    "task_update": "Edit a task. Status is the operator's.",
    "task_report": "Say a task is done, in your opinion.",
    "task_done": "After #done: what the operator's #done moved, and each task's stretch of the chat.",
    "undo_find": "After #undo: the operator's request and the entries it could mean, numbered.",
    "undo_propose": "Send the entries the operator chose to archive; answers the confirmation to show.",
    "undo_apply": "After #undo-yes: archive the confirmed entries. Refused without the operator's #undo-yes.",
    "undo_restore": "Bring back one entry archived with #undo.",
    "task_evidence_ask": "After #evidence: the operator's instructions for this task.",
    "task_evidence": "Attach evidence to a task.",
    "task_work": "The files the repository saw this task touch.",
    "task_story": "Post a piece on a task, under a request id the operator gave.",
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
}


# The server is on this computer: an HTTP_PROXY in the agent's environment
# sent the calls to the proxy, which cannot reach 127.0.0.1 here.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


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
            with _DIRECT.open(req, timeout=30) as resp:
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
                         if l["mutable"] and l.get("agent_write", True))
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
            {"name": "task_done",
             "description": (
                 "The operator typed #done: the server moves the task to done as the operator's "
                 "verdict and gives it its stretch of the chat. This returns what moved (or "
                 "unnamed: ask which task), each with its stretch counted, and `next`: your "
                 "one-line task_report and any evidence (the skill finish-a-task). You never "
                 "change a status yourself."),
             "inputSchema": {"type": "object", "properties": {}}},
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
                 "and the operator's switches are refused by name."),
             "inputSchema": {
                 "type": "object",
                 "properties": {
                     "id": {"type": "string"},
                     "status": {"type": "string", "enum": task_status},
                     "title": {"type": "string"},
                     "today_on": {"type": "string",
                                  "description": "ISO date to plan it for that day; empty clears"},
                     "description": {"type": "string",
                                     "description": "the task's text: what is wrong or wanted, and where"},
                 },
                 "required": ["id"],
             }},
            {"name": "interpret",
             "description": (
                 "Write the interpretation of a kept #vision, #rule, #problem or "
                 "#entrypoint (the id the [slightly-parallel] notice named): the "
                 "message read with the conversation around it, in plain words. "
                 "An entry point has five sections: What, Where, How, State, Next. "
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
            return self.api.get(f"/api/done-tags?agent_id={urllib.parse.quote(str(who['agent_id']))}")
        if name in ("undo_find", "undo_propose", "undo_apply", "undo_restore"):
            who = self.identity()["agent_id"]
            if name == "undo_find":
                return self.api.get(f"/api/undo/candidates?agent_id={urllib.parse.quote(str(who))}")
            if name == "undo_propose":
                return self.api.post("/api/undo/propose", {"agent_id": who, "ids": list(args.get("ids") or [])})
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
        if name == "task_story":
            return self.api.post(
                f"/api/tasks/{_id(args)}/story",
                {"agent_id": self.identity()["agent_id"],
                 "request_id": str(args.get("request_id") or ""),
                 "body": str(args.get("body") or ""),
                 "images": args.get("images") or []},
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
        raise ApiError(f"unknown tool: {name}")

    # -- resources ---------------------------------------------------------

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

    if method == "initialize":
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
            out = tr._by_name(tr.call(name, args))
            return _result(msg_id, {"content": [
                {"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}
            ], "isError": False})
        except ApiError as exc:
            return _result(msg_id, {"content": [
                {"type": "text", "text": str(exc)}
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
    base = os.environ.get("SP_API", "http://127.0.0.1:8123")
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
