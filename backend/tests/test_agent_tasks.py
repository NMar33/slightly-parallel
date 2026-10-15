"""/task — an agent's own card, gated.

1. An agent's create lands in the `agent` column: any other status is a
   422, no status means `agent`.
2. Tags: 1–3 from the closed ``ag_*`` set; the title is ≤ 80 characters.
3. Everything the operator owns is dropped and named back as ``ignored``.
4. The board (house actors) passes untouched.
5. "Drop it": the creating agent may archive its own `agent` card; every
   other status change by an agent stays refused.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _post(client: TestClient, expect: int = 201, **over) -> dict:
    body = {
        "created_date": "2609-01", "created_time": "21:10", "project": "alpha",
        "agent_id": "cc-a", "title": "Architecture form without a scan",
        "tags": "ag_followup",
        "description": "rn the form accepts an empty trigger_id.\nbackend/routers/architecture.py:architecture_form",
    }
    body.update(over)
    r = client.post("/api/tasks", json=body)
    assert r.status_code == expect, r.text
    return r.json()


def test_an_agent_task_lands_in_the_agent_column(client: TestClient) -> None:
    out = _post(client)
    assert out["metadata"]["status"] == "agent"
    assert out["metadata"]["tags"] == "ag_followup"
    assert out["description"].startswith("rn the form")
    assert "ignored" not in out
    explicit = _post(client, created_time="21:11", status="agent")
    assert explicit["metadata"]["status"] == "agent"
    wrong = _post(client, expect=422, created_time="21:12", status="todo")
    assert "agent" in wrong["detail"] and "todo" in wrong["detail"]


def test_tags_come_from_the_closed_set_one_to_three(client: TestClient) -> None:
    none = _post(client, expect=422, tags="")
    assert "ag_debt" in none["detail"]
    unknown = _post(client, expect=422, tags="ag_followup, urgent")
    assert "urgent" in unknown["detail"]
    many = _post(client, expect=422, tags="ag_debt,ag_bug,ag_idea,ag_decision")
    assert "at most 3" in many["detail"]
    three = _post(client, tags="ag_debt, ag_decision ,ag_idea")
    assert three["metadata"]["tags"] == "ag_debt,ag_decision,ag_idea"


def test_title_is_required_and_short(client: TestClient) -> None:
    assert "title" in _post(client, expect=422, title="")["detail"]
    long = _post(client, expect=422, title="x" * 81)
    assert "80" in long["detail"]


def test_operator_metadata_is_dropped_and_named(client: TestClient) -> None:
    out = _post(
        client, priority="high", impact="high", effort="L", sprint_id="sp_1",
        due_date="2609-09", position="7", auto_manage="yes", remember="yes",
    )
    assert out["ignored"] == [
        "auto_manage", "due_date", "effort", "impact", "position", "priority",
        "remember", "sprint_id",
    ]
    meta = out["metadata"]
    assert meta["priority"] in ("", None) and meta["sprint_id"] in ("", None)
    assert str(meta.get("auto_manage") or "") == ""


def test_lane_follows_a_named_assignee(client: TestClient) -> None:
    out = _post(client, assignee="Bugs")
    assert out["metadata"]["lane"] == "Bugs" and out["metadata"]["assignee"] == "Bugs"
    bare = _post(client, created_time="21:20")
    assert str(bare["metadata"].get("lane") or "") == ""


def test_the_board_passes_untouched(client: TestClient) -> None:
    board = _post(client, agent_id="operator", status="todo", tags="", priority="high")
    assert board["metadata"]["status"] == "todo" and board["metadata"]["priority"] == "high"
    assert "ignored" not in board


def test_drop_it_archives_only_the_agents_own_agent_card(client: TestClient) -> None:
    tid = _post(client)["metadata"]["id"]
    # the creating agent may not move it anywhere else
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "todo", "actor": "cc-a"})
    assert r.status_code == 422
    # another agent may not archive it
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "done-archived", "actor": "cc-b"})
    assert r.status_code == 422
    # the creator may
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "done-archived", "actor": "cc-a"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/tasks/{tid}").json()["metadata"]["status"] == "done-archived"
    # once the operator has classified it, the exception is gone
    other = _post(client, created_time="21:30")["metadata"]["id"]
    client.post(f"/api/tasks/{other}/update", json={"status": "todo", "actor": "operator"})
    r = client.post(f"/api/tasks/{other}/update", json={"status": "done-archived", "actor": "cc-a"})
    assert r.status_code == 422


def test_agent_is_a_known_status_for_the_operator_too(client: TestClient) -> None:
    out = _post(client, agent_id="operator", status="agent", tags="")
    assert out["metadata"]["status"] == "agent"
    r = client.post(f"/api/tasks/{out['metadata']['id']}/update", json={"status": "next", "actor": "operator"})
    assert r.status_code == 200


def test_the_sprint_is_the_operators_on_update_too(client: TestClient) -> None:
    """The create gate drops `sprint_id` and the contract says sprints are the
    operator's; the update gate used to take it from an agent."""
    tid = _post(client)["metadata"]["id"]
    r = client.post(f"/api/tasks/{tid}/update", json={"sprint_id": "sp_1", "actor": "cc-a"})
    assert r.status_code == 422 and "task_report" in r.json()["detail"]
    assert client.get(f"/api/tasks/{tid}").json()["metadata"].get("sprint_id", "") in ("", None)
    # the operator still plans
    assert client.post(f"/api/tasks/{tid}/update",
                       json={"sprint_id": "sp_1", "actor": "operator"}).status_code == 200
