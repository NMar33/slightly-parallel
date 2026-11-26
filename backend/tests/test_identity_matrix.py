"""The identity-protection matrix (tk_0b8a32d2): every agent write path ×
every identity field × where the agent puts it.

Each cell sends one write with one forged identity field through the real
translator into the real gated server, then reads the data folder: the
forged value stored is «PASSED THROUGH», a refusal that wrote nothing is
«refused», a write that stored the true identity is «stamped over». The
matrix is built by walking the paths, never filled in by hand; with
IDENTITY_MATRIX_OUT set it is written there as JSON (the report compares
master with the branch). The assertions then hold every cell to the one
decision table, mcp_args.IDENTITY.

Over plain HTTP (agents.mcp_only off) there is no stamp: the body is the
agent's own claim, and the walk shows what the server does with two claims
that disagree.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

import pytest

from backend import mcp
from tests.conftest import make_chat
from tests.test_membership_tools import A, PAGE, world  # noqa: F401 — the fixture

pytestmark = pytest.mark.strict_membership

B = "cc-bbbb2222"
FORGED = {
    "agent_id": "cc-forged999", "actor": "cc-forged998", "from": "cc-forged997", "from_agent": "cc-forged996",
    "agent": "cc-forged995", "created_by": "cc-forged994", "session": "FORGEDSESSION1", "session_id": "FORGEDSESSION2",
    "created_date": "0101-01", "created_time": "04:44", "project": "GAMMA",
}


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")
            and "logs/" not in p.relative_to(root).as_posix()}


def _stored(root: Path, before: dict[str, str], value: str) -> tuple[bool, bool]:
    """(something was written, the value is in what was written)."""
    after = _files(root)
    touched = [k for k, h in after.items() if before.get(k) != h]
    found = False
    for rel in touched:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if value in text:
            found = True
    return bool(touched), found


def _seed(c, root: Path) -> dict[str, str]:
    make_chat(root, "ALPHA", B, [("2026-11-20T10:00:00", "hello", "ok")])
    c.app.state.store.rebuild()
    task = c.post("/api/tasks", json={"project": "ALPHA", "title": "Seed task", "status": "doing",
                                      "agent_id": "operator", "created_date": "2611-20",
                                      "created_time": "10:00"}).json()["metadata"]["id"]
    doc = c.post("/api/docs", json={"project": "ALPHA", "kind": "post", "title": "Seed doc"}).json()["doc"]["id"]
    return {"task": task, "doc": doc}


# The write tools walked, each with a call that succeeds (n keeps each one new).
def _tools(tr: mcp.Translator, ids: dict[str, str]) -> dict[str, Callable[[int], dict[str, Any]]]:
    decision = tr.call("write_entry", {"lens": "decision", "fields": {"decision": "seed decision", "why": "x"}})
    did = decision["metadata"]["id"]
    return {
        "write_entry": lambda n: {"lens": "decision", "fields": {"decision": f"chose sqlite {n}", "why": "small"}},
        "update_entry": lambda n: {"lens": "decision", "id": did, "changes": {"why": f"because {n}"}},
        "task_update": lambda n: {"id": ids["task"], "comment": f"A note on the seed, {n}."},
        "task_report": lambda n: {"id": ids["task"], "summary": f"Done, step {n}."},
        "message": lambda n: {"to": B, "text": f"hello {n}"},
        "note_write": lambda n: {"text": f"# Note {n}\n\nbody {n}", "kind": "context"},
        "core_new": lambda n: {"name": f"core {n}", "type": "feature", "text": f"keep {n} in view"},
        "map_write": lambda n: {"map": {"template": "tool", "rows": [], "note": f"n{n}"}, "note": f"v{n}"},
        "architecture_page": lambda n: {"text": PAGE + f"\n- step {n}\n", "note": f"v{n}"},
        "doc_version": lambda n: {"id": ids["doc"], "body": f"# Seed doc\n\nDraft {n}.", "note": f"v{n}"},
    }


def _place(tool: str, args: dict, where: str, field: str, value: str) -> dict | None:
    if where == "top":
        return {**args, field: value}
    inner = {"fields": "fields", "changes": "changes"}[where]
    if inner not in args:
        return None
    return {**args, inner: {**args[inner], field: value}}


def _cell(tr: mcp.Translator, root: Path, args: dict, value: str, tool: str) -> str:
    before = _files(root)
    calls = len(tr.api.calls)
    try:
        tr.call(tool, args)
    except mcp.ApiError as exc:
        wrote, found = _stored(root, before, value)
        if found:
            return "PASSED THROUGH"
        posted = any(m != "GET" for m, *_ in tr.api.calls[calls:])
        who = "server" if posted else "translator"
        return f"refused ({who})" + (" but wrote" if wrote else "") + f": {str(exc)[:90]}"
    wrote, found = _stored(root, before, value)
    if found:
        return "PASSED THROUGH"
    return "stamped over" if wrote else "no write"


def _build(tr: mcp.Translator, root: Path, ids: dict[str, str]) -> dict[str, dict[str, str]]:
    tools = _tools(tr, ids)
    matrix: dict[str, dict[str, str]] = {}
    n = 0
    for tool, base in tools.items():
        n += 1
        before = _files(root)
        tr.call(tool, base(n))      # the valid call writes: the fixture is right
        assert _stored(root, before, "\0")[0], f"{tool}: the valid call wrote nothing"
        row: dict[str, str] = {}
        for where in ("top", "fields", "changes"):
            for field, value in FORGED.items():
                n += 1
                args = _place(tool, base(n), where, field, value)
                if args is None:
                    continue
                row[f"{field}@{where}"] = _cell(tr, root, args, value, tool)
        matrix[tool] = row
    return matrix


def _http(c, root: Path, ids: dict[str, str], monkeypatch) -> dict[str, dict[str, str]]:
    """agents.mcp_only off: the agent posts its own body. Two identity claims
    that disagree, and the stamped fields the body carries."""
    from backend import server as _server
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: False)
    routes = {
        "POST /api/decisions": lambda n: ("/api/decisions", {"project": "ALPHA", "agent_id": A,
                                                             "decision_text": f"raw {n}", "created_date": "2611-20",
                                                             "created_time": "10:00"}),
        "POST /api/tasks/{id}/update": lambda n: ("/api/tasks/" + ids["task"] + "/update",
                                                  {"actor": A, "comment": f"raw note {n}"}),
        "POST /api/messages": lambda n: ("/api/messages", {"agent_id": A, "to": B, "text": f"raw {n}"}),
    }
    out: dict[str, dict[str, str]] = {}
    n = 1000
    for name, make in routes.items():
        n += 1
        path, body = make(n)
        r = c.post(path, json=body)
        assert r.status_code < 400, (name, r.text)   # the valid call writes: the fixture is right
        row = {}
        for field, value in FORGED.items():
            n += 1
            path, body = make(n)
            if field == "project" and "project" not in body:
                continue
            before = _files(root)
            r = c.post(path, json={**body, field: value})
            wrote, found = _stored(root, before, value)
            if found:
                row[f"{field}@body"] = "PASSED THROUGH"
            elif r.status_code >= 400:
                row[f"{field}@body"] = f"refused ({r.status_code})"
            else:
                row[f"{field}@body"] = "dropped (not stored)" if wrote else "no write"
        out[name] = row
    return out


def test_the_identity_matrix(world, monkeypatch) -> None:  # noqa: F811
    tr, c, root = world
    ids = _seed(c, root)
    matrix = {"mcp": _build(tr, root, ids), "http (mcp_only off)": _http(c, root, ids, monkeypatch)}
    out = os.environ.get("IDENTITY_MATRIX_OUT")
    if out:
        Path(out).write_text(json.dumps(matrix, indent=1, ensure_ascii=False), encoding="utf-8")

    from backend import mcp_args
    # Every tool, the ones the walk has no fixture for included: a stamped
    # name sent top-level dies in the translator, before any request.
    for tool in sorted(mcp_args.TOOL_ARGS):
        for field in sorted(mcp_args.STAMPED):
            calls = len(tr.api.calls)
            with pytest.raises(mcp.ApiError, match=f"^{field} is stamped by Slightly Parallel; leave it out$"):
                tr.call(tool, {field: FORGED[field]})
            assert not [m for m, *_ in tr.api.calls[calls:] if m != "GET"], (tool, field)
    passed = [(t, k) for t, row in matrix["mcp"].items() for k, v in row.items() if v == "PASSED THROUGH"]
    assert not passed, passed
    for tool, row in matrix["mcp"].items():
        for key, got in row.items():
            field = key.split("@")[0]
            want = mcp_args.IDENTITY[field]
            if field == "project" and key.endswith("@top") and tool in mcp_args.PROJECT_TOOLS:
                # A real argument there: a project the chat is not in is the gate's refusal.
                assert got.startswith("refused (server)") and "not a member of GAMMA" in got, (tool, key, got)
            elif want == "refuse":
                assert got.startswith("refused (translator)"), (tool, key, got)
            else:
                assert got == "stamped over", (tool, key, got)
    # Plain HTTP: the body is the agent's own claim. A second writer name,
    # identity a lens has no column for, and an unrecorded sender are refused;
    # a create's own created_date/created_time are the stamp itself there
    # (the translator sends them the same way), so they are the one exception.
    http_passed = sorted((r, k) for r, row in matrix["http (mcp_only off)"].items()
                         for k, v in row.items() if v == "PASSED THROUGH")
    assert http_passed == [("POST /api/decisions", "created_date@body"),
                           ("POST /api/decisions", "created_time@body")], http_passed
