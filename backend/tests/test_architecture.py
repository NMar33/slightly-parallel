"""The architecture form — the vocabulary gate, the receipt, the screening.

1. A change needs a known op/type, a name, the type's required fields and
   existing path anchors (checked against the registered project folder).
2. Every group is answered — in ``checked`` or with changes — or 422.
3. The check receipt closes the scan and hook reminders even when nothing
   changed; posts are idempotent.
4. ``/api/architecture/state`` screens the scans and folds standing owes.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


capture = _load("sp_capture_arch", "capture.py")

GROUPS = (
    "does", "owes", "runs", "stores", "talks", "built with", "faces", "holds",
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "app").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "app" / "main.py").write_text(
        "class Limiter:\n    pass\n\n\ndef dispatch():\n    pass\n",
        encoding="utf-8",
    )
    (r / "tests" / "test_app.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    return r


@pytest.fixture()
def root(tmp_path: Path, repo: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    with open(r / "integrations.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["project", "path", "created_date"])
        w.writerow(["alpha", str(repo), "2608-28"])
    return r


@pytest.fixture()
def client(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _scan(client: TestClient, **over) -> dict:
    body = {
        "created_date": "2608-28", "created_time": "10:00", "project": "alpha",
        "agent_id": "cc-a", "l1": "rate limiter shipped", "files_n": 1,
        "lines_add": 10, "lines_del": 2, "decisions_n": 0, "scope": "auth",
    }
    body.update(over)
    r = client.post("/api/scans", json=body)
    assert r.status_code in (200, 201), r.text      # 200 when the same scan is written again
    return r.json()


def _form(client: TestClient, status: int = 201, **over) -> dict:
    body = {
        "created_date": "2608-28", "created_time": "10:01", "project": "alpha",
        "agent_id": "cc-a", "trigger_id": "",
        "checked": [g for g in GROUPS if g != "does"],
        "changes": [{
            "op": "add", "type": "feature", "name": "rate-limited requests",
            "path": ["app/main.py"], "surface": "api",
            "note": "429 with Retry-After per token",
        }],
    }
    body.update(over)
    r = client.post("/api/architecture", json=body)
    assert r.status_code == status, r.text
    return r.json()


# ---------------------------------------------------------------------------
# 1. the write gate
# ---------------------------------------------------------------------------


def test_type_op_and_name_come_from_the_vocabulary(client: TestClient) -> None:
    bad_type = _form(client, status=422, changes=[
        {"op": "add", "type": "widget", "name": "x", "path": ["app/main.py"]}])
    assert "widget" in bad_type["detail"] and "does: feature, fix" in bad_type["detail"]
    bad_op = _form(client, status=422, changes=[
        {"op": "delete", "type": "feature", "name": "x", "path": ["app/main.py"]}])
    assert "delete" in bad_op["detail"] and "remove" in bad_op["detail"]
    no_name = _form(client, status=422, changes=[
        {"op": "add", "type": "feature", "path": ["app/main.py"]}])
    assert "name" in no_name["detail"]


def test_required_fields_per_type(client: TestClient) -> None:
    out = _form(client, status=422, checked=[g for g in GROUPS if g != "stores"],
                changes=[{"op": "add", "type": "database", "name": "limits",
                          "path": ["app/main.py"]}])
    assert "engine" in out["detail"]
    ok = _form(client, checked=[g for g in GROUPS if g != "stores"],
               changes=[{"op": "add", "type": "database", "name": "limits",
                         "path": ["app/main.py"], "engine": "sqlite"}])
    assert ok["posted"] == 2  # the change + the receipt


def test_every_group_is_answered_or_422(client: TestClient) -> None:
    out = _form(client, status=422, checked=["runs", "stores"])
    for g in ("owes", "talks", "built with", "faces", "holds"):
        assert g in out["detail"]
    unknown = _form(client, status=422, checked=list(GROUPS) + ["vibes"])
    assert "vibes" in unknown["detail"]


def test_path_anchors_are_checked_against_the_project_folder(client: TestClient) -> None:
    missing = _form(client, status=422, changes=[
        {"op": "add", "type": "feature", "name": "x", "path": ["app/nope.py"]}])
    assert "app/nope.py" in missing["detail"]
    ghost_sym = _form(client, status=422, changes=[
        {"op": "add", "type": "feature", "name": "x", "path": ["app/main.py:Ghost"]}])
    assert "Ghost" in ghost_sym["detail"]
    escape = _form(client, status=422, changes=[
        {"op": "add", "type": "feature", "name": "x", "path": ["../secrets"]}])
    assert "relative" in escape["detail"]
    none_at_all = _form(client, status=422, changes=[
        {"op": "add", "type": "feature", "name": "x"}])
    assert "path" in none_at_all["detail"]
    # a real symbol and a folder pass; debt needs no path at all
    ok = _form(client, checked=[g for g in GROUPS if g not in ("does", "owes")],
               changes=[
                   {"op": "add", "type": "feature", "name": "x",
                    "path": ["app/main.py:Limiter", "tests"]},
                   {"op": "add", "type": "debt", "name": "no size cap on uploads",
                    "risk": "a huge file lands in the data root"},
               ])
    assert ok["posted"] == 3


def test_unknown_extra_fields_warn_but_do_not_block(client: TestClient) -> None:
    out = _form(client, changes=[
        {"op": "add", "type": "feature", "name": "x", "path": ["app/main.py"],
         "shiny": "yes"}])
    assert any("shiny" in w for w in out["warnings"])


# ---------------------------------------------------------------------------
# 2. the receipt and idempotency
# ---------------------------------------------------------------------------


def test_nothing_changed_is_a_receipt_that_closes_the_reminder(client: TestClient) -> None:
    scan = _scan(client)
    sid = scan["metadata"]["id"]
    assert scan["architecture_entry"] is None
    assert any(sid in w and "lens architecture" in w for w in scan["warnings"])

    out = _form(client, trigger_id=sid, checked=list(GROUPS), changes=[])
    assert out["posted"] == 1 and out["ids"] == []

    again = client.get(f"/api/scans/{sid}").json()
    assert again["architecture_entry"] == out["check_id"]
    assert not any("lens architecture" in w for w in again["warnings"])


def test_reposting_the_same_form_appends_nothing(client: TestClient) -> None:
    first = _form(client)
    assert first["posted"] == 2 and first["skipped"] == 0
    second = _form(client, status=200)      # a repeat writes nothing new
    assert second["posted"] == 0 and second["skipped"] == 2
    assert second["ids"] == first["ids"]
    rows = client.get("/api/architecture").json()["architecture"]
    assert len([r for r in rows if r["op"] != "check"]) == 1


# ---------------------------------------------------------------------------
# 3. the screening
# ---------------------------------------------------------------------------


def test_state_screens_scans_and_folds_owes(client: TestClient) -> None:
    s1 = _scan(client)["metadata"]["id"]
    _form(client, trigger_id=s1,
          checked=[g for g in GROUPS if g not in ("does", "owes")],
          changes=[
              {"op": "add", "type": "feature", "name": "rate-limited requests",
               "path": ["app/main.py"], "surface": "api"},
              {"op": "add", "type": "debt", "name": "no cap on keys",
               "risk": "memory grows unbounded"},
              {"op": "add", "type": "action-needed", "name": "restart the service",
               "action": "./run.sh restart"},
          ])
    s2 = _scan(client, created_time="11:00", l1="cleanup")["metadata"]["id"]
    _form(client, created_time="11:01", trigger_id=s2,
          checked=[g for g in GROUPS if g != "owes"],
          changes=[
              {"op": "remove", "type": "debt", "name": "no cap on keys"},
          ])
    # a loose change, no scan behind it
    _form(client, created_time="12:00", trigger_id="",
          checked=[g for g in GROUPS if g != "holds"],
          changes=[{"op": "change", "type": "tests", "name": "backend pytest",
                    "path": ["tests"], "command": "pytest -q"}])

    state = client.get("/api/architecture/state", params={"project": "alpha"}).json()
    assert state["total_changes"] == 5
    by_id = {s["id"]: s for s in state["scans"]}
    assert [c["name"] for c in by_id[s2]["changes"]] == ["no cap on keys"]
    assert len(by_id[s1]["changes"]) == 3
    assert by_id[s1]["answered"] and by_id[s2]["answered"]
    assert "does" not in by_id[s1]["checked"] and "does" in by_id[s2]["checked"]
    assert [c["name"] for c in state["loose"]] == ["backend pytest"]
    # the debt was paid; the action still stands
    assert [o["name"] for o in state["owes"]] == ["restart the service"]
    types = {t["type"]: t["n"] for t in state["counts"]["types"]}
    assert types == {"feature": 1, "debt": 2, "action-needed": 1, "tests": 1}
    ops = {o["op"]: o["n"] for o in state["counts"]["ops"]}
    assert ops == {"add": 3, "remove": 1, "change": 1}
    groups = state["groups"]
    assert groups["does"] == ["feature", "fix"] and len(groups) == 8


def test_an_unanswered_scan_is_marked_owed(client: TestClient) -> None:
    sid = _scan(client)["metadata"]["id"]
    state = client.get("/api/architecture/state", params={"project": "alpha"}).json()
    scan = next(s for s in state["scans"] if s["id"] == sid)
    assert scan["answered"] is False and scan["changes"] == [] and scan["checked"] == []


def test_state_is_empty_and_cheap_for_a_project_without_entries(client: TestClient) -> None:
    r = client.get("/api/architecture/state", params={"project": "alpha"})
    assert r.status_code == 200 and r.headers.get("etag")
    body = r.json()
    assert body["scans"] == [] and body["owes"] == [] and body["total_changes"] == 0
    again = client.get("/api/architecture/state", params={"project": "alpha"},
                       headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304


def test_paths_are_not_checked_for_an_unregistered_project(client: TestClient) -> None:
    out = _form(client, project="beta", changes=[
        {"op": "add", "type": "feature", "name": "x", "path": ["anything/at/all.py"]}])
    assert out["posted"] == 2


# ---------------------------------------------------------------------------
# 4. the hook reminder
# ---------------------------------------------------------------------------


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def test_hook_architecture_due_once_per_scan_and_closed_by_any_row(root: Path) -> None:
    today = capture._yymm_dd(datetime.now())
    _write_csv(root / "scans.csv", ["id", "created_date", "created_time", "project"],
               [["sn_new", today, "09:00", "alpha"]])
    _write_csv(root / "files.csv", ["id", "trigger_id"], [["fl_1", "sn_new"]])
    cap = capture.TurnCapture(root, "alpha", "cc-h")

    s1 = cap.open_turn("what next?")
    assert s1["files_due"] is None
    assert s1["architecture_due"] == "sn_new"
    assert "architecture" in capture.format_signals(s1)
    cap.complete_turn("posting it")

    assert cap.open_turn("and now?")["architecture_due"] is None  # notified already

    # a check receipt (or any row) against the scan covers it for everyone
    _write_csv(root / "architecture.csv", ["id", "trigger_id"], [["ar_1", "sn_new"]])
    other = capture.TurnCapture(root, "alpha", "cc-other")
    assert other.open_turn("hi")["architecture_due"] is None
