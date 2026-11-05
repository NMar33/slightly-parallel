"""Usage: the tokens each chat used and the plan limits (usagelib.py,
routers/usage.py). Synthetic usage.jsonl and limits.jsonl only."""

from __future__ import annotations

import importlib.util
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import app_settings, mcp, usagelib
from tests.conftest import make_chat

AGENT = "cc-usage001"


def _rec(turn: int, at: datetime, mid: str, *, new: int = 0, cache: int = 0, output: int = 0,
         model: str = "claude-opus-4-5", helper: str = "", **more: Any) -> dict[str, Any]:
    return {"turn": turn, "at": at.strftime("%Y-%m-%dT%H:%M:%S"), "id": mid, "tool": "claude-code",
            "model": model, "new": new, "cache_write": more.pop("cache_write", 0), "cache": cache,
            "output": output, "thinking": more.pop("thinking", 0), "ttl": more.pop("ttl", "5m"),
            "helper": helper, **more}


def _write(path: Path, lines: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


# One table for Python, the hook and TypeScript: testdata/usage/format-table.json.
TABLE = json.loads((Path(__file__).resolve().parents[2] / "testdata" / "usage" / "format-table.json")
                   .read_text(encoding="utf-8"))


@pytest.mark.parametrize("n, shown", TABLE["tokens"])
def test_tokens_are_rounded_by_the_one_table(n: int, shown: str) -> None:
    assert usagelib.format_tokens(n) == shown


@pytest.mark.parametrize("x, shown", TABLE["pct"])
def test_percent_is_the_nearest_a_tie_down(x: float | None, shown: str) -> None:
    assert usagelib.pct_text(x) == shown


@pytest.mark.parametrize("pair, shown", TABLE["ratio"])
def test_the_ratio_is_tenths_a_tie_down(pair: list[int], shown: str) -> None:
    assert usagelib.ratio_text(*pair) == shown


@pytest.mark.parametrize("mins, shown", TABLE["span_min"])
def test_durations_are_floored(mins: int, shown: str) -> None:
    assert usagelib.span_text(timedelta(minutes=mins)) == shown


def test_odd_values_read_softly() -> None:
    assert usagelib.format_tokens(2.6e6) == "2.6M"
    assert usagelib.format_tokens(None) == "—"
    assert usagelib.format_tokens(-2_386) == "-2.4k"
    assert usagelib.format_tokens(float("inf")) == "0" and usagelib.format_tokens(float("nan")) == "0"
    assert usagelib.format_tokens("many") == "—"
    # Counts never raise: CSV text, NaN, infinity, a list.
    assert [usagelib._int(v) for v in ("3", "3.0", " 7 ", 3.9, float("nan"), float("inf"), 1e309, "x", [1], None,
                                        -4)] == [3, 3, 7, 3, 0, 0, 0, 0, 0, 0, 0]
    assert usagelib.pct_text(float("nan")) == "—" and usagelib._pct(-0.2) == 0


# ---------------------------------------------------------------------------
# One chat
# ---------------------------------------------------------------------------

T0 = datetime(2026, 10, 1, 14, 0, 0)


def _chat(root: Path, records: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> Path:
    folder = root / "projects" / "ALPHA" / "chats" / AGENT
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "meta.json").write_text(json.dumps({"agent_id": AGENT, "tool": "claude-code",
                                                  "session_ref": "sess-1", **(meta or {})}), encoding="utf-8")
    _write(folder / "usage.jsonl", records)
    return folder


def test_a_turn_sums_its_messages_and_keeps_helpers_apart(tmp_path: Path) -> None:
    _chat(tmp_path, [
        _rec(1, T0, "m1", new=1_000, cache=0, output=10),
        # The same id again: output grew across its content blocks, the last line wins.
        _rec(1, T0 + timedelta(seconds=5), "m2", new=874, cache=50_000, output=6),
        _rec(1, T0 + timedelta(seconds=9), "m2", new=874, cache=50_000, output=502, thinking=200),
        _rec(1, T0 + timedelta(seconds=20), "h1", new=200_000, cache=0, output=100_412, helper="agent-a"),
        _rec(1, T0 + timedelta(seconds=21), "h2", new=0, cache=0, output=0, model="<synthetic>"),
        _rec(1, T0 + timedelta(seconds=30), "m3", new=0, cache=58_233, output=0, model="claude-sonnet-4-5"),
    ])
    turns = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)
    t = turns[1]
    assert (t["new"], t["output"], t["cache"], t["thinking"], t["messages"]) == (1_874, 512, 108_233, 200, 3)
    assert t["models"] == ["claude-opus-4-5", "claude-sonnet-4-5"] and t["model"] == "claude-sonnet-4-5"
    assert t["helpers"] == {"n": 1, "new_output": 300_412, "cache": 0}
    assert t["compacted"] is False
    assert t["line"] == "→ 1.9k ↑ 512 ↓ (108k) + helpers 300k"
    assert t["rebuild"] is None and t["share"] == round(108_233 / (108_233 + 1_874), 4)


def test_a_cache_rebuild_is_named_with_its_cause(tmp_path: Path) -> None:
    _chat(tmp_path, [
        _rec(1, T0, "a", new=500, cache=100_000, output=100),
        # Twelve minutes later, a 5-minute cache: expired.
        _rec(2, T0 + timedelta(minutes=12), "b", new=101_000, cache=0, output=300),
        _rec(3, T0 + timedelta(minutes=13), "c", new=200, cache=101_000, output=50),
        # Within a minute, another model: the cache was built again for it.
        _rec(4, T0 + timedelta(minutes=14), "d", new=101_000, cache=0, output=50, model="claude-sonnet-4-5"),
        _rec(5, T0 + timedelta(minutes=15), "e", new=200, cache=101_000, output=50, model="claude-sonnet-4-5"),
        _rec(6, T0 + timedelta(minutes=16), "f", new=101_000, cache=0, output=50, model="claude-sonnet-4-5"),
    ])
    turns = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)
    assert turns[1]["rebuild"] is None and turns[3]["rebuild"] is None
    assert turns[2]["rebuild"] == {"cause": "cache expired: 12 min since the last turn", "kind": "expired"}
    assert turns[2]["line"] == "→ 101k ↑ 300 ↓ (0) · cache expired"
    assert turns[4]["rebuild"]["cause"] == "model changed: claude-opus-4-5 → claude-sonnet-4-5"
    assert turns[6]["rebuild"]["cause"] == "cause not recorded"
    assert turns[6]["line"].endswith("· cache rebuilt")


def test_claude_codes_own_miss_cause_wins_within_two_minutes(tmp_path: Path) -> None:
    _chat(tmp_path, [
        _rec(1, T0, "a", new=500, cache=100_000, output=100),
        _rec(2, T0 + timedelta(minutes=12), "b", new=101_000, cache=0, output=300),
    ])
    _write(tmp_path / ".usage" / "sessions" / "claude-code-sess-1.json", [])
    (tmp_path / ".usage" / "sessions" / "claude-code-sess-1.json").write_text(json.dumps({
        "prompt_cache": {"last_miss_cause": "system prompt changed",
                         "last_miss_at": (T0 + timedelta(minutes=12, seconds=30)).isoformat()}}), encoding="utf-8")
    assert usagelib.chat_turns(tmp_path, "ALPHA", AGENT)[2]["rebuild"] == {
        "cause": "system prompt changed", "kind": "tool"}


def test_the_line_names_the_5_hour_limit_when_it_passes_a_ten(tmp_path: Path) -> None:
    _chat(tmp_path, [
        _rec(1, T0, "a", new=500, cache=1_000, output=100, limit={"five_hour": 62.0, "seven_day": 31.0}),
        _rec(2, T0 + timedelta(minutes=1), "b", new=500, cache=1_000, output=100, limit={"five_hour": 68.0}),
        _rec(3, T0 + timedelta(minutes=2), "c", new=500, cache=1_000, output=100, limit={"five_hour": 71.0}),
    ])
    turns = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)
    assert turns[1]["limit"] == {"five_hour": 62.0, "seven_day": 31.0}
    assert turns[2]["line"] == "→ 500 ↑ 100 ↓ (1k)"
    assert turns[3]["line"] == "→ 500 ↑ 100 ↓ (1k) · 5-hour 71%"


def test_claude_code_turns_take_their_limit_from_the_limits_file(tmp_path: Path) -> None:
    _chat(tmp_path, [
        _rec(1, T0, "a", new=500, cache=1_000, output=100),
        _rec(2, T0 + timedelta(minutes=3), "b", new=500, cache=1_000, output=100),
    ])
    _write(tmp_path / ".usage" / "limits.jsonl", [
        {"at": (T0 - timedelta(minutes=1)).isoformat(), "tool": "claude-code",
         "five_hour": {"used": 59.0, "resets_at": "2026-10-01T16:40:00"}},
        {"at": (T0 + timedelta(minutes=2)).isoformat(), "tool": "claude-code",
         "five_hour": {"used": 60.0, "resets_at": "2026-10-01T16:40:00"}},
    ])
    turns = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)
    assert turns[1]["limit"] == {"five_hour": 59.0} and turns[2]["limit"] == {"five_hour": 60.0}
    assert turns[2]["line"] == "→ 500 ↑ 100 ↓ (1k) · 5-hour 60%"


@pytest.mark.parametrize("before, after, word", [
    (68.0, 69.9, " · 5-hour 70%"),   # 69.9 shows as 70%: the ten is passed as shown
    (69.9, 70.0, ""),                # both show 70%
    (71.0, 79.6, " · 5-hour 80%"),   # the block says 80% too
    (79.4, 79.5, ""),                # 79.5 is a tie: down, 79%
])
def test_the_5_hour_word_follows_the_shown_percent(tmp_path: Path, before: float, after: float, word: str) -> None:
    _chat(tmp_path, [
        _rec(1, T0, "a", new=500, cache=1_000, output=100, limit={"five_hour": before}),
        _rec(2, T0 + timedelta(minutes=1), "b", new=500, cache=1_000, output=100, limit={"five_hour": after}),
    ])
    assert usagelib.chat_turns(tmp_path, "ALPHA", AGENT)[2]["line"] == "→ 500 ↑ 100 ↓ (1k)" + word


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


def test_limits_go_stale_and_expire(tmp_path: Path) -> None:
    now = datetime(2026, 11, 1, 14, 48, 0)
    _write(tmp_path / ".usage" / "limits.jsonl", [
        {"at": "2026-11-01T14:02:11", "tool": "claude-code",
         "five_hour": {"used": 61.0, "resets_at": "2026-11-01T16:40:00"}, "source": "statusline"},
        {"at": "2026-11-01T14:40:00", "tool": "claude-code",
         "five_hour": {"used": 62.0, "resets_at": "2026-11-01T16:40:00"},
         "seven_day": {"used": 31.0, "resets_at": "2026-11-05T09:00:00"}, "source": "statusline"},
        {"at": "2026-11-01T13:48:00", "tool": "codex", "plan": "plus",
         "five_hour": {"used": 9.0, "resets_at": "2026-11-01T14:10:00"},
         "seven_day": {"used": 81.0, "resets_at": "2026-11-03T06:00:00"}, "source": "rollout"},
        "not json",
    ])
    got = usagelib.limits(tmp_path, now)
    cc, cx = got["claude-code"], got["codex"]
    assert cc["read_at"] == "2026-11-01T14:40:00" and cc["stale"] is False and cc["expired"] is False
    assert cc["five_hour"] == {"used": 62.0, "resets_at": "2026-11-01T16:40:00", "in": "1 h 52 min", "expired": False,
                               "span_s": 18_000, "resets_text": "16:40", "expired_text": ""}
    assert cc["read_at_text"] == "14:40" and cc["seven_day"]["resets_text"] == "Thu 09:00"
    assert cc["seven_day"]["in"] == "3 d 18 h"
    # Codex: read an hour ago (stale), its 5-hour window reset since (expired).
    assert cx["stale"] is True and cx["age_min"] == 60 and cx["expired"] is True and cx["plan"] == "plus"
    assert cx["five_hour"]["expired"] is True and cx["five_hour"]["in"] == ""
    assert cx["five_hour"]["expired_text"] == "Reset at 14:10. No reading since."
    assert cx["seven_day"]["expired"] is False
    assert "opencode" not in got


def _cc(at: str, model: str, five: float, week: float, *, account: str = "aaaaaaaaaaaa", session: str = "s",
        five_resets: str = "2026-11-01T16:40:00", week_resets: str = "2026-11-05T09:00:00") -> dict[str, Any]:
    return {"at": at, "tool": "claude-code", "account": account, "model": model, "session": session,
            "five_hour": {"used": five, "resets_at": five_resets},
            "seven_day": {"used": week, "resets_at": week_resets}, "source": "statusline"}


def test_limits_keep_one_series_per_account(tmp_path: Path) -> None:
    """The limits are the account's: two chats on two models read the same
    numbers, and one model's idle session sending an older reading again
    does not make a second truth."""
    now = datetime(2026, 11, 1, 14, 48, 0)
    _write(tmp_path / ".usage" / "limits.jsonl", [
        # Before readings named their account: given way to the newer named ones.
        {"at": "2026-11-01T14:00:00", "tool": "claude-code", "five_hour": {"used": 50.0, "resets_at": "2026-11-01T16:40:00"}},
        _cc("2026-11-01T14:40:00", "claude-opus-5-5", 56.0, 67.0, session="opus1234"),
        _cc("2026-11-01T14:40:03", "claude-fable-5-1", 4.0, 60.0, session="fable123"),     # stale re-send
        _cc("2026-11-01T14:40:06", "claude-fable-5-1", 56.0, 67.0, session="fable123"),
        _cc("2026-11-01T14:41:00", "claude-opus-5-5", 30.0, 63.0, account="bbbbbbbbbbbb", session="other123"),
    ])
    cc = usagelib.limits(tmp_path, now)["claude-code"]
    assert [(x["account"], x["model"], x["five_hour"]["used"], x["seven_day"]["used"], x["read_at"], x["session"])
            for x in cc["series"]] == [
        ("bbbbbbbbbbbb", "claude-opus-5-5", 30.0, 63.0, "2026-11-01T14:41:00", "other123"),
        ("aaaaaaaaaaaa", "claude-fable-5-1", 56.0, 67.0, "2026-11-01T14:40:06", "fable123"),
    ]
    assert list(cc["series"][0]) == ["account", "model", "five_hour", "seven_day", "read_at", "read_at_text",
                                     "age_min", "stale", "expired", "plan", "source", "session"]
    assert cc["accounts_n"] == 2 and cc["models_n"] == 2
    # The tool's own fields: the newest series, as one reading answered before.
    top = {k: v for k, v in cc.items() if k not in ("series", "accounts_n", "models_n")}
    assert top == {k: v for k, v in cc["series"][0].items() if k not in ("account", "model", "session")}


def test_a_line_without_an_account_is_one_series(tmp_path: Path) -> None:
    now = datetime(2026, 11, 1, 14, 48, 0)
    _write(tmp_path / ".usage" / "limits.jsonl", [
        {"at": "2026-11-01T14:40:00", "tool": "claude-code", "five_hour": {"used": 50.0, "resets_at": "2026-11-01T16:40:00"}},
    ])
    cc = usagelib.limits(tmp_path, now)["claude-code"]
    assert [(x["account"], x["model"], x["session"]) for x in cc["series"]] == [("", "", "")]
    assert cc["five_hour"]["used"] == 50.0 and cc["accounts_n"] == 1 and cc["models_n"] == 0


def test_a_window_holds_its_highest_reading(tmp_path: Path) -> None:
    """An idle session's status line sends its last reading again: within
    one window the percentage never goes down, so the highest holds; a new
    reset starts a new window at its own reading."""
    now = datetime(2026, 11, 1, 14, 48, 0)
    path = tmp_path / ".usage" / "limits.jsonl"
    _write(path, [_cc(f"2026-11-01T14:40:{s:02d}", m, v, 60.0, session=f"s{s}")
                  for s, v, m in ((0, 38.0, "claude-opus-5-5"), (10, 39.0, "claude-fable-5-1"),
                                  (20, 26.0, "claude-opus-5-5"), (30, 40.0, "claude-fable-5-1"),
                                  (40, 39.0, "claude-opus-5-5"))])
    cc = usagelib.limits(tmp_path, now)["claude-code"]
    assert len(cc["series"]) == 1
    assert cc["five_hour"]["used"] == 40.0 and cc["read_at"] == "2026-11-01T14:40:30"
    assert (cc["series"][0]["session"], cc["series"][0]["model"]) == ("s30", "claude-fable-5-1")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_cc("2026-11-01T14:45:00", "claude-opus-5-5", 2.0, 60.0,
                                five_resets="2026-11-01T19:45:00")) + "\n")
    cc = usagelib.limits(tmp_path, now)["claude-code"]
    assert cc["five_hour"]["used"] == 2.0 and cc["five_hour"]["resets_at"] == "2026-11-01T19:45:00"
    assert cc["read_at"] == "2026-11-01T14:45:00"
    # A stale reading of the window before, sent again later: the new window holds.
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_cc("2026-11-01T14:46:00", "claude-opus-5-5", 40.0, 60.0)) + "\n")
    assert usagelib.limits(tmp_path, now)["claude-code"]["five_hour"]["used"] == 2.0


def test_a_turn_takes_what_its_account_held(tmp_path: Path) -> None:
    t = T0.strftime("%Y-%m-%dT%H:%M:%S")
    _chat(tmp_path, [_rec(1, T0, "a", new=500, cache=1_000, output=100, model="claude-opus-5-5")])
    resets = {"five_resets": "2026-10-01T16:40:00", "week_resets": "2026-10-05T09:00:00"}
    _write(tmp_path / ".usage" / "limits.jsonl", [
        _cc(t, "claude-opus-5-5", 38.0, 63.0, **resets),
        _cc((T0 + timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%S"), "claude-fable-5-1", 39.0, 63.0, **resets),
        # An idle session's older reading again, later.
        _cc((T0 + timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%S"), "claude-opus-5-5", 26.0, 62.0, **resets),
    ])
    turns = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)
    assert turns[1]["limit"] == {"five_hour": 39.0, "seven_day": 63.0}


def test_the_block_names_each_account_only_when_there_are_several(tmp_path: Path) -> None:
    now = datetime(2026, 11, 1, 14, 48, 0)
    _chat(tmp_path, [_rec(1, now - timedelta(minutes=5), "a", new=500, cache=1_000, output=100)])
    path = tmp_path / ".usage" / "limits.jsonl"
    _write(path, [
        _cc("2026-11-01T14:40:00", "claude-fable-5-1", 4.0, 60.0, five_resets="2026-11-01T18:00:00",
            week_resets="2026-11-06T09:00:00"),
        _cc("2026-11-01T14:41:00", "claude-opus-5-5", 30.0, 63.0, account="bbbbbbbbbbbb"),
    ])
    block = usagelib.usage_block(tmp_path, "ALPHA", AGENT, "http://x", now=now)
    part = block[block.index("Plan limits"):block.index("\n  Codex")]
    assert part.splitlines() == [
        "Plan limits",
        "  Claude Code · account bbbbbbbb",
        "               5-hour  30%  resets 16:40, in 1 h 52 min   (read 14:41)",
        "               weekly  63%  resets Thu 09:00",
        "  Claude Code · account aaaaaaaa",
        "               5-hour   4%  resets 18:00",
        "               weekly  60%  resets Fri 09:00              (read 14:40)",
    ]
    # One account, two models: the tool's name alone.
    _write(path, [
        _cc("2026-11-01T14:40:00", "claude-fable-5-1", 30.0, 63.0),
        _cc("2026-11-01T14:41:00", "claude-opus-5-5", 30.0, 63.0),
    ])
    block = usagelib.usage_block(tmp_path, "ALPHA", AGENT, "http://x", now=now)
    part = block[block.index("Plan limits"):block.index("\n  Codex")]
    assert part.splitlines() == [
        "Plan limits",
        "  Claude Code  5-hour  30%  resets 16:40, in 1 h 52 min   (read 14:41)",
        "               weekly  63%  resets Thu 09:00",
    ]


# ---------------------------------------------------------------------------
# The #usage block
# ---------------------------------------------------------------------------


def test_the_usage_block_has_the_d1_layout(tmp_path: Path) -> None:
    now = datetime(2026, 11, 1, 14, 48, 0)
    day = datetime(2026, 11, 1, 14, 0, 0)
    _chat(tmp_path, [
        _rec(1, day, "a", new=1_000_000, cache=30_000_000, output=50_000),
        _rec(2, day + timedelta(minutes=1), "b", new=100_000, cache=31_000_000, output=46_000),
        _rec(2, day + timedelta(minutes=1), "h", new=200_000, output=100_000, helper="agent-x"),
        # Yesterday and before: the usual day.
        _rec(0, day - timedelta(days=1), "y1", new=500_000, output=500_000),
        _rec(0, day - timedelta(days=2), "y2", new=300_000, output=400_000),
        _rec(0, day - timedelta(days=3), "y3", new=1_000_000, output=1_000_000),
    ])
    (tmp_path / ".usage" / "sessions").mkdir(parents=True)
    (tmp_path / ".usage" / "sessions" / "claude-code-sess-1.json").write_text(json.dumps({
        "context": {"used_pct": 61, "size": 200_000},
        "prompt_cache": {"warm": True, "expires_at": "2026-11-01T14:51:00"}}), encoding="utf-8")
    _write(tmp_path / ".usage" / "limits.jsonl", [
        {"at": "2026-11-01T14:02:11", "tool": "claude-code",
         "five_hour": {"used": 62.0, "resets_at": "2026-11-01T16:40:00"},
         "seven_day": {"used": 31.0, "resets_at": "2026-11-05T09:00:00"}},
        {"at": "2026-11-01T13:48:00", "tool": "codex",
         "five_hour": {"used": 9.0, "resets_at": "2026-11-01T18:10:00"},
         "seven_day": {"used": 81.0, "resets_at": "2026-11-03T06:00:00"}},
    ])
    text = usagelib.usage_block(tmp_path, "ALPHA", AGENT, "http://127.0.0.1:8123/", now=now)
    assert text.splitlines() == [
        "This chat · 3 turns · claude-opus-4-5",
        "  new 2.9M · output 2M · cache 61M · share 95% · helpers 300k",
        "  context 61% of 200k · cache warm, 3 min left · no rebuilds",
        "Plan limits",
        "  Claude Code  5-hour  62%  resets 16:40, in 1 h 52 min   (read 14:02)",
        "               weekly  31%  resets Thu 09:00",
        "  Codex        5-hour   9%  resets 18:10",
        "               weekly  81%  resets Tue 06:00              (read 13:48)",
        "ALPHA today · 1.2× your usual day",
        "  new + output 1.2M · cache 61M · share 98% · 1 chat",
        "  Usage page: http://127.0.0.1:8123/usage",
    ]


def test_the_usage_block_says_what_is_missing(tmp_path: Path) -> None:
    (tmp_path / "projects" / "ALPHA" / "chats" / AGENT).mkdir(parents=True)
    text = usagelib.usage_block(tmp_path, "ALPHA", AGENT, "http://127.0.0.1:8123", now=T0)
    assert text.splitlines()[:3] == ["This chat · no usage recorded yet", "  context — · cache — · no rebuilds",
                                     "Plan limits"]
    assert "  Claude Code  no limits recorded" in text and "  Codex        no limits recorded" in text
    assert "ALPHA today\n  new + output 0 · cache 0 · share — · 0 chats" in text


def test_the_hook_can_load_usagelib_by_path(tmp_path: Path) -> None:
    """The capture hook loads the file by path, outside the package
    (capture._backend_module): nothing at its top may need the backend."""
    path = Path(usagelib.__file__)
    spec = importlib.util.spec_from_file_location("sp_usagelib_alone", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _chat(tmp_path, [_rec(3, T0, "a", new=1_874, cache=108_233, output=512)])
    assert mod.chat_turns(tmp_path, "ALPHA", AGENT)[3]["line"] == "→ 1.9k ↑ 512 ↓ (108k)"
    assert mod.usage_block(tmp_path, "ALPHA", AGENT, "http://x", now=T0).startswith("This chat · 1 turn")


def test_showing_follows_the_chat_then_the_setting(tmp_path: Path) -> None:
    folder = _chat(tmp_path, [])
    assert usagelib.show_usage(tmp_path, folder) is False
    (tmp_path / "settings.json").write_text(json.dumps({"agent": {"usage_show": True}}), encoding="utf-8")
    assert usagelib.show_usage(tmp_path, folder) is True
    (folder / "meta.json").write_text(json.dumps({"usage_show": False}), encoding="utf-8")
    assert usagelib.show_usage(tmp_path, folder) is False
    spec = {s.key: s for s in app_settings.SPECS}["agent.usage_show"]
    assert (spec.type, spec.default, spec.group, spec.label) == ("bool", False, "Agent signals",
                                                                 "Show usage after each reply")


# ---------------------------------------------------------------------------
# The page and the routes
# ---------------------------------------------------------------------------


def _today_chat(data_root: Path) -> datetime:
    """A chat in ALPHA with four turns today and usage on each, a #done
    stretch over turns 1–2 for tk_alpha_auth, and days before for the usual day."""
    now = datetime.now()
    base = max(now - timedelta(hours=1), now.replace(hour=0, minute=0, second=1, microsecond=0))
    at = [base + timedelta(minutes=i) for i in range(4)]
    make_chat(data_root, "ALPHA", AGENT, [
        (a.strftime("%Y-%m-%dT%H:%M:%S"), u, "ok") for a, u in zip(at, [
            "work on tk_alpha_auth", "go on", "#done", "something else"])])
    folder = data_root / "projects" / "ALPHA" / "chats" / AGENT
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    meta.update({"tool": "claude-code", "session_ref": "sess-1", "chat_title": "Usage design"})
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    _write(folder / "usage.jsonl", [
        _rec(1, at[0], "a", new=1_000, cache=10_000, output=100),
        _rec(1, at[0], "h", new=5_000, cache=0, output=500, helper="agent-a", model="claude-haiku-4-5"),
        _rec(2, at[1], "b", new=2_000, cache=20_000, output=200),
        _rec(3, at[2], "c", new=100, cache=21_000, output=10),
        _rec(4, at[3], "d", new=3_000, cache=22_000, output=300, model="claude-sonnet-4-5"),
        _rec(0, base - timedelta(days=1), "y1", new=1_000, output=1_000),
        _rec(0, base - timedelta(days=2), "y2", new=2_000, output=2_000),
        _rec(0, base - timedelta(days=9), "y3", new=4_000, output=4_000),
    ])
    (data_root / "done.csv").write_text(
        "id,task_id,project,agent_id,session_id,turn,start_turn,at,applied_at,result,from_status,excerpt\n"
        f"dn_1,tk_alpha_auth,ALPHA,{AGENT},,3,1,{at[2].isoformat()},{at[2].isoformat()},moved,doing,#done\n",
        encoding="utf-8")
    _write(data_root / ".usage" / "limits.jsonl", [
        {"at": now.strftime("%Y-%m-%dT%H:%M:%S"), "tool": "claude-code",
         "five_hour": {"used": 62.0, "resets_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")}}])
    return now


def test_the_summary_counts_the_range(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    client.app.state.store.rebuild()  # type: ignore[attr-defined]
    got = client.get("/api/usage?project=ALPHA&range=today").json()
    tot = got["totals"]
    # new_output is the main agent's, everywhere; the helpers apart.
    assert (tot["new"], tot["output"], tot["cache"], tot["turns"], tot["chats"]) == (6_100, 610, 73_000, 4, 1)
    assert tot["new_output"] == 6_710 and tot["helpers"] == {"n": 1, "new_output": 5_500, "cache": 0}
    assert got["usual"] == {"new_output": 4_000, "cache": 0, "share": 0.0, "days_used": 3}
    assert len(got["days"]) == 1
    [tool] = got["by_tool"]
    assert tool["tool"] == "claude-code" and tool["turns"] == 4 and tool["new_output"] == 6_710
    assert tool["helpers"] == {"n": 1, "new_output": 5_500, "cache": 0}
    assert [m["model"] for m in tool["models"]] == ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"]
    [chat] = got["chats"]
    assert chat["agent_id"] == AGENT and chat["title"] == "Usage design" and chat["new_output"] == 6_710
    assert chat["helpers"] == {"n": 1, "new_output": 5_500, "cache": 0} and chat["helpers_n"] == 1
    assert chat["task_id"] == "tk_alpha_auth" and chat["model"] == "claude-sonnet-4-5"
    assert chat["models"] == ["claude-haiku-4-5", "claude-opus-4-5", "claude-sonnet-4-5"]
    assert chat["tools"] == ["claude-code"] and got["chats_total"] == 1
    [task] = got["tasks"]
    # Turns 1–3 are the task's stretch (the #done closes it at its own turn).
    assert task["id"] == "tk_alpha_auth" and task["new_output"] == 1_100 + 2_200 + 110
    assert task["helpers"] == {"n": 1, "new_output": 5_500, "cache": 0}
    assert task["chats"] == 1 and task["turns"] == 3 and task["done_at"] and got["tasks_total"] == 1
    assert task["models"] == ["claude-haiku-4-5", "claude-opus-4-5"] and task["tools"] == ["claude-code"]
    assert got["coverage"] == {"chats_recorded": 1, "chats_without_usage": 0, "chats_from_log": 0, "unreadable": []}
    assert got["limits"]["claude-code"]["five_hour"]["used"] == 62.0
    # The sums agree: the chats add up to the totals, the tasks never pass the chat.
    assert sum(c["new_output"] for c in got["chats"]) == tot["new_output"]
    assert sum(c["helpers"]["new_output"] for c in got["chats"]) == tot["helpers"]["new_output"]
    assert sum(t["new_output"] for t in got["tasks"]) <= chat["new_output"]

    week = client.get("/api/usage?project=all&range=30d").json()
    assert len(week["days"]) == 30 and week["totals"]["turns"] == 5  # turn 0 holds three days
    assert week["totals"]["new_output"] == 6_710 + 14_000


def test_the_summary_answers_304_and_refuses_an_unknown_project(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    r = client.get("/api/usage?project=ALPHA&range=7d")
    assert r.status_code == 200 and r.headers.get("ETag")
    again = client.get("/api/usage?project=ALPHA&range=7d", headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304
    assert client.get("/api/usage?project=NOPE").status_code == 404
    assert client.get("/api/usage?range=year").status_code == 422
    empty = client.get("/api/usage?project=BETA").json()
    assert empty["totals"]["turns"] == 0 and empty["chats"] == [] and empty["by_tool"] == []
    lim = client.get("/api/usage/limits")
    assert lim.status_code == 200 and "claude-code" in lim.json()["limits"]
    assert client.get("/api/usage/limits", headers={"If-None-Match": lim.headers["ETag"]}).status_code == 304


def test_a_chats_turns_carry_their_usage(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    client.app.state.store.rebuild()  # type: ignore[attr-defined]
    got = client.get(f"/api/usage/chat/{AGENT}").json()
    assert got["project"] == "ALPHA" and got["show"] is False and "block" not in got
    assert got["turns"]["1"]["line"] == "→ 1k ↑ 100 ↓ (10k) + helpers 5.5k"
    block = client.get(f"/api/usage/chat/{AGENT}?block=true").json()["block"]
    assert block.startswith("This chat · 5 turns · claude-sonnet-4-5")
    assert block.endswith("Usage page: http://127.0.0.1:8123/usage")
    assert client.get("/api/usage/chat/cc-nobody").status_code == 404

    sessions = client.get(f"/api/sessions?agent_id={AGENT}").json()["sessions"]
    assert sessions
    ids = ",".join(s["id"] for s in sessions)
    turns = [t for ts in client.get(f"/api/sessions/turns?ids={ids}").json()["turns"].values() for t in ts]
    by_n = {t["n"]: t for t in turns}
    assert by_n[2]["usage"]["new"] == 2_000 and by_n[4]["usage"]["model"] == "claude-sonnet-4-5"
    detail = client.get(f"/api/sessions/{sessions[0]['id']}").json()
    assert any("usage" in t for t in detail["turns"])


def test_a_new_usage_line_moves_the_store_but_derives_no_session(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    store = client.app.state.store  # type: ignore[attr-defined]
    store.rebuild()
    before = store.view_mtime
    chats_before = store._chats_signature(store._projects)
    path = data_root / "projects" / "ALPHA" / "chats" / AGENT / "usage.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec(5, datetime.now(), "z", new=1, output=1)) + "\n")
    import os
    os.utime(path, (before + 5, before + 5))
    store.rebuild()
    assert store.view_mtime > before
    # No session is derived from usage.jsonl: an append re-parses no chat log.
    assert store._chats_signature(store._projects) == chats_before
    assert not any(f.endswith("usage.jsonl") for f, *_ in chats_before[0])


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


class _Api(mcp.Api):
    def __init__(self, client: TestClient) -> None:
        super().__init__("http://testserver")
        self.client = client
        self.methods: list[str] = []

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        self.methods.append(method)
        r = self.client.request(method, path, json=body, headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        if r.status_code >= 400:
            raise mcp.ApiError(f"{r.status_code}: {r.text}")
        return r.json()


def test_the_mcp_tool_reads_the_block_and_the_summary(client: TestClient, data_root: Path, monkeypatch) -> None:
    _today_chat(data_root)
    client.app.state.store.rebuild()  # type: ignore[attr-defined]
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {"project": "ALPHA", "agent_id": AGENT})
    api = _Api(client)
    tr = mcp.Translator(api, cwd=str(data_root))
    got = tr.call("usage", {"range": "7d"})
    assert got["block"].startswith("This chat · 5 turns") and got["summary"]["range"] == "7d"
    assert got["summary"]["project"] == "ALPHA" and set(api.methods) == {"GET"}
    with pytest.raises(mcp.ApiError):
        tr.call("usage", {"range": "year"})
    from backend.server import _WRITE_TOOLS
    assert "usage" in mcp.TOOLS and "usage" not in _WRITE_TOOLS
    assert any(t["name"] == "usage" for t in tr.tool_defs())


# ---------------------------------------------------------------------------
# Round 2: rebuilds, the usual day, limits, robustness, tags
# ---------------------------------------------------------------------------


def test_a_rebuild_is_measured_on_what_the_turn_before_left_cached(tmp_path: Path) -> None:
    _chat(tmp_path, [
        # The turn before read nothing and wrote 25k: that is what it left cached.
        _rec(1, T0, "a", new=25_500, cache_write=25_000, cache=0, output=100),
        _rec(2, T0 + timedelta(minutes=6), "b", new=25_400, cache_write=25_000, cache=0, output=100),
    ])
    rb = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)[2]["rebuild"]
    # A 5-minute cache and a gap of 6 minutes: expired, the gap rounded up.
    assert rb == {"cause": "cache expired: 6 min since the last turn", "kind": "expired"}


def test_the_cache_lifetime_is_the_last_one_the_chat_asked_for(tmp_path: Path) -> None:
    _chat(tmp_path, [
        _rec(1, T0, "a", new=30_000, cache_write=30_000, cache=0, output=100, ttl="1h"),
        # A turn that only read the cache asks for no lifetime: the hour holds.
        _rec(2, T0 + timedelta(minutes=1), "b", new=10, cache=30_000, output=10, ttl=""),
        _rec(3, T0 + timedelta(minutes=21), "c", new=30_000, cache_write=30_000, cache=0, output=10, ttl=""),
    ])
    rb = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)[3]["rebuild"]
    assert rb == {"cause": "cause not recorded", "kind": "unknown"}


def test_a_compaction_names_the_rebuild(tmp_path: Path) -> None:
    _chat(tmp_path, [
        _rec(1, T0, "a", new=500, cache=100_000, output=100),
        _rec(2, T0 + timedelta(minutes=1), "b", new=20_000, cache=0, output=100, compacted=True),
    ])
    t = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)[2]
    assert t["rebuild"] == {"cause": "context compacted", "kind": "compacted"} and t["compacted"] is True
    assert t["line"].endswith("· context compacted")


def test_the_order_of_the_lines_does_not_change_a_turn(tmp_path: Path) -> None:
    lines = [
        _rec(1, T0, "a", new=500, cache=100_000, output=100, limit={"five_hour": 60.0}),
        _rec(2, T0 + timedelta(minutes=12), "b1", new=101_000, cache=0, output=300, limit={"five_hour": 70.0}),
        _rec(2, T0 + timedelta(minutes=13), "b2", new=10, cache=101_000, output=30, model="claude-sonnet-4-5"),
        # A helper's line, written later with an earlier time and an older limit.
        _rec(2, T0 + timedelta(minutes=11, seconds=50), "h", new=5, output=5, helper="agent-x",
             limit={"five_hour": 20.0}),
    ]
    _chat(tmp_path, lines)
    first = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)
    _chat(tmp_path, list(reversed(lines)))
    second = usagelib.chat_turns(tmp_path, "ALPHA", AGENT)
    assert first == second
    t = first[2]
    assert t["limit"] == {"five_hour": 70.0} and t["model"] == "claude-sonnet-4-5"
    assert t["rebuild"]["kind"] == "expired" and t["context_tokens"] == 101_010


def test_claude_codes_miss_cause_may_be_an_object(tmp_path: Path) -> None:
    assert usagelib.miss_cause_text({"system_prompt_changed": True, "tools": 2, "model": False}) == \
        "system_prompt_changed, tools: 2"
    assert usagelib.miss_cause_text(["a", "b"]) == "a, b" and usagelib.miss_cause_text(None) == ""
    _chat(tmp_path, [
        _rec(1, T0, "a", new=500, cache=100_000, output=100),
        _rec(2, T0 + timedelta(minutes=12), "b", new=101_000, cache=0, output=300),
    ])
    path = tmp_path / ".usage" / "sessions" / "claude-code-sess-1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"prompt_cache": {"last_miss_cause": {"tools_changed": True},
                                                 "last_miss_at": (T0 + timedelta(minutes=12)).isoformat()}}))
    assert usagelib.chat_turns(tmp_path, "ALPHA", AGENT)[2]["rebuild"] == {"cause": "tools_changed", "kind": "tool"}


def test_an_expired_cache_is_never_called_warm(tmp_path: Path) -> None:
    ref = datetime(2026, 11, 1, 14, 5)
    assert usagelib._cache_text({"warm": True, "expires_at": "2026-11-01T14:00:00"}, ref) == "cache cold"
    assert usagelib._cache_text({"warm": False, "expires_at": "2026-11-01T14:08:30"}, ref) == "cache warm, 3 min left"
    assert usagelib._cache_text({"warm": True}, ref) == "cache warm"
    assert usagelib._cache_text({}, ref) == "cache —"


def _day_usage(root: Path, values: dict[datetime, tuple[int, int]]) -> None:
    _chat(root, [_rec(i + 1, at, f"d{i}", new=v[0], cache=v[1]) for i, (at, v) in enumerate(sorted(values.items()))])


def test_the_usual_day_is_the_median_of_recent_active_days(tmp_path: Path) -> None:
    today = date(2026, 11, 1)
    noon = datetime(2026, 11, 1, 12, 0)
    # 31 active days before today: only the 30 most recent count.
    vals = {noon - timedelta(days=d): (d * 100, 0) for d in range(1, 32)}
    vals[noon] = (10**9, 0)                                     # today: left out
    vals[noon - timedelta(days=95)] = (10**9, 0)                # over 90 days back: left out
    _day_usage(tmp_path, vals)
    cu = usagelib.chat_usage(tmp_path / "projects" / "ALPHA" / "chats" / AGENT / "usage.jsonl")
    got = usagelib.usual_day([cu], today)
    # Days 1–30 → 100 … 3000: an even count, the mean of 1500 and 1600.
    assert got["days_used"] == 30 and got["new_output"] == 1_550


def test_a_cache_only_day_is_active_and_the_x_needs_three_days(tmp_path: Path) -> None:
    noon = datetime(2026, 11, 1, 12, 0)
    _day_usage(tmp_path, {noon - timedelta(days=1): (0, 50_000), noon - timedelta(days=2): (3_000, 0),
                          noon: (6_000, 0)})
    cu = usagelib.chat_usage(tmp_path / "projects" / "ALPHA" / "chats" / AGENT / "usage.jsonl")
    got = usagelib.usual_day([cu], noon.date())
    assert got["days_used"] == 2 and got["new_output"] == 1_500 and got["cache"] == 25_000
    # Two days are not enough for "× your usual day".
    head = usagelib.usage_block(tmp_path, "ALPHA", AGENT, "http://x", now=noon).splitlines()[-3]
    assert head == "ALPHA today"


@pytest.mark.parametrize("stamp", [
    1_793_544_000,                       # epoch seconds
    "2026-11-01T14:40:00",               # naive: local
    "2026-11-01T14:40:00+00:00",         # zoned: converted
])
def test_limits_stamps_of_every_kind_are_read(tmp_path: Path, stamp: Any) -> None:
    _write(tmp_path / ".usage" / "limits.jsonl", [
        {"at": stamp, "tool": "claude-code", "five_hour": {"used": 10.0, "resets_at": stamp}}])
    got = usagelib.limits(tmp_path, usagelib._moment(stamp) + timedelta(minutes=16))
    assert got["claude-code"]["stale"] is True and got["claude-code"]["read_at"] == usagelib._iso(usagelib._moment(stamp))
    assert got["claude-code"]["five_hour"]["expired"] is True


def test_a_window_without_a_number_keeps_its_place(tmp_path: Path) -> None:
    _write(tmp_path / ".usage" / "limits.jsonl", [
        {"at": "2026-11-01T14:40:00", "tool": "codex",
         "five_hour": {"used": "NaN", "resets_at": "2026-11-01T16:00:00", "window_minutes": 300},
         "seven_day": {"used": 1e999, "resets_at": "2026-11-03T06:00:00", "window_minutes": 10080}}])
    (tmp_path / ".usage" / "limits.jsonl").write_text(
        (tmp_path / ".usage" / "limits.jsonl").read_text().replace("Infinity", "1e999"))
    got = usagelib.limits(tmp_path, datetime(2026, 11, 1, 14, 45))["codex"]
    assert got["five_hour"]["used"] is None and got["five_hour"]["span_s"] == 18_000
    assert got["seven_day"]["used"] is None and got["seven_day"]["span_s"] == 604_800
    json.dumps(got, allow_nan=False)  # nothing that is not a number


def test_the_limits_file_is_read_only_from_where_it_stopped(tmp_path: Path) -> None:
    path = tmp_path / ".usage" / "limits.jsonl"
    line = {"at": "2026-11-01T14:00:00", "tool": "claude-code", "five_hour": {"used": 1.0, "resets_at": ""}}
    _write(path, [line])
    reader = usagelib._limits_of(tmp_path)
    assert reader.offset == path.stat().st_size and len(reader.rows["claude-code"]) == 1
    # Half a line: kept for later.
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"at": "2026-11-01T14:05:00", "tool": "claude-code", "five_hour"')
    assert len(usagelib._limits_of(tmp_path).rows["claude-code"]) == 1
    with path.open("a", encoding="utf-8") as fh:
        fh.write(': {"used": 2.0}}\n')
        fh.write(json.dumps({**line, "at": "2026-11-01T13:00:00"}) + "\n")  # out of order
    rows = usagelib._limits_of(tmp_path).rows["claude-code"]
    assert [r["at"] for r in rows] == ["2026-11-01T13:00:00", "2026-11-01T14:00:00", "2026-11-01T14:05:00"]
    # Cut short: read again from the start.
    _write(path, [{**line, "five_hour": {"used": 9.0}}])
    assert [r["five_hour"]["used"] for r in usagelib._limits_of(tmp_path).rows["claude-code"]] == [9.0]


def test_a_line_without_a_time_is_counted_in_its_turn_and_said(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    path = data_root / "projects" / "ALPHA" / "chats" / AGENT / "usage.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**_rec(4, datetime.now(), "late", new=7, output=3), "at": "soon"}) + "\n")
        fh.write('{"turn": 4, "new": 1e999, "id": "huge", "at": "x"}\n')
    client.app.state.store.rebuild()  # type: ignore[attr-defined]
    got = client.get("/api/usage?project=ALPHA&range=today").json()
    assert "Claude Code: 2 lines in 1 chat without a time, on no day" in got["coverage"]["unreadable"]
    assert client.get(f"/api/usage/chat/{AGENT}").json()["turns"]["4"]["new"] == 3_000 + 7


@pytest.mark.skipif(not hasattr(__import__("os"), "geteuid") or __import__("os").geteuid() == 0,
                    reason="root reads every file")
def test_an_unreadable_usage_file_is_said_and_tried_again(client: TestClient, data_root: Path) -> None:
    import os
    _today_chat(data_root)
    store = client.app.state.store  # type: ignore[attr-defined]
    store.rebuild()
    path = data_root / "projects" / "ALPHA" / "chats" / AGENT / "usage.jsonl"
    os.chmod(path, 0)
    try:
        got = usagelib.summary(store, "ALPHA", "today")
        assert got["coverage"]["unreadable"] == ["Claude Code: the usage of 1 chat could not be read"]
        assert got["totals"]["turns"] == 0
    finally:
        os.chmod(path, 0o644)
    # The same file, not moved: read now, not remembered as empty.
    assert usagelib.summary(store, "ALPHA", "today")["totals"]["turns"] == 4


def test_coverage_counts_the_chats_active_in_the_range(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    now = datetime.now()
    at = max(now - timedelta(minutes=30), now.replace(hour=0, minute=0, second=2, microsecond=0))
    # Made long ago, a turn today, nothing recorded.
    make_chat(data_root, "ALPHA", "cc-quiet", [("2026-01-05T10:00:00", "old", "ok"),
                                               (at.strftime("%Y-%m-%dT%H:%M:%S"), "today", "ok")])
    client.app.state.store.rebuild()  # type: ignore[attr-defined]
    got = client.get("/api/usage?project=ALPHA&range=today").json()
    assert got["coverage"]["chats_recorded"] == 1 and got["coverage"]["chats_without_usage"] == 1


def test_a_ledger_turn_written_as_a_decimal_is_read(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    done = data_root / "done.csv"
    done.write_text(done.read_text(encoding="utf-8").replace(",3,1,", ",3.0,,"), encoding="utf-8")
    client.app.state.store.rebuild()  # type: ignore[attr-defined]
    r = client.get("/api/usage?project=ALPHA&range=today")
    assert r.status_code == 200
    # No start in the ledger: the stretch starts after the chat's previous #done (none: turn 1).
    assert r.json()["tasks"][0]["turns"] == 3


def test_a_turn_counts_in_one_task(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    # The operator names another task at turn 2, inside tk_alpha_auth's #done stretch.
    chat = data_root / "projects" / "ALPHA" / "chats" / AGENT / "chat.md"
    chat.write_text(chat.read_text(encoding="utf-8").replace("go on", "go on, and tk_alpha_cyr too"),
                    encoding="utf-8")
    client.app.state.store.rebuild()  # type: ignore[attr-defined]
    got = client.get("/api/usage?project=ALPHA&range=today").json()
    turns = sum(t["turns"] for t in got["tasks"])
    assert turns <= got["chats"][0]["turns"]
    assert sum(t["new_output"] for t in got["tasks"]) <= got["chats"][0]["new_output"]


def test_a_chat_with_no_path_is_not_found(client: TestClient, data_root: Path, monkeypatch) -> None:
    store = client.app.state.store  # type: ignore[attr-defined]
    rows = store.agents() + [{"agent_id": "cc-nopath", "project": "ALPHA", "_chat_path": ""}]
    monkeypatch.setattr(store, "agents", lambda: rows)
    assert client.get("/api/usage/chat/cc-nopath").status_code == 404
    assert usagelib.chat_folder({"_chat_path": ""}) is None and usagelib.chat_folder({"_chat_path": "chat.md"}) is None


def test_the_tags_follow_the_files_beside_the_store(client: TestClient, data_root: Path) -> None:
    _today_chat(data_root)
    client.app.state.store.rebuild()  # type: ignore[attr-defined]
    r = client.get(f"/api/usage/chat/{AGENT}")
    tag = r.headers["ETag"]
    state = data_root / ".usage" / "sessions" / "claude-code-sess-1.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"context": {"used_pct": 10}}), encoding="utf-8")
    assert client.get(f"/api/usage/chat/{AGENT}", headers={"If-None-Match": tag}).status_code == 200
    tag = client.get(f"/api/usage/chat/{AGENT}").headers["ETag"]
    (data_root / "settings.json").write_text(json.dumps({"agent": {"usage_show": True}}), encoding="utf-8")
    again = client.get(f"/api/usage/chat/{AGENT}", headers={"If-None-Match": tag})
    assert again.status_code == 200 and again.json()["show"] is True

    sessions = client.get(f"/api/sessions?agent_id={AGENT}").json()["sessions"]
    sid = sessions[0]["id"]
    ids = ",".join(s["id"] for s in sessions)
    one = client.get(f"/api/sessions/{sid}")
    many = client.get(f"/api/sessions/turns?ids={ids}")
    assert many.headers.get("ETag")
    assert client.get(f"/api/sessions/turns?ids={ids}",
                      headers={"If-None-Match": many.headers["ETag"]}).status_code == 304
    # A new limits reading changes the turns' limits: the tags move without the store.
    limits = data_root / ".usage" / "limits.jsonl"
    with limits.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "tool": "claude-code",
                             "five_hour": {"used": 63.0}}) + "\n")
    assert client.get(f"/api/sessions/{sid}", headers={"If-None-Match": one.headers["ETag"]}).status_code == 200
    assert client.get(f"/api/sessions/turns?ids={ids}",
                      headers={"If-None-Match": many.headers["ETag"]}).status_code == 200


def test_sp_now_fixes_the_clock(monkeypatch) -> None:
    monkeypatch.setenv("SP_NOW", "2026-11-01T14:48:00")
    assert usagelib.now() == datetime(2026, 11, 1, 14, 48)
    assert usagelib.range_days("7d")[-1] == "2611-01"
    monkeypatch.setenv("SP_NOW", "not a moment")
    assert abs((usagelib.now() - datetime.now()).total_seconds()) < 5


def test_the_caches_let_go_of_files_that_are_gone(tmp_path: Path, monkeypatch) -> None:
    folder = _chat(tmp_path, [_rec(1, T0, "a", new=1)])
    key = str(folder / "usage.jsonl")
    usagelib.turns_in(folder, tmp_path)
    assert key in usagelib._usage and key in usagelib._derived
    (folder / "usage.jsonl").unlink()
    # The last sweep a minute ago, by the same clock: 0.0 is not that on a machine
    # that booted less than a minute ago (monotonic time counts from the boot).
    monkeypatch.setattr(usagelib, "_swept", [time.monotonic() - usagelib.SWEEP_S - 1])
    usagelib._sweep()
    assert key not in usagelib._usage and key not in usagelib._derived


def test_the_mcp_tool_answers_without_a_captured_chat(client: TestClient, data_root: Path, monkeypatch) -> None:
    def nobody(self: Any) -> dict:
        raise mcp.ApiError("404: no captured session")
    monkeypatch.setattr(mcp.Translator, "identity", nobody)
    got = mcp.Translator(_Api(client), cwd=str(data_root)).call("usage", {"project": "ALPHA"})
    assert got["block"] == "" and got["summary"]["project"] == "ALPHA"


def test_a_long_chat_beside_a_long_limits_history_reads_fast(tmp_path: Path) -> None:
    import time as _time
    lines = []
    for n in range(1, 501):
        at = T0 + timedelta(minutes=2 * n)
        lines.append(_rec(n, at, f"m{n}a", new=900, cache=60_000 + n, output=200))
        lines.append(_rec(n, at + timedelta(seconds=20), f"m{n}b", new=100, cache=60_900 + n, output=300))
    folder = _chat(tmp_path, lines)
    _write(tmp_path / ".usage" / "limits.jsonl", [
        {"at": (T0 + timedelta(seconds=6 * i)).strftime("%Y-%m-%dT%H:%M:%S"), "tool": "claude-code",
         "five_hour": {"used": i / 200, "resets_at": "2026-10-03T00:00:00"}} for i in range(10_000)])
    usagelib.turns_in(folder, tmp_path)          # the files read once
    import gc
    took = 1.0
    gc.disable()
    try:
        for _ in range(5):                       # the best of five: a busy machine is not the code
            usagelib._derived.clear()
            t = _time.perf_counter()
            got = usagelib.turns_in(folder, tmp_path)
            took = min(took, _time.perf_counter() - t)
    finally:
        gc.enable()
    assert len(got) == 500 and got[500]["limit"] is not None
    assert took < 0.02, f"{took * 1000:.1f} ms"


def test_a_limits_file_rewritten_in_place_is_read_again(tmp_path: Path) -> None:
    path = tmp_path / ".usage" / "limits.jsonl"
    old = {"at": "2026-11-01T14:00:00", "tool": "claude-code", "five_hour": {"used": 1.0}}
    _write(path, [old])
    assert usagelib._limits_of(tmp_path).rows["claude-code"][0]["five_hour"]["used"] == 1.0
    version = usagelib._limits_of(tmp_path).version
    # The same file written again, longer: no reading of the old one is kept.
    with path.open("r+", encoding="utf-8") as fh:
        fh.write("".join(json.dumps({**old, "five_hour": {"used": 50.0 + i}}) + "\n" for i in range(3)))
    import os
    later = path.stat().st_mtime_ns + 10**9
    os.utime(path, ns=(later, later))
    rows = usagelib._limits_of(tmp_path).rows["claude-code"]
    assert [r["five_hour"]["used"] for r in rows] == [50.0, 51.0, 52.0]
    # Emptied: the turns that took their limits from it are worked out again.
    path.write_text("", encoding="utf-8")
    assert usagelib._limits_of(tmp_path).rows == {} and usagelib._limits_of(tmp_path).version > version


def test_an_absurd_stamp_is_no_moment() -> None:
    assert usagelib._moment(10**400) is None and usagelib._moment(float("nan")) is None
    assert usagelib._moment(True) is None
    raw = json.dumps({"turn": 1, "at": 10**400, "id": "x", "new": 5}).encode()
    assert usagelib._parse_usage(raw)["no_time"] == 1


def test_the_limits_tag_moves_when_a_window_resets_inside_a_minute(client: TestClient, data_root: Path,
                                                                     monkeypatch) -> None:
    _write(data_root / ".usage" / "limits.jsonl", [
        {"at": "2026-11-01T11:00:00", "tool": "codex", "five_hour": {"used": 9.0, "resets_at": "2026-11-01T12:00:30"}}])
    monkeypatch.setenv("SP_NOW", "2026-11-01T12:00:10")
    r = client.get("/api/usage/limits")
    assert r.json()["limits"]["codex"]["expired"] is False
    monkeypatch.setenv("SP_NOW", "2026-11-01T12:00:40")
    again = client.get("/api/usage/limits", headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 200 and again.json()["limits"]["codex"]["expired"] is True


def test_rebuilt_is_old_context_written_again_and_the_price_counts_each_kind(tmp_path: Path) -> None:
    now = datetime(2026, 11, 1, 14, 0, 0)
    f = tmp_path / "usage.jsonl"
    base = {"tool": "claude-code", "model": "claude-opus-5-5", "output": 0, "thinking": 0, "helper": ""}
    _write(f, [
        {**base, "turn": 1, "at": now.isoformat(), "id": "a", "new": 1_000_000, "cache_write": 1_000_000, "cache": 0, "ttl": "5m"},
        {**base, "turn": 2, "at": (now + timedelta(minutes=1)).isoformat(), "id": "b", "new": 100_000, "cache_write": 100_000, "cache": 1_000_000, "ttl": "5m"},
        # The cache expired: 1.1M left cached, none read, 1.2M written: 1.1M is old, 100k is new.
        {**base, "turn": 3, "at": (now + timedelta(hours=2)).isoformat(), "id": "c", "new": 1_200_000, "cache_write": 1_200_000, "cache": 0, "ttl": "1h", "output": 1_000_000},
        # A compaction: nothing here counts as rebuilt.
        {**base, "turn": 4, "at": (now + timedelta(hours=3)).isoformat(), "id": "d", "new": 50_000, "cache_write": 50_000, "cache": 0, "ttl": "5m", "compacted": True},
    ])
    turns = usagelib.chat_usage(f)["turns"]
    assert [turns[n]["main"]["rebuilt"] for n in (1, 2, 3, 4)] == [0, 0, 1_100_000, 0]
    assert turns[1]["main"]["cost_new"] == 5_000_000              # 1M at the 5-minute write price
    assert (turns[2]["main"]["cost_new"], turns[2]["main"]["cost_warm"]) == (500_000, 200_000)  # 100k written, 1M read
    m = turns[3]["main"]                                          # at the 1-hour write price, and 1M out
    assert (m["cost_new"], m["cost_rebuilt"], m["cost_output"]) == (800_000, 8_800_000, 20_000_000)


def test_a_model_with_no_price_counts_as_unpriced(tmp_path: Path) -> None:
    f = tmp_path / "usage.jsonl"
    _write(f, [{"turn": 1, "at": "2026-11-01T14:00:00", "id": "a", "tool": "codex", "model": "gpt-x",
                "new": 10, "cache_write": 0, "cache": 20, "output": 5, "thinking": 0, "helper": ""}])
    main = usagelib.chat_usage(f)["turns"][1]["main"]
    assert main["cost_new"] == 0 and main["unpriced"] == 35 and main["rebuilt"] == 0


def _msg(mid: str, at: str, model: str = "claude-opus-5-5", **kw: Any) -> dict[str, Any]:
    return {"turn": 1, "at": at, "id": mid, "tool": "claude-code", "model": model, "new": 0, "cache_write": 0,
            "cache": 0, "output": 0, "thinking": 0, "helper": "", "ttl": "5m", **kw}


def test_a_rebuild_is_named_by_what_happened(tmp_path: Path) -> None:
    f = tmp_path / "usage.jsonl"
    big = {"new": 100_000, "cache_write": 100_000}
    _write(f, [_msg("a", "2026-11-01T10:00:00", **big),
               _msg("b", "2026-11-01T11:00:00", **big),                            # an hour past a 5-minute cache
               _msg("c", "2026-11-01T11:01:00", model="claude-fable-5-1", **big),  # another model
               _msg("d", "2026-11-01T11:02:00", model="claude-fable-5-1", **big)])  # neither
    cu = usagelib.chat_usage(f)
    got = {}
    for b in cu["buckets"].values():
        got.update(b["causes"])
    assert sorted(got) == ["expired", "model", "other"]
    assert got["expired"]["events"] == 1 and got["expired"]["rebuilt"] == 100_000


def test_a_message_is_priced_as_of_its_own_day_and_a_new_book_counts_again(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / ".usage").mkdir(parents=True)
    f = tmp_path / "usage.jsonl"
    _write(f, [_msg("a", "2026-11-01T10:00:00", output=1_000_000), _msg("b", "2026-11-10T10:00:00", output=1_000_000)])
    usagelib.use_prices(root)
    assert sum(b["main"]["cost_output"] for b in usagelib.chat_usage(f)["buckets"].values()) == 40_000_000
    (root / ".usage" / usagelib.PRICES_FILE).write_text(json.dumps(
        {"at": "2026-11-05T12:00:00", "models": {"claude-opus-5-5": {"input": 8, "read": 1, "output": 100}}}) + "\n")
    usagelib.use_prices(root)
    costs = sorted(b["main"]["cost_output"] for b in usagelib.chat_usage(f)["buckets"].values())
    assert costs == [20_000_000, 100_000_000]
    usagelib.use_prices(tmp_path / "other")  # what the next test finds


def test_a_long_prompt_costs_the_price_over_its_threshold(tmp_path: Path) -> None:
    f = tmp_path / "usage.jsonl"
    usagelib.use_prices(tmp_path)
    _write(f, [_msg("a", "2026-11-01T10:00:00", model="claude-haiku-5-5", cache=200_000)])
    assert next(iter(usagelib.chat_usage(f)["buckets"].values()))["main"]["cost_warm"] == 10_000


def test_an_update_of_the_prices_says_what_changed_and_keeps_the_days_before(tmp_path: Path) -> None:
    (tmp_path / ".usage").mkdir()
    body = {"sources": ["https://example.com/pricing"], "models": {
        "claude-opus-5-5": {"input": 5, "write_5m": 5, "write_1h": 8, "read": 0.2, "output": 200},
        "new-model": {"input": 1, "read": 0.1, "output": 2}}}
    got = usagelib.write_prices(tmp_path, body, "cc-x", at=datetime(2026, 12, 1, 10, 0))
    assert got["new_models"] == ["new-model"]
    assert {(c["field"], c["old"], c["new"]) for c in got["changed"]} == {("input", 4.0, 5.0), ("output", 20.0, 200.0)}
    assert got["warnings"] == ["claude-opus-5-5.output moved from 20.0 to 200.0: check it on the page"]
    book = usagelib.use_prices(tmp_path)
    assert usagelib.price_of("claude-opus-5-5", "2026-11-30T23:00:00", book)["input"] == 4.0
    assert usagelib.price_of("claude-opus-5-5", "2026-12-01T00:10:00", book)["input"] == 5.0
    assert usagelib.price_of("new-model", "2026-01-01T00:00:00", book)["input"] == 1.0   # its first known, before that
    usagelib.use_prices(tmp_path / "other")


def test_a_price_for_long_prompts_counts_as_a_change(tmp_path: Path) -> None:
    (tmp_path / ".usage").mkdir()
    long = {"input": 4, "read": 0.2, "output": 15}
    got = usagelib.write_prices(tmp_path, {"sources": ["https://x"], "models": {
        "gpt-6.1-sol": {"input": 2, "read": 0.1, "output": 10, "over_tokens": 272000, "over": long}}}, "cc-x")
    assert {c["field"] for c in got["changed"]} == {"over_tokens", "over"} and got["unchanged"] == []
    usagelib.use_prices(tmp_path / "other")


@pytest.mark.parametrize("body, word", [
    ({"models": {"m": {"input": 1, "read": 1, "output": 1}}}, "sources"),
    ({"sources": ["http://x"], "models": {"m": {"input": 1, "read": 1, "output": 1}}}, "sources"),
    ({"sources": ["https://x"], "models": {}}, "models"),
    ({"sources": ["https://x"], "models": {"m": {"input": 1, "output": 1}}}, "read"),
    ({"sources": ["https://x"], "models": {"m": {"input": 0, "read": 1, "output": 1}}}, "input"),
    ({"sources": ["https://x"], "models": {"m": {"input": 1, "read": 1, "output": 1, "cost": 3}}}, "cost"),
    ({"sources": ["https://x"], "models": {"m": {"input": 1, "read": 1, "output": 1, "over_tokens": 5}}}, "over"),
])
def test_an_update_of_the_prices_that_cannot_be_right_is_refused(tmp_path: Path, body: dict[str, Any], word: str) -> None:
    with pytest.raises(usagelib.PricesRefused, match=word):
        usagelib.write_prices(tmp_path, body, "cc-x")
    assert not (tmp_path / ".usage" / usagelib.PRICES_FILE).exists()
