"""Writes that are the operator's alone — refused from an agent id.

Sprints are planned by a person; the Storyboard's documents are the operator's. The board (house actors)
passes; any other agent_id/actor is a 422 naming the rule.
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


def _sprint(client: TestClient, agent: str, expect: int) -> dict:
    r = client.post("/api/sprints", json={
        "created_date": "2609-02", "started_date": "2609-02", "name": "S1",
        "projects": "alpha", "status": "active", "bet_days": 5, "agent_id": agent,
    })
    assert r.status_code == expect, r.text
    return r.json()


def test_sprints_are_started_ended_and_changed_by_the_operator_only(client: TestClient) -> None:
    out = _sprint(client, "cc-a", 422)
    assert "operator" in out["detail"]
    sid = _sprint(client, "operator", 201)["metadata"]["id"]
    r = client.post(f"/api/sprints/{sid}/update", json={"status": "ended", "ended_date": "2609-03", "actor": "cc-a"})
    assert r.status_code == 422
    r = client.post(f"/api/sprints/{sid}/update", json={"status": "ended", "ended_date": "2609-03", "agent_id": "cc-a"})
    assert r.status_code == 422
    r = client.post(f"/api/sprints/{sid}/update", json={"bet_days": 6})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/sprints/{sid}/update", json={"status": "ended", "ended_date": "2609-03", "actor": "operator"})
    assert r.status_code == 200, r.text
