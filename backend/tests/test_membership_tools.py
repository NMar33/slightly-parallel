"""The MCP tools write where the agent names, else home, and say where
(tk_d1d25a4d step 3, note nt_258a7ed7 §2 table).

Fixture: chat A from ALPHA joins BETA; GAMMA is no project of A's. Each
create tool, through the real translator into the real gated server: no
`project` lands in the home, a member project lands there, a non-member is
refused with the gate's line and writes nothing; every create answer carries
`where`. Standups stay home. Scan, map and architecture material warn when
the project's folder is not where the chat works.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import mcp
from backend import server as _server
from backend.server import create_app
from tests.conftest import make_chat

pytestmark = pytest.mark.strict_membership

A = "cc-aaaa1111"
NOT_GAMMA = (f"403: agent {A} is not a member of GAMMA; its projects: ALPHA, BETA. "
             "The operator adds it on the agent card")


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


class _GatedApi(mcp.Api):
    def __init__(self, client: TestClient) -> None:
        super().__init__("http://testserver")
        self.client = client
        self.calls: list[tuple[str, str, dict | None]] = []

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        self.calls.append((method, path, body))
        r = self.client.request(method, path, json=body, headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        if r.status_code >= 400:
            raise mcp.ApiError(f"{r.status_code}: {r.json().get('detail', '')}")
        return r.json()


@pytest.fixture()
def world(data_root: Path, tmp_path: Path, monkeypatch):
    make_chat(data_root, "ALPHA", A, [("2026-11-20T10:00:00", "work", "ok")])
    (data_root / "projects" / "GAMMA").mkdir(parents=True)
    alpha_dir, beta_dir = tmp_path / "alpha-work", tmp_path / "beta-work"
    (alpha_dir / "sub").mkdir(parents=True)
    beta_dir.mkdir()
    (data_root / "integrations.csv").write_text(
        f"project,path\nALPHA,{alpha_dir}\nBETA,{beta_dir}\n", encoding="utf-8")
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {
        "project": "ALPHA", "agent_id": A, "home": "ALPHA", "members": ["ALPHA", "BETA"], "level": 2})
    with TestClient(create_app(data_root=data_root, watch=False, run_monitor=False)) as c:
        assert c.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "BETA"}).status_code == 200
        yield mcp.Translator(_GatedApi(c), cwd=str(alpha_dir / "sub")), c, data_root


PAGE = ("## What it is\nx\n## The live work\nx\n## What it does or has produced\n"
        "1. **Rename photos** — `rename.py` · where: `rename.py` · seen: ran it\n"
        "## What is owed\n- nothing\n")
DECISION = {"lens": "decision", "fields": {"decision": "chose sqlite", "why": "small"}}


def _creates() -> dict[str, dict]:
    return {
        "write_entry": DECISION,
        "note_write": {"text": "# A note\n\nbody", "kind": "context"},
        "core_new": {"name": "the gate", "type": "feature", "text": "keep it in view"},
        "map_write": {"map": {"template": "tool", "rows": []}, "note": "first"},
        "architecture_page": {"text": PAGE, "note": "first"},
    }


def _project_of(c: TestClient, tool: str, got: dict) -> str:
    if tool == "map_write":
        return str(got.get("project") or "")
    if tool == "architecture_page":
        return str(got.get("project") or (got.get("page") or {}).get("project") or "")
    meta = got.get("metadata") if isinstance(got.get("metadata"), dict) else got
    return str(meta.get("project") or (got.get("core") or {}).get("project") or (got.get("note") or {}).get("project") or "")


@pytest.mark.parametrize("tool", sorted(_creates()))
def test_no_project_is_home_a_member_is_there_and_where_says_so(world, tool: str) -> None:
    tr, c, _root = world
    for named, expect in ((None, "ALPHA"), ("BETA", "BETA")):
        args = dict(_creates()[tool])
        if named:
            args["project"] = named
        if tool == "core_new":
            args["name"] = f"the gate {expect}"
        got = tr.call(tool, args)
        posted = tr.api.calls[-1][2] or {}
        assert posted.get("project") == expect, (tool, posted)
        assert got["where"].endswith(f"→ {expect}"), (tool, got["where"])


@pytest.mark.parametrize("tool", sorted(_creates()))
def test_a_non_member_project_is_refused_and_writes_nothing(world, tool: str) -> None:
    tr, _c, root = world
    before = tree(root)
    with pytest.raises(mcp.ApiError) as err:
        tr.call(tool, {**_creates()[tool], "project": "GAMMA"})
    assert str(err.value) == NOT_GAMMA
    assert tree(root) == before


def test_a_fields_project_is_refused_with_the_shape(world) -> None:
    """It used to be written over by the home without a word (tk_0b8a32d2)."""
    tr, _c, root = world
    before = tree(root)
    with pytest.raises(mcp.ApiError, match=r'put project next to lens.*"project":"GAMMA"'):
        tr.call("write_entry", {"lens": "decision", "fields": {**DECISION["fields"], "project": "GAMMA"}})
    assert tree(root) == before


def test_a_task_says_its_project(world) -> None:
    tr, _c, _root = world
    got = tr.call("write_entry", {"lens": "task", "project": "BETA",
                                  "fields": {"title": "Check the gate", "tags": "ag_bug"}})
    assert got["metadata"]["project"] == "BETA"
    assert got["where"] == f"{got['metadata']['id']} → BETA"


def test_a_project_of_the_wrong_shape_dies_in_the_translator(world) -> None:
    tr, _c, _root = world
    with pytest.raises(mcp.ApiError, match="project is one project code"):
        tr.call("write_entry", {**DECISION, "project": ["BETA"]})


def test_standups_stay_home(world) -> None:
    tr, _c, _root = world
    tr.call("standup_material", {"date": "2611-19", "claim": True})
    claim = next(b for m, p, b in tr.api.calls if p == "/api/standups/claim")
    assert claim and claim["project"] == "ALPHA"


@pytest.mark.parametrize("tool", ["scan_material", "map_material", "architecture_material"])
def test_material_warns_on_another_folder_and_refuses_a_non_member(world, tool: str) -> None:
    tr, _c, _root = world
    home = tr.call(tool, {})
    assert "folder_warning" not in home, home.get("folder_warning")   # a subfolder of ALPHA's
    beta = tr.call(tool, {"project": "BETA"})
    assert beta["folder_warning"].startswith("folder ") and "is not where you work" in beta["folder_warning"]
    assert beta["folder_warning"].endswith("— check you can read its files")
    with pytest.raises(mcp.ApiError) as err:
        tr.call(tool, {"project": "GAMMA"})
    assert str(err.value) == NOT_GAMMA


def test_the_create_tools_ask_to_repeat_where(world) -> None:
    tr, _c, _root = world
    defs = {d["name"]: d for d in tr.tool_defs()}
    for tool in _creates():
        assert "`where`" in defs[tool]["description"], tool
        assert "project" in defs[tool]["inputSchema"]["properties"], tool
    for tool in ("scan_material", "map_material", "architecture_material"):
        assert "project" in defs[tool]["inputSchema"]["properties"], tool
    for tool in ("standup_material", "standup_postpone"):
        assert "project" not in defs[tool]["inputSchema"].get("properties", {}), tool
