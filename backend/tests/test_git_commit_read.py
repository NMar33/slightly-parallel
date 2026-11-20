"""GET /api/git/commit: one commit of a project's repository, read only.

The terminal window asks it before underlining a hash it printed, and its
commit card reads it. The repository is named by a project code, never a
path, and only a hash of one of its commits answers.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend import gitwork
from tests.conftest import git_repo
from tests.test_commit_tasks import _commit


def _project(data_root: Path) -> Path:
    gitwork.forget()
    repo = git_repo(data_root.parent / "proj")
    (data_root / "integrations.csv").write_text(f"project,path\nALPHA,{repo}\n", encoding="utf-8")
    return repo


def test_a_commit_of_the_project_answers_with_its_files_and_task_lines(client: TestClient, data_root: Path) -> None:
    repo = _project(data_root)
    when = datetime.now() - timedelta(days=400)   # older than the log's horizon: still found
    sha = _commit(repo, "a.py", "Wire the card\n\nTask: tk_aaaa1111\nAgent: cc-one", when, data_root.parent)
    for n in (sha, sha[:7], sha[:12].upper()):
        r = client.get("/api/git/commit", params={"repo": "ALPHA", "sha": n})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["sha"] == sha and d["short"] == sha[:7] and d["subject"] == "Wire the card"
        assert d["tasks"] == ["tk_aaaa1111"] and d["agent"] == "cc-one" and d["project"] == "ALPHA"
        assert [(f["path"], f["add"], f["del"]) for f in d["files"]] == [("a.py", 5, 0)]
        assert "diff" not in d
    d = client.get("/api/git/commit", params={"repo": "ALPHA", "sha": sha[:7], "diff": 1}).json()
    assert "+++ b/a.py" in d["diff"] and d["diff_cut"] is False


def test_an_unknown_hash_is_404(client: TestClient, data_root: Path) -> None:
    repo = _project(data_root)
    sha = _commit(repo, "a.py", "one", datetime.now(), data_root.parent)
    tree = gitwork.git(repo, "rev-parse", "HEAD^{tree}").strip()
    for bad in ("deadbeef", "0" * 40, tree, tree[:10]):
        assert client.get("/api/git/commit", params={"repo": "ALPHA", "sha": bad}).status_code == 404, bad
    # Not a hash at all: too short, an option, a ref name, a path.
    for bad in (sha[:6], "--all", "HEAD", "master", "../etc", "", f"{sha[:7]} x"):
        assert client.get("/api/git/commit", params={"repo": "ALPHA", "sha": bad}).status_code == 404, bad


def test_the_repository_is_a_known_project_never_a_path(client: TestClient, data_root: Path) -> None:
    repo = _project(data_root)
    sha = _commit(repo, "a.py", "one", datetime.now(), data_root.parent)
    for bad in (str(repo), "../proj", "..", "ALPHA/../BETA", "NOPE", ""):
        assert client.get("/api/git/commit", params={"repo": bad, "sha": sha}).status_code == 404, bad
    # A known project with no repository registered.
    assert client.get("/api/git/commit", params={"repo": "BETA", "sha": sha}).status_code == 404


def test_the_read_writes_nothing(client: TestClient, data_root: Path) -> None:
    repo = _project(data_root)
    sha = _commit(repo, "a.py", "one", datetime.now(), data_root.parent)
    before = sorted((p.as_posix(), p.stat().st_mtime_ns) for p in data_root.rglob("*") if p.is_file() and not p.name.endswith(".lock"))
    client.get("/api/git/commit", params={"repo": "ALPHA", "sha": sha, "diff": 1})
    client.get("/api/git/commit", params={"repo": "ALPHA", "sha": "deadbeef"})
    after = sorted((p.as_posix(), p.stat().st_mtime_ns) for p in data_root.rglob("*") if p.is_file() and not p.name.endswith(".lock"))
    assert before == after
