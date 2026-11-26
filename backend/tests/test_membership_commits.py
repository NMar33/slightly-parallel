"""A task's commits are read from every repository it lives in (tk_d1d25a4d
step 3, note nt_258a7ed7 §3 «Commits across repositories»).

ALPHA and BETA each have a repository. A task of BETA sees a commit made for
it in ALPHA's repository when ALPHA is in its ``projects``, when a chat
working in ALPHA's repository named it, and after it moved from ALPHA to
BETA; task_commits accepts such a commit and names the repository.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import gitwork, taskwork
from backend.server import create_app
from tests.conftest import git_env, git_repo, make_chat

TASK = "tk_beta_x"   # BETA's task in the conftest data root


def _commit(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(name + "\n", encoding="utf-8")
    env = git_env()
    subprocess.run(["git", "add", name], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, check=True, env=env)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def world(data_root: Path, tmp_path: Path):
    repo_a, repo_b = git_repo(tmp_path / "repo-a"), git_repo(tmp_path / "repo-b")
    _commit(repo_b, "b.txt", "beta's own work")
    signed = _commit(repo_a, "a.txt", f"work for the beta task\n\nTask: {TASK}")
    loose = _commit(repo_a, "a2.txt", "more work, unsigned")
    (data_root / "integrations.csv").write_text(f"project,path\nALPHA,{repo_a}\nBETA,{repo_b}\n", encoding="utf-8")
    gitwork.forget()
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        yield c, data_root, repo_a, signed, loose


def _set_task(root: Path, project: str, projects: str) -> None:
    import csv
    path = root / "tasks.csv"
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["id"] == TASK:
            r["project"], r["projects"] = project, projects
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _signed(c: TestClient) -> set[str]:
    work = c.get(f"/api/tasks/{TASK}/work").json()["work"]
    return {x["sha"] for x in work["commit_list"] if x["how"] == "signed"}


def test_only_the_projects_repository_before(world) -> None:
    c, _root, _repo_a, signed, _loose = world
    assert signed[:7] not in _signed(c)


def test_a_commit_in_a_for_a_task_shown_on_a_is_seen_and_accepted(world) -> None:
    c, root, repo_a, signed, loose = world
    _set_task(root, "BETA", "BETA,ALPHA")
    c.app.state.store.rebuild()
    assert signed[:7] in _signed(c)
    r = c.post(f"/api/tasks/{TASK}/commits", json={"shas": [loose[:7]]})
    assert r.status_code == 200, r.text
    assert r.json()["linked"] == [loose[:7]]
    assert Path(r.json()["repositories"][loose[:7]]).resolve() == repo_a.resolve()


def test_a_chat_in_as_repository_that_named_the_task_brings_it(world) -> None:
    c, root, repo_a, signed, _loose = world
    make_chat(root, "ALPHA", "cc-aaaa1111", [("2026-11-20T10:00:00", f"look at {TASK}", "ok")])
    meta = root / "projects" / "ALPHA" / "chats" / "cc-aaaa1111" / "meta.json"
    m = json.loads(meta.read_text(encoding="utf-8"))
    m["cwd"] = str(repo_a)
    meta.write_text(json.dumps(m), encoding="utf-8")
    c.app.state.store.rebuild()
    assert any(Path(r).resolve() == repo_a.resolve() for r in taskwork.task_repos(c.app.state.store, TASK))
    assert signed[:7] in _signed(c)


def test_after_a_move_from_a_the_commits_of_a_still_show(world) -> None:
    c, root, _repo_a, signed, _loose = world
    with open(root / "task_events.csv", "a", encoding="utf-8") as fh:
        fh.write(f"ev_move,{TASK},2026-11-20T12:00:00,operator,project,ALPHA,BETA\n")
    c.app.state.store.rebuild()
    assert signed[:7] in _signed(c)


def test_a_hash_in_no_repository_of_the_task_is_refused(world) -> None:
    c, root, _repo_a, _signed_sha, loose = world
    before = (root / "tasks.csv").read_bytes()
    r = c.post(f"/api/tasks/{TASK}/commits", json={"shas": [loose[:7]]})
    assert r.status_code == 422 and "is not a commit of the task's repositories" in r.json()["detail"]
    assert (root / "tasks.csv").read_bytes() == before
    assert not (root / taskwork.LINKS_FILE).exists() or loose[:7] not in (root / taskwork.LINKS_FILE).read_text()



def test_every_refused_hash_is_named_once(world) -> None:
    # tk_90c1ba5f: each well-formed hash the repositories refuse, together;
    # the same hash sent twice is one line (the critic of 7ace3e1d).
    c, root, _repo_a, _signed, _loose = world
    before = (root / "tasks.csv").read_bytes()
    r = c.post(f"/api/tasks/{TASK}/commits", json={"shas": ["abcdef1", "abcdef1", "1234567"]})
    assert r.status_code == 422
    days = gitwork.HORIZON_DAYS
    assert r.json()["detail"] == (f"abcdef1 is not a commit of the task's repositories (the last {days} days)\n"
                                  f"1234567 is not a commit of the task's repositories (the last {days} days)")
    assert (root / "tasks.csv").read_bytes() == before


def test_a_malformed_hash_is_refused_before_git_is_asked(world, monkeypatch) -> None:
    c, _root, _repo_a, _signed, _loose = world

    def no_git(*_a, **_k):
        raise AssertionError("git was asked about a malformed hash")

    monkeypatch.setattr(taskwork, "task_repo_log", no_git)
    r = c.post(f"/api/tasks/{TASK}/commits", json={"shas": ["zz", "abcdef1"]})
    assert (r.status_code, r.json()["detail"]) == (422, "not a commit hash: zz")
