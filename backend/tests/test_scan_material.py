"""What a scan is written from, and where its instructions live."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend import gitwork
from tests.conftest import git_env, git_repo


def _commit(repo, data_root, name: str, body: str, subject: str, when: datetime) -> None:
    (repo / name).write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    # An aware stamp: git and this process agree on the instant whatever
    # zone each reads (TZ=UTC on a machine set elsewhere).
    at = when.astimezone().isoformat()
    subprocess.run(
        ["git", "commit", "-q", "-m", subject, "--date", at], cwd=repo, check=True,
        env=git_env(GIT_COMMITTER_DATE=at, HOME=str(data_root.parent)),
    )


def test_material_is_the_work_since_the_last_scan(client: TestClient, data_root) -> None:
    gitwork.forget()
    repo = git_repo(data_root.parent / "scanproj")
    now = datetime.now()
    _commit(repo, data_root, "old.py", "1\n", "before the scan", now - timedelta(hours=5))

    chat = data_root / "projects" / "ALPHA" / "chats" / "cc-scanner"
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": "cc-scanner", "cwd": str(repo)}), encoding="utf-8")
    (chat / "chat.md").write_text("# Chat log — cc-scanner\n", encoding="utf-8")

    at = now - timedelta(hours=3)
    made = client.post("/api/scans", json={
        "created_date": f"{at:%y%m-%d}", "created_time": f"{at:%H:%M}", "project": "ALPHA",
        "agent_id": "cc-scanner", "summary": "The last checkpoint",
    })
    assert made.status_code == 201, made.text

    _commit(repo, data_root, "new.py", "a\nb\nc\n", "after the scan", now - timedelta(hours=1))
    _commit(repo, data_root, "new.py", "a\nb\nc\nd\n", "after the scan, again", now - timedelta(minutes=30))
    (repo / "new.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")        # not committed
    client.app.state.store.rebuild()
    gitwork.forget()

    got = client.get("/api/scans/material?project=ALPHA&agent_id=cc-scanner").json()
    assert got["last_scan"]["summary"] == "The last checkpoint"
    assert [c["subject"] for c in got["commits"]] == ["after the scan, again", "after the scan"]
    assert got["files"] == [{"path": "new.py", "lines_add": 4, "lines_del": 0, "commits_n": 2}]
    assert got["counters"] == {"files_n": 1, "lines_add": 4, "lines_del": 0, "decisions_n": 0}
    assert got["uncommitted"] == [{"path": "new.py", "lines_add": 1, "lines_del": 0}]
    # How to write all three entries comes with it, from the contract's own parts.
    for words in ("team lead", "Checkpoint", "blast_radius", "eight"):
        assert words in got["instructions"], words
    assert client.get("/api/scans/material?project=NOPE").status_code == 404


def test_a_part_with_a_brief_is_short_in_the_contract_and_whole_for_the_skill() -> None:
    from pathlib import Path

    from backend import contract_parts, scanlib

    root = Path(__file__).resolve().parents[2]
    contract = contract_parts.compose(contract_parts.load_parts(root))
    assert "make-a-scan" in contract and "scan_material" in contract
    assert "blast_radius" not in contract            # the long parts left the contract
    assert "blast_radius" in scanlib.instructions(root)
    # The command table still lists the commands of a briefed part.
    assert "#scan" in contract and "#architecture" in contract


def test_work_a_scan_described_before_it_was_committed_is_not_counted_again(client: TestClient, data_root) -> None:
    gitwork.forget()
    repo = git_repo(data_root.parent / "scanproj2")
    now = datetime.now()
    _commit(repo, data_root, "base.py", "1\n", "base", now - timedelta(hours=6))
    chat = data_root / "projects" / "ALPHA" / "chats" / "cc-scanner2"
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": "cc-scanner2", "cwd": str(repo)}), encoding="utf-8")
    (chat / "chat.md").write_text("# Chat log\n", encoding="utf-8")
    client.app.state.store.rebuild()

    # The scan is written while the work is still uncommitted: one edited file, one new file.
    (repo / "base.py").write_text("1\n2\n", encoding="utf-8")
    (repo / "fresh.py").write_text("x\n" * 50, encoding="utf-8")
    at = now - timedelta(hours=2)
    made = client.post("/api/scans", json={
        "created_date": f"{at:%y%m-%d}", "created_time": f"{at:%H:%M}", "project": "ALPHA",
        "agent_id": "cc-scanner2", "summary": "Described before it was committed",
    })
    assert made.status_code == 201, made.text

    # Committed minutes later; then real new work, one part of it on the same file.
    _commit(repo, data_root, "fresh.py", "x\n" * 50, "the work the scan described", now - timedelta(minutes=110))
    _commit(repo, data_root, "later.py", "a\nb\n", "new work", now - timedelta(minutes=60))
    _commit(repo, data_root, "fresh.py", "x\n" * 50 + "y\n", "more on the same file", now - timedelta(minutes=30))
    client.app.state.store.rebuild()
    gitwork.forget()

    got = client.get("/api/scans/material?project=ALPHA&agent_id=cc-scanner2").json()
    assert [c["subject"] for c in got["already_described"]] == ["the work the scan described"]
    assert [c["subject"] for c in got["commits"]] == ["more on the same file", "new work"]
    assert got["counters"]["lines_add"] == 3 and got["counters"]["files_n"] == 2


def _stamp(chat, turn: int, when: datetime, head: str, commits: list[str], touched: list[str] | None = None) -> None:
    line = {"turn": turn, "at": when.isoformat(timespec="seconds"), "head": head, "commits": commits, "dirty": []}
    if touched is not None:
        line["touched"] = touched
    with open(chat / "work.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def _sha(repo) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def test_the_window_is_this_chats_work_since_this_agents_last_scan(client: TestClient, data_root) -> None:
    """Two agents commit to one repository. Each one's scan material holds
    the commits its own turns made (by the hook's stamps) since its own
    last scan; the other's commits are counted apart, never in both."""
    gitwork.forget()
    repo = git_repo(data_root.parent / "twoagents")
    now = datetime.now()
    _commit(repo, data_root, "base.py", "1\n", "base", now - timedelta(hours=6))
    base = _sha(repo)

    chats = {}
    for agent in ("cc-aaaa", "cc-bbbb"):
        chat = data_root / "projects" / "ALPHA" / "chats" / agent
        chat.mkdir(parents=True, exist_ok=True)
        (chat / "meta.json").write_text(json.dumps({"agent_id": agent, "cwd": str(repo)}), encoding="utf-8")
        (chat / "chat.md").write_text(f"# Chat log — {agent}\n", encoding="utf-8")
        chats[agent] = chat

    # A scans at -3h; B has never scanned.
    at = now - timedelta(hours=3)
    assert client.post("/api/scans", json={
        "created_date": f"{at:%y%m-%d}", "created_time": f"{at:%H:%M}", "project": "ALPHA",
        "agent_id": "cc-aaaa", "summary": "A's checkpoint",
    }).status_code == 201

    # As the hook writes them: a stamp lists every commit HEAD gained during
    # the turn, the other agent's too; `touched` says which files the turn's
    # tools changed.
    _stamp(chats["cc-bbbb"], 0, now - timedelta(hours=2, minutes=30), base, [], [])
    _commit(repo, data_root, "a.py", "a\na\n", "A's work", now - timedelta(hours=2))
    a_sha = _sha(repo)
    _stamp(chats["cc-aaaa"], 2, now - timedelta(hours=2, minutes=-1), a_sha, [a_sha], ["a.py"])
    _commit(repo, data_root, "b.py", "b\nb\nb\n", "B's work", now - timedelta(hours=1))
    b_sha = _sha(repo)
    _stamp(chats["cc-bbbb"], 1, now - timedelta(hours=1, minutes=-1), b_sha, [a_sha, b_sha], ["b.py"])
    _stamp(chats["cc-aaaa"], 3, now - timedelta(minutes=30), b_sha, [b_sha], [])   # A's next turn: HEAD moved, not by A
    client.app.state.store.rebuild()
    gitwork.forget()

    a = client.get("/api/scans/material?project=ALPHA&agent_id=cc-aaaa").json()
    assert a["last_scan"]["summary"] == "A's checkpoint"
    assert [c["subject"] for c in a["commits"]] == ["A's work"]
    assert a["counters"]["files_n"] == 1 and a["counters"]["lines_add"] == 2
    assert a["others_commits_n"] == 1 and "outside this chat" in a["others_note"]

    b = client.get("/api/scans/material?project=ALPHA&agent_id=cc-bbbb").json()
    assert b["last_scan"] is None                      # A's scan did not close B's window
    assert [c["subject"] for c in b["commits"]] == ["B's work"]
    assert b["counters"]["lines_add"] == 3
    assert base not in {c["sha"] for c in b["commits"]}

    # The two windows add up to the repository's work since A's scan: nothing twice.
    assert a["counters"]["lines_add"] + b["counters"]["lines_add"] == 5


def test_without_git_the_scan_has_the_files_the_chat_touched(client: TestClient, data_root) -> None:
    """No repository: the material lists the files the chat's tools changed
    (from the capture stamps) and counts them, and says git had nothing."""
    gitwork.forget()
    folder = data_root.parent / "plainfolder"
    folder.mkdir()
    chat = data_root / "projects" / "nogit" / "chats" / "cc-nogit"
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": "cc-nogit", "cwd": str(folder)}), encoding="utf-8")
    (chat / "chat.md").write_text("# Chat log — cc-nogit\n", encoding="utf-8")
    now = datetime.now()
    for turn, when, touched in ((1, now - timedelta(hours=2), ["notes/plan.md"]), (2, now - timedelta(hours=1), ["notes/plan.md", "data/rows.csv"])):
        with open(chat / "work.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"turn": turn, "at": when.isoformat(timespec="seconds"), "head": "", "commits": [], "dirty": None, "touched": touched,
                                 "changed": ["notes/plan.md", "out/report.pdf"] if turn == 2 else []}) + "\n")
    client.app.state.store.rebuild()

    got = client.get("/api/scans/material?project=nogit&agent_id=cc-nogit").json()
    assert got["repo"] == "" and got["commits"] == []
    assert got["touched"] == ["notes/plan.md", "data/rows.csv"]
    assert got["changed"] == ["notes/plan.md", "out/report.pdf"]
    assert got["counters"]["files_n"] == 3                       # the two lists, each file once
    assert "No git repository" in got["note"] and "touched" in got["note"]


def test_an_uncommitted_file_says_whether_this_chat_touched_it(client: TestClient, data_root) -> None:
    gitwork.forget()
    repo = git_repo(data_root.parent / "shared")
    now = datetime.now()
    _commit(repo, data_root, "a.py", "1\n", "base", now - timedelta(hours=2))
    (repo / "a.py").write_text("1\n2\n", encoding="utf-8")       # this chat's edit
    (repo / "b.py").write_text("x\n", encoding="utf-8")          # someone else's
    subprocess.run(["git", "add", "b.py"], cwd=repo, check=True)
    chat = data_root / "projects" / "shared" / "chats" / "cc-mine"
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": "cc-mine", "cwd": str(repo)}), encoding="utf-8")
    (chat / "chat.md").write_text("# Chat log — cc-mine\n", encoding="utf-8")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    with open(chat / "work.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"turn": 1, "at": (now - timedelta(minutes=5)).isoformat(timespec="seconds"),
                             "head": head, "commits": [], "dirty": [], "touched": ["a.py"]}) + "\n")
    client.app.state.store.rebuild()
    gitwork.forget()

    got = client.get("/api/scans/material?project=shared&agent_id=cc-mine").json()
    mine = {f["path"]: f["mine"] for f in got["uncommitted"]}
    assert mine == {"a.py": True, "b.py": False}


def test_a_commit_no_tool_touched_goes_to_the_chat_that_stamped_it_first(client: TestClient, data_root) -> None:
    """A commit made by a shell command names no file a tool touched: the
    chat whose stamp lists it first made it; the other chat only saw HEAD move."""
    gitwork.forget()
    repo = git_repo(data_root.parent / "shellcommit")
    now = datetime.now()
    _commit(repo, data_root, "base.py", "1\n", "base", now - timedelta(hours=3))
    chats = {}
    for agent in ("cc-cccc", "cc-dddd"):
        chat = data_root / "projects" / "SHELL" / "chats" / agent
        chat.mkdir(parents=True, exist_ok=True)
        (chat / "meta.json").write_text(json.dumps({"agent_id": agent, "cwd": str(repo)}), encoding="utf-8")
        (chat / "chat.md").write_text(f"# Chat log — {agent}\n", encoding="utf-8")
        chats[agent] = chat
    _commit(repo, data_root, "gen.txt", "x\n", "generated by a script", now - timedelta(hours=1))
    sha = _sha(repo)
    _stamp(chats["cc-cccc"], 1, now - timedelta(minutes=58), sha, [sha], [])
    _stamp(chats["cc-dddd"], 1, now - timedelta(minutes=40), sha, [sha], [])
    client.app.state.store.rebuild()
    gitwork.forget()
    c = client.get("/api/scans/material?project=SHELL&agent_id=cc-cccc").json()
    d = client.get("/api/scans/material?project=SHELL&agent_id=cc-dddd").json()
    assert [x["subject"] for x in c["commits"]] == ["generated by a script"]
    assert d["commits"] == [] and d["others_commits_n"] == 2   # the script's commit and the first one
