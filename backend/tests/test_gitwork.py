"""Commits attributed to the turns they landed in — from git, after the fact."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from backend import gitwork
from tests.conftest import git_env, git_repo


def _repo(tmp: Path) -> Path:
    return git_repo(tmp / "proj")


def _commit(repo: Path, at: str, subject: str, files: dict[str, str]) -> None:
    for name, body in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    env = git_env(GIT_AUTHOR_DATE=at, GIT_COMMITTER_DATE=at)
    subprocess.run(
        ["git", "commit", "-q", "-m", f"{subject}\n\nClaude-Session: https://claude.ai/code/session_x"],
        cwd=repo, check=True, env=env,
    )


def test_commits_land_in_the_turn_whose_window_holds_them(tmp_path):
    gitwork.forget()
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "first thing", {"a.py": "1\n2\n"})
    _commit(repo, "2026-09-01T10:12:00", "second thing", {"a.py": "1\n", "b.py": "x\n"})
    _commit(repo, "2026-09-01T10:40:00", "after the session, still mine", {"c.py": "y\n"})
    _commit(repo, "2026-09-01T12:00:00", "somebody else's afternoon", {"d.py": "z\n"})

    turns = [{"n": 1, "at": "10:00"}, {"n": 2, "at": "10:10"}, {"n": 3, "at": "10:20"}]
    stamps = gitwork.turn_stamps("2609-01", turns)
    per = gitwork.attribute(gitwork.commits(repo), stamps, datetime(2026, 9, 1, 10, 25))

    assert [c.subject for c in per[0]] == ["first thing"]
    assert [c.subject for c in per[1]] == ["second thing"]
    assert [c.subject for c in per[2]] == ["after the session, still mine"], \
        "the last turn keeps a tail — the commit lands after the reply that describes it"
    assert per[1][0].files == [("a.py", 0, 1), ("b.py", 1, 0)]
    assert per[0][0].session == "https://claude.ai/code/session_x"


def test_a_session_across_midnight_keeps_its_turns_in_order():
    stamps = gitwork.turn_stamps("2609-01", [{"at": "23:50"}, {"at": "00:05"}, {"at": "00:30"}])
    assert [s.day for s in stamps] == [1, 2, 2]
    assert stamps[1] > stamps[0]


def test_the_log_is_read_once_per_head(tmp_path, monkeypatch):
    gitwork.forget()
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "one", {"a.py": "1\n"})
    calls = {"n": 0}
    real = gitwork.git

    def counting(r, *args):
        if args and args[0] == "log":
            calls["n"] += 1
        return real(r, *args)

    monkeypatch.setattr(gitwork, "git", counting)
    gitwork.commits(repo)
    gitwork.commits(repo)
    assert calls["n"] == 1
    _commit(repo, "2026-09-01T10:04:00", "two", {"b.py": "1\n"})
    assert len(gitwork.commits(repo)) == 2
    assert calls["n"] == 2


def _shape(cs):
    return [(c.sha, c.at, c.subject, c.files) for c in cs]


def test_a_new_head_reads_only_the_new_commits_and_matches_a_full_read(tmp_path, monkeypatch):
    gitwork.forget()
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "one", {"a.py": "1\n"})
    _commit(repo, "2026-09-01T10:05:00", "two", {"b.py": "1\n2\n"})
    ranges: list[tuple[str, ...]] = []
    real = gitwork.git

    def recording(r, *args):
        if args and args[0] == "log":
            ranges.append(tuple(a for a in args if ".." in a))
        return real(r, *args)

    monkeypatch.setattr(gitwork, "git", recording)
    gitwork.commits(repo)
    _commit(repo, "2026-09-01T10:09:00", "three", {"a.py": "1\n2\n3\n", "c.py": "x\n"})
    grown = gitwork.commits(repo)
    assert ranges[-1] and ranges[-1][0].endswith(".." + gitwork.head(repo))   # only the new commit's diff
    gitwork.forget()
    assert _shape(grown) == _shape(gitwork.commits(repo))
    assert [c.subject for c in grown] == ["three", "two", "one"]


def test_a_head_that_does_not_descend_reads_the_whole_log_again(tmp_path):
    gitwork.forget()
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "one", {"a.py": "1\n"})
    _commit(repo, "2026-09-01T10:05:00", "two", {"b.py": "1\n"})
    assert len(gitwork.commits(repo)) == 2
    subprocess.run(["git", "reset", "-q", "--hard", "HEAD~1"], cwd=repo, check=True)
    _commit(repo, "2026-09-01T10:07:00", "two again", {"c.py": "1\n"})
    assert [c.subject for c in gitwork.commits(repo)] == ["two again", "one"]
    # A commit dated before the newest one held goes where a full read puts it.
    _commit(repo, "2026-09-01T10:06:00", "back-dated", {"d.py": "1\n"})
    got = gitwork.commits(repo)
    gitwork.forget()
    assert _shape(got) == _shape(gitwork.commits(repo))


def test_session_work_from_the_chats_own_cwd(tmp_path):
    gitwork.forget()
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "first thing", {"a.py": "1\n2\n"})
    chat_dir = tmp_path / "chats" / "cc-1"
    chat_dir.mkdir(parents=True)
    (chat_dir / "meta.json").write_text('{"cwd": "%s"}' % repo, encoding="utf-8")
    chat = chat_dir / "chat.md"
    chat.write_text("# x\n", encoding="utf-8")

    work, total = gitwork.session_work(chat, "2609-01", "10:20", [
        {"n": 1, "at": "10:00", "user": "do it", "agent": "done"},
        {"n": 2, "at": "10:10", "user": "thanks", "agent": "ok"},
    ])
    assert work[0]["files_n"] == 1 and work[0]["add"] == 2
    assert work[0]["commits"][0]["subject"] == "first thing"
    assert work[1] is None, "a turn with no commit says nothing"
    assert total == {"commits": 1, "files": 1, "add": 2, "del": 0}


def test_no_repo_no_work(tmp_path):
    gitwork.forget()
    chat_dir = tmp_path / "chats" / "cc-2"
    chat_dir.mkdir(parents=True)
    (chat_dir / "meta.json").write_text('{"cwd": "%s"}' % (tmp_path / "nowhere"), encoding="utf-8")
    chat = chat_dir / "chat.md"
    chat.write_text("# x\n", encoding="utf-8")
    work, total = gitwork.session_work(chat, "2609-01", "10:20", [{"n": 1, "at": "10:00"}])
    assert work == [None] and total["commits"] == 0


# ---------------------------------------------------------------------------
# The hook's stamp — exact commits, and edits that were never committed
# ---------------------------------------------------------------------------

import json as _json
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "hooks"))
import capture as _capture  # noqa: E402


def test_the_hook_stamps_head_new_commits_and_the_dirty_tree(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "first", {"a.py": "1\n2\n"})
    first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()

    stamp = _capture.work_stamp(str(repo), prev_head="")
    assert stamp["head"] == first and stamp["commits"] == [], "nothing since a first stamp"
    assert stamp["dirty"] == {"files": 0, "add": 0, "del": 0, "paths": []}

    _commit(repo, "2026-09-01T10:12:00", "second", {"b.py": "x\n"})
    (repo / "a.py").write_text("1\n2\n3\n", encoding="utf-8")       # tracked, edited
    (repo / "notes.md").write_text("one\ntwo\n", encoding="utf-8")   # untracked
    second = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()

    stamp = _capture.work_stamp(str(repo), prev_head=first)
    assert stamp["head"] == second
    assert stamp["commits"] == [second], "exactly the commit since the previous stamp"
    assert stamp["dirty"]["files"] == 2
    assert {p["path"]: (p["add"], p["del"], p.get("new", False)) for p in stamp["dirty"]["paths"]} == {
        "a.py": (1, 0, False), "notes.md": (2, 0, True),
    }

    assert _capture.work_stamp(str(tmp_path / "nowhere"), "") is None
    assert _capture.work_stamp("", "") is None


def test_a_stamped_turn_is_exact_and_an_unstamped_one_falls_back_to_the_clock(tmp_path):
    gitwork.forget()
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "clocked in", {"a.py": "1\n"})
    _commit(repo, "2026-09-01T10:11:00", "stamped", {"b.py": "1\n"})
    shas = subprocess.run(["git", "rev-list", "--reverse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.split()

    chat_dir = tmp_path / "chats" / "cc-1"
    chat_dir.mkdir(parents=True)
    (chat_dir / "meta.json").write_text('{"cwd": "%s"}' % repo, encoding="utf-8")
    chat = chat_dir / "chat.md"
    chat.write_text("# x\n", encoding="utf-8")
    # Only turn 2 was stamped; it claims the second commit and carries an edit.
    (chat_dir / "work.jsonl").write_text(_json.dumps({
        "turn": 2, "at": "2026-09-01T10:12:00", "head": shas[1], "commits": [shas[1]],
        "dirty": {"files": 1, "add": 4, "del": 1, "paths": [{"path": "c.py", "add": 4, "del": 1}]},
    }) + "\n", encoding="utf-8")

    work, total = gitwork.session_work(chat, "2609-01", "10:20", [
        {"n": 1, "at": "10:00"}, {"n": 2, "at": "10:10"}, {"n": 3, "at": "10:15"},
    ])
    assert work[0]["exact"] is False and [c["subject"] for c in work[0]["commits"]] == ["clocked in"]
    assert work[1]["exact"] is True and [c["subject"] for c in work[1]["commits"]] == ["stamped"]
    assert work[1]["uncommitted"]["paths"][0]["path"] == "c.py"
    assert work[2] is None, "the stamped commit is not offered to the clock again"
    assert total["commits"] == 2


def test_the_diff_behind_a_work_line(tmp_path):
    gitwork.forget()
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "first", {"a.py": "1\n2\n"})
    _commit(repo, "2026-09-01T10:12:00", "second", {"a.py": "1\n", "b.py": "x\n"})
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()

    one = gitwork.diff(repo, sha, "a.py")
    assert one["live"] is False and one["sha"] == sha[:7]
    assert "-2" in one["diff"] and "b.py" not in one["diff"], "one file of the commit"
    whole = gitwork.diff(repo, sha, None)
    assert "a.py" in whole["diff"] and "b.py" in whole["diff"]

    (repo / "a.py").write_text("1\n3\n", encoding="utf-8")
    (repo / "new.txt").write_text("hello\nworld\n", encoding="utf-8")
    live = gitwork.diff(repo, None, "a.py")
    assert live["live"] is True and "+3" in live["diff"]
    fresh = gitwork.diff(repo, None, "new.txt")
    assert "+hello" in fresh["diff"] and "/dev/null" in fresh["diff"], "an untracked file is all new"

    assert gitwork.diff(repo, "not-a-sha!", None) is None
    assert gitwork.diff(repo, sha, "../../etc/passwd") is None, "never outside the repo"
    assert gitwork.open_file(repo, "../../etc/passwd") == (False, "../../etc/passwd is not in the repository")


def test_a_commit_made_after_the_stamp_still_belongs_to_its_turn(tmp_path):
    """The stamp is written when the turn opens; the work comes after it."""
    gitwork.forget()
    repo = _repo(tmp_path)
    _commit(repo, "2026-09-01T10:03:00", "before the stamp", {"a.py": "1\n2\n"})
    early = gitwork.commits(repo)[0].sha
    _commit(repo, "2026-09-01T10:08:00", "after the stamp", {"b.py": "x\n"})

    chat_dir = tmp_path / "chats" / "cc-late"
    chat_dir.mkdir(parents=True)
    (chat_dir / "meta.json").write_text('{"cwd": "%s"}' % repo, encoding="utf-8")
    chat = chat_dir / "chat.md"
    chat.write_text("# x\n", encoding="utf-8")
    # The hook stamped turn 1 knowing only the commit that existed then.
    (chat_dir / "work.jsonl").write_text(
        json.dumps({"turn": 1, "commits": [early]}) + "\n", encoding="utf-8")

    gitwork.forget()
    work, total = gitwork.session_work(chat, "2609-01", "10:20", [
        {"n": 1, "at": "10:00", "user": "do it", "agent": "done"},
    ])
    subjects = [c["subject"] for c in work[0]["commits"]]
    assert subjects == ["before the stamp", "after the stamp"]
    assert total["commits"] == 2 and work[0]["files_n"] == 2


def test_head_is_read_from_the_repo_without_starting_git(tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "r")
    (repo / "a").write_text("1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "one"], cwd=repo, check=True)
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()

    calls = {"n": 0}
    real = gitwork.git

    def counting(r, *args, **kw):
        calls["n"] += 1
        return real(r, *args, **kw)

    monkeypatch.setattr(gitwork, "git", counting)
    assert gitwork.head(repo) == expected
    assert calls["n"] == 0, "HEAD is in .git/HEAD and the ref file; no process needed"
    # A packed ref, or anything the files do not say plainly, still asks git.
    subprocess.run(["git", "pack-refs", "--all"], cwd=repo, check=True)
    assert gitwork.head(repo) == expected
    assert calls["n"] == 1
