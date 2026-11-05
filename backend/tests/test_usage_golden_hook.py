"""The golden logs (testdata/usage/logs, all made up) through the hooks and
through the import: each writes exactly the usage.jsonl checked in under
testdata/usage/expected, and the two agree line for line (the server reads
the last line of an id). The hooks run as the tool runs them, one event at a
time, with the log as it stood at that moment and the clock fixed (SP_NOW).

To see a changed rule's new files: SP_GOLDEN_WRITE=1 writes them (then read
every line before committing them)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend import hookshared, sessionimport

_REPO = Path(__file__).resolve().parents[2]
_HOOKS = _REPO / "scripts" / "hooks"
_LOGS = _REPO / "testdata" / "usage" / "logs"
_EXPECTED = _REPO / "testdata" / "usage" / "expected"
_SID = "6a5e0d1c-7f3b-4c2a-9e1d-0123456789ab"
_THREAD = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001"
_ROLLOUT = f"rollout-2026-11-01T10-00-00-{_THREAD}.jsonl"


@pytest.fixture()
def utc(monkeypatch):
    """Local time is UTC here, in this process and in the hooks it starts."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path / "data"


def _epoch(local: str) -> float:
    return datetime.fromisoformat(local).replace(tzinfo=timezone.utc).timestamp()


def _cut(src: Path, dst: Path, until: float) -> None:
    """``src`` as it stood at ``until``: its lines written by then (a line
    with no time goes with the one before it)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    keep, last = [], True
    for raw in src.read_text(encoding="utf-8").splitlines():
        try:
            t = hookshared.epoch_of(json.loads(raw).get("timestamp"))
        except (ValueError, AttributeError):
            t = None
        last = last if t is None else t <= until
        if last:
            keep.append(raw + "\n")
    dst.write_text("".join(keep), encoding="utf-8")


def _stage_claude(work: Path, until: float) -> Path:
    src = _LOGS / "claude"
    for f in src.rglob("*"):
        if f.is_file():
            to = work / f.relative_to(src)
            if f.suffix == ".jsonl":
                _cut(f, to, until)
            else:
                to.parent.mkdir(parents=True, exist_ok=True)
                to.write_bytes(f.read_bytes())
    return work / f"{_SID}.jsonl"


def _hook(root: Path, payload: dict, now: str, tool: str = "claude-code") -> subprocess.CompletedProcess:
    args = [sys.executable, str(_HOOKS / "claude-code-capture.py"), "--project", "alpha", "--data-root", str(root)]
    if tool != "claude-code":
        args += ["--tool", tool]
    # A fixed Codex home: its key names the account on the limits lines.
    env = {**os.environ, "TZ": "UTC", "SP_NOW": now, "CODEX_HOME": "/sp-test/codex-home"}
    p = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True, timeout=60, env=env)
    assert p.returncode == 0, p.stderr
    return p


def _chat(root: Path, agent: str) -> Path:
    return root / "projects" / "alpha" / "chats" / agent


def _golden(name: str, got: str) -> str:
    path = _EXPECTED / name
    if os.environ.get("SP_GOLDEN_WRITE"):
        path.write_text(got, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _jsonl(text: str) -> list[dict]:
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def _last_wins(lines: list[dict]) -> dict[str, dict]:
    """What the server reads of a usage.jsonl: the last line of each id."""
    out: dict[str, dict] = {}
    for x in lines:
        out[x["id"]] = x
    return out


def _drive_claude(root: Path, work: Path) -> Path:
    stop = {"hook_event_name": "Stop", "session_id": _SID}
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": _SID, "prompt": "plan the change"},
          "2026-10-31T23:40:00")
    t = _stage_claude(work, _epoch("2026-10-31T23:45:10"))
    _hook(root, {**stop, "transcript_path": str(t), "last_assistant_message": "Planned."}, "2026-10-31T23:45:10")
    # Turn 2 is interrupted: no Stop. Turn 3 runs across midnight.
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": _SID, "prompt": "build it"},
          "2026-10-31T23:50:00")
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": _SID, "prompt": "go on"},
          "2026-10-31T23:58:00")
    t = _stage_claude(work, _epoch("2026-11-01T00:01:00"))
    _hook(root, {**stop, "transcript_path": str(t), "last_assistant_message": "Done."}, "2026-11-01T00:01:00")
    return t


def test_the_claude_hook_writes_the_golden_usage(utc, root: Path, tmp_path: Path) -> None:
    _drive_claude(root, tmp_path / "log")
    got = (_chat(root, "cc-6a5e0d1c") / "usage.jsonl").read_text(encoding="utf-8")
    assert got == _golden("usage.claude-code.jsonl", got)
    by_id = _last_wins(_jsonl(got))
    # Read by hand from the log, so the golden file is not just what the code says:
    m1 = by_id["msg_01"]          # three blocks of one message; the last one's output
    assert (m1["turn"], m1["new"], m1["cache_write"], m1["cache"], m1["output"], m1["ttl"]) == (1, 2003, 2000, 10000, 300, "1h")
    assert not {"msg_old1", "msg_other", "msg_syn"} & set(by_id)          # copies and Claude Code's own
    assert (by_id["msg_sc1"]["helper"], by_id["msg_sc1"]["turn"]) == ("side7", 1)   # a helper in the main file
    assert by_id["msg_03"]["turn"] == 2                                   # the interrupted turn keeps its tokens
    assert [by_id[k]["turn"] for k in ("msg_04", "msg_05", "msg_06")] == [3, 3, 3]
    assert by_id["msg_05"]["at"] == "2026-11-01T00:00:30" and by_id["msg_05"].get("compacted") is True
    assert sum(1 for x in by_id.values() if x.get("compacted")) == 1
    assert (by_id["msg_06"]["new"], by_id["msg_06"]["output"], by_id["msg_06"]["cache"]) == (0, 0, 500)   # 1e999, "lots"
    helpers = {k: (v["helper"], v["turn"]) for k, v in by_id.items() if v["helper"] not in ("", "side7")}
    # The helper and the helper it started stay with turn 1, whenever they wrote.
    assert helpers == {"hmsg_1": ("h1", 1), "hmsg_2": ("h1", 1), "hmsg_3": ("h1", 1),
                       "nmsg_1": ("n1", 1), "nmsg_2": ("n1", 1)}
    meta = json.loads((_chat(root, "cc-6a5e0d1c") / "meta.json").read_text(encoding="utf-8"))
    assert [h[0] for h in meta["turns"]] == [1, 2, 3]
    assert meta["helper_turns"] == {"toolu_A1": 1, "toolu_N1": 1}


def test_the_import_writes_what_the_hook_wrote(utc, root: Path, tmp_path: Path) -> None:
    _drive_claude(root, tmp_path / "log")
    hook = _jsonl((_chat(root, "cc-6a5e0d1c") / "usage.jsonl").read_text(encoding="utf-8"))
    imported = sessionimport.claude_usage(_LOGS / "claude" / f"{_SID}.jsonl", _SID)
    assert _last_wins(imported) == _last_wins(hook)
    assert len(imported) == len(_last_wins(imported))                   # one line per message
    assert sessionimport.claude_usage(_LOGS / "claude" / f"{_SID}.jsonl", _SID) == imported   # and again: the same


def test_a_stop_again_adds_nothing_with_or_without_its_read_position(utc, root: Path, tmp_path: Path) -> None:
    t = _drive_claude(root, tmp_path / "log")
    usage = _chat(root, "cc-6a5e0d1c") / "usage.jsonl"
    before = usage.read_bytes()
    stop = {"hook_event_name": "Stop", "session_id": _SID, "transcript_path": str(t), "stop_hook_active": True}
    _hook(root, stop, "2026-11-01T00:01:05")
    assert usage.read_bytes() == before
    meta_path = _chat(root, "cc-6a5e0d1c") / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.pop("transcript_pos")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    (_chat(root, "cc-6a5e0d1c") / "helpers.json").unlink()
    _hook(root, stop, "2026-11-01T00:01:10")           # the whole log, and every helper, read again
    assert usage.read_bytes() == before


def test_the_codex_hook_writes_the_golden_usage_and_limits(utc, root: Path, tmp_path: Path) -> None:
    work = tmp_path / "codex" / _ROLLOUT
    stop = {"hook_event_name": "Stop", "session_id": _THREAD, "transcript_path": str(work)}
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": _THREAD, "prompt": "go"},
          "2026-11-01T10:00:01", tool="codex")
    _cut(_LOGS / "codex" / _ROLLOUT, work, _epoch("2026-11-01T10:00:10"))
    _hook(root, {**stop, "turn_id": "t1", "last_assistant_message": "done"}, "2026-11-01T10:00:10", tool="codex")
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": _THREAD, "prompt": "next"},
          "2026-11-01T10:01:00", tool="codex")
    _cut(_LOGS / "codex" / _ROLLOUT, work, _epoch("2026-11-01T10:01:10"))
    _hook(root, {**stop, "turn_id": "t2", "last_assistant_message": "ok"}, "2026-11-01T10:01:10", tool="codex")
    agent = "codex-ffff0001"
    got = (_chat(root, agent) / "usage.jsonl").read_text(encoding="utf-8")
    assert got == _golden("usage.codex.jsonl", got)
    lines = _jsonl(got)
    # The call reported three times (twice in turn 1, once after turn 2 began) is one line, in turn 1.
    assert [(x["id"], x["turn"], x["new"], x["cache"], x["output"], x["model"]) for x in lines] == [
        ("30000", 1, 12000, 12000, 3000, "gpt-5-codex"),
        ("31500", 2, 1000, 0, 500, "gpt-5.1-codex"),
        ("31600", 2, 0, 0, 0, "gpt-5.1-codex"),
    ]
    limits = (root / ".usage" / "limits.jsonl").read_text(encoding="utf-8")
    assert limits == _golden("limits.codex.jsonl", limits)
    assert [json.loads(x)["five_hour"]["used"] for x in limits.splitlines()] == [10.0, 12.5]
    imported = sessionimport.codex_usage(_LOGS / "codex" / _ROLLOUT, _THREAD)
    assert _last_wins(imported) == _last_wins(lines)


def test_opencode_hands_the_golden_messages_through_the_cli(utc, root: Path) -> None:
    cli = [sys.executable, str(_HOOKS / "capture-cli.py"), "--project", "alpha", "--data-root", str(root),
           "--agent", "oc-golden01", "--json-stdin"]
    env = {**os.environ, "TZ": "UTC", "SP_NOW": "2026-11-01T12:00:00"}
    subprocess.run([*cli, "--phase", "open"], input=json.dumps({"text": "hi"}), text=True, check=True, timeout=60, env=env)
    env["SP_NOW"] = "2026-11-01T12:00:10"
    complete = (_LOGS / "opencode" / "complete.json").read_text(encoding="utf-8")
    for _ in range(2):    # sent twice: the same lines
        subprocess.run([*cli, "--phase", "complete"], input=complete, text=True, check=True, timeout=60, env=env)
    got = (_chat(root, "oc-golden01") / "usage.jsonl").read_text(encoding="utf-8")
    assert got == _golden("usage.opencode.jsonl", got)
    lines = _jsonl(got)
    assert [(x["id"], x["new"], x["output"], x["thinking"], x["cache"], x["helper"]) for x in lines] == [
        ("msg_oc1", 216, 49, 40, 9216, ""), ("msg_oc2", 30, 12, 0, 100, "ses_child01"), ("msg_oc3", 0, 0, 0, 0, "")]
