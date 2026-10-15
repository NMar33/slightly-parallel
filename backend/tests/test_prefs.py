"""UI prefs — the server copy that makes settings survive origin changes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(data_root=tmp_path / "data", watch=False)
    with TestClient(app) as c:
        yield c


def test_prefs_round_trip_merge_and_delete(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/api/prefs").json()["prefs"] == {}
    r = client.post("/api/prefs", json={"values": {"sp-kanban-view:slightly-parallel": "lanes"}})
    assert r.status_code == 200 and r.json()["total"] == 1
    client.post("/api/prefs", json={"values": {"sp-kanban-desc": "1"}})
    prefs = client.get("/api/prefs").json()["prefs"]
    assert prefs == {"sp-kanban-view:slightly-parallel": "lanes", "sp-kanban-desc": "1"}
    # The durable copy is a plain JSON file at the data root.
    on_disk = json.loads((tmp_path / "data" / "ui_prefs.json").read_text(encoding="utf-8"))
    assert on_disk["sp-kanban-view:slightly-parallel"] == "lanes"
    # null deletes; junk bodies are refused.
    client.post("/api/prefs", json={"values": {"sp-kanban-desc": None}})
    assert "sp-kanban-desc" not in client.get("/api/prefs").json()["prefs"]
    assert client.post("/api/prefs", json={"values": {}}).status_code == 422
    assert client.post("/api/prefs", json={}).status_code == 422


def test_prefs_survive_a_server_restart(tmp_path: Path) -> None:
    root = tmp_path / "data"
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        c.post("/api/prefs", json={"values": {"sp-kanban-view:slightly-parallel": "lanes"}})
    app2 = create_app(data_root=root, watch=False)  # a fresh process
    with TestClient(app2) as c2:
        assert c2.get("/api/prefs").json()["prefs"]["sp-kanban-view:slightly-parallel"] == "lanes"
