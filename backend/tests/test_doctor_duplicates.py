"""A note posted twice is one note, and the doctor names the copies an older
build left behind."""

from __future__ import annotations

import csv
from pathlib import Path

from fastapi.testclient import TestClient

from backend.entities import TASK_NOTE_COLUMNS


def _task(client: TestClient) -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2609-18", "created_time": "12:00", "project": "alpha",
        "agent_id": "operator", "title": "Stacks", "status": "doing", "description": "x",
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def test_the_same_note_twice_is_one_note(client: TestClient):
    tid = _task(client)
    body = {"type": "article", "body": "1) Press release\n\nStacks: tasks that wait in line."}
    first = client.post(f"/api/tasks/{tid}/notes", json=body)
    again = client.post(f"/api/tasks/{tid}/notes", json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["existing"] is True and again.json()["note"]["id"] == first.json()["note"]["id"]
    assert client.get(f"/api/tasks/{tid}/notes").json()["total"] == 1
    assert client.get("/api/doctor").json()["ok"] is True


def test_the_doctor_names_duplicate_copies(client: TestClient, data_root: Path):
    tid = _task(client)
    note = client.post(f"/api/tasks/{tid}/notes", json={"type": "post", "body": "hello"}).json()["note"]
    path = data_root / "task_notes.csv"
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TASK_NOTE_COLUMNS, lineterminator="\n")
        w.writerow({k: note.get(k, "") for k in TASK_NOTE_COLUMNS})  # an identical copy
        w.writerow({**{k: note.get(k, "") for k in TASK_NOTE_COLUMNS}, "body": "hello, edited"})  # a different one
    client.app.state.store.rebuild()
    report = client.get("/api/doctor").json()
    assert report["ok"] is False and report["issues"][0]["kind"] == "duplicate-id"

