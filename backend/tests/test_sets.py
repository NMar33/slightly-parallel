"""Sets: named, ordered groups of kept entries, saved on the server."""

from __future__ import annotations


def test_a_set_is_made_renamed_reordered_and_deleted(client):
    r = client.post("/api/sets", json={
        "name": "  UI for the   new app ", "kind": "vision", "items": ["vs_a", "vs_b", "vs_a"]})
    assert r.status_code == 201, r.text
    made = r.json()
    assert made["id"].startswith("ks_")
    assert made["name"] == "UI for the new app" and made["items"] == ["vs_a", "vs_b"]

    assert [s["id"] for s in client.get("/api/sets", params={"kind": "vision"}).json()["sets"]] == [made["id"]]
    assert client.get("/api/sets", params={"kind": "rule"}).json()["sets"] == []

    changed = client.post(f"/api/sets/{made['id']}/update", json={
        "name": "UI", "items": ["vs_b", "vs_a", "vs_c"]}).json()
    assert changed["name"] == "UI" and changed["items"] == ["vs_b", "vs_a", "vs_c"]
    assert client.get("/api/sets").json()["sets"][0]["items"] == ["vs_b", "vs_a", "vs_c"]

    assert client.post(f"/api/sets/{made['id']}/delete").status_code == 200
    assert client.get("/api/sets").json()["sets"] == []


def test_two_sets_may_share_a_name_and_keep_their_own_items(client):
    a = client.post("/api/sets", json={"name": "Handoff", "kind": "vision", "items": ["vs_a"]}).json()
    b = client.post("/api/sets", json={"name": "Handoff", "kind": "vision"}).json()
    assert a["id"] != b["id"] and b["items"] == []
    client.post(f"/api/sets/{b['id']}/update", json={"items": ["vs_z"]})
    rows = {s["id"]: s["items"] for s in client.get("/api/sets").json()["sets"]}
    assert rows == {a["id"]: ["vs_a"], b["id"]: ["vs_z"]}


def test_a_set_refuses_what_it_cannot_keep(client):
    assert client.post("/api/sets", json={"name": " ", "kind": "vision"}).status_code == 422
    assert client.post("/api/sets", json={"name": "x", "kind": "task"}).status_code == 422
    assert client.post("/api/sets", json={"name": "x", "kind": "vision", "items": "vs_a"}).status_code == 422
    assert client.post("/api/sets", json={"name": "x" * 81, "kind": "vision"}).status_code == 422
    assert client.post("/api/sets/ks_00000000/update", json={"name": "y"}).status_code == 404
    assert client.post("/api/sets/ks_00000000/delete").status_code == 404
