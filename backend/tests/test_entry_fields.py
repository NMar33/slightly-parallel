"""Entries are written by what they hold, not by numbered levels."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import entry_fields
from backend.entities import ENTITIES
from backend.routers.schema_api import build_schema

STAMP = {"created_date": "2609-20", "created_time": "12:00", "project": "ALPHA", "agent_id": "cc-x"}


def test_a_decision_is_written_by_name(client: TestClient) -> None:
    r = client.post("/api/decisions", json={
        **STAMP, "decision": "Chose Redis over an in-process cache",
        "why": "Workers must share counters. Revisit if we go single-worker.",
        "alternatives": ["in-process LRU — rejected: undercounts across workers"],
        "excerpt": "user: two workers\nagent: then Redis",
    })
    assert r.status_code in (200, 201), r.text
    got = client.get(f"/api/decisions/{r.json()['metadata']['id']}").json()
    assert got["metadata"]["decision_text"] == "Chose Redis over an in-process cache"
    assert got["l2"].startswith("Workers must share") and got["l3"][0].startswith("in-process LRU")
    assert "then Redis" in got["l4"]


def test_a_scan_is_written_by_name_and_names_its_own_fields_in_a_refusal(client: TestClient) -> None:
    ok = client.post("/api/scans", json={
        **STAMP, "summary": "Auth shipped; rate limiting half-done",
        "why": "Goal was both; auth landed.", "deltas": ["src/auth/* +90/-12"],
        "proof": "pytest: 34 passed.", "files_n": 3,
    })
    assert ok.status_code == 201, ok.text
    assert ok.json()["metadata"]["l1"].startswith("Auth shipped") and ok.json()["l3"] == ["src/auth/* +90/-12"]
    bad = client.post("/api/scans", json={**STAMP, "why": "no summary"})
    assert bad.status_code == 422 and "summary" in bad.text and "l1" not in bad.text


def test_the_numbered_slots_are_still_taken(client: TestClient) -> None:
    r = client.post("/api/decisions", json={**STAMP, "l1": "An older session", "l2": "still works"})
    assert r.status_code in (200, 201)


def test_the_schema_publishes_names_and_never_the_slots() -> None:
    schema = build_schema()
    assert schema["version"] == 2
    for lens in schema["lenses"]:
        assert not set(lens["fields"]) & {"l2", "l3", "l4"}, lens["name"]
        assert lens["text_fields"], lens["name"]
    by = {l["name"]: l for l in schema["lenses"]}
    assert by["decision"]["text_fields"] == ["decision", "why", "alternatives", "excerpt"]
    assert by["scan"]["base"] == "scans" and by["scan"]["required"] == ["summary"]
    assert by["problem"]["fields"]["attempts"]["type"] == "array"


def test_no_name_shadows_a_column_with_another_meaning() -> None:
    """A named text field that is also a column of its lens must be the headline."""
    for ent in ENTITIES.values():
        for f in entry_fields.BY_LENS.get(ent.name, entry_fields.DEFAULT):
            if f.name in ent.columns and f.slot != "l1":
                offered = [x.name for x in entry_fields.fields_for(ent.name, ent.columns)]
                assert f.name not in offered, (ent.name, f.name)


def test_an_entry_reads_back_by_name(client: TestClient) -> None:
    made = client.post("/api/problems", json={
        **STAMP, "problem": "Deploy is blocked", "impact": "Nothing ships.",
        "attempts": ["restarted — no change"],
    }).json()
    assert made["text"] == {"problem": "Deploy is blocked", "impact": "Nothing ships.",
                            "attempts": ["restarted — no change"], "excerpt": ""}
    got = client.get(f"/api/problems/{made['metadata']['id']}").json()
    assert got["text"]["attempts"] == ["restarted — no change"]

    scan = client.post("/api/scans", json={**STAMP, "summary": "One thing", "why": "Because."}).json()
    assert scan["text"] == {"summary": "One thing", "why": "Because.", "deltas": [], "proof": ""}
    assert client.get(f"/api/scans/{scan['metadata']['id']}").json()["text"]["why"] == "Because."


def test_the_translator_hides_the_slots_when_the_names_are_there() -> None:
    from backend.mcp import Translator

    out = Translator._by_name({"metadata": {"id": "x"}, "l2": "a", "l3": [], "l4": "", "text": {"why": "a"}})
    assert "l2" not in out and out["text"] == {"why": "a"}
    assert Translator._by_name({"l2": "kept: no names here"}) == {"l2": "kept: no names here"}


def test_a_repeated_create_answers_the_same_way_everywhere(client: TestClient) -> None:
    """Nothing new written → 200 and `existing: true`; something written → 201."""
    dec = {**STAMP, "decision": "Same twice", "why": "To see the repeat."}
    first, again = client.post("/api/decisions", json=dec), client.post("/api/decisions", json=dec)
    assert (first.status_code, again.status_code) == (201, 200) and again.json()["existing"] is True

    scan = {**STAMP, "summary": "Same scan twice"}
    first, again = client.post("/api/scans", json=scan), client.post("/api/scans", json=scan)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["existing"] is False and again.json()["existing"] is True

    form = {**STAMP, "trigger_id": first.json()["metadata"]["id"],
            "checked": ["does", "owes", "runs", "stores", "talks", "built with", "faces", "holds"], "changes": []}
    first, again = client.post("/api/architecture", json=form), client.post("/api/architecture", json=form)
    assert (first.status_code, again.status_code) == (201, 200) and again.json()["existing"] is True

    tid = client.post("/api/tasks", json={"project": "ALPHA", "title": "Evidence twice", "actor": "operator"}).json()["metadata"]["id"]
    ev = {"agent_id": "cc-x", "items": [{"kind": "text", "title": "It works", "body": "Seen."}]}
    first, again = client.post(f"/api/tasks/{tid}/evidence", json=ev), client.post(f"/api/tasks/{tid}/evidence", json=ev)
    assert (first.status_code, again.status_code) == (201, 200) and again.json()["existing"] is True
