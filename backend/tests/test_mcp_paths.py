"""A write marked as the MCP server's goes only where the MCP tools write
(server.mcp_may_write). The mark is a header anyone can send: before, an
agent body with it reached settings, setup, backup and terminals."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import server as _server
from backend.server import create_app, mcp_may_write

MARK = {"x-sp-via": "mcp"}
AGENT = "cc-alpha123"


@pytest.fixture()
def gated(data_root: Path, monkeypatch):
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    with TestClient(create_app(data_root=data_root, watch=False, run_monitor=False)) as c:
        yield c


@pytest.mark.parametrize("path", ["/api/settings", "/api/backup/run", "/api/setup/integrate",
                                  "/api/terminal/sessions", "/api/prefs"])
def test_a_marked_agent_write_outside_the_tools_is_refused(gated, path) -> None:
    r = gated.post(path, json={"agent_id": AGENT, "values": {}}, headers=MARK)
    assert r.status_code == 403, r.text
    assert "MCP tools do not write here" in r.json()["detail"]


def test_a_marked_agent_write_the_tools_make_passes(gated) -> None:
    body = {"created_date": "2609-17", "created_time": "12:00", "project": "alpha",
            "agent_id": AGENT, "l1": "chose sqlite", "l2": "why"}
    r = gated.post("/api/decisions", json=body, headers=MARK)
    assert r.status_code in (200, 201), r.text
    r = gated.post("/api/tasks/tk_none/report", json={"agent_id": AGENT, "summary": "x"}, headers=MARK)
    assert r.status_code != 403, r.text
    # #undo: refused for want of a request in the chat (409), not by the gate.
    r = gated.post("/api/undo/propose", json={"agent_id": AGENT, "ids": ["vs_1"]}, headers=MARK)
    assert r.status_code == 409, r.text


def test_the_list_holds_every_path_the_translator_posts_to() -> None:
    for path in ("/api/decisions", "/api/decisions/d_1/update", "/api/tasks", "/api/tasks/tk_1/update",
                 "/api/tasks/tk_1/report", "/api/tasks/tk_1/evidence", "/api/tasks/tk_1/story",
                 "/api/standups/claim", "/api/standups/postpone", "/api/architecture/page",
                 "/api/map", "/api/docs/dc_1/versions", "/api/artifacts/ar_1/write",
                 "/api/skills/sk_1/draft", "/api/visions/v_1/interpretation", "/api/scans",
                 "/api/undo/propose", "/api/undo/apply", "/api/undo/restore"):
        assert mcp_may_write(path), path
    for path in ("/api/settings", "/api/backup/run", "/api/tasks/tk_1/delete",
                 "/api/decisions/x/y/update", "/api/terminal/sessions"):
        assert not mcp_may_write(path), path

