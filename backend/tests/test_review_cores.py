"""Review findings on cores (corelib.detail / timeline): each test fails on
the code as found and names the bug it pins."""

from __future__ import annotations

import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import git_env, git_repo, make_task


def _signed_commit(repo: Path, data_root: Path, path: str, tid: str, subject: str) -> None:
    when = (datetime.now() - timedelta(minutes=5)).astimezone().isoformat()
    (repo / path).write_text(subject + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=git_env())
    subprocess.run(["git", "commit", "-q", "-m", f"{subject}\n\nTask: {tid}\nAgent: cc-signer", "--date", when],
                   cwd=repo, check=True, env=git_env(GIT_COMMITTER_DATE=when))


def test_detail_nearby_leaves_out_the_commits_of_its_own_tasks(client: TestClient, data_root: Path) -> None:
    """``nearby`` is shown as "commits in its files, not linked to a task"
    (PagesBody); the timeline drops a linked task's commit from it, detail
    does not, so a task's own commit is listed twice and mislabelled. Live:
    Marketing films lists 15 of its 60 nearby commits among its task commits."""
    from backend import gitwork

    gitwork.forget()
    repo = git_repo(data_root.parent / "proj")
    (data_root / "integrations.csv").write_text(f"project,path\nALPHA,{repo}\n", encoding="utf-8")
    cid = client.post("/api/cores", json={"project": "ALPHA", "name": "Lock", "type": "capability",
                                          "anchors": ["t.py"]}).json()["core"]["id"]
    tid = make_task(client, "lock turns", project="ALPHA")
    client.post(f"/api/cores/{cid}/links", json={"kind": "task", "target": tid})
    _signed_commit(repo, data_root, "t.py", tid, "lock it")
    client.app.state.store.rebuild()
    d = client.get(f"/api/cores/{cid}").json()
    assert [c["subject"] for c in d["commits"]] == ["lock it"]
    assert [c["subject"] for c in d["nearby"]] == []     # found: ["lock it"]


def test_timeline_made_carries_the_tasks_creation_time(client: TestClient) -> None:
    """``_tasks_of`` selects no ``created_time``, so every "made" item is at
    00:00 (StoryBody prints the time and sorts the day by it). Live: every
    made item in /api/cores/timeline ends in T00:00:00."""
    cid = client.post("/api/cores", json={"project": "ALPHA", "name": "Lock", "type": "capability"}).json()["core"]["id"]
    today = date.today()
    tid = make_task(client, "lock turns", project="ALPHA", created_date=today.strftime("%y%m-%d"), created_time="14:35")
    client.post(f"/api/cores/{cid}/links", json={"kind": "task", "target": tid})
    lane = next(l for l in client.get("/api/cores/timeline?project=ALPHA&days=14").json()["lanes"] if l["id"] == cid)
    made = lane["days"][today.isoformat()]["made"]
    assert made[0]["at"] == f"{today.isoformat()}T14:35:00"   # found: T00:00:00
