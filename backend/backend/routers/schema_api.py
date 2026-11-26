"""The write contract as data — GET /api/schema.

Everything a client needs to construct a valid entry, derived from the same
registries the API enforces with: ENTITIES for shape, READ_MODELS for what a
reader requires, ENUM_FIELDS for the vocabularies that gate writes. The MCP
translator builds its tools from this endpoint at startup, so its schemas
come from the process that will enforce them — version skew between the two
cannot reintroduce drift.

Also GET /api/whoami: the capture hook leaves a per-cwd session breadcrumb
(agent id, project); a local client presents its cwd and gets the identity
to stamp on entries — agents stop carrying identity by hand.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..db import ViewStore
from ..hookshared import process_started, session_key
from .deps import etag_for, get_store, json_response, maybe_304
from ..entities import ENTITIES
from ..tasklib import AGENT_TAGS
from .. import chatstore, entry_fields, memberships
from ..mcp import TOOLS as _MCP_TOOLS
from ..entitylib import AGENT_CREATE_REFUSED
from .lenses import ENUM_FIELDS, HEADLINE_REQUIRED, OPERATOR_ONLY
from .architecture import GROUPS as _ARCH_GROUPS, OPS as _ARCH_OPS

router = APIRouter()

# Stamped by the server (or the translator) — never part of a tool's input.
_STAMPED = {"id", "md_ref", "created_date", "created_time", "project", "agent_id"}

# One line per lens on when an agent reaches for it — the contract's §4,
# compressed. Lenses not listed still appear in the schema, undocumented.
# A lens in OPERATOR_ONLY says the refusal instead, so the line an agent
# reads and the answer the server gives are the same text.
_WHEN = {
    "standup": "A new day started: the day's outcomes for one project, one standup per day.",
    "decision": "A choice was made between alternatives; `alternatives` holds what was rejected and why.",
    "vision": "A product idea worth keeping, not yet a commitment.",
    "problem": "You are blocked — log it before workarounds bury it.",
    "entrypoint": "The operator wrote #entrypoint: a topic they come back to; its record (what, where, how, state, next) is written through `interpret`, never as a new entry.",
    "file": "The per-path judgment behind a scan: what moved and which moves matter.",
    "architecture": "The form behind a scan: eight groups, each checked or with its changes.",
    "idea": "A thought worth keeping, filed by title.",
    "note": "Reference text, filed by title.",
    "task": "Board work the operator asked you to write: title, description, tags, status agent.",
    "time_entry": "A manual time record; live clocks use /api/time/start instead.",
    "snippet": "A shell command worth keeping, with a label.",
}


def _field_schema(ent, col: str) -> dict:
    enum = ENUM_FIELDS.get(ent.name, {}).get(col)
    if enum:
        return {"type": "string", "enum": sorted(enum)}
    if col in ent.int_columns:
        return {"type": "integer"}
    if col in ent.float_columns:
        return {"type": "number"}
    return {"type": "string"}


def build_schema() -> dict:
    lenses = []
    for ent in ENTITIES.values():
        fields: dict[str, dict] = {}
        for col in ent.columns:
            if col in _STAMPED:
                continue
            fields[col] = _field_schema(ent, col)
        # What the entry holds, by name (entry_fields.py). The storage
        # slots behind the names are not published.
        fields.pop("l1", None)
        text = entry_fields.fields_for(ent.name, ent.columns)
        for f in text:
            shape = ({"type": "array", "items": {"type": "string"}}
                     if f.kind == "list" else {"type": "string"})
            fields[f.name] = {**fields.get(f.name, shape), "description": f.holds}
        headline = next((f.name for f in text if f.slot == "l1"), "")
        if ent.name == "task":
            # A task's text is its own column, kept by the tasks router
            # (routers/tasks_extra.py), not a storage slot. Without it here
            # the translator's name gate refused every #task.
            fields["description"] = {"type": "string",
                                     "description": "2–6 plain lines: what is wrong or wanted, and where"}
            # An agent's tags: the names as text, comma-separated; a list of
            # the same names is accepted (tasklib.agent_tags).
            fields["tags"] = {"type": "string", "description": (
                "1–3 of " + ", ".join(AGENT_TAGS) + ", comma-separated; a list of these names is the same")}
        refused = OPERATOR_ONLY.get(ent.name) or AGENT_CREATE_REFUSED.get(ent.name)
        lenses.append({
            "name": ent.name,
            "base": ent.list_key.replace("_", "-") if ent.name != "activity" else "activity",
            "headline_field": ent.headline_field,
            "id_prefix": ent.id_prefix,
            # An agent's create is refused here (routers/lenses.py): the lens
            # says so in its own line, and the MCP translator keeps it out of
            # the lens list an agent picks from.
            "agent_write": not refused,
            # Made only by the operator, yet an agent changes some of its
            # fields (an entry point's topic): update_entry offers it.
            "agent_update": not OPERATOR_ONLY.get(ent.name),
            "when_to_use": f"Operator only — {refused}." if refused else _WHEN.get(ent.name, ""),
            "fields": fields,
            "headline": headline,
            "text_fields": [f.name for f in text],
            # A standup is rewritten whole, its summary too (entry_fields.HEADLINE_MUTABLE).
            "headline_mutable": ent.name in entry_fields.HEADLINE_MUTABLE,
            "required": [headline] if ent.name in HEADLINE_REQUIRED and headline else [],
            "mutable": sorted(ent.mutable_fields),
        })
    scan_text = entry_fields.fields_for("scan")
    lenses.append({
        "name": "scan",
        "base": "scans",
        "headline_field": "l1",
        "id_prefix": "sn_",
        "agent_write": True,
        "when_to_use": "A checkpoint: what changed since the last scan. Then the file entry and the architecture form.",
        "fields": {
            **{f.name: {**({"type": "array", "items": {"type": "string"}} if f.kind == "list"
                           else {"type": "string"}), "description": f.holds} for f in scan_text},
            "files_n": {"type": "integer"}, "lines_add": {"type": "integer"},
            "lines_del": {"type": "integer"}, "decisions_n": {"type": "integer"},
            "scope": {"type": "string"},
        },
        "headline": "summary",
        "text_fields": [f.name for f in scan_text],
        "required": ["summary"],
        "mutable": ["files_n", "lines_add", "lines_del", "decisions_n", "scope"],
    })
    from .evidence import MAX_ITEMS as _EVIDENCE_MAX_ITEMS
    return {
        "version": 2,
        "stamped_by_server": sorted(_STAMPED - {"id", "md_ref"}),
        # The caps the server enforces, so a tool description states the
        # number the refusal will use.
        "limits": {"evidence_items": _EVIDENCE_MAX_ITEMS},
        "vocabularies": {
            name: {field: sorted(vals) for field, vals in fields.items()}
            for name, fields in ENUM_FIELDS.items()
        },
        # The architecture form's closed vocabulary, which a task's `change`
        # evidence uses too. Here so the MCP translator reads it from the
        # process that enforces it, like everything else on this endpoint.
        # The MCP tools, from the one list (mcp.TOOLS). Pages and docs read
        # them here instead of keeping a list of their own.
        "tools": [{"name": n, "summary": t} for n, t in _MCP_TOOLS.items()],
        "architecture": {
            "groups": {g: list(ts) for g, ts in _ARCH_GROUPS.items()},
            "ops": list(_ARCH_OPS),
        },
        "lenses": lenses,
    }


@router.get("/api/schema")
def schema(request: Request, store: ViewStore = Depends(get_store)) -> Response:
    etag = etag_for("schema:v1", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response(build_schema(), etag)


# ---------------------------------------------------------------------------
# Session identity for local clients
# ---------------------------------------------------------------------------

SESSIONS_DIR = ".sessions"


def breadcrumb_path(data_root: Path, cwd: str) -> Path:
    """The folder's breadcrumb, named by its one spelling (hookshared.folder_key)."""
    from ..hookshared import folder_digest
    return data_root / SESSIONS_DIR / f"{folder_digest(cwd)}.json"


def _raw_breadcrumb_path(data_root: Path, cwd: str) -> Path:
    """The name a hook from before round 5 gave it: the path as the tool spelled it."""
    import hashlib
    return data_root / SESSIONS_DIR / f"{hashlib.sha1(cwd.encode('utf-8')).hexdigest()[:12]}.json"


#: How near the shared process must be, in both chains, to be the chat's
#: own tool. Measured on Claude Code: the hook's chain is [its shell, claude,
#: the terminal's bash, the terminal]; the MCP server's is [claude, bash, …].
#: The tool is at most one step up from either (a launcher may sit between);
#: farther up is a terminal or a shell that other chats and scripts share.
OWN_TOOL_DEPTH = 1


def _crumb_by_process(folder: Path, pids: str, everywhere: bool = False) -> tuple[dict | None, str]:
    """The chat in this folder that shares a parent process with the client,
    and how sure that is: ``process`` when the shared process is near both
    (the chat's own tool), ``shared-parent`` when it is only a common
    ancestor (a terminal, a shell — a guess). The nearest shared parent wins,
    and of two at the same distance the newer. (None, "") when nothing is
    shared or nothing was sent."""
    try:
        chain = [int(p) for p in pids.split(",") if p.strip()][:16]
    except ValueError:
        return None, ""
    if not chain or not folder.is_dir():
        return None, ""
    best: tuple[tuple[bool, int, float], dict, bool] | None = None
    matches: list[tuple[dict, list[int]]] = []
    started: dict[int, float | None] = {}

    def reused(pid: int, crumb: dict) -> bool:
        # A process with this number that started after the breadcrumb was
        # written is not the one the breadcrumb names (Windows reuses numbers).
        if pid not in started:
            started[pid] = process_started(pid)
        at = float(crumb.get("at") or 0)
        return bool(at and started[pid] and started[pid] > at + 2)

    for file in folder.glob("*/*.json" if everywhere else "*.json"):
        try:
            crumb = json.loads(file.read_text(encoding="utf-8"))
            theirs = [int(p) for p in crumb.get("pids") or []]
        except (OSError, ValueError, TypeError):
            continue
        near = next((i for i, pid in enumerate(chain) if pid in theirs and not reused(pid, crumb)), None)
        if near is None:
            continue
        matches.append((crumb, [p for p in theirs if not reused(p, crumb)]))
        own = near <= OWN_TOOL_DEPTH and theirs.index(chain[near]) <= OWN_TOOL_DEPTH
        # A chat's own tool wins over a guess through a shared terminal,
        # whatever the distances; then the nearest, then the newest.
        key = (not own, near, -float(crumb.get("at") or 0))
        if best is None or key < best[0]:
            best = (key, crumb, own)
    if best is None:
        return None, ""
    agent = str(best[1].get("agent_id") or "")
    if agent.startswith("codex-"):
        # Codex's shared app-server daemon is above the hook and the MCP
        # server of every Codex chat: a process two Codex chats share names
        # neither (a Codex that sends no thread id, an MCP server started
        # before the fix).
        pid = chain[best[0][1]]
        rivals = {str(c.get("agent_id") or "") for c, mine in matches if pid in mine}
        if len({a for a in rivals if a.startswith("codex-")}) > 1:
            return None, "ambiguous"
    return best[1], "process" if best[2] else "shared-parent"


def _crumb_by_thread(data_root: Path, thread: str) -> dict | None:
    """The Codex chat whose thread is ``thread``: its own breadcrumb (the
    hook names it by the thread), else its chat folder, which a subagent's
    thread has without a breadcrumb. None when no captured chat has it."""
    crumb: dict | None = None
    for file in (data_root / SESSIONS_DIR).glob(f"*/{thread}.json"):
        try:
            got = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(got, dict) and str(got.get("agent_id") or "").startswith("codex-") and (
                crumb is None or float(got.get("at") or 0) > float(crumb.get("at") or 0)):
            crumb = got
    if crumb is not None:
        return crumb
    agent = f"codex-{session_key('codex', thread)}"
    for _project, chat in chatstore.folders_of(data_root, agent, has="meta.json"):
        meta_path = chat / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            at = meta_path.stat().st_mtime
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict) and str(meta.get("session_ref") or "").lower() == thread.lower():
            return {"agent_id": agent, "project": chatstore.project_of(chat, meta),
                    "session_id": thread, "at": at}
    return None


@router.get("/api/whoami")
def whoami(
    cwd: str = Query(..., description="the client's working directory"),
    pids: str = Query("", description="the client's parent processes, nearest first"),
    thread: str = Query("", description="the Codex thread the call came from (its _meta)"),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Identity for the session running in ``cwd``.

    The capture hook writes a breadcrumb per working directory on every
    prompt, and one per chat with the processes above the hook. A client
    that sends its own parents (``pids``) gets the chat whose tool process
    it shares — the nearest one, so two chats in one folder each get their
    own. With no match the newest chat in the folder answers. 404 means no
    captured session runs there.

    Codex runs every chat under one app-server daemon, so processes cannot
    tell its chats apart: its MCP calls name their ``thread``, which is the
    chat. A process that several Codex chats share answers 409, never the
    newest of them.
    """
    if thread:
        # A Codex call names its own thread: that chat, or none — never a
        # guess by folder or by the daemon's processes.
        crumb = _crumb_by_thread(store.data_root, thread) if re.fullmatch(r"[0-9A-Za-z-]{8,80}", thread) else None
        if crumb is None:
            raise HTTPException(status_code=404, detail=(
                f"cannot tell which Codex chat is calling: thread {thread[:80]} has no captured "
                "chat (its first message not recorded yet, or capture not set up here). "
                "Tell the user, and write nothing as an agent."))
        return _with_membership(store, _identity(crumb, "thread"))
    crumb, source = None, ""
    for path in dict.fromkeys((breadcrumb_path(store.data_root, cwd), _raw_breadcrumb_path(store.data_root, cwd))):
        crumb, source = _crumb_by_process(path.with_suffix(""), pids)
        if source == "ambiguous":
            break
        if crumb is None:
            try:
                crumb, source = json.loads(path.read_text(encoding="utf-8")), "folder"
            except (OSError, json.JSONDecodeError):
                crumb = None
        if crumb is not None:
            break
    if crumb is None and source != "ambiguous":
        # Nothing for this folder: the chat may run in another spelling of it
        # or in a subfolder (a chat started there, or a cd). Its own tool
        # process, shared with this client, still names it; a guess through a
        # shared terminal does not.
        crumb, source = _crumb_by_process(store.data_root / SESSIONS_DIR, pids, everywhere=True)
        if source not in ("process", "ambiguous"):
            crumb = None
    if source == "ambiguous":
        raise HTTPException(status_code=409, detail=(
            "cannot tell which Codex chat is calling: its processes are the shared Codex "
            "app-server's, which several Codex chats run under, and the call named no thread. "
            "Nothing was written or read as this chat; restart Codex (its MCP servers) or "
            "update it, or tell the user."))
    if crumb is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"no captured session for cwd {cwd}. The capture hook writes the "
                "breadcrumb on each message: none here means a chat started in "
                "another folder, a first message not recorded yet, or capture not "
                "set up or failing here. Tell the user, and write nothing as an agent."
            ),
        )
    return _with_membership(store, _identity(crumb, source))


def _with_membership(store: ViewStore, who: dict) -> dict:
    """whoami's answer with the chat's projects (tk_d1d25a4d step 3): its
    ``home`` (where a write that names no project goes), its ``members``
    and its task ``level``. A chat not recorded yet is its folder's project."""
    view = memberships.agent_view(store, who["agent_id"])
    if view is None or not view.members:
        home, members, level = who["project"], [who["project"]] if who["project"] else [], 2
    else:
        home, members, level = view.home or who["project"], list(view.members), view.level
    return {**who, "home": home, "members": members, "level": level}


def _identity(crumb: dict, source: str) -> dict:
    age_min = round((time.time() - float(crumb.get("at") or 0)) / 60)
    return {
        "agent_id": str(crumb.get("agent_id") or ""),
        "project": str(crumb.get("project") or ""),
        "session_id": str(crumb.get("session_id") or ""),
        "age_min": age_min,
        # How the chat was found: its Codex thread or its own tool process
        # (sure), a shared terminal or shell (a guess), or the newest chat in
        # the folder (a guess).
        "identity_source": source,
    }
