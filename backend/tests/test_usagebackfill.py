"""The usage backfill (usagebackfill.py) on made-up logs only: a fake home
with the golden Claude Code transcript and its helpers, the golden Codex
rollout, and chat folders as the hook leaves them. What the hook wrote stays
byte for byte; what is added is what the import writes, marked as from the
log; a second run adds nothing; a chat whose turns do not match is refused."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import server, sessionimport, usagebackfill, usagelib
from backend.db import ViewStore

_REPO = Path(__file__).resolve().parents[2]
_LOGS = _REPO / "testdata" / "usage" / "logs"
_EXPECTED = _REPO / "testdata" / "usage" / "expected"
_SID = "6a5e0d1c-7f3b-4c2a-9e1d-0123456789ab"
_SID2 = "7b6f1e2d-8a4c-4d3b-af2e-123456789abc"
_SID3 = "8c7a2f3e-9b5d-4e4c-b03f-23456789abcd"
_SID4 = "9d8b3a4f-ac6e-4f5d-8140-3456789abcde"
_THREAD = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001"
_ROLLOUT = f"rollout-2026-11-01T10-00-00-{_THREAD}.jsonl"
_CWD = "/sp-test/work/alpha"
_NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc).timestamp()
_CLAUDE_TURNS = ["2026-10-31T23:40:00", "2026-10-31T23:50:00", "2026-10-31T23:58:00"]
_CODEX_TURNS = ["2026-11-01T10:00:01", "2026-11-01T10:01:00"]
_LATER = ["2026-11-01T05:00:00", "2026-11-01T06:00:00", "2026-11-01T07:00:00"]


@pytest.fixture()
def utc(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _copy_session(home: Path, sid: str) -> Path:
    """The golden transcript (and its helpers) as session ``sid``: its own
    records carry the new id; the copies of another session stay others'."""
    dst = home / "claude" / "projects" / usagebackfill.capturewatch.folder_slug(_CWD)
    src = _LOGS / "claude"
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(src)).replace(_SID, sid)
        to = dst / rel
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_text(f.read_text(encoding="utf-8").replace(_SID, sid), encoding="utf-8")
    return dst / f"{sid}.jsonl"


def _chat(root: Path, agent: str, meta: dict, turns: list[str]) -> Path:
    folder = root / "projects" / "alpha" / "chats" / agent
    folder.mkdir(parents=True)
    body = [f"# Chat log — {agent}\n\n---\n"]
    for n, at in enumerate(turns, start=1):
        body.append(f"\n## Turn {n} · {at}\n**User**: prompt {n}\n**Agent**: reply {n}\n")
    (folder / "chat.md").write_text("".join(body), encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps({"agent_id": agent, "project": "alpha", "cwd": _CWD,
                                                  "last_active": turns[-1] if turns else "", **meta},
                                                 indent=2) + "\n", encoding="utf-8")
    return folder


def _old(*paths: Path) -> None:
    """Untouched for a day: no chat here is still going on."""
    for p in paths:
        for f in [p, *p.rglob("*")] if p.is_dir() else [p]:
            os.utime(f, (_NOW - 86400, _NOW - 86400))


def _lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _meta(folder: Path) -> dict:
    return json.loads((folder / "meta.json").read_text(encoding="utf-8"))


@pytest.fixture()
def world(tmp_path: Path, utc):
    root = tmp_path / "data"
    root.mkdir()
    (root / "integrations.csv").write_text(f"project,path\nalpha,{_CWD}\n", encoding="utf-8")
    home = tmp_path / "home"
    for sid in (_SID, _SID2, _SID3, _SID4):
        _copy_session(home, sid)
    codex = home / "codex"
    (codex / "sessions" / "2026" / "11" / "01").mkdir(parents=True)
    shutil.copy(_LOGS / "codex" / _ROLLOUT, codex / "sessions" / "2026" / "11" / "01" / _ROLLOUT)
    claude = {"tool": "claude-code"}
    chats = {
        # Recorded before the hooks kept usage: none at all.
        "whole": _chat(root, "cc-6a5e0d1c", {**claude, "session_ref": _SID}, _CLAUDE_TURNS),
        # Ran across the upgrade: the hook kept turn 3 on.
        "partial": _chat(root, "cc-7b6f1e2d", {**claude, "session_ref": _SID2}, _CLAUDE_TURNS),
        # One turn of four has its prompt: below half.
        "mismatch": _chat(root, "cc-8c7a2f3e", {**claude, "session_ref": _SID3}, _CLAUDE_TURNS[:1] + _LATER),
        # The transcript's first prompt has no turn (a branched session's
        # history, hooks wired late): its tokens stay out.
        "extra_start": _chat(root, "cc-e0000001", {**claude, "session_ref": _SID}, _CLAUDE_TURNS[1:]),
        # A turn the transcript has no prompt for (absorbed mid-turn, a
        # helper's hand-back): it gets nothing, the numbers after it shift.
        "gap": _chat(root, "cc-e0000002", {**claude, "session_ref": _SID},
                     [*_CLAUDE_TURNS[:2], "2026-10-31T23:55:00", _CLAUDE_TURNS[2]]),
        # More turns than prompts: the chat went on after the transcript.
        "more_turns": _chat(root, "cc-e0000003", {**claude, "session_ref": _SID}, _CLAUDE_TURNS + _LATER[:2]),
        # Refused by the first version: tried again.
        "old_refusal": _chat(root, "cc-e0000004", {**claude, "session_ref": _SID, usagebackfill.MARKER:
                             {"at": "2026-11-02T10:00:00", "result": "turns do not match"}}, _CLAUDE_TURNS),
        # Done by the first version: never run again.
        "old_done": _chat(root, "cc-e0000005", {**claude, "session_ref": _SID, usagebackfill.MARKER:
                          {"at": "2026-11-02T10:00:00", "result": "done", "lines": 0, "turns": []}}, _CLAUDE_TURNS),
        # A message ten minutes ago: the hook may be writing.
        "active": _chat(root, "cc-9d8b3a4f", {**claude, "session_ref": _SID4}, _CLAUDE_TURNS),
        "codex": _chat(root, "codex-ffff0001", {"tool": "codex", "session_ref": _THREAD}, _CODEX_TURNS),
        "lost": _chat(root, "cc-0f0f0f0f", {**claude, "session_ref": "0f0f0f0f-0000-4000-8000-000000000000"},
                      _CLAUDE_TURNS),
        "other": _chat(root, "oc-12345678", {"tool": "opencode", "session_ref": "ses_x"}, _CLAUDE_TURNS),
    }
    hook = [x for x in _lines(_EXPECTED / "usage.claude-code.jsonl") if x["turn"] == 3]
    (chats["partial"] / "usage.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in hook), encoding="utf-8")
    _old(root, home)
    active = chats["active"]
    meta = _meta(active)
    meta["last_active"] = datetime.fromtimestamp(_NOW - 600).strftime("%Y-%m-%dT%H:%M:%S")
    (active / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    os.utime(active / "meta.json", (_NOW - 86400, _NOW - 86400))

    def run() -> dict:
        return usagebackfill.backfill(root, claude_root=home / "claude" / "projects", codex_dir=codex, now=_NOW)

    return {"root": root, "home": home, "chats": chats, "run": run, "hook": hook}


def _imported() -> list[dict]:
    """What the import writes for the golden transcript (its copies hold the same messages)."""
    return [{**x, "source": "log"} for x in sessionimport.claude_usage(_LOGS / "claude" / f"{_SID}.jsonl", _SID)]


def test_a_chat_without_usage_gets_what_the_import_writes(world) -> None:
    got = world["run"]()
    assert got == {"done": 7, "lines": 12 + 9 + 3 + 4 + 12 + 12 + 12, "no transcript": 1, "turns do not match": 1}
    whole = world["chats"]["whole"]
    assert _lines(whole / "usage.jsonl") == _imported()
    assert {x["turn"] for x in _lines(whole / "usage.jsonl")} == {1, 2, 3}
    mark = _meta(whole)[usagebackfill.MARKER]
    assert mark | {"at": ""} == {"at": "", "result": "done", "lines": 12, "turns": [1, 3], "matched": 3,
                                 "unmatched_turns": 0, "unmatched_prompts": 0, "version": 2}
    assert datetime.fromisoformat(mark["at"])


def test_prompts_without_a_turn_keep_their_tokens_out(world) -> None:
    world["run"]()
    chat = world["chats"]["extra_start"]
    # The first prompt's window (and the helpers it started) is no turn of this chat.
    want = [{**x, "turn": x["turn"] - 1} for x in _imported() if x["turn"] >= 2]
    want = [x for x in want if not x["helper"]]
    assert _lines(chat / "usage.jsonl") == want
    mark = _meta(chat)[usagebackfill.MARKER]
    assert (mark["matched"], mark["unmatched_turns"], mark["unmatched_prompts"]) == (2, 0, 1)


def test_a_turn_without_its_prompt_gets_nothing(world) -> None:
    world["run"]()
    chat = world["chats"]["gap"]
    want = [{**x, "turn": 4 if x["turn"] == 3 else x["turn"]} for x in _imported()]
    assert _lines(chat / "usage.jsonl") == want
    assert 3 not in {x["turn"] for x in want}
    mark = _meta(chat)[usagebackfill.MARKER]
    assert (mark["matched"], mark["unmatched_turns"], mark["unmatched_prompts"], mark["turns"]) == (3, 1, 0, [1, 4])


def test_more_turns_than_prompts(world) -> None:
    world["run"]()
    chat = world["chats"]["more_turns"]
    assert _lines(chat / "usage.jsonl") == _imported()
    mark = _meta(chat)[usagebackfill.MARKER]
    assert (mark["matched"], mark["unmatched_turns"], mark["unmatched_prompts"]) == (3, 2, 0)


def test_an_old_refusal_is_tried_again_an_old_done_never(world) -> None:
    world["run"]()
    c = world["chats"]
    assert _lines(c["old_refusal"] / "usage.jsonl") == _imported()
    assert _meta(c["old_refusal"])[usagebackfill.MARKER]["version"] == 2
    assert not (c["old_done"] / "usage.jsonl").exists()
    assert _meta(c["old_done"])[usagebackfill.MARKER] == {"at": "2026-11-02T10:00:00", "result": "done",
                                                          "lines": 0, "turns": []}
    # A refusal of this version is not tried again.
    assert _meta(c["mismatch"])[usagebackfill.MARKER] | {"at": ""} == {
        "at": "", "result": "turns do not match", "version": 2}
    before = (c["mismatch"] / "meta.json").read_bytes()
    world["run"]()
    assert (c["mismatch"] / "meta.json").read_bytes() == before


def test_the_hooks_lines_stay_byte_for_byte_and_only_earlier_turns_are_added(world) -> None:
    usage = world["chats"]["partial"] / "usage.jsonl"
    before = usage.read_bytes()
    world["run"]()
    after = usage.read_bytes()
    assert after.startswith(before)
    added = _lines(usage)[len(world["hook"]):]
    assert added == [x for x in _imported() if x["turn"] < 3]
    assert {x["turn"] for x in added} == {1, 2} and all(x["source"] == "log" for x in added)
    assert not {x["id"] for x in added} & {x["id"] for x in world["hook"]}
    assert _meta(world["chats"]["partial"])[usagebackfill.MARKER] | {"at": ""} == {
        "at": "", "result": "done", "lines": 9, "turns": [1, 2], "matched": 3, "unmatched_turns": 0,
        "unmatched_prompts": 0, "version": 2}
    # What the server reads: the import's numbers for every message.
    by_id = {x["id"]: x for x in _lines(usage)}
    assert {k: {**v, "source": ""} for k, v in by_id.items()} == \
        {x["id"]: {**x, "source": ""} for x in _imported()}


def test_codex_chats_are_filled_by_the_same_rule(world) -> None:
    world["run"]()
    want = [{**x, "source": "log"} for x in sessionimport.codex_usage(_LOGS / "codex" / _ROLLOUT, _THREAD)]
    assert _lines(world["chats"]["codex"] / "usage.jsonl") == want
    assert [x["turn"] for x in want] == [1, 2, 2]


def test_mismatch_is_refused_active_waits_others_are_left(world) -> None:
    world["run"]()
    c = world["chats"]
    assert _meta(c["mismatch"])[usagebackfill.MARKER]["result"] == "turns do not match"
    assert not (c["mismatch"] / "usage.jsonl").exists()
    assert usagebackfill.MARKER not in _meta(c["active"]) and not (c["active"] / "usage.jsonl").exists()
    assert _meta(c["lost"])[usagebackfill.MARKER]["result"] == "no transcript"
    assert usagebackfill.MARKER not in _meta(c["other"])


def test_a_second_run_writes_nothing_even_without_the_marks(world) -> None:
    world["run"]()
    files = {p: p.read_bytes() for p in world["root"].rglob("usage.jsonl")}
    assert world["run"]() == {}
    for folder in world["chats"].values():
        meta = _meta(folder)
        if (meta.get(usagebackfill.MARKER) or {}).get("version") != 2:
            continue
        meta.pop(usagebackfill.MARKER, None)
        (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        os.utime(folder / "meta.json", (_NOW - 86400, _NOW - 86400))
    for p in files:
        os.utime(p, (_NOW - 86400, _NOW - 86400))
    again = world["run"]()
    assert again.get("done") == 7
    assert {p: p.read_bytes() for p in world["root"].rglob("usage.jsonl")} == files
    # The mark still counts the file's lines from the log.
    assert _meta(world["chats"]["whole"])[usagebackfill.MARKER]["lines"] == 12


def test_one_broken_chat_never_stops_the_rest(world, caplog) -> None:
    (world["chats"]["whole"] / "meta.json").write_text("{not json", encoding="utf-8")
    os.utime(world["chats"]["whole"] / "meta.json", (_NOW - 86400, _NOW - 86400))
    got = world["run"]()
    assert got.get("done") == 6
    assert "cc-6a5e0d1c" in caplog.text
    usagebackfill.run_once(world["root"] / "nowhere")      # nothing there: no raise


def test_alignment_turn_by_turn() -> None:
    def talk(*ts: float) -> list:
        return [(n, t, False, f"say {n}") for n, t in enumerate(ts, start=1)]

    def said(*pairs) -> list:
        return [(t, text) for t, text in pairs]

    hist, counts = usagebackfill.align(talk(100.0, 200.0), said((99.5, "say 1"), (201.0, "say 2")))
    assert hist == [[1, 99.5, False], [2, 201.0, False]] and counts["matched"] == 2
    # A prompt with no turn: a window of its own, numbered 0 (dropped).
    hist, counts = usagebackfill.align(talk(100.0, 200.0), said((10.0, "x"), (99.5, "say 1"), (150.0, "y"), (201.0, "say 2")))
    assert hist == [[0, 10.0, False], [1, 99.5, False], [0, 150.0, False], [2, 201.0, False]]
    assert counts == {"matched": 2, "unmatched_turns": 0, "unmatched_prompts": 2}
    # A turn with no prompt is left out; half matched is enough.
    hist, counts = usagebackfill.align(talk(100.0, 200.0), said((99.5, "say 1")))
    assert hist == [[1, 99.5, False]] and counts["unmatched_turns"] == 1
    # Two prompts for one turn: the text tells them apart, else refused.
    hist, _ = usagebackfill.align(talk(100.0), said((95.0, "other"), (101.0, "say 1")))
    assert hist == [[0, 95.0, False], [1, 101.0, False]]
    # The same message sent twice, kept as two turns: taken in order.
    resent = [(1, 100.0, False, "again"), (2, 105.0, False, "again")]
    hist, _ = usagebackfill.align(resent, said((100.5, "again"), (104.0, "again")))
    assert hist == [[1, 100.5, False], [2, 104.0, False]]
    # One prompt two turns could claim: the text gives it to its own.
    hist, _ = usagebackfill.align(talk(100.0, 103.0), said((103.5, "say 2")))
    assert hist == [[2, 103.5, False]]
    for chat, prompts in ((talk(100.0), said((95.0, "a"), (101.0, "b"))),          # two, text silent
                          (talk(100.0, 200.0, 300.0), said((99.0, "say 1"))),       # below half
                          (talk(100.0), said((None, "say 1"))),                     # no time
                          (talk(100.0, 200.0), said((201.0, "say 2"), (99.5, "say 1")))):   # out of order
        with pytest.raises(usagebackfill.Refused):
            usagebackfill.align(chat, prompts)
    # A turn the hook answered itself (#usage) never reached the model.
    quiet = [(1, 100.0, False, "a"), (2, 150.0, True, "#usage"), (3, 200.0, False, "b")]
    hist, counts = usagebackfill.align(quiet, said((99.5, "a"), (201.0, "b")))
    assert hist == [[1, 99.5, False], [3, 201.0, False]] and counts["unmatched_turns"] == 0


def test_the_usage_page_counts_the_chats_from_the_log(world) -> None:
    world["run"]()
    store = ViewStore(world["root"])
    store.rebuild()
    now = datetime(2026, 11, 1, 14, 48)
    cov = usagelib.summary(store, None, "30d", now=now)["coverage"]
    assert cov["chats_from_log"] == 7
    assert cov["chats_recorded"] >= 7


def test_the_server_starts_it_only_in_the_served_app(tmp_path: Path, monkeypatch) -> None:
    called: list[Path] = []
    done = threading.Event()

    def fake(root: Path) -> None:
        called.append(Path(root))
        done.set()

    monkeypatch.setattr(server, "_backfill_turn_times", lambda root: None)
    monkeypatch.setattr(server, "_backfill_usage", fake)
    from backend import timeauto
    from backend.routers import setup as setup_mod

    class _Idle:
        def start(self) -> None: ...
        def stop(self) -> None: ...

    monkeypatch.setattr(timeauto, "of", lambda app: _Idle())
    monkeypatch.setattr(setup_mod, "ensure_statuslines", lambda root: [])
    monkeypatch.setattr(server, "_warm_git", lambda store: None)
    for watch, monitor in ((False, True), (True, False), (False, False)):
        root = tmp_path / f"r{int(watch)}{int(monitor)}"
        root.mkdir()
        with TestClient(server.create_app(data_root=root, watch=watch, run_monitor=monitor)):
            pass
    assert called == []
    served = tmp_path / "served"
    served.mkdir()
    import backend.sysmon as sysmon
    monkeypatch.setattr(sysmon, "Monitor", lambda root: _Idle())
    with TestClient(server.create_app(data_root=served, watch=True, run_monitor=True)):
        assert done.wait(10)
    assert called == [served]


def test_a_chat_that_moves_while_it_is_read_is_left_for_the_next_start(world, monkeypatch) -> None:
    real = sessionimport.claude_usage_parts
    whole = world["chats"]["whole"]

    def moving(path: Path, session: str):
        got = real(path, session)
        meta = _meta(whole)
        meta["last_stop"] = {"at": "now"}            # the hook wrote meanwhile
        (whole / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return got

    monkeypatch.setattr(sessionimport, "claude_usage_parts", moving)
    assert usagebackfill.backfill_chat(whole, world["home"] / "claude" / "projects",
                                       world["home"] / "codex", _NOW) is None
    assert not (whole / "usage.jsonl").exists() and usagebackfill.MARKER not in _meta(whole)
