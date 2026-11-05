"""A commit says which task it is for (a ``Task:`` line, or a link made later
with task_commits), and a task's stretch of a chat no longer takes another
agent's commits or opens on a turn that only filed a task."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend import gitwork, taskwork
from tests.conftest import git_env, git_repo


def _task(client: TestClient, title: str) -> str:
    r = client.post("/api/tasks", json={"created_date": "2610-25", "created_time": "10:00", "project": "ALPHA",
                                        "agent_id": "operator", "title": title, "status": "todo"})
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _commit(repo: Path, name: str, message: str, when: datetime, home: Path) -> str:
    (repo / name).write_text(f"{name}\n{message}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    stamp = when.astimezone().isoformat()
    subprocess.run(["git", "commit", "-q", "-m", message, "--date", stamp], cwd=repo, check=True,
                   env=git_env(GIT_COMMITTER_DATE=stamp, HOME=str(home)))
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _project(client: TestClient, data_root: Path) -> Path:
    gitwork.forget()
    repo = git_repo(data_root.parent / "proj")
    (data_root / "integrations.csv").write_text(f"project,path\nALPHA,{repo}\n", encoding="utf-8")
    return repo


def _chat(data_root: Path, agent: str, repo: Path, turns: list[tuple[datetime, str]], stamps: list[dict] | None = None) -> None:
    chat = data_root / "projects" / "ALPHA" / "chats" / agent
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": agent, "cwd": str(repo)}), encoding="utf-8")
    body = f"# Chat log — {agent}\n\n---\n\n"
    for i, (at, text) in enumerate(turns, 1):
        body += f"## Turn {i} · {at.strftime('%Y-%m-%dT%H:%M:%S')}\n**User**: {text}\n**Agent**: done\n\n"
    (chat / "chat.md").write_text(body, encoding="utf-8")
    if stamps:
        (chat / "work.jsonl").write_text("".join(json.dumps(s) + "\n" for s in stamps), encoding="utf-8")


def test_the_log_reads_the_task_and_agent_lines(data_root: Path) -> None:
    gitwork.forget()
    repo = git_repo(data_root.parent / "proj")
    now = datetime.now() - timedelta(minutes=5)
    _commit(repo, "a.py", "Fix the hook\n\nTask: tk_aaaa1111\nTask: tk_bbbb2222\nAgent: cc-one", now, data_root.parent)
    _commit(repo, "b.py", "Plain change\x1fwith a separator", now, data_root.parent)
    log = gitwork.commits(repo)
    signed, plain = log[1], log[0]
    assert signed.tasks == ["tk_aaaa1111", "tk_bbbb2222"] and signed.agent == "cc-one"
    assert plain.tasks == [] and plain.agent == "" and plain.subject == "Plain change\x1fwith a separator"
    assert signed.as_dict()["tasks"] == ["tk_aaaa1111", "tk_bbbb2222"]


def test_a_signed_commit_is_its_tasks_wherever_it_was_made(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    tid = _task(client, "Wire the thing")
    other = _task(client, "Something else")
    t0 = datetime.now() - timedelta(minutes=40)
    # No chat ever named the task: the line alone makes the commit its.
    _commit(repo, "x.py", f"Wire it\n\nTask: {tid}\nAgent: cc-one", t0, data_root.parent)
    client.app.state.store.rebuild()
    work = client.get(f"/api/tasks/{tid}/work").json()["work"]
    assert [c["how"] for c in work["commit_list"]] == ["signed"] and work["signed"] == 1
    assert {f["path"] for f in work["files"]} == {"x.py"}
    assert client.get(f"/api/tasks/{other}/work").json()["work"]["commits"] == 0


def test_a_stretch_skips_commits_signed_for_another_task(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    mine, theirs = _task(client, "Mine"), _task(client, "Theirs")
    t0 = datetime.now() - timedelta(minutes=30)
    _commit(repo, "plain.py", "my unsigned work", t0 + timedelta(minutes=1), data_root.parent)
    _commit(repo, "other.py", f"their work\n\nTask: {theirs}", t0 + timedelta(minutes=2), data_root.parent)
    _chat(data_root, "cc-worker", repo, [(t0, f"take {mine}"), (t0 + timedelta(minutes=5), "go on")])
    client.app.state.store.rebuild()
    work = client.get(f"/api/tasks/{mine}/work").json()["work"]
    assert [(c["subject"], c["how"]) for c in work["commit_list"]] == [("my unsigned work", "chat")]
    assert [c["how"] for c in client.get(f"/api/tasks/{theirs}/work").json()["work"]["commit_list"]] == ["signed"]


def test_a_turn_that_only_files_a_task_opens_no_stretch(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    filed = _task(client, "Later")
    t0 = datetime.now() - timedelta(minutes=30)
    _commit(repo, "w.py", "unrelated work", t0 + timedelta(minutes=3), data_root.parent)
    # The operator files the task with #now-todo; the agent names it in its answer; the chat goes on.
    _chat(data_root, "cc-worker", repo, [(t0, f"#now-todo later: {filed}"), (t0 + timedelta(minutes=5), "now something else")])
    client.app.state.store.rebuild()
    assert client.get(f"/api/tasks/{filed}/work").json()["work"]["commits"] == 0
    # #undo lists candidates by id: that names a task, it does not work on it.
    _chat(data_root, "cc-undo", repo, [(t0, f"#undo the card I made by mistake {filed}"), (t0 + timedelta(minutes=5), "thanks")])
    client.app.state.store.rebuild()
    assert client.get(f"/api/tasks/{filed}/work").json()["work"]["commits"] == 0


def test_a_commit_linked_later_counts_and_leaves_other_stretches(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    mine, other = _task(client, "Mine"), _task(client, "Other")
    t0 = datetime.now() - timedelta(minutes=30)
    sha = _commit(repo, "l.py", "forgot the line", t0 + timedelta(minutes=2), data_root.parent)
    _chat(data_root, "cc-worker", repo, [(t0, f"take {other}"), (t0 + timedelta(minutes=5), "go on")])
    client.app.state.store.rebuild()
    assert [c["how"] for c in client.get(f"/api/tasks/{other}/work").json()["work"]["commit_list"]] == ["chat"]
    r = client.post(f"/api/tasks/{mine}/commits", json={"shas": [sha], "agent_id": "cc-worker"},
                    headers={"X-SP-Via": "mcp"})
    assert r.status_code in (200, 403), r.text
    if r.status_code == 403:   # the gate wants a captured agent: link as the operator instead
        r = client.post(f"/api/tasks/{mine}/commits", json={"shas": [sha]})
    assert r.status_code == 200 and r.json()["linked"] == [sha[:7]]
    assert [c["how"] for c in r.json()["work"]["commit_list"]] == ["linked"]
    assert client.get(f"/api/tasks/{other}/work").json()["work"]["commits"] == 0
    # Twice is once; nonsense is refused.
    assert client.post(f"/api/tasks/{mine}/commits", json={"shas": [sha]}).json()["linked"] == []
    assert client.post(f"/api/tasks/{mine}/commits", json={"shas": ["zz"]}).status_code == 422
    assert client.post("/api/tasks/tk_nope/commits", json={"shas": [sha]}).status_code == 404


def test_the_clock_never_gives_a_chat_another_agents_signed_commit(data_root: Path) -> None:
    gitwork.forget()
    repo = git_repo(data_root.parent / "proj")
    t0 = datetime.now() - timedelta(minutes=30)
    _commit(repo, "o.py", "theirs\n\nAgent: cc-other", t0 + timedelta(minutes=2), data_root.parent)
    _commit(repo, "m.py", "mine", t0 + timedelta(minutes=3), data_root.parent)
    _chat(data_root, "cc-me", repo, [(t0, "work"), (t0 + timedelta(minutes=10), "more")])
    chat = data_root / "projects" / "ALPHA" / "chats" / "cc-me" / "chat.md"
    turns = [{"n": 1, "at": t0.strftime("%H:%M")}, {"n": 2, "at": (t0 + timedelta(minutes=10)).strftime("%H:%M")}]
    work, _ = gitwork.session_work(chat, f"{t0:%y%m-%d}", (t0 + timedelta(minutes=12)).strftime("%H:%M"), turns)
    subjects = [c["subject"] for w in work if w for c in w["commits"]]
    assert subjects == ["mine"]


def test_the_count_of_commits_that_name_their_task(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    tid = _task(client, "T")
    now = datetime.now() - timedelta(minutes=5)
    _commit(repo, "1.py", f"one\n\nTask: {tid}\nAgent: cc-a", now, data_root.parent)
    sha = _commit(repo, "2.py", "two\n\nAgent: cc-a", now, data_root.parent)
    _commit(repo, "3.py", "three", now, data_root.parent)
    client.post(f"/api/tasks/{tid}/commits", json={"shas": [sha]})
    got = client.get("/api/commits/signed?days=7").json()["projects"]
    row = next(p for p in got if p["project"] == "ALPHA")
    assert (row["total"], row["signed"], row["linked"]) == (3, 1, 1)
    assert {a["agent_id"]: (a["commits"], a["signed"]) for a in row["agents"]} == {"cc-a": (2, 2), "": (1, 0)}
    assert taskwork.LINKS_FILE == "commit_links.csv"


def test_the_hook_names_unsigned_commits_once(data_root: Path) -> None:
    import importlib.util
    import sys

    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
    spec = importlib.util.spec_from_file_location("sp_capture_commits", hooks / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_commits"] = mod
    spec.loader.exec_module(mod)
    repo = git_repo(data_root.parent / "proj2")
    a = _commit(repo, "a.py", "Fix it", datetime.now(), data_root.parent)
    b = _commit(repo, "b.py", "Signed\n\nTask: tk_aaaa1111", datetime.now(), data_root.parent)
    c = _commit(repo, "c.py", "Theirs\n\nAgent: cc-other", datetime.now(), data_root.parent)
    cap = mod.TurnCapture(data_root, "ALPHA", "cc-me")
    cap._note_unsigned(str(repo), [a, b, c], sure=True)
    signals = cap.open_turn("next")
    assert [u["sha"] for u in signals["unsigned_commits"]["commits"]] == [a[:7]]
    note = mod.format_signals(signals)
    assert f"[slightly-parallel] commits — {a[:7]} \"Fix it\" has no `Task:` line." in note
    assert "If you made them" not in note and "task_commits" in note
    assert cap.open_turn("again")["unsigned_commits"] is None   # told once
    # A shell call that commits is recognised; other git calls are not.
    rec = lambda cmd: {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}
    shared = mod.shared
    assert shared.ran_commit(rec('git add -A && git commit -q -m "x"')) and shared.ran_commit(rec("git -C repo commit -m y"))
    assert shared.ran_commit(rec('git -C "/a repo/with spaces" commit -m fix'))
    assert not shared.ran_commit(rec("git log --oneline")) and not shared.ran_commit(rec("echo commit"))
    assert not shared.ran_commit(rec("git status; echo commit"))


def _talk(data_root: Path, agent: str, repo: Path, turns: list[tuple[datetime, str, str]]) -> None:
    """A chat whose turns carry the agent's own answer."""
    chat = data_root / "projects" / "ALPHA" / "chats" / agent
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": agent, "cwd": str(repo)}), encoding="utf-8")
    body = f"# Chat log — {agent}\n\n---\n\n"
    for i, (at, user, answer) in enumerate(turns, 1):
        body += f"## Turn {i} · {at.strftime('%Y-%m-%dT%H:%M:%S')}\n**User**: {user}\n**Agent**: {answer}\n\n"
    (chat / "chat.md").write_text(body, encoding="utf-8")


def test_only_the_operator_opens_and_closes_a_stretch(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    mine, listed = _task(client, "Mine"), _task(client, "Listed")
    t0 = datetime.now() - timedelta(minutes=40)
    _commit(repo, "a.py", "first part", t0 + timedelta(minutes=2), data_root.parent)
    _commit(repo, "b.py", "second part", t0 + timedelta(minutes=12), data_root.parent)
    _talk(data_root, "cc-worker", repo, [
        (t0, f"take {mine}", "on it"),
        # The agent names another task in its answer: a list, not a switch.
        (t0 + timedelta(minutes=10), "go on", f"still on it; left in To do: {listed}"),
        (t0 + timedelta(minutes=20), "thanks", "done"),
    ])
    client.app.state.store.rebuild()
    assert sorted(c["subject"] for c in client.get(f"/api/tasks/{mine}/work").json()["work"]["commit_list"]) == ["first part", "second part"]
    assert client.get(f"/api/tasks/{listed}/work").json()["work"]["commits"] == 0
    # The mention still ties the turn to the task.
    rows = client.app.state.store.query("SELECT role FROM task_mentions WHERE task_id = ?", (listed,))
    assert [r["role"] for r in rows] == ["agent"]


def test_a_now_card_written_by_the_agent_opens_its_stretch(client: TestClient, data_root: Path) -> None:
    from backend.csvio import rewrite_rows
    from backend.entities import ENTITIES
    from backend.taskevents import append_events

    repo = _project(client, data_root)
    t0 = datetime.now() - timedelta(minutes=3)
    _talk(data_root, "cc-now", repo, [(t0, "#now fix the hook", "on it")])
    _commit(repo, "n.py", "the work", t0 + timedelta(minutes=1), data_root.parent)
    # The agent writes the card in the #now turn; nothing in the chat names its id.
    tid = _task(client, "Fix the hook")
    ent = ENTITIES["task"]

    def mine(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == tid:
                r["agent_id"] = "cc-now"
        return True
    rewrite_rows(data_root / ent.csv, ent.columns, mine)
    append_events(client.app.state.store, tid, "operator", [("started", "", "in the chat, with #now (written by cc-now)")])
    client.app.state.store.rebuild()
    assert [c["subject"] for c in client.get(f"/api/tasks/{tid}/work").json()["work"]["commit_list"]] == ["the work"]


def test_after_a_pause_the_stretch_goes_on_only_where_the_task_is_named_again(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    kept, dropped = _task(client, "Kept"), _task(client, "Dropped")
    t0 = datetime.now() - timedelta(hours=6)
    later = t0 + timedelta(hours=4)          # past the pause that cuts a session
    _commit(repo, "k.py", "kept after the pause", later + timedelta(minutes=2), data_root.parent)
    _talk(data_root, "cc-k", repo, [(t0, f"take {kept}", "on it"),
                                    (later, "go on", f"back on {kept}"), (later + timedelta(minutes=10), "ok", "done")])
    # A second chat, an hour after the first one's last turn: the clock gives each chat only its own commits.
    t1, later1 = t0 + timedelta(minutes=30), later + timedelta(minutes=70)
    _commit(repo, "d.py", "other work after the pause", later1 + timedelta(minutes=3), data_root.parent)
    _talk(data_root, "cc-d", repo, [(t1, f"take {dropped}", "on it"),
                                    (later1, "something else now", "sure"), (later1 + timedelta(minutes=10), "ok", "done")])
    client.app.state.store.rebuild()
    assert [c["subject"] for c in client.get(f"/api/tasks/{kept}/work").json()["work"]["commit_list"]] == ["kept after the pause"]
    assert client.get(f"/api/tasks/{dropped}/work").json()["work"]["commits"] == 0


def test_a_now_card_the_server_wrote_opens_its_stretch_without_any_mention(client: TestClient, data_root: Path) -> None:
    repo = _project(client, data_root)
    tid = _task(client, "Server card")
    t0 = datetime.now() - timedelta(minutes=40)
    _commit(repo, "s.py", "work after #now", t0 + timedelta(minutes=3), data_root.parent)
    _talk(data_root, "cc-srv", repo, [(t0, "#now fix it", "working"), (t0 + timedelta(minutes=10), "ok", "done")])
    client.app.state.store.rebuild()
    sid = client.app.state.store.query("SELECT id FROM sessions WHERE agent_id = 'cc-srv'")[0]["id"]
    (data_root / "now.csv").write_text(
        "id,task_id,project,agent_id,session_id,turn,at,applied_at,column,result\n"
        f"nw_1,{tid},ALPHA,cc-srv,{sid},1,,,doing,\n", encoding="utf-8")
    client.app.state.store.rebuild()
    assert [c["subject"] for c in client.get(f"/api/tasks/{tid}/work").json()["work"]["commit_list"]] == ["work after #now"]


def test_the_hook_records_each_tools_commit_calls(data_root: Path, tmp_path: Path) -> None:
    """Claude Code (a Bash call and its result), Codex (a tool call and its
    output, from its session file) and OpenCode (epoch ms through the CLI)
    each put the turn's calls that may make a commit into the work stamp."""
    import importlib.util
    import sys

    from backend import hookshared as shared

    # Claude Code: a commit call and an ordinary one.
    calls = shared.CommitCalls()
    calls.take({"type": "assistant", "timestamp": "2026-10-26T07:00:00Z", "message": {"content": [
        {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": 'git add -A && git commit -q -m "x"'}},
        {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "git status"}}]}})
    calls.take({"type": "user", "timestamp": "2026-10-26T07:00:03Z", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "a"}, {"type": "tool_result", "tool_use_id": "b"}]}})
    assert calls.calls == [[shared.local_iso("2026-10-26T07:00:00Z"), shared.local_iso("2026-10-26T07:00:03Z")]]
    assert shared.makes_commit("git -C x cherry-pick abc") and shared.makes_commit("git pull --rebase")
    assert not shared.makes_commit("git log --oneline") and not shared.makes_commit("echo commit")

    # Codex: the session file of a thread, its last turn only.
    day = tmp_path / "codex" / "sessions" / "2026" / "10" / "26"
    day.mkdir(parents=True)
    thread = "01a17709-2aa5-78e0-b261-df1c7d3c234a"
    recs = [
        {"timestamp": "2026-10-26T06:00:00Z", "type": "event_msg", "payload": {"type": "task_started"}},
        {"timestamp": "2026-10-26T06:00:05Z", "type": "response_item", "payload": {"type": "function_call", "call_id": "old", "arguments": '{"cmd":"git commit -m old"}'}},
        {"timestamp": "2026-10-26T07:00:00Z", "type": "event_msg", "payload": {"type": "task_started"}},
        {"timestamp": "2026-10-26T07:00:10Z", "type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "c1", "input": 'tools.exec_command({cmd:"git commit -qm fix"})'}},
        {"timestamp": "2026-10-26T07:00:12Z", "type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "c1"}},
    ]
    (day / f"rollout-2026-10-26T18-00-00-{thread}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    rollout = shared.codex_rollout(thread, str(tmp_path / "codex"))
    assert rollout is not None and shared.codex_rollout("../x", str(tmp_path / "codex")) is None
    started, codex_calls = shared.codex_last_turn(rollout)
    assert started == shared.local_iso("2026-10-26T07:00:00Z")
    # By its id: the notify of an earlier turn reads that turn, not the last one.
    recs[0]["payload"]["turn_id"], recs[2]["payload"]["turn_id"] = "t-old", "t-new"
    (day / f"rollout-2026-10-26T18-00-00-{thread}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    old_start, old_calls = shared.codex_last_turn(rollout, "t-old")
    # The old turn's call had no output: it is closed at that turn's last record.
    assert old_start == shared.local_iso("2026-10-26T06:00:00Z")
    assert old_calls == [[shared.local_iso("2026-10-26T06:00:05Z"), shared.local_iso("2026-10-26T06:00:05Z")]]
    assert shared.codex_last_turn(rollout, "t-none") == ("", [])
    open_calls = shared.CommitCalls()
    open_calls.started("x", "git commit -m y", "2026-10-26T07:00:00")
    assert open_calls.finish("2026-10-26T07:05:00") == [["2026-10-26T07:00:00", "2026-10-26T07:05:00"]]
    assert codex_calls == [[shared.local_iso("2026-10-26T07:00:10Z"), shared.local_iso("2026-10-26T07:00:12Z")]]

    # The stamp carries the turn's start and its calls.
    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
    spec = importlib.util.spec_from_file_location("sp_capture_calls", hooks / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_calls"] = mod
    spec.loader.exec_module(mod)
    repo = git_repo(data_root.parent / "proj3")
    cap = mod.TurnCapture(data_root, "ALPHA", "codex-abc")
    cap.note_origin("codex", thread, str(repo))
    cap.full_turn("do it", "done", turn_started=started, commit_calls=codex_calls)
    stamp = json.loads((data_root / "projects" / "ALPHA" / "chats" / "codex-abc" / "work.jsonl").read_text().splitlines()[-1])
    assert stamp["started"] == started and stamp["commit_calls"] == codex_calls

    # OpenCode: epoch ms on stdin, local time in the stamp.
    cli = hooks / "capture-cli.py"
    ms = int(datetime(2026, 10, 26, 18, 0, 0).timestamp() * 1000)
    common = ["--project", "ALPHA", "--data-root", str(data_root), "--agent", "oc-12345678", "--tool", "opencode",
              "--session", "ses_x", "--cwd", str(repo)]
    subprocess.run([sys.executable, str(cli), "--phase", "open", *common, "--json-stdin"], input=json.dumps({"text": "go"}),
                   text=True, check=True, capture_output=True)
    subprocess.run([sys.executable, str(cli), "--phase", "complete", *common, "--json-stdin"],
                   input=json.dumps({"text": "ok", "commit_calls": [[ms, ms + 2000]]}), text=True, check=True, capture_output=True)
    stamp = json.loads((data_root / "projects" / "ALPHA" / "chats" / "oc-12345678" / "work.jsonl").read_text().splitlines()[-1])
    assert stamp["commit_calls"] == [["2026-10-26T18:00:00", "2026-10-26T18:00:02"]]


def test_a_cherry_pick_is_dated_by_when_it_was_made(data_root: Path) -> None:
    """A cherry-pick keeps the old author date; the commit was made now, and
    its maker is the chat whose call ran now."""
    gitwork.forget()
    repo = git_repo(data_root.parent / "proj")
    long_ago = (datetime.now() - timedelta(days=30)).astimezone().isoformat()
    now = (datetime.now() - timedelta(minutes=2)).replace(microsecond=0)
    (repo / "p.py").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "picked", "--date", long_ago], cwd=repo, check=True,
                   env=git_env(GIT_COMMITTER_DATE=now.astimezone().isoformat(), HOME=str(data_root.parent)))
    c = gitwork.commits(repo)[0]
    assert c.made is not None and abs((c.made - now).total_seconds()) < 2 and (now - c.at).days >= 29
    iso = lambda d: d.isoformat(timespec="seconds")
    claims = [gitwork.Claim("cc-a", iso(now - timedelta(minutes=5)), iso(now + timedelta(minutes=1)), [],
                            [[iso(now - timedelta(seconds=1)), iso(now + timedelta(seconds=1))]]),
              gitwork.Claim("cc-b", iso(now - timedelta(minutes=5)), iso(now + timedelta(minutes=1)), [], [])]
    assert gitwork.maker_of(c, claims) == "cc-a"
