"""What the capture hook costs per message, and what it must never do.

The hook runs on every message of every agent, inside the session it
observes: it reads the end of a file, not the file; it holds the meta lock
for a write, not for a transcript or a git call; and nothing a tool hands
it makes it fail the session.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

try:  # POSIX only: the lock checks below skip on Windows
    import fcntl
except ImportError:  # pragma: no cover — Windows
    fcntl = None

needs_flock = pytest.mark.skipif(fcntl is None, reason="fcntl.flock is POSIX only")

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


capture = _load("sp_capture_cost", "capture.py")
sys.modules.setdefault("capture", capture)
cc = _load("sp_cc_cost", "claude-code-capture.py")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir(exist_ok=True)
    return tmp_path / "data"


def _rec(kind: str, content, at: str = "") -> str:
    return json.dumps({"type": kind, "timestamp": at, "message": {"content": content}}) + "\n"


def _text(s: str) -> list[dict]:
    return [{"type": "text", "text": s}]


def _hook(script: str, args: list[str], payload: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_HOOKS / script), *args], input=payload, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# The transcript: one read, of what was written since the previous Stop
# ---------------------------------------------------------------------------


def test_a_stop_reads_the_transcript_on_from_where_the_last_one_stopped(tmp_path: Path) -> None:
    t = tmp_path / "t.jsonl"
    t.write_text(
        json.dumps({"type": "custom-title", "customTitle": "the name"}) + "\n"
        + _rec("user", "first", "2026-01-01T10:00:00Z")
        + _rec("assistant", _text("first answer"), "2026-01-01T10:00:05Z"), encoding="utf-8")
    tt = capture._turntimes()
    one = cc.Segment(str(t), 0, tt).read()
    assert (one.text, one.title, len(one.points)) == ("first answer", "the name", 2)
    assert one.end == t.stat().st_size

    with open(t, "a", encoding="utf-8") as fh:
        fh.write(_rec("user", "second", "2026-01-01T10:01:00Z")
                 + _rec("assistant", [{"type": "tool_use", "name": "Skill", "input": {"skill": "make-a-scan"}}],
                        "2026-01-01T10:01:02Z")
                 + _rec("assistant", _text("second answer"), "2026-01-01T10:01:05Z"))
    two = cc.Segment(str(t), one.end, tt).read()
    assert two.text == "second answer"
    assert len(two.points) == 3                      # only the new records were read
    assert [u["skill"] for u in two.skills] == ["make-a-scan"]
    assert two.title == ""                           # nothing renamed since: the chat keeps its title

    # A line still being written is not skipped for ever: it is read once whole.
    with open(t, "a", encoding="utf-8") as fh:
        fh.write('{"type": "assistant", "message": {"content": [{"type": "te')
    three = cc.Segment(str(t), two.end, tt).read()
    assert three.text == "" and three.end == two.end
    with open(t, "a", encoding="utf-8") as fh:
        fh.write('xt", "text": "late"}]}}\n')
    assert three.read().text == "late"


def test_a_position_that_is_not_a_line_start_reads_the_whole_file(tmp_path: Path) -> None:
    t = tmp_path / "t.jsonl"
    t.write_text(_rec("user", "q") + _rec("assistant", _text("the answer")), encoding="utf-8")
    assert cc.Segment(str(t), 7).read().text == "the answer"          # mid-line: another file
    assert cc.Segment(str(t), 10_000).read().text == "the answer"     # past the end: a shorter file


def test_the_stop_hook_remembers_how_far_it_read(root: Path, tmp_path: Path) -> None:
    t = tmp_path / "t.jsonl"
    t.write_text(_rec("user", "hello") + _rec("assistant", _text("hi")), encoding="utf-8")
    args = ["--project", "alpha", "--data-root", str(root)]
    for event in ({"hook_event_name": "UserPromptSubmit", "session_id": "pos12345", "prompt": "hello"},
                  {"hook_event_name": "Stop", "session_id": "pos12345", "transcript_path": str(t)}):
        assert _hook("claude-code-capture.py", args, json.dumps(event)).returncode == 0
    folder = root / "projects/alpha/chats/cc-pos12345"
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["transcript_pos"] == {"path": str(t), "pos": t.stat().st_size}
    assert "**Agent**: hi" in (folder / "chat.md").read_text(encoding="utf-8")
    assert capture.TurnCapture(root, "alpha", "cc-pos12345").transcript_pos(str(t)) == t.stat().st_size
    assert capture.TurnCapture(root, "alpha", "cc-pos12345").transcript_pos("/another/file") == 0


def test_the_times_come_from_the_points_the_adapter_read(root: Path, tmp_path: Path, monkeypatch) -> None:
    """Given the transcript's activity times, the stamp does not read the file again."""
    cap = capture.TurnCapture(root, "alpha", "cc-points1")
    cap.open_turn("go")
    tt = capture._turntimes()
    monkeypatch.setattr(tt, "points_of", lambda path: pytest.fail("the transcript was read a second time"))
    now = datetime.now()
    cap.complete_turn("done", transcript=str(tmp_path / "not-read.jsonl"),
                      points=[now, now + timedelta(seconds=1)])
    line = json.loads((cap.folder / "turns.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert "busy" in line and "active_sec" in line


# ---------------------------------------------------------------------------
# The meta lock is held for a write, never for a transcript or for git
# ---------------------------------------------------------------------------


def _lock_is_free(cap) -> bool:
    with open(cap.folder / capture.META_LOCK, "a", encoding="utf-8") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return True


@needs_flock
def test_the_stamps_are_written_outside_the_meta_lock(root: Path, monkeypatch) -> None:
    cap = capture.TurnCapture(root, "alpha", "cc-lockfree")
    cap.open_turn("go")
    seen: dict[str, bool] = {}
    real_time, real_work = cap._stamp_time, cap._stamp_work
    monkeypatch.setattr(cap, "_stamp_time", lambda *a, **k: (seen.setdefault("time", _lock_is_free(cap)), real_time(*a, **k))[1])
    monkeypatch.setattr(cap, "_stamp_work", lambda *a, **k: (seen.setdefault("work", _lock_is_free(cap)), real_work(*a, **k))[1])
    cap.complete_turn("done")
    assert seen == {"time": True, "work": True}


@needs_flock
def test_the_origin_is_written_under_the_meta_lock(root: Path, monkeypatch) -> None:
    cap = capture.TurnCapture(root, "alpha", "cc-origin01")
    cap.open_turn("go")
    held: list[bool] = []
    real = capture._atomic_write_json
    monkeypatch.setattr(capture, "_atomic_write_json", lambda *a, **k: (held.append(not _lock_is_free(cap)), real(*a, **k))[1])
    cap.note_origin("claude-code", "origin01-full", "/somewhere")
    assert held == [True]


# ---------------------------------------------------------------------------
# The files beside a chat are read from their end
# ---------------------------------------------------------------------------


def test_the_end_of_a_long_file_is_read_not_the_file(tmp_path: Path) -> None:
    shared = capture.shared
    f = tmp_path / "turns.jsonl"
    f.write_text("".join(json.dumps({"turn": i, "end": f"e{i}", "pad": "x" * 200}) + "\n" for i in range(5000)),
                 encoding="utf-8")
    lines = shared.tail_lines(f, max_bytes=4096)
    assert 1 <= len(lines) < 40 and json.loads(lines[-1])["turn"] == 4999
    assert all(line.startswith("{") for line in lines)          # no half line at the cut
    assert shared.last_json(f, "end") == "e4999"
    # A last line longer than the window is still found.
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"turn": 5000, "end": "last", "pad": "y" * 20_000}) + "\n")
    assert json.loads(shared.tail_lines(f, max_bytes=4096)[-1])["end"] == "last"
    assert shared.tail_lines(tmp_path / "missing.jsonl") == [] and shared.last_json(tmp_path / "missing.jsonl", "end") is None


def test_the_previous_end_and_head_come_from_the_last_lines(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", "cc-tail0001")
    cap.open_turn("one")
    (cap.folder / "turns.jsonl").write_text('{"turn": 1, "end": "2026-01-01T10:00:00"}\nnot json\n', encoding="utf-8")
    (cap.folder / "work.jsonl").write_text('{"turn": 1, "head": "abc"}\n{"turn": 2, "head": "def"}\n', encoding="utf-8")
    assert cap._last_end() == "2026-01-01T10:00:00"
    assert cap._last_stamp_head() == "def"


# ---------------------------------------------------------------------------
# git: a cap on what is read, and unknown is not clean
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "one")
    return repo


def test_untracked_files_are_counted_up_to_a_cap(repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(capture, "_UNTRACKED_MAX_FILES", 5)
    for i in range(12):
        (repo / f"new{i:02d}.txt").write_text("x\ny\n", encoding="utf-8")
    dirty = capture.work_stamp(str(repo))["dirty"]
    assert dirty["files"] == 12                 # every file is still listed
    assert dirty["add"] == 10                   # lines counted in the first five only
    assert dirty["capped"] is True

    monkeypatch.setattr(capture, "_UNTRACKED_MAX_FILES", 200)
    whole = capture.work_stamp(str(repo))["dirty"]
    assert whole["add"] == 24 and "capped" not in whole


def test_a_git_that_did_not_answer_is_unknown_not_clean(repo: Path, monkeypatch) -> None:
    (repo / "a.txt").write_text("a\nb\n", encoding="utf-8")
    real = capture._git
    monkeypatch.setattr(capture, "_git", lambda cwd, *args: None if args[0] == "diff" else real(cwd, *args))
    stamp = capture.work_stamp(str(repo))
    assert stamp["head"] and stamp["dirty"] is None


# ---------------------------------------------------------------------------
# A message: one read of scans.csv, none for a repeat, old chats left alone
# ---------------------------------------------------------------------------


def test_scans_are_read_once_and_a_repeat_reads_nothing(root: Path, monkeypatch) -> None:
    (root / "scans.csv").write_text("id,project,created_date,created_time\nsc_1,alpha,2001-01,10:00\n", encoding="utf-8")
    read: list[str] = []
    real = capture._read_csv
    monkeypatch.setattr(capture, "_read_csv", lambda path: (read.append(Path(path).name), real(path))[1])
    cap = capture.TurnCapture(root, "alpha", "cc-once0001")
    cap.open_turn("the message")
    assert read.count("scans.csv") == 1
    read.clear()
    again = cap.open_turn("the message")           # the same one, still unanswered
    assert again["turn_number"] == 1 and read == []


def test_a_chat_untouched_since_before_yesterday_is_not_read_for_the_standup(root: Path) -> None:
    yesterday = datetime.now() - timedelta(days=1)
    body = f"\n## Turn 1 · {yesterday:%Y-%m-%d}T10:00:00\n**User**: hi\n"
    chats = root / "projects/alpha/chats"
    fresh, stale = chats / "cc-fresh/chat.md", chats / "cc-stale/chat.md"
    for f in (fresh, stale):
        f.parent.mkdir(parents=True)
        f.write_text(body, encoding="utf-8")
    old = time.time() - 5 * 86400
    os.utime(stale, (old, old))                    # nobody wrote to it for five days
    owed = capture._standup_owed(root, "alpha")
    assert owed is not None and (owed["chats_n"], owed["messages_n"]) == (1, 1)


# ---------------------------------------------------------------------------
# Nothing a tool hands the hook fails the session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", ["[1, 2]", '"text"', "null", "{not json", ""])
def test_a_payload_that_is_no_event_exits_quietly(root: Path, payload: str) -> None:
    got = _hook("claude-code-capture.py", ["--project", "alpha", "--data-root", str(root)], payload)
    assert (got.returncode, got.stderr) == (0, "")
    assert not (root / "projects").exists()


def test_an_event_without_a_session_id_is_not_the_chat_called_none(root: Path) -> None:
    got = _hook("claude-code-capture.py", ["--project", "alpha", "--data-root", str(root)],
                json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "hello"}))
    assert got.returncode == 0
    assert [p.name for p in (root / "projects/alpha/chats").iterdir()] == ["cc-unknown"]


def test_the_cli_adapter_never_builds_a_data_root(tmp_path: Path) -> None:
    missing = tmp_path / "unmounted"
    got = _hook("capture-cli.py", ["--phase", "open", "--project", "alpha", "--data-root", str(missing),
                                   "--agent", "oc-1", "--text", "hello", "--tool", "opencode", "--cwd", str(tmp_path)])
    assert got.returncode == 0 and "does not exist" in got.stdout
    assert not missing.exists()


def test_the_cli_adapter_records_its_failures(root: Path) -> None:
    # A chats path that cannot be a folder: the turn cannot be written.
    (root / "projects").write_text("not a folder", encoding="utf-8")
    got = _hook("capture-cli.py", ["--phase", "open", "--project", "alpha", "--data-root", str(root),
                                   "--agent", "oc-1", "--text", "hello", "--tool", "opencode"])
    assert got.returncode == 0
    errors = [json.loads(x) for x in (root / ".capture/errors.jsonl").read_text(encoding="utf-8").splitlines()]
    assert errors and errors[-1]["agent_id"] == "oc-1" and errors[-1]["tool"] == "opencode"
