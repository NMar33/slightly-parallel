"""The agent-done loop: reports move only opted-in tasks, evidence lands
as files + ledger rows, prompts are named and editable, and the update
guard keeps agents off the board."""

from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient
from tests.conftest import git_env, git_repo

PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
).decode()


def _mk_task(client: TestClient, title: str, **fields) -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-31", "created_time": "12:00",
        "project": "ALPHA", "agent_id": "operator", "title": title,
        "status": "doing", **fields,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["metadata"]["id"]


def _task(client: TestClient, tid: str) -> dict:
    tasks = client.get("/api/tasks?project=ALPHA").json()["tasks"]
    return next(t for t in tasks if t["id"] == tid)


# ---------------------------------------------------------------- report ---


def test_report_without_auto_stamps_but_never_moves(client: TestClient) -> None:
    tid = _mk_task(client, "quiet report")
    r = client.post(f"/api/tasks/{tid}/report", json={
        "agent_id": "cc-test", "summary": "wired and verified",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["moved"] is False and body["evidence"] is False
    t = _task(client, tid)
    assert t["status"] == "doing"                # never moved
    assert t["agent_done_by"] == "cc-test"       # but the opinion shows
    assert t["agent_done_note"] == "wired and verified"


def test_report_with_auto_moves_to_review_and_stamps(client: TestClient) -> None:
    tid = _mk_task(client, "auto report")
    client.post(f"/api/tasks/{tid}/update", json={"auto_manage": "yes"})
    r = client.post(f"/api/tasks/{tid}/report", json={"agent_id": "cc-test", "summary": "done"})
    assert r.json()["moved"] is True
    t = _task(client, tid)
    assert t["status"] == "review"
    assert t["agent_moved_at"]
    # the history names the agent
    events = client.get(f"/api/tasks/{tid}/events").json()["events"]
    move = next(e for e in events if e["field"] == "status" and e["new_value"] == "review")
    assert move["actor"] == "cc-test"


def test_report_answers_with_the_evidence_prompt(client: TestClient) -> None:
    tid = _mk_task(client, "prove it")
    client.post(f"/api/tasks/{tid}/update", json={"evidence_required": "yes"})
    body = client.post(f"/api/tasks/{tid}/report", json={"agent_id": "cc-test"}).json()
    assert body["evidence"] is True
    assert "before/after" in body["evidence_prompt"]
    assert "task_evidence" in body["next"] and "POST" not in body["next"]


# ----------------------------------------------------------------- guard ---


def test_agent_status_change_refused_without_auto(client: TestClient) -> None:
    tid = _mk_task(client, "hands off")
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "done", "actor": "cc-test"})
    assert r.status_code == 422
    assert "report" in r.json()["detail"]
    # operator (default actor) still may
    r2 = client.post(f"/api/tasks/{tid}/update", json={"status": "done"})
    assert r2.status_code == 200


def test_agent_status_change_allowed_with_auto(client: TestClient) -> None:
    tid = _mk_task(client, "opted in")
    client.post(f"/api/tasks/{tid}/update", json={"auto_manage": "yes"})
    r = client.post(f"/api/tasks/{tid}/update", json={"status": "review", "actor": "cc-test"})
    assert r.status_code == 200


def test_operator_verdict_clears_the_report_stamps(client: TestClient) -> None:
    tid = _mk_task(client, "verdict clears")
    client.post(f"/api/tasks/{tid}/report", json={"agent_id": "cc-test", "summary": "done imo"})
    assert _task(client, tid)["agent_done_by"] == "cc-test"
    client.post(f"/api/tasks/{tid}/update", json={"status": "done"})
    t = _task(client, tid)
    # DuckDB reads a cleared CSV cell back as NULL — empty either way.
    assert not t["agent_done_by"] and not t["agent_done_note"]


# -------------------------------------------------------------- evidence ---


def test_evidence_text_and_image_round_trip(client: TestClient, data_root) -> None:
    tid = _mk_task(client, "with proof")
    r = client.post(f"/api/tasks/{tid}/evidence", json={
        "agent_id": "cc-test",
        "items": [
            {"kind": "text", "title": "tests pass", "body": "34 passed, 0 failed"},
            {"kind": "image", "title": "after", "data_base64": PNG, "ext": "png"},
        ],
    })
    assert r.status_code == 201, r.text
    saved = r.json()["saved"]
    assert [s["kind"] for s in saved] == ["text", "image"]

    listing = client.get(f"/api/tasks/{tid}/evidence").json()["evidence"]
    assert len(listing) == 2
    img = next(e for e in listing if e["kind"] == "image")
    assert (data_root / img["body"]).exists()
    f = client.get(img["url"])
    assert f.status_code == 200
    assert f.content[:4] == b"\x89PNG"


def test_evidence_summary_counts_per_task_for_the_board(client: TestClient) -> None:
    """The card's mark: one query per project, items and images apart."""
    a = _mk_task(client, "with proof")
    b = _mk_task(client, "nothing shown")
    client.post(f"/api/tasks/{a}/evidence", json={
        "agent_id": "cc-test",
        "items": [
            {"kind": "text", "title": "tests pass", "body": "34 passed"},
            {"kind": "image", "title": "after", "data_base64": PNG, "ext": "png"},
            {"kind": "image", "title": "before", "data_base64": PNG, "ext": "png"},
        ],
    })
    d = client.get("/api/tasks/evidence/summary?project=ALPHA").json()
    assert d["evidence"] == {a: 3}
    assert d["images"] == {a: 2}
    assert b not in d["evidence"]  # a task with none is simply absent
    assert client.get("/api/tasks/evidence/summary?project=NOPE").json()["evidence"] == {}


def test_evidence_delete_drops_the_row_and_the_file(client: TestClient, data_root) -> None:
    """The operator's cut: the ledger row goes, and so does the screenshot."""
    tid = _mk_task(client, "too much proof")
    client.post(f"/api/tasks/{tid}/evidence", json={
        "agent_id": "cc-test",
        "items": [
            {"kind": "text", "title": "keep", "body": "34 passed"},
            {"kind": "image", "title": "drop", "data_base64": PNG, "ext": "png"},
        ],
    })
    listing = client.get(f"/api/tasks/{tid}/evidence").json()["evidence"]
    img = next(e for e in listing if e["kind"] == "image")
    path = data_root / img["body"]
    assert path.exists()

    r = client.post(f"/api/tasks/evidence/{img['id']}/delete")
    assert r.status_code == 200, r.text
    assert r.json()["task_id"] == tid
    assert not path.exists()

    left = client.get(f"/api/tasks/{tid}/evidence").json()["evidence"]
    assert [e["title"] for e in left] == ["keep"]
    assert client.get("/api/tasks/evidence/summary?project=ALPHA").json()["images"].get(tid, 0) == 0
    assert client.post(f"/api/tasks/evidence/{img['id']}/delete").status_code == 404


def test_evidence_validation(client: TestClient) -> None:
    tid = _mk_task(client, "bad proof")
    assert client.post(f"/api/tasks/{tid}/evidence", json={
        "agent_id": "cc-test", "items": [{"kind": "video", "title": "x"}],
    }).status_code == 422
    assert client.post(f"/api/tasks/{tid}/evidence", json={
        "agent_id": "cc-test",
        "items": [{"kind": "image", "title": "x", "data_base64": "%%%", "ext": "png"}],
    }).status_code == 422
    assert client.post(f"/api/tasks/{tid}/evidence", json={
        "agent_id": "", "items": [{"kind": "text", "title": "x", "body": "y"}],
    }).status_code == 422


# --------------------------------------------------------------- prompts ---


def test_prompt_store_named_saved_defaulted(client: TestClient) -> None:
    base = client.get("/api/evidence-prompts").json()
    assert base["default_id"] == "default"
    assert any(p["id"] == "default" for p in base["prompts"])

    r = client.post("/api/evidence-prompts", json={
        "name": "UI work", "text": "Always attach before/after screenshots.",
        "make_default": True,
    })
    assert r.status_code == 200
    pid = r.json()["saved"]
    now = client.get("/api/evidence-prompts").json()
    assert now["default_id"] == pid

    # a task with evidence on now receives the new default
    tid = _mk_task(client, "ui task")
    client.post(f"/api/tasks/{tid}/update", json={"evidence_required": "yes"})
    body = client.post(f"/api/tasks/{tid}/report", json={"agent_id": "cc-test"}).json()
    assert body["evidence_prompt"].startswith("Always attach")

    # rename in place; delete falls back to the built-in
    client.post("/api/evidence-prompts", json={"id": pid, "name": "UI work v2", "text": "New text."})
    assert any(p["name"] == "UI work v2" for p in client.get("/api/evidence-prompts").json()["prompts"])
    client.post(f"/api/evidence-prompts/{pid}/delete")
    assert client.get("/api/evidence-prompts").json()["default_id"] == "default"
    assert client.post("/api/evidence-prompts/default/delete").status_code == 409


def test_evidence_says_what_was_touched_and_what_was_done(client: TestClient) -> None:
    """The upgrade: two structured kinds beside the text and the screenshots."""
    tid = _mk_task(client, "Rich evidence")
    r = client.post(f"/api/tasks/{tid}/evidence", json={"agent_id": "cc-x", "items": [
        {"kind": "files", "title": "What changed",
         "start_here": "backend/routers/evidence.py:evidence_add",
         "paths": [
             {"path": "backend/routers/evidence.py", "action": "changed",
              "lines_add": 120, "lines_del": 30, "importance": 5,
              "blast_radius": 8, "test_coverage": "covered", "why": "the whole flow"},
             "backend/evidence_items.py",
         ]},
        {"kind": "change", "title": "What landed", "changes": [
            {"op": "add", "type": "feature", "name": "evidence says what a task did",
             "path": "backend/evidence_items.py", "note": "two structured kinds"},
        ]},
    ]})
    assert r.status_code == 201, r.text

    got = client.get(f"/api/tasks/{tid}/evidence").json()
    files = next(i for i in got["evidence"] if i["kind"] == "files")
    assert files["start_here"].endswith(":evidence_add")
    assert [p["path"] for p in files["paths"]] == [
        "backend/routers/evidence.py", "backend/evidence_items.py",
    ]
    # the file entry's own words: "changed" is spelt "modified", and a bare
    # string is a record with the default action.
    assert files["paths"][0]["action"] == "modified"
    assert files["paths"][1]["action"] == "modified"
    # No captured turn named this task, so git saw nothing: every claim is
    # marked, and there is nothing for the agent to have missed.
    assert [p["in_git"] for p in files["paths"]] == [False, False]
    assert got["work"]["files"] == [] and got["missing"] == []

    landed = next(i for i in got["evidence"] if i["kind"] == "change")
    assert landed["changes"][0]["group"] == "does"       # derived from the type
    assert landed["changes"][0]["path"] == ["backend/evidence_items.py"]

    # The same post again is the same rows.
    again = client.post(f"/api/tasks/{tid}/evidence", json={"agent_id": "cc-x", "items": [
        {"kind": "change", "title": "What landed", "changes": [
            {"op": "add", "type": "feature", "name": "evidence says what a task did",
             "path": "backend/evidence_items.py", "note": "two structured kinds"},
        ]},
    ]})
    assert again.json()["saved"][0]["existing"] is True
    assert len(client.get(f"/api/tasks/{tid}/evidence").json()["evidence"]) == 2


def test_the_structured_kinds_have_closed_vocabularies(client: TestClient) -> None:
    tid = _mk_task(client, "Guard rails")

    def post(item: dict):
        return client.post(f"/api/tasks/{tid}/evidence",
                           json={"agent_id": "cc-x", "items": [item]})

    assert post({"kind": "files", "title": "x", "paths": []}).status_code == 422
    bad = post({"kind": "files", "title": "x", "paths": [{"path": "a.py", "action": "yeeted"}]})
    assert bad.status_code == 422 and "created" in bad.text
    loud = post({"kind": "files", "title": "x", "paths": [{"path": "a.py", "importance": 9}]})
    assert loud.status_code == 422 and "between 1 and 5" in loud.text
    cover = post({"kind": "files", "title": "x", "paths": [{"path": "a.py", "test_coverage": "meh"}]})
    assert cover.status_code == 422 and "untested" in cover.text
    kind = post({"kind": "change", "title": "x", "changes": [{"op": "add", "type": "vibe", "name": "n"}]})
    assert kind.status_code == 422 and "feature" in kind.text
    op = post({"kind": "change", "title": "x", "changes": [{"op": "yeet", "type": "feature", "name": "n"}]})
    assert op.status_code == 422 and "remove" in op.text
    nameless = post({"kind": "change", "title": "x", "changes": [{"op": "add", "type": "feature"}]})
    assert nameless.status_code == 422 and "name" in nameless.text
    # An agent's spelling is taken where it is unambiguous.
    ok = post({"kind": "files", "title": "x", "paths": [{"path": "a.py", "action": "added"}]})
    assert ok.status_code == 201
    got = client.get(f"/api/tasks/{tid}/evidence").json()["evidence"][0]
    assert got["paths"][0]["action"] == "created"


def test_task_work_is_empty_without_captured_turns(client: TestClient) -> None:
    tid = _mk_task(client, "No chat named me")
    work = client.get(f"/api/tasks/{tid}/work").json()["work"]
    assert work == {"files": [], "commits": 0, "add": 0, "del": 0, "sessions": 0}


def test_the_repositorys_account_sits_beside_the_agents(client: TestClient, data_root) -> None:
    """git sees the turns that named the task; claims and misses are shown."""
    import subprocess
    from datetime import datetime, timedelta

    from backend import gitwork

    gitwork.forget()
    repo = git_repo(data_root.parent / "proj")

    tid = _mk_task(client, "Wire the thing")
    now = datetime.now()
    when = now - timedelta(minutes=20)
    big = "".join(f"line {i}\n" for i in range(30))
    for name, body in (("touched.py", "1\n2\n3\n"), ("also.py", big), ("tiny.py", "x\n")):
        (repo / name).write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "the work", "--date", when.astimezone().isoformat()],
        cwd=repo, check=True,
        env=git_env(GIT_COMMITTER_DATE=when.astimezone().isoformat(), HOME=str(data_root.parent)),
    )

    chat = data_root / "projects" / "ALPHA" / "chats" / "cc-worker"
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(
        json.dumps({"agent_id": "cc-worker", "cwd": str(repo)}), encoding="utf-8")
    (chat / "chat.md").write_text(
        f"# Chat log — cc-worker\n\n---\n\n## Turn 1 · {when.strftime('%Y-%m-%dT%H:%M:%S')}\n"
        f"**User**: take {tid} · Wire the thing\n**Agent**: done\n",
        encoding="utf-8")
    client.app.state.store.rebuild()

    work = client.get(f"/api/tasks/{tid}/work").json()["work"]
    assert {f["path"] for f in work["files"]} == {"touched.py", "also.py", "tiny.py"}
    assert work["commits"] == 1 and work["sessions"] == 1

    # The agent claims one real file and one the repository never saw.
    client.post(f"/api/tasks/{tid}/evidence", json={"agent_id": "cc-worker", "items": [
        {"kind": "files", "title": "What changed", "paths": [
            {"path": "touched.py", "why": "the change itself"},
            {"path": "imagined.py", "why": "not in this repo"},
        ]},
    ]})
    got = client.get(f"/api/tasks/{tid}/evidence").json()
    marks = {p["path"]: p["in_git"] for p in got["evidence"][0]["paths"]}
    assert marks == {"touched.py": True, "imagined.py": False}
    # Only the large one is news; the one-line file left out is not.
    assert [f["path"] for f in got["missing"]] == ["also.py"]


def test_an_uncommitted_file_is_reported_but_never_held_against_the_agent(client: TestClient) -> None:
    """The working tree is shared by whatever else runs on the laptop."""
    from backend import taskwork

    per: dict = {}
    taskwork._add(per, "committed.py", 10, 2, committed=True)
    taskwork._add(per, "dirty.py", 3, 0, committed=False)
    taskwork._add(per, "both.py", 1, 1, committed=False)
    taskwork._add(per, "both.py", 4, 0, committed=True)
    # The same dirty file seen at a second turn is the same edit, not a second one.
    taskwork._add(per, "dirty.py", 3, 0, committed=False)
    assert per["committed.py"]["committed"] is True
    assert per["dirty.py"]["committed"] is False and per["dirty.py"]["_dirty"] == (3, 0)
    assert per["both.py"]["lines_add"] == 4 and per["both.py"]["_dirty"] == (1, 1)
    assert per["both.py"]["committed"] is True


def test_a_task_owns_the_turns_after_it_was_handed_over(client: TestClient) -> None:
    """Named once, worked for ten turns — until the next task is named."""
    from backend.taskwork import LAST_TURN, _spans

    rows = [
        {"session_id": "ses_1", "turn": 2, "task_id": "tk_mine"},
        {"session_id": "ses_1", "turn": 7, "task_id": "tk_other"},
        {"session_id": "ses_1", "turn": 9, "task_id": "tk_mine"},
        {"session_id": "ses_2", "turn": 1, "task_id": "tk_other"},
    ]
    # Turns 2-6 are mine, 7-8 belong to the other task, 9 to the end is mine.
    assert _spans(rows, "tk_mine") == {"ses_1": [(2, 6), (9, LAST_TURN)]}
    # A session where the task is never named owns nothing in it.
    assert _spans(rows, "tk_nobody") == {}
    # A turn naming both keeps the span open.
    both = [{"session_id": "s", "turn": 1, "task_id": "tk_mine"},
            {"session_id": "s", "turn": 1, "task_id": "tk_other"}]
    assert _spans(both, "tk_mine") == {"s": [(1, LAST_TURN)]}


def test_both_ways_in_carry_the_same_instructions(client: TestClient) -> None:
    """The checkbox with a done-report, and #evidence by hand: one framework."""
    client.post("/api/evidence-prompts", json={
        "name": "Backend work", "text": "Show the request and the response.", "make_default": True,
    })
    tid = _mk_task(client, "Two doors")

    # By hand: the checkbox is off, and the instructions still arrive.
    asked = client.get(f"/api/tasks/{tid}/evidence/ask").json()
    assert asked["evidence_prompt"] == "Show the request and the response."
    assert "files" in asked["evidence_extra"] and "change" in asked["evidence_extra"]
    assert asked["work"]["files"] == []

    # Through the checkbox: the same prompt, the same addition.
    client.post(f"/api/tasks/{tid}/update", json={"evidence_required": "yes"})
    reported = client.post(f"/api/tasks/{tid}/report", json={"agent_id": "cc-test"}).json()
    assert reported["evidence_prompt"] == asked["evidence_prompt"]
    assert reported["evidence_extra"] == asked["evidence_extra"]
    assert "task_evidence" in reported["next"]

    # The operator's prompt is never edited by the server; the addition is apart.
    assert "files" not in reported["evidence_prompt"]

    # The addition is a setting.
    client.post("/api/settings", json={"values": {"evidence.work_items": False}})
    assert client.get(f"/api/tasks/{tid}/evidence/ask").json()["evidence_extra"] == ""
    assert client.get("/api/tasks/tk_nope/evidence/ask").status_code == 404


def test_an_unedited_default_follows_the_built_in_text(client: TestClient) -> None:
    from backend.routers import evidence

    root = client.app.state.store.data_root
    old = evidence.PREVIOUS_DEFAULT_TEXTS[0]
    (root / evidence.PROMPTS_FILE).write_text(json.dumps({
        "default_id": "default",
        "prompts": [{"id": "default", "name": "Prove it, briefly", "text": old}],
    }), encoding="utf-8")
    got = client.get("/api/evidence-prompts").json()["prompts"][0]["text"]
    assert got == evidence.DEFAULT_PROMPT["text"] and "did not verify" in got

    # One the operator rewrote is theirs.
    client.post("/api/evidence-prompts", json={"id": "default", "name": "Mine", "text": "Show me the page."})
    assert client.get("/api/evidence-prompts").json()["prompts"][0]["text"] == "Show me the page."


def test_built_in_skills_go_into_all_projects_once(client: TestClient, tmp_path, monkeypatch) -> None:
    from backend import skilllib

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows reads this one
    store = client.app.state.store
    skilllib.seed_builtin_skills(store)
    store.rebuild()

    notes = skilllib.autoinstall_builtin(store)
    assert {n["skill"] for n in notes} >= {"task-evidence", "make-an-artifact"}
    copy = home / ".claude" / "skills" / "task-evidence" / "SKILL.md"
    assert copy.is_file() and (home / ".agents" / "skills" / "task-evidence" / "SKILL.md").is_file()
    assert skilllib.autoinstall_builtin(store) == []          # nothing twice

    # Taken out by the operator: it stays out.
    row = store.query_one("SELECT * FROM skills_mutual WHERE name = 'task-evidence'")
    skilllib.uninstall(store, row, skilllib.ALL_PROJECTS)
    assert not copy.exists()
    skilllib.autoinstall_builtin(store)
    assert not copy.exists()


def test_a_bad_image_is_refused_with_its_slot_named(client: TestClient) -> None:
    """The refusals story_images.checked_image gives, word for word."""
    tid = _mk_task(client, "bad images")
    for item, detail in (
        ({"ext": "bmp", "data_base64": PNG}, "item 0: ext must be one of gif, jpeg, jpg, png, webp"),
        ({"ext": "png", "data_base64": "not base64!"}, "item 0: data_base64 is not valid base64"),
        ({"ext": "png", "data_base64": ""}, "item 0: image is empty"),
    ):
        r = client.post(f"/api/tasks/{tid}/evidence", json={
            "agent_id": "cc-test", "items": [{"kind": "image", "title": "x", **item}]})
        assert (r.status_code, r.json()["detail"]) == (422, detail)
