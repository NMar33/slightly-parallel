"""Agent time: when each answer ended, the working time inside it, and the
session's three numbers — session, agent, waiting on the person."""

from __future__ import annotations

import json
from pathlib import Path

from backend import turntimes
from backend.sessions import derive_sessions

CHAT = """# chat

## Turn 1 · 2026-09-29T10:00:00
**User**: first
**Agent**: done

## Turn 2 · 2026-09-29T10:20:00
**User**: second
**Agent**: done too
"""


def _chat(tmp_path: Path, times: list[dict] | None = None, meta: dict | None = None) -> Path:
    folder = tmp_path / "data" / "projects" / "alpha" / "chats" / "cc-abc"
    folder.mkdir(parents=True)
    (folder / "chat.md").write_text(CHAT, encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps(meta or {"tool": "claude-code"}), encoding="utf-8")
    if times is not None:
        (folder / "turns.jsonl").write_text("".join(json.dumps(t) + "\n" for t in times), encoding="utf-8")
    return folder


def _session(folder: Path):
    [s] = derive_sessions([("alpha", "cc-abc", folder / "chat.md")], gap_minutes=30)
    return s


def test_the_session_runs_to_the_last_answer_and_the_agent_only_worked_its_turns(tmp_path: Path) -> None:
    folder = _chat(tmp_path, [
        {"turn": 1, "start": "2026-09-29T10:00:00", "end": "2026-09-29T10:05:00", "active_sec": 300},
        # Ran to 10:50, but asleep for half an hour inside: 20 working minutes.
        {"turn": 2, "start": "2026-09-29T10:20:00", "end": "2026-09-29T10:50:00", "active_sec": 1200},
    ])
    s = _session(folder)
    # Waiting on the person: 10:05 → 10:20. Turn 2's half hour asleep is neither.
    assert (s.duration_min, s.agent_min, s.waiting_min, s.timed) == (50, 25, 15, "exact")
    assert s.end_time == "10:50"
    assert [t.get("worked_sec") for t in s.turns] == [300, 1200]


def test_an_old_chat_without_ends_is_an_estimate_and_says_so(tmp_path: Path) -> None:
    s = _session(_chat(tmp_path))
    # Turn 1 is counted to the next prompt, capped at 20 min; the last is unknown.
    assert (s.duration_min, s.agent_min, s.timed) == (20, 20, "approx")


def test_the_git_stamp_ends_a_turn_when_nothing_better_is_there(tmp_path: Path) -> None:
    folder = _chat(tmp_path)
    (folder / "work.jsonl").write_text(
        json.dumps({"turn": 1, "at": "2026-09-29T10:03:00"}) + "\n"
        + json.dumps({"turn": 2, "at": "2026-09-29T10:21:00"}) + "\n", encoding="utf-8")
    s = _session(folder)
    assert (s.duration_min, s.agent_min, s.waiting_min, s.timed) == (21, 4, 17, "exact")


def _rec(kind: str, at: str, content) -> dict:
    return {"type": kind, "timestamp": at, "message": {"content": content}}


def test_the_backfill_reads_the_answer_out_of_the_transcript(tmp_path: Path) -> None:
    folder = _chat(tmp_path, meta={"tool": "claude-code", "session_ref": "sess-1"})
    claude = tmp_path / "claude" / "-work"
    claude.mkdir(parents=True)
    # Transcript times carry their zone; build them from local times.
    from datetime import datetime

    def utc(local: str) -> str:
        return datetime.fromisoformat(local).astimezone().isoformat()

    recs = [
        _rec("user", utc("2026-09-29T09:59:59"), "first"),
        _rec("assistant", utc("2026-09-29T10:01:00"), [{"type": "text", "text": "…"}]),
        _rec("user", utc("2026-09-29T10:02:00"), [{"type": "tool_result", "content": "ok"}]),
        _rec("assistant", utc("2026-09-29T10:04:00"), [{"type": "text", "text": "done"}]),
        # A task notification: work after it is not turn 1's.
        _rec("user", utc("2026-09-29T10:10:00"), "<task-notification>helper done</task-notification>"),
        _rec("assistant", utc("2026-09-29T10:11:00"), [{"type": "text", "text": "noted"}]),
        _rec("user", utc("2026-09-29T10:19:59"), "second"),
        _rec("assistant", utc("2026-09-29T10:25:00"), [{"type": "text", "text": "done too"}]),
    ]
    (claude / "sess-1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")

    assert turntimes.backfill(tmp_path / "data", claude_dir=tmp_path / "claude") == 2
    got = turntimes.times(folder)
    assert got[1].end.strftime("%H:%M") == "10:04" and got[1].active_sec == 240
    assert got[2].end.strftime("%H:%M") == "10:25"
    # Twice is once.
    assert turntimes.backfill(tmp_path / "data", claude_dir=tmp_path / "claude") == 0
    assert _session(folder).timed == "exact"


def test_a_turn_ends_before_the_next_captured_turn_even_unseen_in_the_transcript(tmp_path: Path) -> None:
    # Turn 2's prompt reached the capture but is no prompt in the transcript
    # (a message the tool injected): turn 1 still ends before 10:20.
    folder = _chat(tmp_path, meta={"tool": "claude-code", "session_ref": "sess-2"})
    claude = tmp_path / "claude" / "-work"
    claude.mkdir(parents=True)
    from datetime import datetime

    def z(local: str) -> str:
        return datetime.fromisoformat(local).astimezone().isoformat()

    recs = [
        _rec("user", z("2026-09-29T09:59:59"), "first"),
        _rec("assistant", z("2026-09-29T10:03:00"), [{"type": "text", "text": "done"}]),
        _rec("assistant", z("2026-09-29T10:21:00"), [{"type": "text", "text": "turn two's work"}]),
        _rec("assistant", z("2026-09-29T10:30:00"), [{"type": "text", "text": "done too"}]),
    ]
    (claude / "sess-2.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    turntimes.backfill(tmp_path / "data", claude_dir=tmp_path / "claude")
    got = turntimes.times(folder)
    assert got[1].end.strftime("%H:%M") == "10:03"
    assert got[2].end.strftime("%H:%M") == "10:30"


def test_helpers_keep_the_chat_busy_and_their_work_adds_up(tmp_path: Path) -> None:
    folder = _chat(tmp_path, [
        # Turn 1 hands work to two helpers and answers at 10:02; they work
        # to 10:15 (busy for you: one stretch; the work: 2 × 13 minutes).
        {"turn": 1, "start": "2026-09-29T10:00:00", "end": "2026-09-29T10:02:00", "active_sec": 120,
         "helper_sec": 2 * 13 * 60, "busy": [["2026-09-29T10:00:00", "2026-09-29T10:02:00"]]},
        # Their stretch after the answer lands on turn 2's line, before its prompt.
        {"turn": 2, "start": "2026-09-29T10:20:00", "end": "2026-09-29T10:25:00", "active_sec": 300,
         "helper_sec": 0, "busy": [["2026-09-29T10:02:00", "2026-09-29T10:15:00"],
                                    ["2026-09-29T10:20:00", "2026-09-29T10:25:00"]]},
    ])
    s = _session(folder)
    # Session 25; busy 10:00–10:15 and 10:20–10:25 = 20; the helpers' work 26;
    # waiting on you only 10:15–10:20: before that the helpers were working.
    assert (s.duration_min, s.agent_min, s.helper_min, s.waiting_min) == (25, 20, 26, 5)


def test_a_helpers_report_in_the_chat_keeps_nothing(tmp_path: Path) -> None:
    folder = tmp_path / "data" / "projects" / "alpha" / "chats" / "cc-abc"
    folder.mkdir(parents=True)
    (folder / "chat.md").write_text(
        "# chat\n\n## Turn 1 · 2026-09-29T10:00:00\n"
        "**User**: Another Claude session sent a message:\n<agent-message from=\"a1\">\n"
        "#vision and #rule keep a message; #important stars it; #done closes tk_12345678.\n"
        "**Agent**: noted\n\n## Turn 2 · 2026-09-29T10:05:00\n"
        "**User**: #vision the board is the spine\n**Agent**: kept\n", encoding="utf-8")
    [s] = derive_sessions([("alpha", "cc-abc", folder / "chat.md")], gap_minutes=30)
    assert [m["turn"] for m in s.keep_marks] == [2]
    assert s.important_tags == [] and s.done_tags == []
