"""Contract warnings: advisory nudges on create, never blocking.

Each lens defines what its text owes the reader. Entries that fall short
still persist (201), but the response carries a ``warnings`` list so agents
can fix them with update_entry.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    root = tmp_path / "data"
    root.mkdir()
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


_BASE = {
    "created_date": "2608-12",
    "created_time": "10:00",
    "project": "alpha",
    "agent_id": "agent-a",
}


def test_decision_without_alternatives_or_reversal_warns(client: TestClient) -> None:
    r = client.post(
        "/api/decisions",
        json={**_BASE, "decision_text": "Chose X over Y", "rationale": "faster", "weight": "major"},
    )
    assert r.status_code == 201  # persisted despite falling short
    warnings = r.json()["warnings"]
    assert any("alternatives" in w for w in warnings)
    assert any("undo" in w for w in warnings)
    assert not any("Level" in w or "l2" in w or "l3" in w for w in warnings)


def test_a_decisions_weight_decides_what_it_owes(client: TestClient) -> None:
    """Minor is one line and one reason; only major owes what would undo it."""
    minor = client.post("/api/decisions", json={
        **_BASE, "decision": "The helper lives in lib/, not utils/", "why": "lib/ holds hooks.", "weight": "minor"})
    assert minor.status_code == 201 and not minor.json().get("warnings")
    normal = client.post("/api/decisions", json={**_BASE, "decision": "One shared copy button", "why": "Twelve copies."})
    w = normal.json()["warnings"]
    assert any("alternatives" in x for x in w) and not any("undo" in x for x in w)
    assert client.post("/api/decisions", json={**_BASE, "decision": "x", "weight": "huge"}).status_code == 422


def test_decision_honoring_contract_has_no_warnings(client: TestClient) -> None:
    r = client.post(
        "/api/decisions",
        json={
            **_BASE,
            "decision_text": "Chose X over Y",
            "l2": "X shares state across workers. Revisit if we go single-worker.",
            "l3": ["Y — rejected: undercounts across workers"],
        },
    )
    assert r.status_code == 201
    assert r.json()["warnings"] == []


def test_problem_without_impact_warns(client: TestClient) -> None:
    r = client.post(
        "/api/problems",
        json={**_BASE, "l1": "Redis refuses connections", "severity": "high",
              "status": "open"},
    )
    assert r.status_code == 201
    warnings = r.json()["warnings"]
    assert any("impact" in w for w in warnings)
    assert any("attempts" in w.lower() or "tried" in w for w in warnings)


def test_a_rule_posted_by_an_agent_is_refused_and_pointed_at_interpret(client: TestClient) -> None:
    """#rule is kept by the server: the agent writes the interpretation, not
    an entry. A rule an agent posted was made active with a warning and
    served to every agent as the operator's; it is refused now."""
    from backend.routers.deps import AGENT_REFUSED
    r = client.post(
        "/api/rules",
        json={**_BASE, "l1": "Always take the lock", "kind": "process",
              "severity": "high", "status": "active"},
    )
    assert r.status_code == AGENT_REFUSED and "interpret" in r.json()["detail"]
    # the operator writing a rule on the Rules page is not coached
    r = client.post(
        "/api/rules",
        json={**_BASE, "agent_id": "operator", "l1": "Take the lock twice",
              "kind": "process", "severity": "high", "status": "active"},
    )
    assert r.status_code == 201 and r.json()["warnings"] == []


def test_unchecked_entities_never_warn(client: TestClient) -> None:
    r = client.post(
        "/api/notes",
        json={**_BASE, "title": "A bare note"},
    )
    assert r.status_code == 201
    assert r.json()["warnings"] == []


def test_idempotent_repost_also_carries_warnings(client: TestClient) -> None:
    payload = {**_BASE, "decision_text": "Chose X over Y"}
    first = client.post("/api/decisions", json=payload)
    second = client.post("/api/decisions", json=payload)
    assert first.json()["metadata"]["id"] == second.json()["metadata"]["id"]
    assert "warnings" in second.json()
