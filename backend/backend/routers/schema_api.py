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
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..db import ViewStore
from .deps import etag_for, get_store, json_response, maybe_304
from ..entities import ENTITIES
from .. import entry_fields
from ..mcp import TOOLS as _MCP_TOOLS
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
        refused = OPERATOR_ONLY.get(ent.name)
        lenses.append({
            "name": ent.name,
            "base": ent.list_key.replace("_", "-") if ent.name != "activity" else "activity",
            "headline_field": ent.headline_field,
            "id_prefix": ent.id_prefix,
            # An agent's create is refused here (routers/lenses.py): the lens
            # says so in its own line, and the MCP translator keeps it out of
            # the lens list an agent picks from.
            "agent_write": not refused,
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
    import hashlib
    digest = hashlib.sha1(cwd.encode("utf-8")).hexdigest()[:12]
    return data_root / SESSIONS_DIR / f"{digest}.json"


def _crumb_by_process(folder: Path, pids: str) -> dict | None:
    """The chat in this folder that shares a parent process with the client:
    the nearest shared parent wins, and of two at the same distance the
    newer. None when nothing is shared (or nothing was sent)."""
    try:
        chain = [int(p) for p in pids.split(",") if p.strip()][:16]
    except ValueError:
        return None
    if not chain or not folder.is_dir():
        return None
    best: tuple[int, float, dict] | None = None
    for file in folder.glob("*.json"):
        try:
            crumb = json.loads(file.read_text(encoding="utf-8"))
            theirs = {int(p) for p in crumb.get("pids") or []}
        except (OSError, ValueError, TypeError):
            continue
        near = next((i for i, pid in enumerate(chain) if pid in theirs), None)
        if near is None:
            continue
        key = (near, -float(crumb.get("at") or 0))
        if best is None or key < (best[0], best[1]):
            best = (key[0], key[1], crumb)
    return best[2] if best else None


@router.get("/api/whoami")
def whoami(
    cwd: str = Query(..., description="the client's working directory"),
    pids: str = Query("", description="the client's parent processes, nearest first"),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Identity for the session running in ``cwd``.

    The capture hook writes a breadcrumb per working directory on every
    prompt, and one per chat with the processes above the hook. A client
    that sends its own parents (``pids``) gets the chat whose tool process
    it shares — the nearest one, so two chats in one folder each get their
    own. With no match the newest chat in the folder answers. 404 means no
    captured session runs there.
    """
    path = breadcrumb_path(store.data_root, cwd)
    crumb = _crumb_by_process(path.with_suffix(""), pids)
    try:
        crumb = crumb or json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=404,
            detail=(
                f"no captured session for cwd {cwd}. The capture hook writes the "
                "breadcrumb on the first turn: tell the user the hook is not "
                "installed in this directory, and write nothing as an agent."
            ),
        )
    age_min = round((time.time() - float(crumb.get("at") or 0)) / 60)
    return {
        "agent_id": str(crumb.get("agent_id") or ""),
        "project": str(crumb.get("project") or ""),
        "session_id": str(crumb.get("session_id") or ""),
        "age_min": age_min,
    }
