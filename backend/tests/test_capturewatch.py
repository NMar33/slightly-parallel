"""The capture watchdog: a turn Claude Code saw and Slightly Parallel did not is found."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from backend import capturewatch
from backend.csvio import append_row
from backend.db import ViewStore

WORK = "/work/my app"


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _transcript(root: Path, session: str, prompts: list[float], tool_result_at: float | None = None) -> None:
    d = root / capturewatch.folder_slug(WORK)
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "user", "timestamp": _utc(t), "message": {"role": "user", "content": "do the thing"}}) for t in prompts]
    lines.append(json.dumps({"type": "user", "timestamp": _utc(prompts[-1] + 5), "message": {"role": "user",
                             "content": "<task-notification>background done</task-notification>"}}))
    if tool_result_at:
        lines.append(json.dumps({"type": "user", "timestamp": _utc(tool_result_at), "message": {"role": "user",
                                 "content": [{"type": "tool_result", "content": "ok"}]}}))
    (d / f"{session}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _captured(data: Path, session: str, at: float) -> None:
    d = data / "projects" / "alpha" / "chats" / f"cc-{session[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({"last_active": datetime.fromtimestamp(at).strftime("%Y-%m-%dT%H:%M:%S")}))


def _setup(tmp_path: Path) -> tuple[ViewStore, Path]:
    data = tmp_path / "data"
    (data / "projects" / "alpha").mkdir(parents=True)
    append_row(data / "integrations.csv", ("project", "path"), {"project": "alpha", "path": WORK})
    return ViewStore(data), tmp_path / "claude"


def test_the_folder_name_is_claude_codes() -> None:
    assert capturewatch.folder_slug("/home/n/my projects/app") == "-home-n-my-projects-app"


def test_captured_sessions_are_fine_and_a_long_turn_is_not_a_gap(tmp_path: Path) -> None:
    st, claude = _setup(tmp_path)
    now = time.time()
    _transcript(claude, "aaaaaaaa-1", [now - 900], tool_result_at=now - 10)   # a turn running for 15 minutes
    _captured(st.data_root, "aaaaaaaa-1", now - 895)
    out = capturewatch.check(st, claude_root=claude, now=now)
    assert out["ok"] and out["watched"] == 1


def test_a_missed_turn_and_a_session_never_captured(tmp_path: Path) -> None:
    st, claude = _setup(tmp_path)
    now = time.time()
    _transcript(claude, "bbbbbbbb-2", [now - 1800, now - 300])
    _captured(st.data_root, "bbbbbbbb-2", now - 1795)                       # the second prompt was lost
    _transcript(claude, "cccccccc-3", [now - 600])                           # the hook never ran
    out = capturewatch.check(st, claude_root=claude, now=now)
    got = {m["agent_id"]: m["why"] for m in out["missed"]}
    assert not out["ok"]
    assert got == {"cc-bbbbbbbb": "its latest messages were not captured", "cc-cccccccc": "this session was never captured"}


def test_hook_errors_of_the_last_day(tmp_path: Path) -> None:
    import importlib.util
    import sys
    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
    sys.path.insert(0, str(hooks))
    spec = importlib.util.spec_from_file_location("capture_for_watch", hooks / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    st, claude = _setup(tmp_path)
    mod.record_failure(st.data_root, "alpha", "cc-dddddddd", "claude-code", "Stop: OSError: disk full")
    out = capturewatch.check(st, claude_root=claude)
    assert not out["ok"] and out["errors_n"] == 1 and "disk full" in out["errors"][0]["error"]


def _rollout(root: Path, session: str, cwd: str, prompt_at: float) -> None:
    d = root / "2026" / "10" / "17"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        {"timestamp": _utc(prompt_at - 5), "type": "session_meta", "payload": {"id": session, "cwd": cwd}},
        {"timestamp": _utc(prompt_at - 4), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "<environment_context>…</environment_context>"}]}},
        {"timestamp": _utc(prompt_at), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "fix the login timeout"}]}},
    ]
    (d / f"rollout-x-{session}.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def test_a_session_never_recorded_in_the_last_week_stays_lost_until_said_not_needed(tmp_path: Path) -> None:
    """A Codex session in a registered folder that nothing recorded: lost, for
    a week, not an hour; recorded ones and other folders are not; the
    operator can say the tool is not needed there."""
    st, claude = _setup(tmp_path)
    codex = tmp_path / "codex"
    now = time.time()
    _rollout(codex, "01a144bc-0000-7000-8000-000000000001", WORK, now - 3 * 86400)       # three days ago, lost
    _rollout(codex, "01a144dd-0000-7000-8000-000000000002", WORK + "/src", now - 7200)  # a subfolder, lost
    _rollout(codex, "01a144ee-0000-7000-8000-000000000003", "/elsewhere", now - 60)     # not ours
    rec = st.data_root / "projects" / "alpha" / "chats" / "codex-00000004"   # Codex agents are named by the end of the id
    rec.mkdir(parents=True)
    (rec / "meta.json").write_text("{}")
    _rollout(codex, "01a144ff-0000-7000-8000-000000000004", WORK, now - 60)             # recorded
    out = capturewatch.check(st, claude_root=claude, codex_root=codex, now=now)
    assert [(g["project"], g["tool"], g["sessions"]) for g in out["lost"]] == [("alpha", "codex", 2)]
    assert out["ok"] is False
    capturewatch.set_ignored(st.data_root, "alpha", "codex", True)
    out = capturewatch.check(st, claude_root=claude, codex_root=codex, now=now)
    assert out["lost"][0]["ignored"] is True and out["ok"] is True
    capturewatch.set_ignored(st.data_root, "alpha", "codex", False)
    assert capturewatch.ignored(st.data_root) == set()



def test_two_codex_sessions_of_one_minute_are_two_agents() -> None:
    """Codex's ids are UUIDv7, time first: the first 8 characters of two
    sessions a few seconds apart are the same."""
    from backend.hookshared import session_key
    a, b = "01a144ed-026f-7092-b414-d8f787fdf7fa", "01a144ed-31c0-7aa1-9b0e-0c5d2f7a1e33"
    assert a[:8] == b[:8]
    assert session_key("codex", a) != session_key("codex", b)
    assert session_key("claude-code", "56a11b0e-3352-480f-b7c9-d4d71b99fee6") == "56a11b0e"


def test_lost_codex_sessions_follow_the_hook_not_any_parent_folder(tmp_path: Path) -> None:
    """A session in a nested project belongs to it alone; a session recorded
    under the old first-8 name is not lost; one older than the wiring is
    not lost; Codex's own AGENTS.md message is not the person writing."""
    st, claude = _setup(tmp_path)
    inner = tmp_path / "inner"
    inner.mkdir()
    append_row(st.data_root / "integrations.csv", ("project", "path"), {"project": "beta", "path": str(inner)})
    codex = tmp_path / "codex"
    now = time.time()
    _rollout(codex, "01a14500-0000-7000-8000-00000000aaaa", str(inner), now - 600)                  # beta's, lost there only
    old = st.data_root / "projects" / "alpha" / "chats" / "codex-01a14501"
    old.mkdir(parents=True)
    (old / "meta.json").write_text("{}")
    _rollout(codex, "01a14501-0000-7000-8000-00000000bbbb", WORK, now - 600)                        # recorded, old name
    got = {(g["project"], g["tool"]): g["sessions"] for g in capturewatch.lost(st, claude, codex, now)}
    assert got == {("beta", "codex"): 1}
    wired = inner / ".codex"
    wired.mkdir()
    (wired / "hooks.json").write_text("{}")                                                          # connected after it
    after = capturewatch.lost(st, claude, codex, now)
    assert [(g["project"], g["sessions"], g["earlier"]) for g in after] == [("beta", 0, 1)]          # importable, no warning


def test_codex_adds_its_own_agents_md_message_and_that_is_not_a_prompt(tmp_path: Path) -> None:
    d = tmp_path / "2026" / "10" / "17"
    d.mkdir(parents=True)
    lines = [{"timestamp": _utc(time.time()), "type": "session_meta", "payload": {"id": "x", "cwd": WORK}},
             {"timestamp": _utc(time.time()), "type": "response_item", "payload": {"type": "message", "role": "user",
              "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /work/my app\n…"}]}}]
    f = d / "rollout-x.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    assert capturewatch._codex_prompt(f) is None
