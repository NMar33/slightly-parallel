"""The reasoning effort of each reply, in usage.jsonl and facts.jsonl.

Where each tool says it (checked against the real programs with local stub
models): Claude Code writes ``effort`` on every assistant record of a model
that has one, and /effort changes it from the next reply (the hook's
CLAUDE_EFFORT read "medium" at every prompt and the right value only at
Stop: it is never read); Codex's ``turn_context`` names ``effort`` per turn;
OpenCode's assistant message names its ``variant``. Unknown is "", and the
by-model table's split adds up to the model's tokens."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from backend import hookshared, sessionimport

HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
FIX = Path(__file__).resolve().parent / "fixtures" / "helpers"


def _assistant(mid: str, effort: str | None, at: str = "2026-11-11T10:00:00.000Z", sid: str = "s1") -> dict:
    rec = {"type": "assistant", "timestamp": at, "sessionId": sid, "entrypoint": "cli",
           "message": {"id": mid, "model": "claude-opus-4-6", "content": [{"type": "text", "text": "ok"}],
                       "usage": {"input_tokens": 10, "output_tokens": 5}}}
    if effort is not None:
        rec["effort"] = effort
    return rec


def test_claude_codes_record_names_the_effort_and_a_model_without_one_names_none() -> None:
    got = hookshared.usage_records_claude([_assistant("m1", "high"), _assistant("m2", "low"),
                                           _assistant("m3", "max"), _assistant("m4", None)], "s1")
    assert [x["effort"] for x in got] == ["high", "low", "max", ""]
    # The recorded claude -p run (Claude Code 2.1.322, --effort high).
    recs = [json.loads(x) for x in (FIX / "claude-print.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["effort"] for x in hookshared.usage_records_claude(recs)] == ["high"]
    # A value no tool uses is no effort.
    assert hookshared.usage_records_claude([_assistant("m5", "turbo")])[0]["effort"] == ""


def _codex_file(tmp_path: Path) -> Path:
    """Two turns: the first at low effort, the second at high (``-c
    model_reasoning_effort=…`` between them), the way Codex 0.163 writes them."""
    def ev(ts: str, kind: str, payload: dict) -> dict:
        return {"timestamp": ts, "type": kind, "payload": payload}

    def tokens(ts: str, total: int) -> dict:
        return ev(ts, "event_msg", {"type": "token_count", "info": {
            "total_token_usage": {"total_tokens": total},
            "last_token_usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 5,
                                 "reasoning_output_tokens": 0, "total_tokens": 15}}})
    recs = [
        ev("2026-11-11T00:00:00Z", "session_meta", {"id": "t", "source": "exec", "originator": "codex_exec"}),
        ev("2026-11-11T00:00:01Z", "event_msg", {"type": "task_started", "turn_id": "a"}),
        ev("2026-11-11T00:00:01Z", "turn_context", {"turn_id": "a", "model": "gpt-6.1-sol", "effort": "low",
                                                    "collaboration_mode": {"settings": {"reasoning_effort": "low"}}}),
        tokens("2026-11-11T00:00:02Z", 15),
        ev("2026-11-11T00:01:00Z", "event_msg", {"type": "task_started", "turn_id": "b"}),
        ev("2026-11-11T00:01:00Z", "turn_context", {"turn_id": "b", "model": "gpt-6.1-sol", "effort": None,
                                                    "collaboration_mode": {"settings": {"reasoning_effort": "high"}}}),
        tokens("2026-11-11T00:01:02Z", 30),
    ]
    f = tmp_path / "rollout-2026-11-11T00-00-00-01a1c7d7-a31d-71d2-9d1e-3f9935e20b38.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    return f


def test_codex_takes_the_effort_of_the_turn_context_in_force(tmp_path: Path) -> None:
    f = _codex_file(tmp_path)
    lines, _ = hookshared.codex_turn_usage(f, back=1)
    assert [x["effort"] for x in lines] == ["low", "high"]
    # The turn alone: its effort comes with it, as its model does.
    lines, _ = hookshared.codex_turn_usage(f, "b")
    assert [x["effort"] for x in lines] == ["high"]
    lines, _ = hookshared.codex_turn_usage(f, since=0)
    assert [x["effort"] for x in lines] == ["low", "high"]
    # The import reads every record of the file in one pass (sessionimport.codex_usage_parts).
    recs = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
    assert [x["effort"] for x in hookshared.usage_records_codex(recs)] == ["low", "high"]
    assert sessionimport.usage_records_codex is hookshared.usage_records_codex


def test_opencode_takes_the_variant_when_it_names_an_effort() -> None:
    fx = json.loads((FIX / "opencode-run.json").read_text(encoding="utf-8"))
    reply = next(m for m in fx["messages"] if m["role"] == "assistant")
    assert reply["variant"] == "high"
    got = hookshared.usage_records_opencode([
        {"id": "a", "at": 1794354412554, "model": "stub-model", "input": 10, "output": 5, "variant": reply["variant"]},
        {"id": "b", "at": 1794354412600, "model": "stub-model", "input": 10, "output": 5, "variant": "default"},
        {"id": "c", "at": 1794354412700, "model": "stub-model", "input": 10, "output": 5},
    ])
    assert [x["effort"] for x in got] == ["high", "", ""]
    src = (HOOKS / "slightly-parallel-opencode.js").read_text(encoding="utf-8")
    assert "variant: String(info.variant || asked || '')" in src


def test_the_stop_hook_keeps_the_effort_in_usage_and_facts(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    t = tmp_path / "t.jsonl"
    # Stamped from now, not a fixed day: the hook reads only the replies
    # after the prompt it saw, so a fixed 10:00Z failed every day after
    # 10:00 UTC (docs/testing.md, two "now"s).
    from datetime import datetime, timedelta, timezone
    base = datetime.now(timezone.utc) + timedelta(minutes=1)
    at = lambda s: (base + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731
    recs = [{"type": "user", "timestamp": at(0), "sessionId": "s1",
             "message": {"role": "user", "content": "go"}},
            _assistant("m1", "low", at(5)),
            _assistant("m2", "max", at(9))]
    t.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    args = [sys.executable, str(HOOKS / "claude-code-capture.py"), "--project", "p", "--data-root", str(root)]
    for payload in ({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": str(tmp_path), "prompt": "go"},
                    {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t),
                     "last_assistant_message": "ok"}):
        # The environment says medium: never read (it reads stale on a prompt).
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CODEX"))}
        p = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True,
                           env={**env, "CLAUDE_EFFORT": "medium"})
        assert p.returncode == 0, p.stderr
    folder = root / "projects" / "p" / "chats" / "cc-s1"
    usage = [json.loads(x) for x in (folder / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["effort"] for x in usage] == ["low", "max"]
    facts = [json.loads(x) for x in (folder / "facts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert facts[-1]["effort"] == "max"


def test_the_effort_split_adds_up_to_each_models_tokens() -> None:
    """docs/testing.md case 4: on the golden data the split equals the row."""
    root = Path(__file__).resolve().parents[2] / "testdata" / "usage" / "expected"
    for name in ("summary.today.json", "summary.30d.json", "summary.7d.json"):
        d = json.loads((root / name).read_text(encoding="utf-8"))
        for tool in d["by_tool"]:
            for m in tool["models"]:
                assert sum(m["efforts"].values()) == m["new_output"] + m["helpers"]["new_output"], (name, m["model"])
