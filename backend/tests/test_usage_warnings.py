"""Usage warnings under a Claude Code reply (backend/usagewarn.py, shown by
the Stop hook) and the facts log (facts.jsonl). Every log here is made up."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import usagewarn

from .test_usage_hook import _asst, _hook_at, _transcript, _user

UTC = timezone.utc
HINT = usagewarn.OFF_HINT
MODEL = "claude-opus-5-5"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path / "data"


def _units(root: Path, models: dict | None = None, fallback: float | None = None) -> None:
    (root / ".usage").mkdir(parents=True, exist_ok=True)
    (root / ".usage" / "units.json").write_text(
        json.dumps({"models": {MODEL: 10.0} if models is None else models, "fallback": fallback}), encoding="utf-8")


def _meta(root: Path, agent: str = "cc-s1") -> dict:
    return json.loads((root / "projects/alpha/chats" / agent / "meta.json").read_text(encoding="utf-8"))


class Chat:
    """One Claude Code chat driven through the real hook with a fixed clock (UTC)."""

    def __init__(self, root: Path, tmp_path: Path, session: str = "s1") -> None:
        self.root, self.tmp, self.session = root, tmp_path, session
        self.n = 0

    def prompt(self, text: str, at: datetime):
        return _hook_at(self.root, {"hook_event_name": "UserPromptSubmit", "session_id": self.session,
                                    "prompt": text}, at.strftime("%Y-%m-%dT%H:%M:%S"))

    def turn(self, at: datetime, *, cr: int, cw: int = 100, out: int = 10, inp: int = 2, extra: list | None = None,
             content=None) -> str:
        """A prompt at ``at``, one API message two seconds later, the Stop: the systemMessage or ''."""
        self.n += 1
        self.prompt(f"go {self.n}", at)
        t = _transcript(self.tmp, [_user(f"go {self.n}", at.replace(tzinfo=UTC), self.session),
                                   *(extra or []),
                                   _asst(f"m{self.n}", (at + timedelta(seconds=2)).replace(tzinfo=UTC),
                                         cr=cr, cw=cw, out=out, inp=inp, model=MODEL, session=self.session,
                                         content=content)])
        p = _hook_at(self.root, {"hook_event_name": "Stop", "session_id": self.session, "transcript_path": str(t),
                                 "last_assistant_message": "ok"},
                     (at + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%S"))
        return json.loads(p.stdout)["systemMessage"] if p.stdout.strip() else ""


T0 = datetime(2026, 11, 1, 9, 0, 0)


def test_the_context_warning_comes_once_per_step_with_the_hint_on_the_first(root: Path, tmp_path: Path) -> None:
    _units(root)
    chat = Chat(root, tmp_path)
    assert chat.turn(T0, cr=100_000) == ""
    msg = chat.turn(T0 + timedelta(minutes=1), cr=310_000)
    # 310k read from the cache at $0.20/M, 100 written at $8/M, 2 new at $4/M, 10 out at $20/M: $0.0630 → 0.6%.
    assert msg == ("This chat has 310k tokens. Each reply now uses about 0.6% of the 5-hour limit.\n" + HINT)
    assert chat.turn(T0 + timedelta(minutes=2), cr=320_000) == ""         # 300k was told
    msg = chat.turn(T0 + timedelta(minutes=3), cr=900_000)
    assert msg == "This chat has 900k tokens. Each reply now uses about 2% of the 5-hour limit."   # no hint again
    assert chat.turn(T0 + timedelta(minutes=4), cr=920_000) == ""         # 500k and 800k both told by the jump
    state = _meta(root)["usage_warned"]
    assert state["context"] == [300_000, 500_000, 800_000] and state["hint"] is True
    facts = [json.loads(x) for x in (root / "projects/alpha/chats/cc-s1/facts.jsonl").read_text().splitlines()]
    assert [f["warnings"] for f in facts] == [[], ["context"], [], ["context"], []]


def test_the_hook_counts_with_the_newer_price_book(root: Path, tmp_path: Path) -> None:
    _units(root)
    # Every price ten times the built-in one, from before the chat: $0.630 a reply, 6%.
    line = {"at": "2026-10-01T00:00:00", "by": "operator", "sources": ["https://example.com/prices"],
            "models": {MODEL: {"input": 40.0, "write_5m": 50.0, "write_1h": 80.0, "read": 2.0, "output": 200.0}}}
    (root / ".usage" / "api-prices.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    assert Chat(root, tmp_path).turn(T0, cr=310_000).startswith(
        "This chat has 310k tokens. Each reply now uses about 6% of the 5-hour limit.")


def test_each_reply_leaves_out_the_context_written_again(root: Path, tmp_path: Path) -> None:
    _units(root)
    chat = Chat(root, tmp_path)
    assert chat.turn(T0, cr=0, cw=250_000) == ""
    # 20 minutes later the 250k is written again with 60k more (a rebuild, no long break):
    # each reply is the 60k at $8/M and the output, $0.48, not the $2.48 with the rewrite.
    msg = chat.turn(T0 + timedelta(minutes=20), cr=0, cw=310_000)
    assert msg.startswith("This chat has 310k tokens. Each reply now uses about 5% of the 5-hour limit.")


COMPACT = "Claude Code will compact it at about {} tokens and keep only a summary."


def _status(root: Path, session: str, size: int) -> None:
    folder = root / ".usage" / "sessions"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"claude-code-{session}.json").write_text(json.dumps(
        {"at": "2026-11-01T09:00:00", "session_id": session, "model": MODEL, "context": {"size": size}}),
        encoding="utf-8")


def test_the_compaction_warning_comes_first_and_once_per_chat(root: Path, tmp_path: Path) -> None:
    _units(root)
    chat = Chat(root, tmp_path)
    assert chat.turn(T0, cr=310_000).startswith("This chat has 310k tokens. Each reply")
    # A 1M window (the chat passed 200k): compacted at about 930k. 800k is crossed too; the compaction is told.
    msg = chat.turn(T0 + timedelta(minutes=1), cr=935_000)
    assert msg == "This chat has 935k tokens. " + COMPACT.format("930k")
    assert chat.turn(T0 + timedelta(minutes=2), cr=960_000) == ""          # once per chat; 800k not told again
    state = _meta(root)["usage_warned"]
    assert state["compact"] is True and 800_000 in state["context"]
    facts = [json.loads(x) for x in (root / "projects/alpha/chats/cc-s1/facts.jsonl").read_text().splitlines()]
    assert [f["warnings"] for f in facts] == [["context"], ["compact"], []]


def test_the_window_size_comes_from_the_status_line(root: Path, tmp_path: Path) -> None:
    # No status line and never past 200k: a 200k window, compacted at about 130k.
    msg = Chat(root, tmp_path, "s1").turn(T0, cr=150_000)
    assert msg == "This chat has 150k tokens. " + COMPACT.format("130k") + "\n" + HINT
    # The status line says 1M: nothing at 150k.
    _status(root, "s2", 1_000_000)
    assert Chat(root, tmp_path, "s2").turn(T0, cr=150_000) == ""
    # It says 400k: compacted at about 330k.
    _status(root, "s3", 400_000)
    assert Chat(root, tmp_path, "s3").turn(T0, cr=340_000).startswith(
        "This chat has 340k tokens. " + COMPACT.format("330k"))


def test_without_units_the_warning_says_only_the_tokens(root: Path, tmp_path: Path) -> None:
    chat = Chat(root, tmp_path)
    assert chat.turn(T0, cr=310_000) == "This chat has 310k tokens.\n" + HINT


def test_a_model_without_a_unit_takes_the_fallback_and_without_one_has_no_percent(root: Path, tmp_path: Path) -> None:
    _units(root, models={"claude-other": 3.0}, fallback=10.0)
    assert Chat(root, tmp_path, "s1").turn(T0, cr=310_000).startswith(
        "This chat has 310k tokens. Each reply now uses about 0.6% of the 5-hour limit.")
    _units(root, models={"claude-other": 3.0}, fallback=None)
    assert Chat(root, tmp_path, "s2").turn(T0, cr=310_000) == "This chat has 310k tokens.\n" + HINT


def test_a_rebuild_after_a_long_break_is_told_with_the_break(root: Path, tmp_path: Path) -> None:
    _units(root)
    chat = Chat(root, tmp_path)
    assert chat.turn(T0, cr=100_000, cw=1_000) == ""
    # 2 h 20 min later the whole chat is written to the cache again.
    msg = chat.turn(T0 + timedelta(hours=2, minutes=20), cr=0, cw=101_000)
    assert msg == ("This reply read the whole chat again after a break of 2 hours 20 minutes. "
                   "It used about 8% of the 5-hour limit.\n" + HINT)
    assert chat.turn(T0 + timedelta(hours=2, minutes=21), cr=101_000, cw=100) == ""     # warm again


def test_a_rebuild_after_less_than_an_hour_is_not_told(root: Path, tmp_path: Path) -> None:
    _units(root)
    chat = Chat(root, tmp_path)
    chat.turn(T0, cr=100_000, cw=1_000)
    # Written again 30 minutes later: a rebuild, but no break of over an hour.
    assert chat.turn(T0 + timedelta(minutes=30), cr=0, cw=101_000) == ""


def _limits(root: Path, at: datetime, used: float, resets: datetime) -> None:
    (root / ".usage").mkdir(parents=True, exist_ok=True)
    line = {"at": at.strftime("%Y-%m-%dT%H:%M:%S"), "tool": "claude-code", "account": "acc1", "model": MODEL,
            "session": "s1", "five_hour": {"used": used, "resets_at": resets.strftime("%Y-%m-%dT%H:%M:%S")},
            "source": "statusline"}
    with open(root / ".usage" / "limits.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def test_the_window_warning_comes_once_per_window_after_the_context_one(root: Path, tmp_path: Path) -> None:
    _units(root, models={MODEL: 100.0})
    _limits(root, T0, 20.0, T0 + timedelta(hours=3))
    chat = Chat(root, tmp_path)
    # 310k context and 20k output: both apply; the context warning comes first.
    msg = chat.turn(T0 + timedelta(minutes=1), cr=310_000, out=20_000)
    assert msg.startswith("This chat has 310k tokens.") and msg.endswith(HINT)
    msg = chat.turn(T0 + timedelta(minutes=2), cr=200_000, out=1_000)
    assert msg.startswith("This chat has used ") and msg.endswith(" of the current 5-hour limit.")
    assert _meta(root)["usage_warned"]["window"] == (T0 + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
    assert chat.turn(T0 + timedelta(minutes=3), cr=200_000, out=1_000) == ""      # once per window
    # The next window: told again.
    later = T0 + timedelta(hours=4)
    _limits(root, later, 5.0, later + timedelta(hours=4))
    assert chat.turn(later + timedelta(minutes=1), cr=200_000, out=20_000).startswith("This chat has used ")


def test_the_line_comes_first_and_the_warning_on_its_own_line(root: Path, tmp_path: Path) -> None:
    (root / "settings.json").write_text(json.dumps({"agent": {"usage_show": True}}), encoding="utf-8")
    msg = Chat(root, tmp_path).turn(T0, cr=310_000)
    line, warning, hint = msg.split("\n")
    assert line.startswith("→ ") and warning == "This chat has 310k tokens." and hint == HINT


def test_the_off_command_and_the_setting_turn_them_off(root: Path, tmp_path: Path) -> None:
    chat = Chat(root, tmp_path)
    p = chat.prompt("#usage-warnings-off", T0)
    out = json.loads(p.stdout)
    assert out["decision"] == "block"
    assert out["reason"] == "[slightly-parallel] Usage warnings are off in this chat. Tokens are still recorded."
    assert _meta(root)["usage_warn"] is False
    assert chat.turn(T0 + timedelta(minutes=1), cr=310_000) == ""
    p = chat.prompt("#usage-warnings-on", T0 + timedelta(minutes=2))
    assert json.loads(p.stdout)["reason"] == "[slightly-parallel] Usage warnings are on in this chat."
    assert chat.turn(T0 + timedelta(minutes=3), cr=320_000).startswith("This chat has 320k tokens.")

    # The setting off: no warning in a chat that said nothing; the chat's own word wins.
    (root / "settings.json").write_text(json.dumps({"usage": {"warnings": False}}), encoding="utf-8")
    other = Chat(root, tmp_path, "s2")
    assert other.turn(T0, cr=310_000) == ""
    assert chat.turn(T0 + timedelta(minutes=4), cr=600_000).startswith("This chat has 600k tokens.")


def test_the_warning_commands_reach_the_agent_with_other_text(root: Path) -> None:
    p = _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s3",
                        "prompt": "#usage-warnings-off and fix the bug"}, "2026-11-01T09:00:00")
    assert "Usage warnings are off in this chat." in p.stdout
    assert _meta(root, "cc-s3")["usage_warn"] is False


def test_units_are_written_by_the_server_for_claude_models_only(root: Path) -> None:
    units = {"models": [{"model": MODEL, "pct_per_usd": 1.5}, {"model": "gpt-6.1-sol", "pct_per_usd": 2.0}],
             "fallback": 1.7, "days": 30}
    assert usagewarn.write_units(root, units) is True
    got = json.loads((root / ".usage/units.json").read_text(encoding="utf-8"))
    assert got["models"] == {MODEL: 1.5} and got["fallback"] == 1.7 and got["days"] == 30
    assert usagewarn.write_units(root, units) is False                 # unchanged: not written again
    assert usagewarn.read_units(root) == {"models": {MODEL: 1.5}, "fallback": 1.7}
    assert usagewarn.rate(usagewarn.read_units(root), "gpt-6.1-sol") is None
    assert usagewarn.read_units(root / "nowhere") is None


def test_a_failed_write_of_the_units_leaves_no_temp_file(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend import hookshared

    def refuse(src, dst):
        raise PermissionError("held open")
    monkeypatch.setattr(hookshared, "replace_file", refuse)
    assert usagewarn.write_units(root, {"models": [{"model": MODEL, "pct_per_usd": 1.5}], "fallback": 1.0}) is False
    assert list((root / ".usage").iterdir()) == []


def test_the_usage_page_writes_the_units(client) -> None:
    assert client.get("/api/usage?project=all&range=today").status_code == 200
    root = Path(client.app.state.store.data_root)
    got = json.loads((root / ".usage" / "units.json").read_text(encoding="utf-8"))
    assert set(got) >= {"at", "models", "fallback", "days"}


def test_the_break_and_percent_words() -> None:
    assert usagewarn.gap_words(2 * 3600 + 59) == "2 hours"
    assert usagewarn.gap_words(3600 + 20 * 60) == "1 hour 20 minutes"
    assert usagewarn.gap_words(3600 + 60) == "1 hour 1 minute"
    assert usagewarn.gap_words(27 * 3600) == "1 day 3 hours"
    from backend import usagelib
    assert usagewarn.pct_words(12.5, usagelib) == "12%" and usagewarn.pct_words(0.04, usagelib) == "0.1%"


def test_facts_count_what_the_stretch_added_by_kind(root: Path, tmp_path: Path) -> None:
    at = T0.replace(tzinfo=UTC)
    stamp = (at + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    call = {"type": "tool_use", "id": "toolu_r1", "name": "Read", "input": {"file_path": "/x"}}
    mcp = {"type": "tool_use", "id": "toolu_m1", "name": "mcp__slightly-parallel__tasks", "input": {}}
    extra = [
        {"type": "attachment", "timestamp": stamp, "attachment": {"type": "date"},
         "rendered": [{"content": "<system-reminder>\nhello\n</system-reminder>"}]},
        {"type": "attachment", "timestamp": stamp,
         "attachment": {"type": "hook_system_message", "content": "→ 1k", "hookEvent": "Stop"}},
        _asst("a1", at + timedelta(seconds=1), model=MODEL,
              content=[{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Reading."}, call, mcp]),
        {"type": "user", "timestamp": stamp, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_r1", "content": "0123456789"},
            {"type": "tool_result", "tool_use_id": "toolu_m1",
             "content": [{"type": "text", "text": "abc"}, {"type": "image", "source": {}}]}]}},
    ]
    Chat(root, tmp_path).turn(T0, cr=1_000, extra=extra)
    lines = (root / "projects/alpha/chats/cc-s1/facts.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    f = json.loads(lines[0])
    assert f["turn"] == 1 and f["warnings"] == [] and f["at"]
    assert f["appended"] == {
        "operator": len("go 1"),
        "notices": len("<system-reminder>\nhello\n</system-reminder>"),
        "thinking": 3, "agent_text": len("Reading.") + len("ok"),
        "agent_tool_calls": len(json.dumps({"file_path": "/x"})) + len("{}"),
        "result_Read": 10, "result_MCP": 3, "images": 1,
    }
    assert f["tools"] == {"Read": 1, "mcp__slightly-parallel__tasks": 1}


def _opencode(root: Path, text: str) -> str:
    import subprocess
    import sys
    cli = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture-cli.py"
    (root / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, str(cli), "--project", "alpha", "--data-root", str(root), "--agent",
                        "oc-abc12345", "--json-stdin", "--tool", "opencode", "--session", "ses_1",
                        "--cwd", str(root), "--phase", "open"], input=json.dumps({"text": text}),
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


@pytest.mark.parametrize("tool", ["codex", "opencode"])
def test_codex_and_opencode_answer_that_warnings_are_claude_codes(root: Path, tool: str) -> None:
    from .test_usage_hook import _hook
    name = "Codex" if tool == "codex" else "OpenCode"
    for cmd in ("#usage-warnings-off", "#usage-warnings-on"):
        if tool == "codex":
            p = _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "0199-thread-abcdef12",
                             "prompt": cmd}, tool=tool)
            assert p.returncode == 0, p.stderr
            out = p.stdout
        else:
            out = _opencode(root, cmd)
        assert ("Usage warnings are shown in Claude Code only. "
                f"{name} does not show them, so this command changes nothing in this chat.") in out
        assert "Usage warnings are on" not in out and "Usage warnings are off" not in out
