"""The membership ledger and its API (tk_d1d25a4d step 2, note nt_9de63b9e §3, §6).

- Only the operator writes; every refusal is one line and leaves the data
  folder byte-identical (docs/testing.md #9), wrong shapes included (#8).
- Two processes posting conflicting rows end in a valid state that the
  file order explains.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import membership_fold as mf
from backend.server import create_app
from tests.conftest import make_chat

AGENT = "cc-aaaa1111"
HELPER = "cc-help0001"
TURNS = [("2026-11-20T10:00:00", "start the work", "started"),
         ("2026-11-20T10:05:00", "go on", "done")]


def tree(root: Path) -> dict[str, str]:
    """Every file under the data root by sha256, lock sidecars aside (taking
    a lock makes one; it is not a write)."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(".lock"):
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture()
def root(data_root: Path) -> Path:
    make_chat(data_root, "ALPHA", AGENT, TURNS)
    make_chat(data_root, "ALPHA", HELPER, TURNS)
    meta = data_root / "projects" / "ALPHA" / "chats" / HELPER / "meta.json"
    m = json.loads(meta.read_text(encoding="utf-8"))
    m.update({"helper": True, "helper_of": AGENT})
    meta.write_text(json.dumps(m), encoding="utf-8")
    (data_root / "projects" / "GAMMA").mkdir(parents=True)
    return data_root


@pytest.fixture()
def op(root: Path):
    """A client as the operator's page: no MCP mark, the operator's cookie."""
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def test_no_rows_answers_as_today(op: TestClient) -> None:
    r = op.get(f"/api/agents/{AGENT}/membership")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["members"] == ["ALPHA"] and got["home"] == "ALPHA" and got["level"] == 2
    assert got["summary"] == (
        f"agent {AGENT}\nhome: ALPHA · member of: ALPHA · runs from folder: ALPHA\n"
        "task level: 2 (picks by context)"
    )


def test_join_then_leave_and_the_level(op: TestClient, root: Path) -> None:
    r = op.post(f"/api/agents/{AGENT}/membership", json={"op": "join", "project": "BETA"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["members"] == ["ALPHA", "BETA"] and got["projects"] == "ALPHA,BETA"
    assert "member of: ALPHA, BETA" in got["summary"]
    assert got["row"]["actor"] == "operator"
    r = op.post(f"/api/agents/{AGENT}/membership", json={"op": "level", "value": 3})
    assert r.status_code == 200, r.text
    assert r.json()["level"] == 3 and "task level: 3 (moves tasks)" in r.json()["summary"]
    r = op.post(f"/api/agents/{AGENT}/membership", json={"op": "leave", "project": "BETA"})
    assert r.status_code == 200, r.text
    assert r.json()["members"] == ["ALPHA"]
    rows, cut = mf.read(root / mf.LEDGER)
    assert [x["op"] for x in rows] == ["join", "level", "leave"] and cut == 0
    assert op.get("/api/doctor").status_code == 200


REFUSALS = [
    # (body, status, words in the refusal)
    ({"op": "join", "project": "BETA", "actor": "cc-other999"}, 422, "operator"),
    ({"op": "join", "project": "BETA", "agent_id": "cc-other999"}, 422, "operator"),
    ({"op": "join", "project": "NOPE"}, 404, "no project «NOPE»"),
    ({"op": "home", "project": "BETA"}, 409, "steps 3 and 8"),
    ({"op": "leave", "project": "ALPHA"}, 409, "the origin is left after the home moves"),
    ({"op": "leave", "project": "BETA"}, 409, "is not in BETA"),
    ({"op": "join", "project": "ALPHA"}, 409, "is in ALPHA already"),
    ({"op": "level", "value": "2"}, 409, "task level 2 already"),
    ({"op": "level", "value": "5"}, 422, "1, 2 or 3"),
    ({"op": "level", "value": 0}, 422, "1, 2 or 3"),
    ({"op": "moved", "project": "BETA", "value": "moved from ALPHA"}, 422, "move-chat"),
    ({"op": "join", "project": "BETA", "value": "project deleted"}, 422, "project delete"),
    ({"op": "join", "project": "BETA", "value": "moved from ALPHA"}, 422, "chat move"),
    ({"op": "join", "project": "BETA", "value": "two\nlines"}, 422, "one line"),
    ({"op": "promote", "project": "BETA"}, 422, "op is one of"),
    ({"op": "join"}, 422, "needs a project"),
    # Wrong shapes (#8): the right meaning in the wrong shape.
    ({"op": ["join"], "project": "BETA"}, 422, "not a list"),
    ({"op": "join", "project": ["BETA"]}, 422, "not a list"),
    ({"op": "join", "project": {"code": "BETA"}}, 422, "not a dict"),
    ({"op": "join", "project": 5}, 422, "not a int"),
    ({"op": "level", "value": [3]}, 422, "not a list"),
    ({"op": "level", "value": True}, 422, "not a bool"),
    ({"op": "join", "project": "BETA", "value": 7}, 422, "not a int"),
]


@pytest.mark.parametrize("body,status,words", REFUSALS, ids=lambda x: json.dumps(x) if isinstance(x, dict) else str(x))
def test_every_refusal_writes_nothing(op: TestClient, root: Path, body, status, words) -> None:
    before = tree(root)
    r = op.post(f"/api/agents/{AGENT}/membership", json=body)
    assert r.status_code == status, r.text
    assert words in r.json()["detail"], r.text
    assert "\n" not in r.json()["detail"]
    assert tree(root) == before


@pytest.mark.parametrize("agent,body,status,words", [
    (HELPER, {"op": "join", "project": "BETA"}, 409, "helper chat"),
    ("cc-nobody00", {"op": "join", "project": "BETA"}, 404, "agent not found"),
])
def test_helpers_and_unknown_agents_are_refused(op: TestClient, root: Path, agent, body, status, words) -> None:
    before = tree(root)
    r = op.post(f"/api/agents/{agent}/membership", json=body)
    assert r.status_code == status and words in r.json()["detail"], r.text
    assert tree(root) == before


def test_an_agent_is_refused_in_one_plain_sentence(op: TestClient, root: Path) -> None:
    r = op.post(f"/api/agents/{AGENT}/membership", json={"op": "join", "project": "BETA", "actor": "cc-other999"})
    assert r.json()["detail"] == "Changing an agent's projects is the operator's — ask the operator"
    r = op.post(f"/api/agents/{AGENT}/move-chat", json={"to": "BETA", "actor": "cc-other999"})
    assert r.json()["detail"] == ("Moving a chat between projects is the operator's — "
                                  "ask the operator to move it from the project delete dialog")


def test_a_body_that_is_not_an_object(op: TestClient, root: Path) -> None:
    before = tree(root)
    for body in (["join", "BETA"], "join", 3):
        r = op.post(f"/api/agents/{AGENT}/membership", json=body)
        assert r.status_code == 422, r.text
    assert tree(root) == before


def test_a_write_without_the_operator_cookie_is_refused(op: TestClient, root: Path) -> None:
    before = tree(root)
    op.cookies.clear()
    r = op.post(f"/api/agents/{AGENT}/membership", json={"op": "join", "project": "BETA"})
    assert r.status_code == 403, r.text
    assert tree(root) == before


def test_the_ledger_is_a_ledger_view_in_the_chats_area(op: TestClient, root: Path) -> None:
    from backend.db import ViewStore
    assert ViewStore._area(Path(mf.LEDGER)) == "chats"
    store = op.app.state.store
    before = store.stamps["chats"]
    time.sleep(0.01)
    op.post(f"/api/agents/{AGENT}/membership", json={"op": "join", "project": "BETA"})
    assert store.stamps["chats"] > before
    got = store.query("SELECT agent_id, op, project FROM agent_memberships_mutual")
    assert got == [{"agent_id": AGENT, "op": "join", "project": "BETA"}]


def test_an_unreadable_ledger_refuses_the_write(op: TestClient, root: Path) -> None:
    """P17: a ledger that cannot be read is not an empty one."""
    (root / mf.LEDGER).write_bytes(b"id,at\n\xff\xfe bad\n")
    before = tree(root)
    r = op.post(f"/api/agents/{AGENT}/membership", json={"op": "join", "project": "BETA"})
    assert r.status_code == 503 and "cannot be read" in r.json()["detail"], r.text
    assert tree(root) == before
    # The lists go on showing what they showed, and say why.
    assert op.get("/api/sessions", params={"project": "ALPHA"}).status_code == 200


# ---------------------------------------------------------------------------
# Two processes, conflicting rows (note §6): 50 runs each pair.
# ---------------------------------------------------------------------------

_RACER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from backend import memberships
root, agent, op, project, value, start = sys.argv[2:8]
while time.time() < float(start):
    pass
try:
    memberships.write(root, agent, op, project, value)
    print("ok")
except memberships.Refused as r:
    print("refused:" + r.detail)
"""


def _race(root: Path, a: tuple[str, str, str], b: tuple[str, str, str]) -> tuple[str, str]:
    backend_dir = str(Path(__file__).resolve().parents[1])
    start = str(time.time() + 0.4)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    procs = [subprocess.Popen([sys.executable, "-c", _RACER, backend_dir, str(root), AGENT, *x, start],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env) for x in (a, b)]
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err
        outs.append(out.strip())
    return outs[0], outs[1]


def _state(root: Path) -> tuple[list[dict], mf.Membership]:
    rows, cut = mf.read(root / mf.LEDGER)
    assert cut == 0
    m = mf.fold(rows, {"ALPHA", "BETA", "GAMMA"}, {AGENT: "ALPHA"})
    assert not m.skips, m.skips  # every row the lock let through applies
    return rows, m


def test_join_against_the_deletes_leave_in_two_processes(root: Path) -> None:
    led = root / mf.LEDGER
    seen: dict[str, int] = {}
    for _ in range(50):
        led.unlink(missing_ok=True)
        j, lv = _race(root, ("join", "BETA", ""), ("leave", "BETA", mf.DELETED))
        seen[lv.split(":")[0]] = seen.get(lv.split(":")[0], 0) + 1
        rows, m = _state(root)
        ops = [r["op"] for r in rows]
        assert j == "ok"
        if lv == "ok":
            # The join came first in the file, then the leave.
            assert ops == ["join", "leave"] and m.members(AGENT) == ["ALPHA"]
        else:
            assert lv.startswith("refused:") and "is not in BETA" in lv
            assert ops == ["join"] and m.members(AGENT) == ["ALPHA", "BETA"]
    print("join vs leave, the leave's outcomes:", seen)


def test_level_three_against_level_one_in_two_processes(root: Path) -> None:
    led = root / mf.LEDGER
    seen: dict[str, int] = {}
    for _ in range(50):
        led.unlink(missing_ok=True)
        a, b = _race(root, ("level", "", "3"), ("level", "", "1"))
        rows, m = _state(root)
        seen[rows[-1]["value"]] = seen.get(rows[-1]["value"], 0) + 1
        assert a == "ok" and b == "ok"  # from 2, both are changes
        assert len(rows) == 2 and m.level(AGENT) == int(rows[-1]["value"])
    print("level 3 vs level 1, the last in the file:", seen)


def test_doctor_reports_the_rows_the_fold_skipped(op: TestClient, root: Path) -> None:
    head = ",".join(mf.COLUMNS) + "\n"
    (root / mf.LEDGER).write_text(
        head + f"am_1,2026-11-25T10:00:00,{AGENT},join,BETA,,operator\n"
        f"am_2,2026-11-25T10:01:00,{AGENT},join,BETA,,operator\n"
        f"am_3,2026-11-25T10:02:00,{AGENT},level,,9,operator\n", encoding="utf-8")
    op.app.state.store.rebuild()
    got = op.get("/api/doctor").json()
    found = {i["detail"].split(":")[1].split("—")[0].strip() for i in got["issues"] if i["kind"] == "membership-skipped"}
    assert found == {"join_twice", "bad_level"}, got["issues"]


def test_append_checked_writes_only_when_the_check_passes(tmp_path: Path) -> None:
    from backend.csvio import append_checked, read_rows
    f = tmp_path / "x.csv"
    assert append_checked(f, ("id", "v"), {"id": "1", "v": "a"}, lambda rows: None) is None
    assert append_checked(f, ("id", "v"), {"id": "2", "v": "b"}, lambda rows: f"have {len(rows)}") == "have 1"
    assert [r["id"] for r in read_rows(f)] == ["1"]
    f.write_bytes(b"id,v\n\xff\xfe\n")
    with pytest.raises(UnicodeDecodeError):
        append_checked(f, ("id", "v"), {"id": "3", "v": "c"}, lambda rows: None)
    assert f.read_bytes() == b"id,v\n\xff\xfe\n"
