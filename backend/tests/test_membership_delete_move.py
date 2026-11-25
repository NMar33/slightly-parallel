"""A project delete under the membership rules, and the one-chat move
(tk_d1d25a4d step 2, note nt_9de63b9e §5, §6).

- Rule 1: a project that holds the chat of an agent that is a member
  elsewhere is not deleted; the refusal names each agent and its projects.
- Rule 2: members from elsewhere get a leave row, «project deleted».
- The delete holds the ledger's lock from its check through the trash: a
  join of the project waits and is refused as unknown; a join elsewhere by
  one of its chats and the delete never both pass.
- The move: the happy path, each refusal (writing nothing), a hook writing
  during the copy, a crash between the rename and the trash.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import chatmove, chatstore
from backend import membership_fold as mf
from backend import memberships, project_admin
from backend.db import ViewStore
from backend.file_safety import acquire_flock
from backend.server import create_app
from tests.conftest import make_chat

A = "cc-aaaa1111"   # starts in ALPHA
B = "cc-bbbb2222"   # starts in BETA
TURNS = [("2026-11-20T10:00:00", "start", "started"), ("2026-11-20T10:05:00", "go on", "done")]
OLD = time.time() - 600


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


def age(folder: Path, when: float = OLD) -> None:
    """The chat has been quiet for a while (the move refuses a running agent)."""
    for p in folder.rglob("*"):
        os.utime(p, (when, when))


@pytest.fixture()
def root(data_root: Path) -> Path:
    make_chat(data_root, "ALPHA", A, TURNS)
    make_chat(data_root, "BETA", B, TURNS)
    (data_root / "projects" / "GAMMA").mkdir(parents=True)
    age(chatstore.folder(data_root, "ALPHA", A))
    return data_root


@pytest.fixture()
def op(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def post(client: TestClient, agent: str, **body) -> dict:
    r = client.post(f"/api/agents/{agent}/membership", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def delete(op: TestClient, code: str):
    return op.post("/api/setup/delete-data", json={"project_code": code, "confirm": code})


# ---------------------------------------------------------------------------
# The delete rules
# ---------------------------------------------------------------------------

def test_rule_one_refuses_and_names_the_agents(op: TestClient, root: Path) -> None:
    post(op, A, op="join", project="BETA")
    post(op, A, op="join", project="GAMMA")
    known = {p["code"]: p for p in op.get("/api/setup/info").json()["data_projects"]}
    assert known["ALPHA"]["held"] == [{"agent_id": A, "also_in": ["BETA", "GAMMA"]}]
    assert known["BETA"]["held"] == []
    before = tree(root)
    r = delete(op, "ALPHA")
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == (
        f"Project ALPHA holds chats of agents that are members elsewhere: {A} (also in BETA, GAMMA). "
        f"Move the chat of {A} to BETA? / Make them leave the other projects first?"
    )
    assert r.json()["held"] == [{"agent_id": A, "also_in": ["BETA", "GAMMA"]}]
    assert tree(root) == before
    # Leaving the other projects first lets it go ahead.
    post(op, A, op="leave", project="BETA")
    post(op, A, op="leave", project="GAMMA")
    assert delete(op, "ALPHA").status_code == 200


def test_setup_info_reads_the_ledger_once_for_every_project(op: TestClient, root: Path, monkeypatch) -> None:
    """data_projects[].held for every project from one ledger read and one
    walk of the chats, not one each per project and per agent."""
    for code in ("DELTA", "EPSILON", "ZETA"):
        make_chat(root, code, f"cc-{code.lower()[:4]}0000", TURNS)
    post(op, A, op="join", project="BETA")
    calls = {"read": 0, "walk": 0, "agent": 0}
    real_read, real_walk, real_agent = memberships.read_ledger, chatstore.iter_chats, memberships.chats_on_disk

    def read(*a, **k):
        calls["read"] += 1
        return real_read(*a, **k)

    def walk(*a, **k):
        calls["walk"] += 1
        return real_walk(*a, **k)

    def agent(*a, **k):
        calls["agent"] += 1
        return real_agent(*a, **k)

    monkeypatch.setattr(memberships, "read_ledger", read)
    monkeypatch.setattr(chatstore, "iter_chats", walk)
    monkeypatch.setattr(memberships, "chats_on_disk", agent)
    got = op.get("/api/setup/info").json()["data_projects"]
    assert len(got) >= 6
    assert {p["code"]: p["held"] for p in got}["ALPHA"] == [{"agent_id": A, "also_in": ["BETA"]}]
    assert calls == {"read": 1, "walk": 1, "agent": 0}, calls


def test_rule_two_writes_a_leave_for_members_from_elsewhere(op: TestClient, root: Path) -> None:
    post(op, B, op="join", project="ALPHA")
    r = delete(op, "ALPHA")
    assert r.status_code == 200, r.text
    assert r.json()["left"] == [B]
    rows, _ = mf.read(root / mf.LEDGER)
    assert [(x["op"], x["project"], x["value"], x["actor"]) for x in rows] == [
        ("join", "ALPHA", "", "operator"), ("leave", "ALPHA", mf.DELETED, "operator")]
    assert op.get(f"/api/agents/{B}/membership").json()["members"] == ["BETA"]
    # A restored ALPHA re-joins nobody: the ledger keeps the leave.
    (root / "projects" / "ALPHA").mkdir(parents=True)
    m = mf.load(root, {"ALPHA", "BETA"}, {B: "BETA"})
    assert m.members(B) == ["BETA"]


def test_a_join_of_the_project_waits_for_the_delete_then_is_refused(root: Path, monkeypatch) -> None:
    store = ViewStore(root)
    started, real = threading.Event(), project_admin._delete_project_data

    def slow(store_, *rest):
        started.set()
        time.sleep(1.0)
        return real(store_, *rest)

    monkeypatch.setattr(project_admin, "_delete_project_data", slow)
    t = threading.Thread(target=project_admin.delete_project_data, args=(store, "GAMMA"))
    t.start()
    assert started.wait(10)
    t0 = time.monotonic()
    with pytest.raises(memberships.Refused) as got:
        memberships.write(root, A, "join", "GAMMA")
    waited = time.monotonic() - t0
    t.join(30)
    assert got.value.status == 404 and "no project «GAMMA»" in got.value.detail
    assert waited > 0.5, waited  # it waited for the delete's lock
    assert not (root / mf.LEDGER).exists()


def test_a_join_elsewhere_and_the_delete_never_both_pass(root: Path, tmp_path: Path) -> None:
    """A starts in ALPHA. Its join of GAMMA and the delete of ALPHA race;
    either the delete is refused (rule 1) or the join (its chat is gone)."""
    template = tmp_path / "template"
    shutil.copytree(root, template)
    seen: dict[str, int] = {}
    for n in range(20):
        run = tmp_path / f"run{n}"
        shutil.copytree(template, run)
        store = ViewStore(run)
        out: dict[str, str] = {}
        go = threading.Event()

        def deleting(go=go, store=store, out=out) -> None:
            go.wait()
            try:
                project_admin.delete_project_data(store, "ALPHA")
                out["delete"] = "ok"
            except project_admin.ProjectHeld:
                out["delete"] = "refused"

        def joining(go=go, run=run, out=out) -> None:
            go.wait()
            try:
                memberships.write(run, A, "join", "GAMMA")
                out["join"] = "ok"
            except memberships.Refused as r:
                out["join"] = f"refused {r.status}"

        threads = [threading.Thread(target=deleting), threading.Thread(target=joining)]
        for t in threads:
            t.start()
        go.set()
        for t in threads:
            t.join(60)
        assert sorted(out.values()) in (["ok", "refused"], ["ok", "refused 404"]), out
        if out["join"] == "ok":
            assert out["delete"] == "refused" and chatstore.folder(run, "ALPHA", A).is_dir()
        else:
            assert out["delete"] == "ok" and not (run / "projects" / "ALPHA").exists()
        key = f"delete {out['delete']}"
        seen[key] = seen.get(key, 0) + 1
    print("join GAMMA vs delete ALPHA:", seen)


# ---------------------------------------------------------------------------
# The one-chat move
# ---------------------------------------------------------------------------

def test_the_move_happy_path_then_the_delete(op: TestClient, root: Path) -> None:
    post(op, A, op="join", project="BETA")
    src = chatstore.folder(root, "ALPHA", A)
    before = {k: v for k, v in tree(src).items() if k != "meta.json"}
    meta_before = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    r = op.post(f"/api/agents/{A}/move-chat", json={"to": "BETA"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["from"] == "ALPHA" and got["to"] == "BETA"
    assert got["turns"] == {"chat_md_turns": 2, "turns_jsonl_lines": 0, "message_count": 0}
    assert any("session ids change" in e for e in got["effects"])
    assert ("close the agent first; if it is started again from the old folder, "
            "it starts a new chat folder there") in got["effects"]
    dst = chatstore.folder(root, "BETA", A)
    assert {k: v for k, v in tree(dst).items() if k != "meta.json"} == before
    meta = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    assert meta == {**meta_before, "project": "BETA"}
    assert not src.exists()
    trashed = Path(got["trash"])
    assert trashed.parent == root / ".trash" and {k: v for k, v in tree(trashed).items()} == {
        **before, "meta.json": hashlib.sha256(json.dumps(meta_before).encode()).hexdigest()}
    assert not list((root / "projects" / "BETA" / "chats").glob(".incoming-*"))
    rows, _ = mf.read(root / mf.LEDGER)
    assert (rows[-1]["op"], rows[-1]["project"], rows[-1]["value"]) == ("moved", "BETA", "moved from ALPHA")
    assert op.get(f"/api/agents/{A}/membership").json()["members"] == ["BETA"]
    sessions = op.get("/api/sessions", params={"project": "BETA"}).json()["sessions"]
    assert {s["project"] for s in sessions if s["agent_id"] == A} == {"BETA"}
    assert all(s["agent_id"] != A for s in op.get("/api/sessions", params={"project": "ALPHA"}).json()["sessions"])
    # Then the delete of ALPHA goes ahead.
    assert delete(op, "ALPHA").status_code == 200


@pytest.mark.parametrize("case", ["running", "open-turn", "lock", "target-exists", "not-member", "origin",
                                  "no-agent", "shape", "agent-identity", "empty-to"])
def test_every_move_refusal_writes_nothing(op: TestClient, root: Path, case: str) -> None:
    post(op, A, op="join", project="BETA")
    src = chatstore.folder(root, "ALPHA", A)
    agent, body, status, words = A, {"to": "BETA"}, 409, ""
    hold = None
    if case == "running":
        age(src, time.time())
        words = "wrote in the last 60 s"
    elif case == "open-turn":
        meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
        meta["pending_turn"] = 3
        (src / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        age(src)
        words = "has a turn open"
    elif case == "lock":
        hold = acquire_flock(src / "turns.jsonl.lock", mode="a")
        hold.__enter__()
        words = "holds the turns.jsonl lock"
    elif case == "target-exists":
        chatstore.folder(root, "BETA", A).mkdir(parents=True)
        words = "has a folder for"
    elif case == "not-member":
        body, words = {"to": "GAMMA"}, "is not a member of GAMMA"
    elif case == "origin":
        body, words = {"to": "ALPHA"}, "is the origin"
    elif case == "no-agent":
        agent, status, words = "cc-nobody00", 404, "agent not found"
    elif case == "shape":
        body, status, words = {"to": ["BETA"]}, 422, "not a list"
    elif case == "agent-identity":
        body, status, words = {"to": "BETA", "actor": "cc-other999"}, 422, "operator"
    elif case == "empty-to":
        body, status, words = {}, 422, "to names"
    before = tree(root)
    try:
        r = op.post(f"/api/agents/{agent}/move-chat", json=body)
    finally:
        if hold is not None:
            hold.__exit__(None, None, None)
    assert r.status_code == status, r.text
    assert words in r.json()["detail"], r.text
    assert tree(root) == before
    assert not (root / "projects" / "BETA" / "chats").exists() or not list(
        (root / "projects" / "BETA" / "chats").glob(".incoming-*"))


@pytest.mark.parametrize("what", ["delete", "move"])
def test_an_unreadable_ledger_refuses_the_delete_and_the_move(op: TestClient, root: Path, what: str) -> None:
    """P17: a ledger that cannot be read is not an empty one — 503, nothing written."""
    (root / mf.LEDGER).write_bytes(b"id,at\n\xff\xfe bad\n")
    before = tree(root)
    if what == "delete":
        r = delete(op, "ALPHA")
    else:
        r = op.post(f"/api/agents/{A}/move-chat", json={"to": "BETA"})
    assert r.status_code == 503, r.text
    assert "membership ledger cannot be read" in r.json()["detail"]
    assert tree(root) == before
    assert (root / "projects" / "ALPHA").is_dir()


def test_a_crash_between_the_trash_and_the_moved_row(op: TestClient, root: Path, monkeypatch) -> None:
    """The chat is at BETA, its meta says BETA, the ledger has the join of
    BETA and no moved row: the fold reads that join as the trace of a move,
    and doctor raises no warning about it."""
    post(op, A, op="join", project="BETA")
    real = memberships.write

    def no_moved_row(root_, agent, op_, *a, **k):
        if op_ == "moved":
            raise RuntimeError("the machine went down")
        return real(root_, agent, op_, *a, **k)

    monkeypatch.setattr(memberships, "write", no_moved_row)
    with pytest.raises(chatmove.MoveRefused) as got:
        chatmove.move(root, A, "BETA")
    monkeypatch.undo()
    assert not chatstore.folder(root, "ALPHA", A).exists() and chatstore.folder(root, "BETA", A).is_dir()
    # The answer names the exact state, in one line (tk_dc394600).
    detail = got.value.detail
    assert got.value.status == 500 and "\n" not in detail
    assert str(chatstore.folder(root, "BETA", A)) in detail and str(root / ".trash") in detail, detail
    assert "the machine went down" in detail and "moved row" in detail, detail
    op.app.state.store.rebuild()
    assert op.get(f"/api/agents/{A}/membership").json()["members"] == ["BETA"]
    issues = [i for i in op.get("/api/doctor").json()["issues"] if i["kind"] == "membership-skipped"]
    assert issues == []
    m = mf.load(root, {"ALPHA", "BETA", "GAMMA"}, {A: "BETA"})
    assert m.skips == {"join_origin": 1}


def _load_capture():
    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
    spec = importlib.util.spec_from_file_location("sp_capture_for_move", hooks / "capture.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_for_move"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_a_hook_writing_during_the_copy_refuses_the_move(root: Path, monkeypatch) -> None:
    """The real TurnCapture, one instance alive across the copy: it writes a
    turn while the move holds the chat's locks (the hook goes ahead without
    them after its timeout). The move is refused at its second look, the
    original holds every turn, no copy is left behind."""
    capture = _load_capture()
    memberships.write(root, A, "join", "BETA")
    tc = capture.TurnCapture(root, "ALPHA", A)
    src = chatstore.folder(root, "ALPHA", A)
    real_copy = shutil.copytree
    wrote: dict[str, object] = {}

    def copy_then_hook(a, b, **kw):
        out = real_copy(a, b, **kw)
        t = threading.Thread(target=lambda: wrote.setdefault("turn", tc.full_turn("a turn during the move", "ok")))
        t.start()
        t.join(60)
        return out

    monkeypatch.setattr(chatmove.shutil, "copytree", copy_then_hook)
    with pytest.raises(chatmove.MoveRefused) as got:
        chatmove.move(root, A, "BETA")
    assert got.value.detail == chatmove.WROTE_DURING
    assert "turn" in wrote
    text = (src / "chat.md").read_text(encoding="utf-8")
    assert "a turn during the move" in text and text.count("## Turn") == 3
    assert json.loads((src / "meta.json").read_text(encoding="utf-8")).get("project") == "ALPHA"
    assert not chatstore.folder(root, "BETA", A).exists()
    assert not list((root / "projects" / "BETA" / "chats").glob(".incoming-*")) if (
        root / "projects" / "BETA" / "chats").exists() else True
    rows, _ = mf.read(root / mf.LEDGER)
    assert [x["op"] for x in rows] == ["join"]


def test_a_crash_between_rename_and_trash(op: TestClient, root: Path, monkeypatch) -> None:
    post(op, A, op="join", project="BETA")

    def crash(*_a, **_k):
        raise RuntimeError("the machine went down")

    monkeypatch.setattr(chatmove, "_trash", crash)
    with pytest.raises(RuntimeError):
        chatmove.move(root, A, "BETA")
    monkeypatch.undo()
    # Two folders: the next call finds the target and refuses.
    assert chatstore.folder(root, "ALPHA", A).is_dir() and chatstore.folder(root, "BETA", A).is_dir()
    op.app.state.store.rebuild()
    before = tree(root)
    r = op.post(f"/api/agents/{A}/move-chat", json={"to": "BETA"})
    assert r.status_code == 409 and "has a folder in BETA already" in r.json()["detail"], r.text
    assert tree(root) == before
    # The delete then goes ahead: the chat is filed at BETA too.
    r = delete(op, "ALPHA")
    assert r.status_code == 200, r.text
    assert chatstore.folder(root, "BETA", A).is_dir()


# ---------------------------------------------------------------------------
# The original goes to the trash with no handle open inside it (Windows
# cannot rename a folder that holds an open file: CI run 45523983400), by
# one rename, never a copy and a delete
# ---------------------------------------------------------------------------

def _open_fds_inside(folder: Path) -> list[str] | None:
    """The paths inside ``folder`` this process holds open, or None where
    there is no /proc/self/fd to read."""
    fds = Path("/proc/self/fd")
    if not fds.is_dir():
        return None
    inside = str(folder.resolve()) + os.sep
    out = []
    for fd in fds.iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if target.startswith(inside):
            out.append(target)
    return out


def _rename_into_trash(monkeypatch, before=None, fail: bool = False) -> None:
    """Wrap ``os.rename`` for the rename whose target is under ``.trash``:
    run ``before(src)`` first, or fail the way Windows does (WinError 5)."""
    real = os.rename

    def rename(a, b, *rest, **kw):
        if chatmove.TRASH_DIR in Path(b).parts:
            if before is not None:
                before(Path(a))
            if fail:
                raise PermissionError(13, "Access is denied", str(a))
        return real(a, b, *rest, **kw)

    monkeypatch.setattr(os, "rename", rename)


def test_no_lock_handle_is_open_when_the_original_goes_to_the_trash(root: Path, monkeypatch) -> None:
    memberships.write(root, A, "join", "BETA")
    src = chatstore.folder(root, "ALPHA", A)
    handles: list = []
    real_flock = chatmove.acquire_flock

    @contextlib.contextmanager
    def tracked(path, **kw):
        with real_flock(path, **kw) as fh:
            handles.append((Path(path), fh))
            yield fh

    seen: dict[str, object] = {}

    def look(folder: Path) -> None:
        seen["open_locks"] = [p.name for p, fh in handles if not fh.closed and p.is_relative_to(folder)]
        seen["fds"] = _open_fds_inside(folder)

    monkeypatch.setattr(chatmove, "acquire_flock", tracked)
    _rename_into_trash(monkeypatch, before=look)
    chatmove.move(root, A, "BETA")
    assert {p.name for p, _fh in handles} == {f"{n}.lock" for n in chatmove.LOCKED_FILES}
    assert seen["open_locks"] == [], seen
    if seen["fds"] is not None:  # the /proc variant, where there is one
        assert seen["fds"] == [], seen
    assert not src.exists() and chatstore.folder(root, "BETA", A).is_dir()


def test_a_write_between_the_release_and_the_trash_leaves_the_original(root: Path, monkeypatch) -> None:
    """A hook writes the moment the move lets go of the meta lock (the last
    one released). The original stays whole where it is, with the write;
    the target stays; no moved row; the one-line refusal names both
    folders; the next call is refused (the crash between rename and trash)."""
    memberships.write(root, A, "join", "BETA")
    src = chatstore.folder(root, "ALPHA", A)
    real_flock = chatmove.acquire_flock

    @contextlib.contextmanager
    def then_write(path, **kw):
        with real_flock(path, **kw) as fh:
            yield fh
        if Path(path).name == "meta.json.lock":
            with open(src / "chat.md", "a", encoding="utf-8") as out:
                out.write("\n## Turn 3 written after the release\n")

    monkeypatch.setattr(chatmove, "acquire_flock", then_write)
    with pytest.raises(chatmove.MoveRefused) as got:
        chatmove.move(root, A, "BETA")
    monkeypatch.undo()
    dst = chatstore.folder(root, "BETA", A)
    assert str(src) in got.value.detail and str(dst) in got.value.detail
    assert "\n" not in got.value.detail
    assert "written after the release" in (src / "chat.md").read_text(encoding="utf-8")
    assert "written after the release" not in (dst / "chat.md").read_text(encoding="utf-8")
    assert not (root / ".trash").exists()
    rows, _ = mf.read(root / mf.LEDGER)
    assert [x["op"] for x in rows] == ["join"]
    with pytest.raises(chatmove.MoveRefused) as again:
        chatmove.move(root, A, "BETA")
    assert "has a folder in BETA already" in again.value.detail


def test_a_failed_rename_to_the_trash_deletes_nothing(root: Path, monkeypatch) -> None:
    """The rename of the original to the trash fails (Windows: WinError 5).
    No copy-then-delete fallback: the original keeps every file byte for
    byte, the target stays, no moved row, the refusal names both folders."""
    memberships.write(root, A, "join", "BETA")
    src = chatstore.folder(root, "ALPHA", A)
    before = tree(src)
    _rename_into_trash(monkeypatch, fail=True)
    with pytest.raises(chatmove.MoveRefused) as got:
        chatmove.move(root, A, "BETA")
    monkeypatch.undo()
    dst = chatstore.folder(root, "BETA", A)
    assert str(src) in got.value.detail and str(dst) in got.value.detail
    assert "\n" not in got.value.detail
    assert tree(src) == before
    assert dst.is_dir()
    assert not any(p.is_file() for p in (root / ".trash").rglob("*")) if (root / ".trash").exists() else True
    rows, _ = mf.read(root / mf.LEDGER)
    assert [x["op"] for x in rows] == ["join"]


def test_a_write_after_the_last_look_is_kept_in_the_trash_and_said(op: TestClient, root: Path,
                                                                    monkeypatch) -> None:
    """A write lands in the original after the post-release look, in the
    instant before the rename: the rename takes it whole into the trash.
    The move is done, and the answer and the moved row say the write is in
    the trash, not at the target."""
    post(op, A, op="join", project="BETA")

    def write(src: Path) -> None:
        with open(src / "chat.md", "a", encoding="utf-8") as fh:
            fh.write("\n## Turn 3 written before the rename\n")

    _rename_into_trash(monkeypatch, before=write)
    got = chatmove.move(root, A, "BETA")
    monkeypatch.undo()
    dst = chatstore.folder(root, "BETA", A)
    trashed = Path(got["trash"])
    assert "written before the rename" in (trashed / "chat.md").read_text(encoding="utf-8")
    assert "written before the rename" not in (dst / "chat.md").read_text(encoding="utf-8")
    warn = (f"a write reached the original after the copy; it is kept in .trash/{trashed.name}/, "
            f"not in projects/BETA/chats/{A}")
    assert got["warning"] == warn
    rows, _ = mf.read(root / mf.LEDGER)
    assert rows[-1]["op"] == "moved" and rows[-1]["value"] == f"moved from ALPHA; {warn}"
    op.app.state.store.rebuild()
    assert op.get(f"/api/agents/{A}/membership").json()["members"] == ["BETA"]
    assert mf.load(root, {"ALPHA", "BETA", "GAMMA"}, {A: "BETA"}).skips == {}


# ---------------------------------------------------------------------------
# A refused move can be undone from inside the product (tk_dc394600)
# ---------------------------------------------------------------------------

def _two_folders(op: TestClient, root: Path, monkeypatch) -> tuple[Path, Path]:
    """The state a move leaves when it stops between the rename and the
    trash: the original at ALPHA, its copy at BETA."""
    post(op, A, op="join", project="BETA")

    def crash(*_a, **_k):
        raise RuntimeError("the machine went down")

    with monkeypatch.context() as m:
        m.setattr(chatmove, "_trash", crash)
        with pytest.raises(RuntimeError):
            chatmove.move(root, A, "BETA")
    op.app.state.store.rebuild()
    return chatstore.folder(root, "ALPHA", A), chatstore.folder(root, "BETA", A)


@pytest.mark.parametrize("newer", ["same", "original", "target"])
def test_a_second_try_says_which_folder_is_newer_and_what_to_do(op: TestClient, root: Path,
                                                                monkeypatch, newer: str) -> None:
    src, dst = _two_folders(op, root, monkeypatch)
    if newer == "original":
        with open(src / "chat.md", "a", encoding="utf-8") as fh:
            fh.write("\n## Turn 3 after the copy\n")
    elif newer == "target":
        with open(dst / "chat.md", "a", encoding="utf-8") as fh:
            fh.write("\n## Turn 3 at the target\n")
    age(src)
    r = op.post(f"/api/agents/{A}/move-chat", json={"to": "BETA"})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "has a folder in BETA already" in detail and "\n" not in detail
    assert str(src) in detail and str(dst) in detail, detail
    if newer == "target":
        assert "holds writes the original" in detail and "by hand" in detail, detail
        assert "move-chat/abandon" not in detail
    else:
        assert ("the same chat" if newer == "same" else "the original is newer") in detail, detail
        assert "move-chat/abandon" in detail and "then move it again" in detail, detail


def test_abandon_takes_only_the_copy_then_the_move_goes_ahead(op: TestClient, root: Path,
                                                              monkeypatch) -> None:
    src, dst = _two_folders(op, root, monkeypatch)
    with open(src / "chat.md", "a", encoding="utf-8") as fh:
        fh.write("\n## Turn 3 after the copy\n")
    age(src)
    original, copy = tree(src), tree(dst)
    r = op.post(f"/api/agents/{A}/move-chat/abandon", json={"to": "BETA"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert tree(src) == original
    assert not dst.exists()
    trashed = Path(got["trash"])
    assert trashed.parent == root / ".trash" and tree(trashed / A) == copy
    rows, _ = mf.read(root / mf.LEDGER)
    assert [x["op"] for x in rows] == ["join"]
    r = op.post(f"/api/agents/{A}/move-chat", json={"to": "BETA"})
    assert r.status_code == 200, r.text
    assert "after the copy" in (dst / "chat.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("case", ["no-copy", "target-newer", "only-folder", "agent-identity", "running"])
def test_every_abandon_refusal_writes_nothing(op: TestClient, root: Path, monkeypatch, case: str) -> None:
    body, status, words = {"to": "BETA"}, 409, ""
    hold = None
    if case == "no-copy":
        post(op, A, op="join", project="BETA")
        words = "no copy"
    else:
        src, dst = _two_folders(op, root, monkeypatch)
        if case == "target-newer":
            with open(dst / "chat.md", "a", encoding="utf-8") as fh:
                fh.write("\n## Turn 3 at the target\n")
            words = "holds writes the original"
        elif case == "only-folder":
            shutil.move(str(src), str(root / "aside"))  # the copy is the only chat left
            words = "the only folder"
        elif case == "agent-identity":
            body, status, words = {"to": "BETA", "actor": "cc-other999"}, 422, "operator"
        elif case == "running":
            hold = acquire_flock(dst / "turns.jsonl.lock", mode="a")
            hold.__enter__()
            words = "holds the turns.jsonl lock"
    before = tree(root)
    try:
        r = op.post(f"/api/agents/{A}/move-chat/abandon", json=body)
    finally:
        if hold is not None:
            hold.__exit__(None, None, None)
    assert r.status_code == status, r.text
    assert words in r.json()["detail"], r.text
    assert "\n" not in r.json()["detail"]
    assert tree(root) == before


def test_the_effects_say_a_write_during_the_move_can_land_in_the_trash() -> None:
    effects = [e.format(to="BETA") for e in chatmove.EFFECTS]
    assert any("during the move" in e and "trash" in e and "close the agent" in e for e in effects), effects


def test_a_trashed_original_that_cannot_be_read_still_writes_the_moved_row(op: TestClient, root: Path,
                                                                          monkeypatch) -> None:
    post(op, A, op="join", project="BETA")
    real = chatmove.fingerprint_bytes

    def unreadable(folder: Path):
        if chatmove.TRASH_DIR in Path(folder).parts:
            raise PermissionError(13, "Access is denied", str(folder))
        return real(folder)

    monkeypatch.setattr(chatmove, "fingerprint_bytes", unreadable)
    got = chatmove.move(root, A, "BETA")
    monkeypatch.undo()
    assert "could not be compared" in got["warning"] and "Access is denied" in got["warning"], got
    rows, _ = mf.read(root / mf.LEDGER)
    assert rows[-1]["op"] == "moved" and got["warning"] in rows[-1]["value"]
