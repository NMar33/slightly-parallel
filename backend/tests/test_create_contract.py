"""Every create answers in one shape.

Two keys, whatever the route wrapped the new thing in:

* ``warnings`` — always a list, empty when there is nothing to say. It used
  to appear only when non-empty, so a caller could not tell "nothing to
  warn about" from "this route has no warnings at all".
* ``existing`` — true when the post found the thing already written and
  wrote nothing, and then the status drops from 201 to 200. Six routes
  detected the repeat and answered 201 anyway, which is exactly the case an
  agent retrying after a timeout cannot read.

The walk below posts to a spread of create routes across the backend —
lens, ledger, per-task, JSON-state and MD-backed — twice each, and holds
both halves of the rule against every one. A new create route belongs in
the list.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_BASE = {"project": "ALPHA", "agent_id": "alpha-lead-2608-01",
         "created_date": "2608-10", "created_time": "09:00"}


def _task(client: TestClient) -> str:
    r = client.post("/api/tasks", json={
        "project": "ALPHA", "title": "Evidence of the create contract",
        "actor": "operator",
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _cases(client: TestClient) -> list[tuple[str, str, dict]]:
    """(name, path, body) — one per family of create route."""
    tid = _task(client)
    return [
        # A lens create: CSV row plus a detail document.
        ("vision", "/api/visions", {**_BASE, "l1": "One shape for every create",
                                    "horizon": "quarter", "status": "active"}),
        ("note", "/api/notes", {**_BASE, "title": "A bare note"}),
        # A decision carries contract warnings when it falls short.
        ("decision", "/api/decisions", {**_BASE, "decision_text": "Chose X over Y"}),
        # JSON state at the data root, not a CSV.
        ("board", "/api/boards", {"name": "The create contract board"}),
        ("set", "/api/sets", {"name": "One set", "kind": "rule"}),
        # Per-task ledgers.
        ("task note", f"/api/tasks/{tid}/notes",
         {"type": "article", "body": "What the create contract is."}),
        ("calendar entry", "/api/calendar/entries",
         {"project": "ALPHA", "kind": "meeting", "date": "2026-10-01",
          "title": "Review the create contract"}),
        ("doc", "/api/docs", {"project": "ALPHA", "kind": "release", "title": "A doc"}),
    ]


def test_every_create_carries_warnings_as_a_list(client: TestClient) -> None:
    for name, path, body in _cases(client):
        r = client.post(path, json=body)
        assert r.status_code in (200, 201), f"{name}: {r.status_code} {r.text}"
        out = r.json()
        assert isinstance(out.get("warnings"), list), f"{name}: {out!r}"
        assert isinstance(out.get("existing"), bool), f"{name}: {out!r}"


# The creates whose id is the content, so posting the same body twice is
# one row. The rest mint a fresh id on purpose (a set's name may repeat, a
# calendar entry on the same day is a second entry) and answer 201 twice —
# they still carry both keys, which is what the walk above checks.
_IDEMPOTENT = {"vision", "note", "decision", "board", "task note"}


def test_a_repeated_create_answers_200_and_says_existing(client: TestClient) -> None:
    for name, path, body in _cases(client):
        if name not in _IDEMPOTENT:
            continue
        first = client.post(path, json=body)
        assert first.status_code == 201, f"{name}: {first.text}"
        assert first.json()["existing"] is False, name

        again = client.post(path, json=body)
        assert again.status_code == 200, f"{name}: {again.status_code} {again.text}"
        assert again.json()["existing"] is True, f"{name}: {again.json()!r}"
        assert isinstance(again.json()["warnings"], list), name


def test_the_two_link_routes_keep_created_and_gain_existing(client: TestClient) -> None:
    """``created`` is what the pages read — it stays, beside the new keys."""
    a, b = _task(client), None
    r = client.post("/api/tasks", json={"project": "ALPHA", "title": "The other end",
                                        "actor": "operator"})
    b = r.json()["metadata"]["id"]

    first = client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "relates"})
    assert first.status_code == 201, first.text
    assert first.json()["created"] is True and first.json()["existing"] is False

    again = client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "relates"})
    assert again.status_code == 200, again.text
    assert again.json()["created"] is False and again.json()["existing"] is True
    assert again.json()["warnings"] == []
