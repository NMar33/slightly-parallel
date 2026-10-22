"""Detail documents are written inside the data root, and a task's
document is changed under one lock.

The CSV rows name their document (md_ref). Reads resolved it under the
data root; writes took it as it was, so ``../../x`` in a row wrote outside.
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi.testclient import TestClient

from backend.csvio import read_rows, rewrite_rows
from backend.entities import ENTITIES
from backend.routers.tasks_extra import tasks_add_turn
from tests.test_evidence import PNG


def _task(client: TestClient, description: str = "first") -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-29", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": "Doc path task", "status": "todo",
        "description": description,
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _point(csv: Path, eid: str, ref: str) -> None:
    def mutate(rows):
        for row in rows:
            if row.get("id") == eid:
                row["md_ref"] = ref
        return True
    rewrite_rows(csv, list(read_rows(csv)[0].keys()), mutate)


def _outside(data_root: Path) -> list[Path]:
    return [p for p in data_root.parent.parent.rglob("x*.md") if data_root not in p.parents]


def test_a_task_row_pointing_outside_never_writes_there(client: TestClient, data_root: Path) -> None:
    tid = _task(client)
    csv = data_root / ENTITIES["task"].csv
    _point(csv, tid, "../../x.md")
    client.app.state.store.rebuild()
    r = client.post(f"/api/tasks/{tid}/update", json={"description": "again", "actor": "operator"})
    assert r.status_code == 200, r.text
    assert _outside(data_root) == []
    ref = next(row for row in read_rows(csv) if row["id"] == tid)["md_ref"]
    assert ref.startswith("task_details/") and (data_root / ref).is_file()

    _point(csv, tid, "../../x-turn.md")
    client.app.state.store.rebuild()
    r = client.post(f"/api/tasks/{tid}/turn", json={"text": "a second turn"})
    assert r.status_code == 201, r.text
    assert _outside(data_root) == []


def test_a_lens_row_pointing_outside_never_writes_there(client: TestClient, data_root: Path) -> None:
    r = client.post("/api/decisions", json={
        "created_date": "2608-29", "created_time": "10:00", "project": "alpha",
        "agent_id": "cc-abc12345", "l1": "chose sqlite", "l2": "why"})
    assert r.status_code in (200, 201), r.text
    did = r.json()["metadata"]["id"]
    csv = data_root / ENTITIES["decision"].csv
    _point(csv, did, "../../x-decision.md")
    client.app.state.store.rebuild()
    r = client.post(f"/api/decisions/{did}/update", json={"l2": "a better why", "actor": "operator"})
    assert r.status_code == 200, r.text
    assert _outside(data_root) == []


def test_two_turns_at_once_both_stay(client: TestClient, monkeypatch) -> None:
    import time

    from backend.routers import tasks_extra

    tid = _task(client)
    store = client.app.state.store
    real = tasks_extra.append_turn

    def slow(*args, **kw):
        # Between the read and the write, where the second reader came in.
        time.sleep(0.05)
        return real(*args, **kw)
    monkeypatch.setattr(tasks_extra, "append_turn", slow)
    errors: list[BaseException] = []

    def add(i: int) -> None:
        try:
            tasks_add_turn(tid, {"text": f"turn from thread {i}", "actor": "operator"}, store)
        except BaseException as exc:  # noqa: BLE001 — reported below
            errors.append(exc)

    threads = [threading.Thread(target=add, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    turns = client.get(f"/api/tasks/{tid}").json()["turns"]
    assert sorted(t["text"] for t in turns[1:]) == sorted(f"turn from thread {i}" for i in range(6))


def test_deleting_evidence_removes_only_a_file_in_the_evidence_folder(client: TestClient, data_root: Path) -> None:
    tid = _task(client)
    client.post(f"/api/tasks/{tid}/evidence", json={
        "agent_id": "cc-test", "items": [{"kind": "image", "title": "shot", "data_base64": PNG, "ext": "png"}]})
    img = next(e for e in client.get(f"/api/tasks/{tid}/evidence").json()["evidence"] if e["kind"] == "image")
    csv = data_root / "task_evidence.csv"

    def mutate(rows):
        for row in rows:
            if row.get("id") == img["id"]:
                row["body"] = ENTITIES["task"].csv
        return True
    rewrite_rows(csv, list(read_rows(csv)[0].keys()), mutate)
    client.app.state.store.rebuild()
    assert client.post(f"/api/tasks/evidence/{img['id']}/delete", json={"actor": "operator"}).status_code == 200
    assert (data_root / ENTITIES["task"].csv).is_file()
