"""A decision like one already logged in the project is named in the
answer, as a warning: nothing is refused (entitylib.create_entity,
similarlib.similar_decisions). And the MCP tools that carry next tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import mcp
from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c


def _decide(c: TestClient, text: str, project: str = "alpha", minute: int = 0) -> Any:
    return c.post("/api/decisions", json={
        "created_date": "2611-01", "created_time": f"10:{minute:02d}", "project": project,
        "agent_id": "cc-dec00001", "decision": text, "why": "a reason. Live.", "weight": "minor",
    })


FIRST = "The prompts page is a sortable table, one row per prompt"


def test_a_similar_decision_is_named_and_nothing_is_refused(client) -> None:
    first = _decide(client, FIRST).json()["metadata"]["id"]
    r = _decide(client, "The prompts page is a table whose row opens the whole prompt", minute=1)
    assert r.status_code == 201
    body = r.json()
    assert [d["id"] for d in body["similar"]] == [first]
    assert set(body["similar"][0]) == {"id", "decision", "created", "score"}
    assert any(first in w and "Nothing was refused" in w for w in body["warnings"])


def test_an_unrelated_decision_has_no_warning(client) -> None:
    _decide(client, FIRST)
    body = _decide(client, "Backups run every six hours and keep fourteen copies", minute=1).json()
    assert body["similar"] == [] and not any("similar decision" in w for w in body["warnings"])


def test_the_first_decision_and_another_project(client) -> None:
    assert _decide(client, FIRST).json()["similar"] == []
    body = _decide(client, FIRST + " with filters", project="beta", minute=1).json()
    assert body["similar"] == []


def test_at_most_one_is_named(client) -> None:
    _decide(client, FIRST)
    _decide(client, FIRST + " and a filter line", minute=1)
    body = _decide(client, FIRST + " and a search box", minute=2).json()
    assert len(body["similar"]) == 1


def test_a_repeat_is_not_compared_with_itself(client) -> None:
    _decide(client, FIRST)
    again = _decide(client, FIRST)
    assert again.status_code == 200 and "similar" not in again.json()
    assert not any("similar decision" in w for w in again.json()["warnings"])


# ---------------------------------------------------------------------------
# The MCP tools
# ---------------------------------------------------------------------------


class _Api(mcp.Api):
    def __init__(self) -> None:
        super().__init__("http://testserver")
        self.calls: list[tuple[str, str, Any]] = []

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        self.calls.append((method, path, body))
        return {}


@pytest.fixture()
def translator(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {"project": "alpha", "agent_id": "cc-x"})
    monkeypatch.setattr(mcp.Translator, "_load_schema", lambda self: None)
    return mcp.Translator(_Api(), cwd=str(tmp_path))


@pytest.mark.parametrize("args", [{}, {"proposals": None}, {"proposals": []}, {"proposals": ""}])
def test_task_done_without_proposals_reads_as_before(translator, args) -> None:
    translator.call("task_done", args)
    assert translator.api.calls == [("GET", "/api/done-tags?agent_id=cc-x", None)]


def test_task_done_with_proposals_posts_them_as_sent(translator) -> None:
    sent = [{"title": "Set up DNS", "line": "www has none"}]
    translator.call("task_done", {"proposals": sent})
    assert translator.api.calls == [("POST", "/api/done-tags", {"agent_id": "cc-x", "proposals": sent})]
    translator.call("task_done", {"proposals": "[1]"})      # the server judges the shape
    assert translator.api.calls[-1][2]["proposals"] == "[1]"


def test_next_tasks_posts_the_numbers(translator) -> None:
    translator.call("next_tasks", {"numbers": [1, 3]})
    assert translator.api.calls == [("POST", "/api/next-tasks/make", {"agent_id": "cc-x", "numbers": [1, 3]})]


def test_the_tools_say_what_they_take() -> None:
    assert "next_tasks" in mcp.TOOLS and "proposals" in mcp.TOOLS["task_done"]
    tr = mcp.Translator.__new__(mcp.Translator)
    tr.schema, tr.lenses, tr.vocab = {}, {}, {}
    tr.ensure = lambda: None      # type: ignore[method-assign]
    defs = {d["name"]: d for d in tr.tool_defs()}
    props = defs["task_done"]["inputSchema"]["properties"]["proposals"]
    assert props["maxItems"] == 3 and props["items"]["required"] == ["title"]
    assert defs["next_tasks"]["inputSchema"]["required"] == ["numbers"]
