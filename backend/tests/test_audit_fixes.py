"""Defects a Codex audit found (2610-19), each checked by reading the code
and fixed: an agent could replace the operator's later rounds of a task
through `turn`; two identical edits in one second wrote one event id; the
minute poll of elapsed time was answered 304 with the old total."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.routers.deps import AGENT_REFUSED
from backend.server import create_app
from tests.conftest import make_task


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c


def test_an_agent_cannot_replace_a_later_round(client: TestClient) -> None:
    tid = make_task(client, "t")
    assert client.post(f"/api/tasks/{tid}/update", json={"description": "first"}).status_code == 200
    assert client.post(f"/api/tasks/{tid}/turn", json={"text": "the operator's second round"}).status_code == 201
    r = client.post(f"/api/tasks/{tid}/update",
                    json={"agent_id": "cc-x1234567", "turn": {"n": 2, "text": "replaced"}})
    assert r.status_code == AGENT_REFUSED, r.text
    assert "operator" in r.json()["detail"]
    turns = client.get(f"/api/tasks/{tid}").json()["turns"]
    assert [t["text"] for t in turns if t["n"] == 2] == ["the operator's second round"]
    # The operator still edits it.
    r = client.post(f"/api/tasks/{tid}/update", json={"turn": {"n": 2, "text": "edited"}})
    assert r.status_code == 200, r.text


def test_two_identical_edits_in_one_second_are_two_events(client: TestClient) -> None:
    tid = make_task(client, "t")
    for _ in range(2):
        assert client.post(f"/api/tasks/{tid}/update", json={"description": "same"}).status_code == 200
    events = [e for e in client.get(f"/api/tasks/{tid}/events").json()["events"] if e["field"] == "description"]
    assert len(events) == 2 and len({e["event_id"] for e in events}) == 2


def test_the_minute_poll_of_elapsed_time_is_not_answered_304(client: TestClient, monkeypatch) -> None:
    """Today's total and a task's minutes grow while a timer runs, with no
    write: the ETag of those answers moves with the minute."""
    import time as _time
    now = [1_800_000_000.0]
    monkeypatch.setattr(_time, "time", lambda: now[0])
    for path in ("/api/time/summary", "/api/time/running"):
        tag = client.get(path).headers["etag"]
        assert client.get(path, headers={"If-None-Match": tag}).status_code == 304
        now[0] += 60
        assert client.get(path, headers={"If-None-Match": tag}).status_code == 200


def test_inputs_that_crashed_are_refused_in_words(client: TestClient) -> None:
    tid = make_task(client, "t")
    r = client.post(f"/api/tasks/{tid}/update", json={"resurface_every_days": "9" * 25})
    assert r.status_code == 422, r.text
    assert client.post(f"/api/tasks/{tid}/update", json={"resurface_every_days": "30"}).status_code == 200
    for share in ("inf", 0, "abc"):
        r = client.post("/api/time/start", json={"project": "alpha", "share_pct": share})
        assert r.status_code == 422, (share, r.text)
    # A cookie value outside ASCII is no operator, not a TypeError (a 500).
    from backend.server import has_operator_cookie, operator_cookie_name
    name = operator_cookie_name(client.app)
    assert has_operator_cookie({b"cookie": f'{name}="\xe9"'.encode("latin-1")}, client.app) is False


def test_a_standup_date_that_is_not_text_is_refused_in_words(client: TestClient) -> None:
    r = client.post("/api/standups/postpone", json={"project": "alpha", "date": 123, "hours": 1})
    assert r.status_code == 422, r.text


def _repo(tmp_path: Path) -> Path:
    import subprocess
    repo = tmp_path / "repo"
    (repo / "d").mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    run("config", "user.email", "a@b")
    run("config", "user.name", "a")
    (repo / "заметки.md").write_text("x\n", encoding="utf-8")
    (repo / "d" / "a.txt").write_text("y\n", encoding="utf-8")
    run("add", ".")
    run("commit", "-qm", "one")
    run("mv", "d/a.txt", "d/b.txt")
    (repo / "заметки.md").write_text("x\nz\n", encoding="utf-8")
    run("commit", "-qam", "two")
    return repo


def test_git_file_names_are_the_files_names(tmp_path: Path) -> None:
    """A name outside ASCII came back as "\\320\\267…" and a rename as
    d/{a.txt => b.txt}: neither matched a file, a stamp or a touched path."""
    from backend import gitwork, hookshared
    repo = _repo(tmp_path)
    files = {path for c in gitwork._parse_log(gitwork.git(repo, "log", "--numstat", f"--format={gitwork._FORMAT}") or "")
             for path, _a, _d in c.files}
    assert files == {"заметки.md", "d/a.txt", "d/b.txt"}
    assert hookshared.numstat_path("a.txt => b.txt") == "b.txt"
    assert hookshared.numstat_path("src/{old => new}/x.py") == "src/new/x.py"
    assert hookshared.numstat_path("src/{ => sub}/x.py") == "src/sub/x.py"
    assert hookshared.numstat_path('"\\320\\267.md"') == "з.md"


def test_the_hook_stamps_git_file_names_as_they_are(tmp_path: Path) -> None:
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        "sp_capture_names", Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture.py")
    cap = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_names"] = cap
    spec.loader.exec_module(cap)
    repo = _repo(tmp_path)
    (repo / "заметки.md").write_text("changed\n", encoding="utf-8")
    stamp = cap.work_stamp(str(repo), "")
    assert [f["path"] for f in stamp["dirty"]["paths"]] == ["заметки.md"]


def test_a_task_document_not_in_utf8_does_not_stop_the_server(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "task_details").mkdir()
    (root / "task_details" / "old.md").write_bytes("## L2\nзадача\n".encode("cp1251"))
    with TestClient(create_app(data_root=root, watch=False)) as c:
        assert c.get("/api/health").status_code == 200


def test_a_work_stamp_holding_a_line_separator_is_read_whole(tmp_path: Path) -> None:
    import json as _json
    from backend import gitwork
    chat = tmp_path / "chat.md"
    (tmp_path / "work.jsonl").write_text(
        _json.dumps({"turn": 1, "commits": ["fix more"]}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert gitwork.read_stamps(chat)[1]["commits"] == ["fix more"]


def test_no_repository_is_asked_again_after_a_while(tmp_path: Path, monkeypatch) -> None:
    import json as _json
    import subprocess
    from backend import gitwork
    gitwork.forget()
    work = tmp_path / "work"
    work.mkdir()
    chat = tmp_path / "chat" / "chat.md"
    chat.parent.mkdir()
    (chat.parent / "meta.json").write_text(_json.dumps({"cwd": str(work)}), encoding="utf-8")
    assert gitwork.repo_for_chat(chat) is None
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    assert gitwork.repo_for_chat(chat) is None          # within the while: the answer kept
    monkeypatch.setattr(gitwork, "NO_REPO_RETRY_S", 0.0)
    assert gitwork.repo_for_chat(chat) == work.resolve()
    gitwork.forget()


def test_a_round_holding_a_heading_line_stays_one_round() -> None:
    """An agent's markdown description with its own "## Description" split
    the task into extra rounds on the next read."""
    from backend.turns import Turn, parse_task_doc, render_turns
    text = "Fix it.\n## Description\nmore\n## Turn 2 · 2610-19\nend"
    back = parse_task_doc(render_turns([Turn(1, "", "", text), Turn(2, "2610-19", "10:00", "second")]))
    assert [(t.n, t.text) for t in back] == [(1, text), (2, "second")]


def test_the_opencode_adapter_takes_a_long_message_on_stdin(tmp_path: Path) -> None:
    """As an argument a long paste passed the system's limit (128 KB for one
    argument on Linux, 32 767 characters for a command on Windows): the
    process never started and the message was lost."""
    import subprocess
    import sys
    root = tmp_path / "data"
    root.mkdir()
    cli = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture-cli.py"
    text = "строка лога\n" * 40_000          # ~ 480 KB
    common = ["--project", "alpha", "--data-root", str(root), "--agent", "oc-abcd1234", "--tool", "opencode"]
    for phase, said in (("open", text), ("complete", "done")):
        proc = subprocess.run([sys.executable, str(cli), "--phase", phase, *common, "--text-stdin"],
                              input=said.encode("utf-8"), capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
    chat = (root / "projects" / "alpha" / "chats" / "oc-abcd1234" / "chat.md").read_text(encoding="utf-8")
    assert chat.count("строка лога") == 40_000 and "**Agent**: done" in chat


def test_a_project_filter_on_a_kind_without_projects_is_no_filter(client: TestClient) -> None:
    assert client.get("/api/prompt-runs", params={"project": "alpha"}).status_code == 200


def test_the_timelapse_reads_git_again_only_for_a_new_head(tmp_path: Path, monkeypatch) -> None:
    import subprocess
    from backend.routers import timelapse
    repo = _repo(tmp_path)
    timelapse._git_cache.clear()
    reads = []
    real = timelapse._git_log
    monkeypatch.setattr(timelapse, "_git_log", lambda *a: reads.append(a) or real(*a))
    from datetime import datetime, timedelta
    span = ("2000-01-01T00:00:00", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"))
    first = timelapse._git_part(str(repo), *span)
    assert timelapse._git_part(str(repo), *span) == first and len(reads) == 1
    (repo / "new.txt").write_text("n\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "three"], cwd=repo, check=True)
    third = timelapse._git_part(str(repo), *span)
    assert len(reads) == 2 and third is not None and len(third[0]["commits"]) == len(first[0]["commits"]) + 1


def test_a_chat_that_names_no_folder_has_no_repository(tmp_path: Path, monkeypatch) -> None:
    """``Path("")`` is ``.``: a meta.json with no ``cwd`` read the server's own
    checkout as the chat's repository, and its commits as the chat's work."""
    import json as _json
    import subprocess
    from backend import gitwork
    from backend.file_safety import given_path
    from backend.skilllib import _dests
    gitwork.forget()
    here = tmp_path / "server"
    here.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=here, check=True)
    monkeypatch.chdir(here)                  # the server runs inside a repository
    for meta in ({}, {"cwd": ""}, {"cwd": "  "}):
        chat = tmp_path / f"chat{len(meta)}{meta.get('cwd', '-')!r}" / "chat.md"
        chat.parent.mkdir()
        (chat.parent / "meta.json").write_text(_json.dumps(meta), encoding="utf-8")
        assert gitwork.repo_for_chat(chat) is None
    assert given_path("") is None and given_path(None) is None
    assert _dests("", "plan") == [] and _dests(None, "plan") == []
    gitwork.forget()
