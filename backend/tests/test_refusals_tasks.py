"""Task writes name every reason at once (tk_90c1ba5f): the update route,
the report, evidence, story posts. Two violations give both reasons, the
most general first; one reason reads as before, to the byte; a missing task
is the only reason. A refusal writes nothing (docs/testing.md #9)."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

AG = "cc-c4c4c4c4"
TASK = "tk_alpha_auth"      # ALPHA, doing, the operator's card
MISSING = "tk_nothere_00"


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


def lines(r) -> list[str]:
    return r.json()["detail"].split("\n")


def _think(c: TestClient, tid: str = TASK) -> None:
    assert c.post(f"/api/tasks/{tid}/update", json={"actor": "operator", "think": True}).status_code == 200


OPERATOR_SWITCH = (f"priority is the operator's switch — an agent does not set it. Report your result "
                   f"instead: MCP tool task_report {{id: \"{TASK}\", summary}}.")
LATER_ROUNDS = (f"a task's later rounds are the operator's — add your words after the text: "
                f"task_update {{id: \"{TASK}\", comment}}.")


# -- the update route --------------------------------------------------------

def test_one_reason_is_the_detail_it_always_was(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/update", json={"agent_id": AG, "priority": "low"})
    assert (r.status_code, r.json()["detail"]) == (422, OPERATOR_SWITCH)
    assert len(r.json()["reasons"]) == 1
    assert tree(data_root) == before


def test_an_operator_field_and_a_turn_are_both_named(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/update", json={"agent_id": AG, "priority": "low", "turn": "more"})
    assert r.status_code == 422
    assert lines(r) == [OPERATOR_SWITCH, LATER_ROUNDS]
    assert tree(data_root) == before


def test_an_operator_field_and_bad_tags_are_both_named(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/update", json={"agent_id": AG, "priority": "low", "tags": "nonsense"})
    assert r.status_code == 422
    got = lines(r)
    assert got[0] == OPERATOR_SWITCH and len(got) == 2 and got[1].startswith("unknown tag(s) nonsense")
    assert tree(data_root) == before


def test_a_title_on_anothers_card_and_a_status_are_both_named(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/update", json={"agent_id": AG, "title": "Mine now", "status": "review"})
    assert r.status_code == 422
    got = lines(r)
    assert len(got) == 2, got
    assert got[0].startswith("title: an agent changes these only on a task it created")
    assert got[1].startswith("task status belongs to the operator")
    assert tree(data_root) == before


def test_the_think_key_and_an_operator_field_are_both_named(client: TestClient, data_root: Path) -> None:
    r = client.post(f"/api/tasks/{TASK}/update", json={"agent_id": AG, "think": True, "priority": "low"})
    assert r.status_code == 422
    assert lines(r) == ["the «think» mark is the operator's — only the operator sets or removes it", OPERATOR_SWITCH]


def test_two_bad_values_are_both_named(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/update", json={"actor": "operator", "status": "bogus", "resurface_to": "nowhere"})
    assert r.status_code == 422
    got = lines(r)
    assert len(got) == 2
    assert got[0].startswith("task.status bogus is not a known value")
    assert got[1].startswith("task.resurface_to nowhere is not a known value")
    assert [x.get("field") for x in r.json()["reasons"]] == ["status", "resurface_to"]
    assert tree(data_root) == before


def test_two_list_fields_are_both_named(client: TestClient, data_root: Path) -> None:
    r = client.post(f"/api/tasks/{TASK}/update", json={"actor": "operator", "lane": ["ui"], "effort": {"a": 1}})
    assert r.status_code == 422
    assert lines(r) == ["lane is text, not a list or an object", "effort is text, not a list or an object"]


@pytest.mark.parametrize("field", ["status", "resurface_to"])
@pytest.mark.parametrize("shape", [["todo"], {"a": 1}])
def test_a_list_in_a_vocabulary_field_is_one_reason(client: TestClient, field: str, shape) -> None:
    # The critic of 7ace3e1d: the shape and the vocabulary each said it.
    r = client.post(f"/api/tasks/{TASK}/update", json={"actor": "operator", field: shape})
    assert r.status_code == 422
    got = lines(r)
    assert len(got) == 1 and got[0].startswith(f"task.{field} is one text value"), got


def test_a_missing_task_is_the_only_reason(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post(f"/api/tasks/{MISSING}/update", json={"agent_id": AG, "think": True, "priority": "low"})
    assert r.status_code == 404 and "\n" not in r.json()["detail"]
    assert tree(data_root) == before


# -- the report --------------------------------------------------------------

def test_a_long_summary_on_a_think_task_hears_both(client: TestClient, data_root: Path) -> None:
    _think(client)
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/report", json={"agent_id": AG, "summary": "x" * 501})
    assert r.status_code == 422
    got = lines(r)
    assert len(got) == 2
    assert "«think»" in got[0] and "reporting it done" in got[0]
    assert got[1] == "summary is at most 500 characters"
    assert tree(data_root) == before


def test_a_report_on_a_missing_task_is_the_404(client: TestClient) -> None:
    r = client.post(f"/api/tasks/{MISSING}/report", json={"agent_id": AG, "summary": 5})
    assert r.status_code == 404


def _set_archived(root: Path, tid: str, value: str) -> None:
    import csv
    path = root / "tasks.csv"
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["id"] == tid:
            r["archived_at"] = value
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def test_a_report_just_after_the_operator_unarchived_is_accepted(client: TestClient, data_root: Path) -> None:
    # The critic of 7ace3e1d: the archived check read the view, which can be
    # a moment behind the file; the check under the lock reads the file.
    _set_archived(data_root, TASK, "2026-11-26T10:00:00")
    client.app.state.store.rebuild()
    _set_archived(data_root, TASK, "")                       # the view still says archived
    stale = client.app.state.store.query_one("SELECT archived_at FROM tasks_mutual WHERE id = ?", (TASK,))
    assert stale and stale["archived_at"]
    r = client.post(f"/api/tasks/{TASK}/report", json={"agent_id": AG, "summary": "done"})
    assert r.status_code == 200, r.text


def test_a_report_on_an_archived_task_is_still_refused(client: TestClient, data_root: Path) -> None:
    _set_archived(data_root, TASK, "2026-11-26T10:00:00")
    client.app.state.store.rebuild()
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/report", json={"agent_id": AG, "summary": "done"})
    assert (r.status_code, r.json()["detail"]) == (409, "the task is archived")
    assert tree(data_root) == before


def test_a_report_with_one_reason_reads_as_before(client: TestClient) -> None:
    r = client.post(f"/api/tasks/{TASK}/report", json={"agent_id": AG, "summary": "x" * 501})
    assert (r.status_code, r.json()["detail"]) == (422, "summary is at most 500 characters")


# -- evidence ----------------------------------------------------------------

def test_every_bad_evidence_item_is_named(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/evidence", json={"agent_id": AG, "items": [
        {"kind": "text", "body": "fine"},
        {"kind": "video"},
        {"kind": "text", "body": "  "},
        "not an object",
    ]})
    assert r.status_code == 422
    got = lines(r)
    assert got[0].startswith("item 1: kind must be one of")
    assert got[1:] == ["item 2: text body is empty", "item 3: not an object"]
    assert tree(data_root) == before


def test_evidence_for_a_missing_task_is_the_404(client: TestClient) -> None:
    r = client.post(f"/api/tasks/{MISSING}/evidence", json={"agent_id": AG, "items": "nope"})
    assert r.status_code == 404


def test_one_bad_item_reads_as_before(client: TestClient) -> None:
    r = client.post(f"/api/tasks/{TASK}/evidence", json={"agent_id": AG, "items": [{"kind": "text"}]})
    assert (r.status_code, r.json()["detail"]) == (422, "item 0: text body is empty")


# -- commits -----------------------------------------------------------------

def test_every_bad_hash_is_named_and_the_404_comes_first(client: TestClient) -> None:
    r = client.post(f"/api/tasks/{TASK}/commits", json={"shas": ["zz", "abc"]})
    assert (r.status_code, r.json()["detail"]) == (422, "not a commit hash: zz, abc")
    assert client.post(f"/api/tasks/{MISSING}/commits", json={"shas": "x"}).status_code == 404


# -- the story ---------------------------------------------------------------

def _request(c: TestClient) -> str:
    r = c.post(f"/api/tasks/{TASK}/story-requests", json={"type": "release", "focus": "the rail"})
    assert r.status_code == 201, r.text
    return r.json()["request"]["id"]


def test_an_empty_story_with_bad_images_hears_both(client: TestClient, data_root: Path) -> None:
    rid = _request(client)
    before = tree(data_root)
    r = client.post(f"/api/tasks/{TASK}/story", json={"request_id": rid, "agent_id": AG, "body": " ",
                                                      "images": "a picture"})
    assert r.status_code == 422
    assert lines(r) == ["body is required", "images: a list of at most 8"]
    assert tree(data_root) == before


def test_every_bad_story_image_is_named(client: TestClient) -> None:
    rid = _request(client)
    png = base64.b64encode(b"not a png").decode()
    r = client.post(f"/api/tasks/{TASK}/story", json={"request_id": rid, "agent_id": AG, "body": "text",
                                                      "images": ["x", {"data_base64": png, "ext": "exe"}]})
    assert r.status_code == 422
    got = lines(r)
    assert got[0] == "image 1: not an object" and got[1].startswith("image 2")


def test_a_request_of_another_task_is_the_only_reason(client: TestClient, data_root: Path) -> None:
    # The critic of 7ace3e1d: the request's state is not told on a task it
    # does not belong to (it may be a task the agent cannot reach).
    rid = _request(client)
    assert client.post(f"/api/story/requests/{rid}/cancel").status_code == 200
    before = tree(data_root)
    r = client.post("/api/tasks/tk_beta_x/story", json={"request_id": rid, "agent_id": AG, "body": ""})
    assert (r.status_code, r.json()["detail"]) == (422, f"request {rid} belongs to task {TASK}")
    assert tree(data_root) == before


def test_a_story_for_a_missing_task_is_the_404(client: TestClient) -> None:
    r = client.post(f"/api/tasks/{MISSING}/story", json={"agent_id": AG})
    assert r.status_code == 404


@pytest.mark.parametrize("body,detail", [
    ({"agent_id": AG, "body": ""}, "body is required"),
])
def test_a_story_with_one_reason_reads_as_before(client: TestClient, body: dict, detail: str) -> None:
    rid = _request(client)
    r = client.post(f"/api/tasks/{TASK}/story", json={"request_id": rid, **body})
    assert (r.status_code, r.json()["detail"]) == (422, detail)
