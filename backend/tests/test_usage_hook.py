"""Usage in the hooks: tokens per API message (usage.jsonl), plan limits
(.usage/limits.jsonl), the status line, #usage answered by the hook, and
Setup's status line. Every log here is made up for the test."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import hookshared, sessionimport
from backend.server import create_app

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
_HOOK = _HOOKS / "claude-code-capture.py"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


capture = _load("sp_capture_usage", "capture.py")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path / "data"


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _asst(mid: str, at: datetime, *, out: int = 10, inp: int = 2, cw: int = 100, cr: int = 1000,
          session: str = "s1", model: str = "claude-opus-4-5", content=None, **extra) -> dict:
    return {"type": "assistant", "timestamp": _utc(at), "sessionId": session, **extra,
            "message": {"id": mid, "model": model, "content": content or [{"type": "text", "text": "ok"}],
                        "usage": {"input_tokens": inp, "cache_creation_input_tokens": cw,
                                  "cache_read_input_tokens": cr, "output_tokens": out,
                                  "output_tokens_details": {"thinking_tokens": 3},
                                  "cache_creation": {"ephemeral_1h_input_tokens": cw, "ephemeral_5m_input_tokens": 0},
                                  "iterations": [{"input_tokens": 999}]}}}


def _user(text: str, at: datetime, session: str = "s1") -> dict:
    return {"type": "user", "timestamp": _utc(at), "sessionId": session, "message": {"role": "user", "content": text}}


def _hook(root: Path, payload: dict, tool: str = "claude-code") -> subprocess.CompletedProcess:
    args = [sys.executable, str(_HOOK), "--project", "alpha", "--data-root", str(root)]
    if tool != "claude-code":
        args += ["--tool", tool]
    return subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=60)


def _usage(root: Path, agent: str) -> list[dict]:
    path = root / "projects" / "alpha" / "chats" / agent / "usage.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


# -- the number format -------------------------------------------------------

_TABLE = Path(__file__).resolve().parents[2] / "testdata" / "usage" / "format-table.json"


def _table(name: str) -> list:
    if not _TABLE.exists():
        pytest.skip("testdata/usage/format-table.json is not there (the server's zone writes it)")
    return json.loads(_TABLE.read_text(encoding="utf-8"))[name]


def test_the_hooks_own_format_follows_the_one_table() -> None:
    """The hook's copy (it answers when usagelib cannot be loaded) and the
    status line's percent follow the table the server and the page use."""
    for n, shown in _table("tokens"):
        assert capture.format_tokens(n) == shown, n
    for share, shown in _table("pct"):
        if share is None:
            assert hookshared.pct_whole(None) is None
            continue
        assert f"{hookshared.pct_whole(share * 100)}%" == shown, share


# -- the parsers ---------------------------------------------------------------

def test_claude_records_count_each_message_once_and_skip_copies() -> None:
    t = datetime(2026, 11, 1, 10, 0, 0)
    recs = [
        _asst("m1", t, out=6), _asst("m1", t + timedelta(seconds=1), out=300),   # one message, two blocks
        _asst("m2", t, model="<synthetic>"),
        _asst("m3", t, forkedFrom={"sessionId": "old"}),
        _asst("m4", t, session="other"),
        {"type": "user", "message": {"content": "x"}},
    ]
    lines = hookshared.usage_records_claude(recs, "s1")
    assert [x["id"] for x in lines] == ["m1"]
    m1 = lines[0]
    assert (m1["new"], m1["cache_write"], m1["cache"], m1["output"], m1["thinking"], m1["ttl"]) == (102, 100, 1000, 300, 3, "1h")
    assert m1["tool"] == "claude-code" and m1["helper"] == "" and "limit" not in m1


def _codex_rollout(path: Path, at: datetime) -> Path:
    def tc(sec: int, inp: int, cached: int, out: int, total: int, used: float = 9.0) -> dict:
        return {"timestamp": _utc(at + timedelta(seconds=sec)), "type": "event_msg", "payload": {
            "type": "token_count",
            "info": {"total_token_usage": {"total_tokens": total},
                     "last_token_usage": {"input_tokens": inp, "cached_input_tokens": cached,
                                          "cache_write_input_tokens": 0, "output_tokens": out,
                                          "reasoning_output_tokens": 5}},
            "rate_limits": {"primary": {"used_percent": used, "window_minutes": 300, "resets_at": 1793516141},
                            "secondary": {"used_percent": 81.0, "window_minutes": 10080, "resets_at": 1793794235},
                            "plan_type": "plus"}}}
    recs = [
        {"timestamp": _utc(at), "type": "event_msg", "payload": {"type": "task_started", "turn_id": "t1"}},
        {"timestamp": _utc(at), "type": "turn_context", "payload": {"model": "gpt-a"}},
        tc(1, 24227, 12288, 3325, 27552),
        tc(2, 24227, 12288, 3325, 27552),            # the same call reported again
        {"timestamp": _utc(at + timedelta(seconds=3)), "type": "event_msg", "payload": {"type": "token_count", "info": None,
                                                                                          "rate_limits": {}}},
        {"timestamp": _utc(at + timedelta(seconds=9)), "type": "event_msg", "payload": {"type": "task_started", "turn_id": "t2"}},
        {"timestamp": _utc(at + timedelta(seconds=9)), "type": "turn_context", "payload": {"model": "gpt-b"}},
        tc(10, 1000, 0, 50, 28602, used=12.0),
    ]
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    return path


def test_codex_new_input_leaves_the_cached_part_out(tmp_path: Path) -> None:
    rollout = _codex_rollout(tmp_path / "rollout-x-thread.jsonl", datetime(2026, 11, 1, 10, 0, 0))
    lines, limits = hookshared.codex_turn_usage(rollout, "t1")
    assert len(lines) == 1
    one = lines[0]
    assert (one["new"], one["cache"], one["output"], one["thinking"], one["model"]) == (11939, 12288, 3325, 5, "gpt-a")
    assert one["limit"] == {"five_hour": 9.0, "seven_day": 81.0}
    assert limits["tool"] == "codex" and limits["plan"] == "plus" and limits["five_hour"]["used"] == 9.0
    assert limits["five_hour"]["resets_at"] == datetime.fromtimestamp(1793516141).strftime("%Y-%m-%dT%H:%M:%S")
    last, limits = hookshared.codex_turn_usage(rollout)
    assert [x["model"] for x in last] == ["gpt-b"] and limits["five_hour"]["used"] == 12.0
    both, _ = hookshared.codex_turn_usage(rollout, back=1)
    assert [x["model"] for x in both] == ["gpt-a", "gpt-b"]
    # A turn the file does not have (yet): the last one.
    assert [x["id"] for x in hookshared.codex_turn_usage(rollout, "nope")[0]] == [x["id"] for x in last]
    assert hookshared.codex_turn_usage(tmp_path / "missing.jsonl") == ([], None)


def test_opencode_reasoning_is_counted_inside_output() -> None:
    lines = hookshared.usage_records_opencode([
        {"id": "msg1", "at": 1793516141000, "model": "m", "input": 211, "output": 8, "reasoning": 40,
         "cache_read": 9216, "cache_write": 5, "helper": ""},
        {"id": "msg1", "at": 1793516141000, "model": "m", "input": 211, "output": 9, "reasoning": 40,
         "cache_read": 9216, "cache_write": 5, "helper": ""},
        {"no": "id"},
    ])
    assert len(lines) == 1 and (lines[0]["new"], lines[0]["output"], lines[0]["thinking"], lines[0]["cache"]) == (216, 49, 40, 9216)


def test_limits_are_appended_only_on_a_change_or_after_five_minutes(root: Path) -> None:
    def line(used: float, at: str) -> dict:
        return {"at": at, "tool": "codex", "five_hour": {"used": used, "resets_at": ""}, "source": "rollout"}
    now = datetime.now()
    at = now.strftime("%Y-%m-%dT%H:%M:%S")
    assert hookshared.limits_append(root, line(9.0, at))
    assert not hookshared.limits_append(root, line(9.0, at))
    assert hookshared.limits_append(root, line(10.0, at))
    assert hookshared.limits_append(root, {**line(9.0, at), "tool": "claude-code"})   # another tool
    later = (now + timedelta(minutes=6)).timestamp()
    assert hookshared.limits_append(root, line(10.0, at), now=later)
    assert len((root / ".usage" / "limits.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    assert not hookshared.limits_append(root / "missing", line(1.0, at))
    assert not (root / "missing").exists()


# -- the Claude Code hook --------------------------------------------------------

def _transcript(tmp_path: Path, recs: list[dict]) -> Path:
    t = tmp_path / "proj" / "s1.jsonl"
    t.parent.mkdir(parents=True, exist_ok=True)
    with open(t, "a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    return t


def test_stop_keeps_each_message_once_with_its_turn_and_its_helpers(root: Path, tmp_path: Path) -> None:
    now = datetime.now().astimezone()
    old = now - timedelta(hours=3)
    # History from before this chat's first prompt (a resumed session): not counted.
    t = _transcript(tmp_path, [_user("old", old), _asst("m0", old + timedelta(seconds=5))])
    assert _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "do it"}).returncode == 0
    call = "toolu_helper1"
    _transcript(tmp_path, [
        _user("do it", now),
        _asst("m1", now + timedelta(seconds=2), out=6,
              content=[{"type": "tool_use", "id": call, "name": "Agent", "input": {}}]),
        _asst("m1", now + timedelta(seconds=3), out=300),
        _asst("m2", now + timedelta(seconds=4)),
    ])
    sub = t.with_suffix("") / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.meta.json").write_text(json.dumps({"toolUseId": call}), encoding="utf-8")
    (sub / "agent-abc.jsonl").write_text(json.dumps(_asst("h1", now + timedelta(seconds=3), agentId="abc",
                                                          isSidechain=True)) + "\n", encoding="utf-8")
    stop = {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t),
            "last_assistant_message": "done"}
    p = _hook(root, stop)
    assert p.returncode == 0 and p.stdout == ""         # showing is off: nothing on stdout
    lines = _usage(root, "cc-s1")
    assert [(x["id"], x["turn"], x["helper"], x["output"]) for x in lines] == [
        ("m1", 1, "", 300), ("m2", 1, "", 10), ("h1", 1, "abc", 10)]
    meta = json.loads((root / "projects/alpha/chats/cc-s1/meta.json").read_text(encoding="utf-8"))
    assert meta["helper_turns"] == {call: 1}

    # A retried Stop hands the same records again: nothing is added.
    (root / "projects/alpha/chats/cc-s1/meta.json").write_text(
        json.dumps({**meta, "transcript_pos": {}}), encoding="utf-8")
    _hook(root, stop)
    assert len(_usage(root, "cc-s1")) == 3

    # The helper goes on during turn 2: its tokens stay with turn 1.
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "next"})
    later = datetime.now().astimezone() + timedelta(seconds=1)
    with open(sub / "agent-abc.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(_asst("h2", later, agentId="abc", isSidechain=True)) + "\n")
    _transcript(tmp_path, [_user("next", later), _asst("m3", later + timedelta(seconds=1))])
    _hook(root, stop)
    by_id = {x["id"]: x["turn"] for x in _usage(root, "cc-s1")}
    assert by_id == {"m1": 1, "m2": 1, "h1": 1, "h2": 1, "m3": 2}


def test_usage_alone_is_answered_by_the_hook_and_kept_as_a_turn(root: Path, tmp_path: Path) -> None:
    p = _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s2", "prompt": "#usage-on"})
    out = json.loads(p.stdout)
    assert out["decision"] == "block" and out["hookSpecificOutput"]["suppressOriginalPrompt"] is True
    assert out["reason"].startswith("[slightly-parallel] Usage is on.\nFrom now on, each reply shows:")
    assert "/usage" in out["reason"]
    folder = root / "projects/alpha/chats/cc-s2"
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["usage_show"] is True and "pending_turn" not in meta and meta["message_count"] == 1
    assert "standup_asked" not in meta               # the model never saw this turn
    chat = (folder / "chat.md").read_text(encoding="utf-8")
    assert "**User**: #usage-on" in chat and "**Agent**: [slightly-parallel] Usage is on." in chat

    # Showing on: the line after the next reply, as the Stop's systemMessage.
    now = datetime.now().astimezone()
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s2", "prompt": "go"})
    t = tmp_path / "s2.jsonl"
    t.write_text("\n".join(json.dumps(r) for r in [
        _user("go", now, "s2"), _asst("x1", now + timedelta(seconds=2), session="s2", out=2000, inp=100, cw=300, cr=108_000),
    ]) + "\n", encoding="utf-8")
    p = _hook(root, {"hook_event_name": "Stop", "session_id": "s2", "transcript_path": str(t), "last_assistant_message": "ok"})
    msg = json.loads(p.stdout)["systemMessage"]
    assert msg.startswith("→ ")
    assert _usage(root, "cc-s2")[0]["turn"] == 2

    p = _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s2", "prompt": "#usage-off"})
    assert json.loads(p.stdout)["reason"] == ("[slightly-parallel] Usage is off. Tokens are still recorded. "
                                             "Type #usage-on to show them.")
    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["usage_show"] is False


def test_usage_with_more_in_the_message_reaches_the_agent_with_the_answer(root: Path) -> None:
    p = _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s3", "prompt": "#usage and fix the test"})
    assert not p.stdout.lstrip().startswith("{")      # not blocked: plain context for the agent
    assert "[slightly-parallel] #usage — the hook's answer is below; show it to the user as it is" in p.stdout
    meta = json.loads((root / "projects/alpha/chats/cc-s3/meta.json").read_text(encoding="utf-8"))
    assert meta["pending_turn"] == 1


def test_usage_only_reads_a_message_of_usage_commands_alone() -> None:
    assert capture.usage_only("#usage") == ["usage"]
    assert capture.usage_only("  #usage-on  #usage ") == ["usage-on", "usage"]
    assert capture.usage_only("###usage") == ["usage"]
    assert capture.usage_only("#usage please") == []
    assert capture.usage_only("#usage #scan") == []
    assert capture.usage_only("#usage #vision") == []
    assert capture.usage_only("#usage #mute") == []


def test_without_the_servers_module_the_block_says_so_and_the_line_is_summed(root: Path, monkeypatch) -> None:
    monkeypatch.setattr(capture, "_usagelib", lambda: None)
    cap = capture.TurnCapture(root, "alpha", "cc-fb")
    answer = cap.answer_usage("#usage")
    assert answer == f"[slightly-parallel] #usage — the server's module is not available; open {capture.server_url()}/usage."
    cap.open_turn("work")
    t = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    base = {"at": t, "tool": "claude-code", "model": "m", "cache_write": 0, "thinking": 0, "ttl": ""}
    turn, written = cap.record_usage([
        {**base, "id": "a", "new": 1874, "cache": 108_233, "output": 512, "helper": ""},
        {**base, "id": "b", "new": 299_000, "cache": 5, "output": 1000, "helper": "h", "tool_use": "x"},
    ])
    assert turn == 2 and len(written) == 2 and "tool_use" not in written[1]
    assert cap.usage_line(2) == "→ 1.9k ↑ 512 ↓ (108k) + helpers 300k"
    assert cap.usage_line(3) == ""
    assert cap.usage_shown() is False
    (root / "settings.json").write_text(json.dumps({"agent": {"usage_show": True}}), encoding="utf-8")
    assert cap.usage_shown() is True


def test_codex_stop_records_tokens_and_limits_from_the_rollout(root: Path, tmp_path: Path) -> None:
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "0199-thread-abcdef12", "prompt": "go"}, tool="codex")
    at = datetime.now().astimezone() + timedelta(seconds=1)
    rollout = _codex_rollout(tmp_path / "rollout-2026-0199-thread-abcdef12.jsonl", at)
    p = _hook(root, {"hook_event_name": "Stop", "session_id": "0199-thread-abcdef12",
                     "transcript_path": str(rollout), "last_assistant_message": "ok"}, tool="codex")
    assert p.returncode == 0
    agent = "codex-abcdef12"
    lines = _usage(root, agent)
    # The last turn and the one before it (read again); both after the prompt.
    assert [(x["model"], x["turn"]) for x in lines] == [("gpt-a", 1), ("gpt-b", 1)]
    limits = [json.loads(x) for x in (root / ".usage" / "limits.jsonl").read_text(encoding="utf-8").splitlines()]
    assert limits[-1]["tool"] == "codex" and limits[-1]["five_hour"]["used"] == 12.0


def test_opencode_hands_its_tokens_through_the_cli(root: Path) -> None:
    cli = _HOOKS / "capture-cli.py"
    common = [sys.executable, str(cli), "--project", "alpha", "--data-root", str(root), "--agent", "oc-x", "--json-stdin"]
    subprocess.run([*common, "--phase", "open"], input=json.dumps({"text": "hi"}), text=True, check=True, timeout=60)
    ms = int((time.time() + 2) * 1000)
    subprocess.run([*common, "--phase", "complete"], input=json.dumps({"text": "ok", "usage": [
        {"id": "msg_1", "at": ms, "model": "m", "input": 10, "output": 5, "reasoning": 1,
         "cache_read": 100, "cache_write": 0, "helper": ""}]}), text=True, check=True, timeout=60)
    lines = _usage(root, "oc-x")
    assert [(x["id"], x["turn"], x["output"], x["tool"]) for x in lines] == [("msg_1", 1, 6, "opencode")]


# -- the status line ----------------------------------------------------------------

_STATUS = _HOOKS / "statusline.py"


def _status(root: Path, data: dict, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_STATUS), "--data-root", str(root), *extra],
                          input=json.dumps(data).encode(), capture_output=True, timeout=60)


def test_the_status_line_keeps_the_limits_and_the_chat_state(root: Path) -> None:
    data = {"session_id": "abc/../x", "model": {"id": "claude-opus-4-5"},
            "rate_limits": {"five_hour": {"used_percentage": 62.0, "resets_at": 1793516141},
                            "seven_day": {"used_percentage": 31.4, "resets_at": 1793794235}},
            "context_window": {"used_percentage": 61, "context_window_size": 200000,
                               "current_usage": {"input_tokens": 2, "output_tokens": 9,
                                                 "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 5}},
            "prompt_cache": {"warm": True, "expires_at": 1793516141, "hit_ratio": 0.9, "last_miss_cause": None},
            "cost": {"total_cost_usd": 1.0}, "cwd": "/secret"}
    p = _status(root, data)
    assert p.returncode == 0 and p.stdout.decode() == "SP · 5-hour 62% · week 31%\n"
    line = json.loads((root / ".usage" / "limits.jsonl").read_text(encoding="utf-8"))
    assert line["tool"] == "claude-code" and line["source"] == "statusline"
    assert line["five_hour"] == {"used": 62.0, "resets_at": datetime.fromtimestamp(1793516141).strftime("%Y-%m-%dT%H:%M:%S")}
    files = list((root / ".usage" / "sessions").glob("*.json"))
    assert [f.name for f in files] == ["claude-code-abc_.._x.json"]
    state = json.loads(files[0].read_text(encoding="utf-8"))
    assert state["context"] == {"used_pct": 61, "size": 200000, "input": 2, "output": 9, "cache": 1000, "cache_write": 5}
    assert state["prompt_cache"]["warm"] is True and state["model"] == "claude-opus-4-5"
    assert "cwd" not in json.dumps(state) and "cost" not in json.dumps(state)
    _status(root, data)       # the same values a moment later: no second line
    assert len((root / ".usage" / "limits.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_the_status_line_runs_the_operators_own_after_itself(root: Path, tmp_path: Path) -> None:
    script = tmp_path / "mine.py"
    script.write_text("import sys, json; print('mine', json.load(sys.stdin)['session_id'])", encoding="utf-8")
    p = _status(root, {"session_id": "s9"}, "--then", f'"{sys.executable}" "{script}"')
    assert p.stdout.decode().strip() == "mine s9"
    p = _status(tmp_path / "no-root", {"rate_limits": {"five_hour": {"used_percentage": 5}}})
    assert p.returncode == 0 and p.stdout.decode() == "SP · 5-hour 5%\n" and not (tmp_path / "no-root").exists()
    assert _status(root, {}).stdout == b""


# -- Setup ----------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    from backend.routers import setup as setup_router
    data_root = tmp_path / "data"
    data_root.mkdir()
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    user = tmp_path / "claude-home" / "settings.json"
    monkeypatch.setattr(setup_router, "CLAUDE_USER_SETTINGS", user)
    with TestClient(create_app(data_root=data_root, watch=False)) as client:
        yield client, project_dir, user


def _local(project_dir: Path) -> dict:
    return json.loads((project_dir / ".claude" / "settings.local.json").read_text(encoding="utf-8-sig"))


def _integrate(client: TestClient, project_dir: Path, **extra) -> dict:
    r = client.post("/api/setup/integrate", json={"project_code": "my-app", "project_dir": str(project_dir), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _data_root(client: TestClient) -> Path:
    return Path(client.get("/api/setup/info").json()["data_root"])


def _side(client: TestClient, project_dir: Path) -> dict | None:
    data_root = _data_root(client)
    return hookshared.read_statusline_then(data_root, hookshared.statusline_key(project_dir))


def _run_status(client: TestClient, project_dir: Path, data: dict) -> str:
    """Our status line as Claude Code runs it: the command Setup wrote, in a shell."""
    cmd = _local(project_dir)["statusLine"]["command"]
    p = subprocess.run(cmd, shell=True, input=json.dumps(data).encode(), capture_output=True, timeout=60)
    return p.stdout.decode()


def test_setup_wraps_the_users_status_line_and_forget_leaves_it(env, tmp_path: Path) -> None:
    client, project_dir, user = env
    user.parent.mkdir(parents=True)
    mine = tmp_path / "my line.py"
    mine.write_text("print('mine')", encoding="utf-8")
    user.write_text(json.dumps({"statusLine": {"type": "command", "command": f'"{sys.executable}" "{mine}"',
                                               "refreshInterval": 5}}), encoding="utf-8")
    _integrate(client, project_dir)
    entry = _local(project_dir)["statusLine"]
    key = hookshared.statusline_key(project_dir)
    # The shell line names the side file only; the user's line is not quoted into it.
    assert entry["command"].endswith(f" --then-key {key}") and "my line" not in entry["command"]
    assert entry["refreshInterval"] == 5
    assert _side(client, project_dir)["from"] == "user"
    assert _run_status(client, project_dir, {"session_id": "s"}).strip() == "mine"
    # The operator edits their own line later: ours runs the new one, nothing re-run in Setup.
    mine.write_text("print('mine, edited')", encoding="utf-8")
    assert _run_status(client, project_dir, {"session_id": "s"}).strip() == "mine, edited"
    info = client.get("/api/setup/info").json()["integrations"][0]
    assert info["statusline"] is True and info["statusline_off"] is False
    again = _integrate(client, project_dir)          # a second run changes nothing
    assert {Path(r["file"]).name: r["action"] for r in again["results"]}["settings.local.json"] == "unchanged"
    client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert not (project_dir / ".claude").exists()
    assert "my line.py" in user.read_text(encoding="utf-8")
    assert _side(client, project_dir) is None


def test_setup_keeps_a_status_line_of_the_same_file_and_puts_it_back(env) -> None:
    client, project_dir, _user = env
    (project_dir / ".claude").mkdir()
    own = {"type": "command", "command": "echo 'it''s mine' \"$HOME\" %PATH%", "padding": 1}
    # A byte-order mark, as an editor on Windows leaves it.
    (project_dir / ".claude" / "settings.local.json").write_text(
        "\ufeff" + json.dumps({"statusLine": own, "model": "x"}), encoding="utf-8")
    _integrate(client, project_dir)
    entry = _local(project_dir)["statusLine"]
    assert entry["padding"] == 1 and "--then-key" in entry["command"] and "mine" not in entry["command"]
    side = _side(client, project_dir)
    assert side["from"] == "local" and side["command"] == own["command"] and side["entry"] == own
    # Integrating again with ours there keeps the operator's line in the side file.
    _integrate(client, project_dir)
    assert _side(client, project_dir)["entry"] == own
    client.post("/api/setup/forget", json={"project_code": "my-app", "path": str(project_dir)})
    assert _local(project_dir) == {"statusLine": own, "model": "x"}         # exactly as it was


def test_setup_without_a_status_line_installs_ours_alone(env) -> None:
    client, project_dir, _user = env
    out = _integrate(client, project_dir)
    cmd = _local(project_dir)["statusLine"]["command"]
    data_root = _data_root(client)
    assert cmd.startswith(('python3 "', 'py -3 "')) and f'--data-root "{data_root}" --then-key ' in cmd and "--then " not in cmd
    assert _side(client, project_dir) == {"from": "user", "command": "", "folder": str(project_dir),
                                          "user_settings": str(env[2])}
    assert _run_status(client, project_dir, {"rate_limits": {"five_hour": {"used_percentage": 62.5}}}) == "SP · 5-hour 62%\n"
    # The two hooks that only add tokens are installed beside the two that capture.
    hooks = _local(project_dir)["hooks"]
    assert set(hooks) == {"UserPromptSubmit", "Stop", "SessionEnd", "StopFailure"}
    assert out["results"]


def test_setup_without_the_status_line_takes_ours_out_and_the_start_adds_none(env) -> None:
    from backend.csvio import read_rows
    from backend.routers import setup as setup_mod
    client, project_dir, _user = env
    data_root = _data_root(client)
    (project_dir / ".claude").mkdir()
    own = {"type": "command", "command": "echo mine"}
    (project_dir / ".claude" / "settings.local.json").write_text(json.dumps({"statusLine": own}), encoding="utf-8")
    _integrate(client, project_dir)
    _integrate(client, project_dir, write_claude_statusline=False)
    assert _local(project_dir)["statusLine"] == own                        # the operator's own is back
    assert _side(client, project_dir) is None
    rows = read_rows(data_root / "integrations.csv")
    assert [r["statusline"] for r in rows] == ["off"]
    assert setup_mod.ensure_statuslines(data_root) == []                   # turned off: the start leaves it
    assert _local(project_dir)["statusLine"] == own
    assert client.get("/api/setup/info").json()["integrations"][0]["statusline_off"] is True
    _integrate(client, project_dir)                                        # on again
    assert [r["statusline"] for r in read_rows(data_root / "integrations.csv")] == [""]
    assert hookshared.is_sp_statusline(_local(project_dir)["statusLine"])


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("command", [
    "bash ~/.claude/statusline-command.sh",
    "echo 'it''s' \"quoted\" $HOME",
    '"C:/Program Files/Git/bin/bash.exe" -c "echo %USERPROFILE% & exit 0"',
    "node C:\\Users\\me\\line.js --flag=\"a b\"",
])
def test_the_wrapped_command_is_kept_as_it_was_on_either_system(tmp_path: Path, windows: bool, command: str) -> None:
    """The side file keeps the operator's command byte for byte, whatever its
    quotes, on Linux and on Windows; the shell line carries only the key. An
    older line that quoted it in (--then) is moved out to the side file."""
    from backend.integration_text import _remove_statusline, _upsert_statusline, statusline_key_of
    own = {"type": "command", "command": command}
    base = 'python3 "/sp/statusline.py" --data-root "/data" --then-key 0123456789ab'
    text, action, kept = _upsert_statusline(json.dumps({"statusLine": own}), base, windows=windows)
    assert action == "updated" and kept == own
    assert json.loads(text)["statusLine"]["command"] == base and statusline_key_of(base) == "0123456789ab"
    back, _ = _remove_statusline(text, windows=windows, restore=kept)
    assert json.loads(back) == {"statusLine": own}
    # The older form: python3 "…" --data-root "…" --then '<command>' --was-local
    import shlex
    quoted = ('"' + command.replace('"', '\\"') + '"') if windows else shlex.quote(command)
    older = {"type": "command", "command": f'python3 "/sp/statusline.py" --data-root "/data" --then {quoted} --was-local'}
    text, _action, kept = _upsert_statusline(json.dumps({"statusLine": older}), base, windows=windows)
    assert json.loads(text)["statusLine"]["command"] == base
    if not windows or '\\"' not in quoted:
        assert kept == {**older, "command": command}


# -- an imported chat -------------------------------------------------------------------

def test_an_imported_claude_chat_gets_its_usage_by_turn(tmp_path: Path) -> None:
    t0 = datetime(2026, 10, 1, 9, 0, 0).astimezone()
    log = tmp_path / "sess.jsonl"
    call = "toolu_9"
    log.write_text("\n".join(json.dumps(r) for r in [
        _user("first", t0, "sess"),
        _asst("a1", t0 + timedelta(seconds=1), session="sess", content=[{"type": "tool_use", "id": call, "name": "Agent"}]),
        _asst("a1", t0 + timedelta(seconds=2), session="sess", out=50),
        _asst("cp", t0 + timedelta(seconds=2), session="sess", forkedFrom={"sessionId": "x"}),
        {"type": "user", "timestamp": _utc(t0 + timedelta(seconds=3)), "message": {"content": [{"type": "tool_result"}]}},
        _user("second", t0 + timedelta(minutes=5), "sess"),
        _asst("a2", t0 + timedelta(minutes=5, seconds=1), session="sess"),
    ]) + "\n", encoding="utf-8")
    sub = tmp_path / "sess" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-h.meta.json").write_text(json.dumps({"toolUseId": call}), encoding="utf-8")
    (sub / "agent-h.jsonl").write_text(json.dumps(_asst("hh", t0 + timedelta(minutes=6), session="sess")) + "\n",
                                       encoding="utf-8")
    got = sessionimport.claude_usage(log, "sess")
    assert [(x["id"], x["turn"], x["helper"], x["output"]) for x in got] == [
        ("a1", 1, "", 50), ("a2", 2, "", 10), ("hh", 1, "h", 10)]
    assert len(sessionimport.claude_turns(log)) == 2


def test_an_imported_codex_chat_gets_its_usage_by_turn(tmp_path: Path) -> None:
    at = datetime(2026, 10, 1, 9, 0, 0).astimezone()
    log = tmp_path / "rollout-a.jsonl"
    recs = [
        {"timestamp": _utc(at), "type": "turn_context", "payload": {"model": "gpt-a"}},
        {"timestamp": _utc(at), "type": "response_item", "payload": {"type": "message", "role": "user",
                                                                     "content": [{"type": "input_text", "text": "go"}]}},
        {"timestamp": _utc(at + timedelta(seconds=1)), "type": "event_msg", "payload": {
            "type": "token_count", "info": {"total_token_usage": {"total_tokens": 9},
                                            "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 40,
                                                                 "output_tokens": 9}}}},
    ]
    log.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    got = sessionimport.codex_usage(log)
    assert [(x["turn"], x["new"], x["cache"], x["model"]) for x in got] == [(1, 60, 40, "gpt-a")]


def test_the_server_adds_the_status_line_to_folders_that_have_the_hooks(tmp_path, monkeypatch) -> None:
    """A folder connected before the status line existed gets it at the
    server's start, beside its hooks; a folder without the hooks, and a
    folder that has the line, are left alone. Idempotent."""
    from backend.routers import setup as setup_mod
    from backend.integration_text import _upsert_hooks
    from backend.folderstate import hooks_installed, statusline_installed
    monkeypatch.setattr(setup_mod, "CLAUDE_USER_SETTINGS", tmp_path / "user-settings.json")
    (tmp_path / "user-settings.json").write_text(json.dumps({"statusLine": {"type": "command", "command": "echo mine"}}), encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    with_hooks, without, gone = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for d in (with_hooks, without):
        (d / ".claude").mkdir(parents=True)
    text, _ = _upsert_hooks("", "python3 /x/claude-code-capture.py --project a")
    (with_hooks / ".claude" / "settings.local.json").write_text(text, encoding="utf-8")
    (without / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
    (root / "integrations.csv").write_text(
        "project,path,created_date\n" + "\n".join(f"{n},{p},2611-01" for n, p in (("a", with_hooks), ("b", without), ("c", gone))) + "\n",
        encoding="utf-8")
    assert hooks_installed(str(with_hooks)) and not statusline_installed(str(with_hooks))
    assert setup_mod.ensure_statuslines(root) == [str(with_hooks)]
    assert statusline_installed(str(with_hooks))
    got = json.loads((with_hooks / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    side = hookshared.read_statusline_then(root, hookshared.statusline_key(with_hooks))
    assert side["from"] == "user" and hookshared.statusline_then_command(side) == "echo mine"   # runs after ours
    assert set(got["hooks"]) == {"UserPromptSubmit", "Stop", "SessionEnd", "StopFailure"}
    assert hooks_installed(str(with_hooks))                       # the hooks are kept
    assert not statusline_installed(str(without))
    assert setup_mod.ensure_statuslines(root) == []               # nothing to do the second time


# -- round 2: attribution, re-reads, events, failures ------------------------------------

#: The Claude Code config folder the status line tests run under: its key
#: names the account on every limits line.
_CONFIG_DIR = "/sp-test/claude-config"


def _env(now: str, tz: str = "UTC", config: str = _CONFIG_DIR) -> dict:
    import os
    return {**os.environ, "TZ": tz, "SP_NOW": now, "CLAUDE_CONFIG_DIR": config}


def _hook_at(root: Path, payload: dict, now: str, tz: str = "UTC") -> subprocess.CompletedProcess:
    args = [sys.executable, str(_HOOK), "--project", "alpha", "--data-root", str(root)]
    p = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=60, env=_env(now, tz))
    assert p.returncode == 0, p.stderr
    return p


def _z(local_utc: str) -> str:
    return local_utc + ".000Z"


def test_a_transcript_read_again_from_its_start_adds_nothing(root: Path, tmp_path: Path) -> None:
    """3 000 messages — far more than the end of usage.jsonl the usual check
    looks at: read again from the first byte, not one line is added."""
    t0 = datetime(2026, 11, 1, 9, 0, 0)
    _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "go"}, "2026-11-01T09:00:00")
    recs = [_user("go", t0.replace(tzinfo=timezone.utc))]
    recs += [_asst(f"msg_{i:05d}", (t0 + timedelta(seconds=1 + i)).replace(tzinfo=timezone.utc)) for i in range(3000)]
    t = _transcript(tmp_path, recs)
    stop = {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t), "last_assistant_message": "ok"}
    _hook_at(root, stop, "2026-11-01T10:00:00")
    usage = root / "projects/alpha/chats/cc-s1/usage.jsonl"
    before = usage.read_bytes()
    assert len(before.splitlines()) == 3000 and len(before) > 256 * 1024
    meta_path = root / "projects/alpha/chats/cc-s1/meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_path.write_text(json.dumps({**meta, "transcript_pos": {}}), encoding="utf-8")
    _hook_at(root, stop, "2026-11-01T10:00:05")
    assert usage.read_bytes() == before


def test_usage_typed_after_an_interrupt_gets_no_tokens_and_keeps_the_turns_in_order(root: Path, tmp_path: Path) -> None:
    """Turn 1 is interrupted (no Stop); #usage is answered without opening a
    turn; the next prompt writes the #usage exchange as turn 2 and opens
    turn 3. At turn 3's Stop, turn 1's tokens go to turn 1, not to #usage."""
    _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "work"}, "2026-11-01T09:00:00")
    t = _transcript(tmp_path, [_user("work", datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)),
                               _asst("m1", datetime(2026, 11, 1, 9, 0, 5, tzinfo=timezone.utc))])
    p = _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "#usage"}, "2026-11-01T09:01:00")
    assert json.loads(p.stdout)["decision"] == "block"
    folder = root / "projects/alpha/chats/cc-s1"
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["pending_turn"] == 1 and meta["message_count"] == 1 and len(meta["usage_deferred"]) == 1
    assert "#usage" not in (folder / "chat.md").read_text(encoding="utf-8")
    _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "again"}, "2026-11-01T09:02:00")
    _transcript(tmp_path, [_user("again", datetime(2026, 11, 1, 9, 2, 0, tzinfo=timezone.utc)),
                           _asst("m2", datetime(2026, 11, 1, 9, 2, 5, tzinfo=timezone.utc))])
    _hook_at(root, {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t),
                    "last_assistant_message": "ok"}, "2026-11-01T09:02:10")
    assert {x["id"]: x["turn"] for x in _usage(root, "cc-s1")} == {"m1": 1, "m2": 3}
    chat = (folder / "chat.md").read_text(encoding="utf-8")
    assert chat.index("## Turn 1 ·") < chat.index("## Turn 2 · 2026-11-01T09:01:00\n**User**: #usage\n**Agent**: ") \
        < chat.index("## Turn 3 ·")
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert [h[0] for h in meta["turns"]] == [1, 2, 3] and [h[2] for h in meta["turns"]] == [False, True, False]


def test_usage_typed_while_the_agent_works_is_written_after_its_reply(root: Path, tmp_path: Path) -> None:
    _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "work"}, "2026-11-01T09:00:00")
    _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "#usage-on"}, "2026-11-01T09:00:30")
    t = _transcript(tmp_path, [_user("work", datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)),
                               _asst("m1", datetime(2026, 11, 1, 9, 0, 50, tzinfo=timezone.utc))])   # after the #usage-on
    p = _hook_at(root, {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t),
                        "last_assistant_message": "ok"}, "2026-11-01T09:01:00")
    assert _usage(root, "cc-s1")[0]["turn"] == 1
    assert json.loads(p.stdout)["systemMessage"].startswith("→ ")     # #usage-on took effect for this reply
    chat = (root / "projects/alpha/chats/cc-s1/chat.md").read_text(encoding="utf-8")
    assert chat.index("**Agent**: ok") < chat.index("## Turn 2 · 2026-11-01T09:00:30\n**User**: #usage-on")


def test_the_hour_the_clocks_go_back_is_told_apart(root: Path, tmp_path: Path) -> None:
    """New York, 1 November 2026: 01:00–02:00 happens twice. Turn 1 begins at
    01:30 EDT, turn 2 at 01:10 EST (40 minutes later); a message at 01:50 EDT
    is turn 1's although its wall-clock time is later than turn 2's start."""
    if not hasattr(time, "tzset"):
        pytest.skip("Windows: a process's time zone cannot be set from TZ")
    tz = "America/New_York"
    _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "one"},
             "2026-11-01T01:30:00-04:00", tz)
    _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "two"},
             "2026-11-01T01:10:00-05:00", tz)
    t = _transcript(tmp_path, [
        _user("one", datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)),
        _asst("early", datetime(2026, 11, 1, 5, 50, tzinfo=timezone.utc)),     # 01:50 EDT
        _user("two", datetime(2026, 11, 1, 6, 10, tzinfo=timezone.utc)),
        _asst("late", datetime(2026, 11, 1, 6, 20, tzinfo=timezone.utc)),      # 01:20 EST
    ])
    _hook_at(root, {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t),
                    "last_assistant_message": "ok"}, "2026-11-01T01:25:00-05:00", tz)
    got = {x["id"]: (x["turn"], x["at"]) for x in _usage(root, "cc-s1")}
    assert got == {"early": (1, "2026-11-01T01:50:00"), "late": (2, "2026-11-01T01:20:00")}


def test_session_end_and_stop_failure_keep_the_tokens_and_close_nothing(root: Path, tmp_path: Path) -> None:
    now = datetime.now().astimezone()
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "go"})
    t = _transcript(tmp_path, [_user("go", now), _asst("m1", now + timedelta(seconds=2), out=6)])
    folder = root / "projects/alpha/chats/cc-s1"
    for event in ("StopFailure", "SessionEnd"):
        p = _hook(root, {"hook_event_name": event, "session_id": "s1", "transcript_path": str(t),
                         "last_assistant_message": "API Error: Rate limit reached", "error": "rate_limit"})
        assert p.stdout == ""
    assert [(x["id"], x["turn"], x["output"]) for x in _usage(root, "cc-s1")] == [("m1", 1, 6)]
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["pending_turn"] == 1 and "transcript_pos" not in meta and "last_stop" not in meta
    assert "**Agent**" not in (folder / "chat.md").read_text(encoding="utf-8")
    # The message went on after the failure: its last block (more output) wins.
    _transcript(tmp_path, [_asst("m1", now + timedelta(seconds=4), out=300)])
    _hook(root, {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t), "last_assistant_message": "ok"})
    lines = _usage(root, "cc-s1")
    assert [(x["id"], x["turn"], x["output"]) for x in lines] == [("m1", 1, 6), ("m1", 1, 300)]   # last wins
    assert "**Agent**: ok" in (folder / "chat.md").read_text(encoding="utf-8")


def test_the_line_after_a_reply_is_shown_once_per_turn(root: Path, tmp_path: Path) -> None:
    (root / "settings.json").write_text(json.dumps({"agent": {"usage_show": True}}), encoding="utf-8")
    now = datetime.now().astimezone()
    _hook(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "go"})
    t = _transcript(tmp_path, [_user("go", now), _asst("m1", now + timedelta(seconds=2))])
    stop = {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t), "last_assistant_message": "ok"}
    assert json.loads(_hook(root, stop).stdout)["systemMessage"].startswith("→ ")
    assert _hook(root, {**stop, "stop_hook_active": True}).stdout == ""


def _load_cc(name: str):
    spec = importlib.util.spec_from_file_location(name, _HOOK)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_usage_write_that_fails_moves_no_read_position(root: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    import io
    cc = _load_cc("sp_cc_usage_fail")
    monkeypatch.setenv("SP_NOW", "2026-11-01T09:00:00+00:00")
    now = datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)
    cap = cc.TurnCapture(root, "alpha", "cc-s1")
    cap.open_turn("go")
    t = _transcript(tmp_path, [_user("go", now), _asst("m1", now + timedelta(seconds=2))])
    sub = t.with_suffix("") / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-h.jsonl").write_text(json.dumps(_asst("h1", now + timedelta(seconds=3))) + "\n", encoding="utf-8")
    monkeypatch.setenv("SP_NOW", "2026-11-01T09:00:10+00:00")

    def full_disk(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(cc.shared, "usage_append", full_disk)
    monkeypatch.setattr(sys, "argv", ["hook", "--project", "alpha", "--data-root", str(root)])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": "s1",
                                                                "transcript_path": str(t), "last_assistant_message": "ok"})))
    assert cc.main() == 0
    meta = json.loads((cap.folder / "meta.json").read_text(encoding="utf-8"))
    assert "transcript_pos" not in meta and not (cap.folder / "helpers.json").exists()
    assert "usage not kept" in (root / ".capture" / "errors.jsonl").read_text(encoding="utf-8")
    capsys.readouterr()
    # The next Stop reads the same records again and keeps them.
    monkeypatch.undo()
    _hook_at(root, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "next"}, "2026-11-01T09:01:00+00:00")
    _hook_at(root, {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(t),
                    "last_assistant_message": "ok"}, "2026-11-01T09:01:10+00:00")
    assert {x["id"]: x["turn"] for x in _usage(root, "cc-s1")} == {"m1": 1, "h1": 1}


def test_a_codex_call_written_after_its_stop_is_kept_at_the_next(root: Path, tmp_path: Path) -> None:
    def tc(sec: int, total: int, out: int) -> dict:
        return {"timestamp": f"2026-11-01T10:00:{sec:02d}.000Z", "type": "event_msg", "payload": {
            "type": "token_count", "info": {"total_token_usage": {"total_tokens": total},
                                            "last_token_usage": {"input_tokens": 10, "output_tokens": out}}}}
    started = lambda sec, tid: {"timestamp": f"2026-11-01T10:00:{sec:02d}.000Z", "type": "event_msg",  # noqa: E731
                                "payload": {"type": "task_started", "turn_id": tid}}
    rollout = tmp_path / "rollout-x-0199-thread-abcdef12.jsonl"
    sid = "0199-thread-abcdef12"

    def write(*recs: dict) -> None:
        with open(rollout, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in recs)

    def run(payload: dict, now: str) -> None:
        args = [sys.executable, str(_HOOK), "--project", "alpha", "--data-root", str(root), "--tool", "codex"]
        subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=60, env=_env(now), check=True)

    stop = {"hook_event_name": "Stop", "session_id": sid, "transcript_path": str(rollout), "last_assistant_message": "ok"}
    run({"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": "a"}, "2026-11-01T10:00:00")
    write(started(1, "t1"), tc(2, 100, 1))
    run({**stop, "turn_id": "t1"}, "2026-11-01T10:00:10")
    write(tc(9, 200, 2))                                  # turn 1's, written after its Stop
    run({"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": "b"}, "2026-11-01T10:00:20")
    run({**stop, "turn_id": "t2"}, "2026-11-01T10:00:25")  # no task_started of t2 yet: read by time
    run({"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": "c"}, "2026-11-01T10:00:30")
    write(started(31, "t3"), tc(35, 300, 3))
    run({**stop, "turn_id": "t3"}, "2026-11-01T10:00:40")
    assert {x["id"]: x["turn"] for x in _usage(root, "codex-abcdef12")} == {"100": 1, "200": 1, "300": 3}


def test_usage_append_keeps_one_line_per_id_and_lets_more_output_win(root: Path) -> None:
    import threading
    path = root / "u.jsonl"
    line = {"turn": 1, "at": "2026-11-01T09:00:00", "id": "m1", "tool": "claude-code", "model": "x", "new": 1,
            "cache_write": 0, "cache": 0, "output": 6, "thinking": 0, "ttl": "", "helper": ""}
    barrier = threading.Barrier(8)

    def write() -> None:
        barrier.wait()
        hookshared.usage_append(path, [line])

    threads = [threading.Thread(target=write) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1        # eight writers at once: one line
    assert hookshared.usage_append(path, [{**line, "turn": 4, "output": 300}])[0]["turn"] == 1   # keeps its turn
    assert hookshared.usage_append(path, [{**line, "output": 6}]) == []                 # an older copy
    assert hookshared.usage_append(path, [{**line, "output": 300, "compacted": True}])  # a mark it did not have
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_a_compaction_with_no_message_after_it_yet_is_marked_at_the_next_stop(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", "cc-cmp")
    cap.open_turn("go")
    now = time.time()
    _, written = cap.record_usage([], compacts=[now - 1])
    assert written == []
    meta = json.loads(cap.meta_path.read_text(encoding="utf-8"))
    assert meta["usage_compacts"] == [now - 1]
    base = {"tool": "claude-code", "model": "m", "new": 1, "cache_write": 0, "cache": 0, "output": 1, "thinking": 0,
            "ttl": "", "helper": ""}
    _, written = cap.record_usage([{**base, "at": "x", "id": "a", "_t": now}, {**base, "at": "y", "id": "b", "_t": now + 1}])
    assert [x.get("compacted") for x in written] == [True, None]
    assert "usage_compacts" not in json.loads(cap.meta_path.read_text(encoding="utf-8"))


# -- the status line, exactly ------------------------------------------------------------

_STATUS_IN = (b'{"session_id": "sess-1", "model": {"id": "claude-opus-4-5", "display_name": "Opus"},'
              b' "cwd": "/secret/folder", "cost": {"total_cost_usd": 3.2},'
              b' "rate_limits": {"five_hour": {"used_percentage": 62.5, "resets_at": 1793551200},'
              b' "seven_day": {"used_percentage": 31.0, "resets_at": 1793869200}},'
              b' "context_window": {"used_percentage": 61, "context_window_size": 200000,'
              b' "current_usage": {"input_tokens": 2, "output_tokens": 1e999, "cache_read_input_tokens": 108233,'
              b' "cache_creation_input_tokens": 1622}},'
              b' "prompt_cache": {"warm": true, "expires_at": 1793541911, "hit_ratio": 0.98,'
              b' "last_miss_cause": {"model_changed": true, "ttl_expired": false}, "last_miss_at": 1793540600}}')


def _status_at(root: Path, now: str, raw: bytes = _STATUS_IN, *extra: str,
               config: str = _CONFIG_DIR) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_STATUS), "--data-root", str(root), *extra], input=raw,
                          capture_output=True, timeout=60, env=_env(now, config=config))


def test_the_status_line_writes_exactly_this(root: Path) -> None:
    p = _status_at(root, "2026-11-01T14:02:11")
    assert p.returncode == 0 and p.stdout == "SP · 5-hour 62% · week 31%\n".encode()   # 62.5: a tie, down
    assert (root / ".usage" / "limits.jsonl").read_text(encoding="utf-8") == (
        '{"at": "2026-11-01T14:02:11", "tool": "claude-code", '
        f'"account": "{hookshared.config_key(_CONFIG_DIR)}", "model": "claude-opus-4-5", "session": "sess-1", '
        '"five_hour": {"used": 62.5, "resets_at": "2026-11-01T16:40:00"}, '
        '"seven_day": {"used": 31.0, "resets_at": "2026-11-05T09:00:00"}, "source": "statusline"}\n')
    state = (root / ".usage" / "sessions" / "claude-code-sess-1.json").read_text(encoding="utf-8")
    assert json.loads(state) == {
        "at": "2026-11-01T14:02:11", "session_id": "sess-1", "model": "claude-opus-4-5",
        "context": {"used_pct": 61, "size": 200000, "input": 2, "cache": 108233, "cache_write": 1622},
        "prompt_cache": {"warm": True, "hit_ratio": 0.98, "last_miss_cause": "model_changed",
                         "expires_at": "2026-11-01T14:05:11", "last_miss_at": "2026-11-01T13:43:20"},
    }
    assert "Infinity" not in state and "secret" not in state and "cost" not in state
    # The same reading 4 minutes later: no line. 6 minutes later: one.
    _status_at(root, "2026-11-01T14:06:11")
    assert len((root / ".usage" / "limits.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    _status_at(root, "2026-11-01T14:08:12")
    assert len((root / ".usage" / "limits.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert not list((root / ".usage" / "sessions").glob(".*.tmp"))


def test_the_status_line_names_the_account_and_the_model(root: Path, tmp_path: Path) -> None:
    other = str(tmp_path / "second-account")
    _status_at(root, "2026-11-01T14:02:11")
    _status_at(root, "2026-11-01T14:02:12", _STATUS_IN.replace(b"sess-1", b"sess-2"), config=other)
    lines = [json.loads(x) for x in (root / ".usage" / "limits.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(x["account"], x["model"], x["session"]) for x in lines] == [
        (hookshared.config_key(_CONFIG_DIR), "claude-opus-4-5", "sess-1"),
        (hookshared.config_key(other), "claude-opus-4-5", "sess-2"),     # the same values, another account
    ]
    assert hookshared.config_key(other) != hookshared.config_key(_CONFIG_DIR)
    assert all(len(x["account"]) == 12 and int(x["account"], 16) >= 0 for x in lines)
    # Without CLAUDE_CONFIG_DIR: ~/.claude's key.
    assert hookshared.config_key("~/.claude") == hookshared.config_key(Path.home() / ".claude")


def _cc_line(at: datetime, model: str, five: float, week: float = 67.0, resets: int = 1793551200) -> dict:
    line = hookshared.limits_line_claude(
        {"five_hour": {"used_percentage": five, "resets_at": resets},
         "seven_day": {"used_percentage": week, "resets_at": 1793869200}},
        at.strftime("%Y-%m-%dT%H:%M:%S"), account="aaaaaaaaaaaa", model=model, session=model[-8:])
    assert line is not None
    return line


def _limit_lines(root: Path) -> list[dict]:
    return [json.loads(x) for x in (root / ".usage" / "limits.jsonl").read_text(encoding="utf-8").splitlines()]


def test_two_models_alternating_write_only_what_is_new(root: Path) -> None:
    """Two chats on two models update their status lines in turn, every
    second; the idle one sends its last, older reading again. The account's
    limits are one series: a line only for a higher percentage, a later
    reset, or every five minutes — not one per update."""
    base = datetime(2026, 11, 1, 14, 0, 0)
    for s in list(range(20)) + [360, 361]:
        at = base + timedelta(seconds=s)
        line = _cc_line(at, "claude-opus-5-5", 57.0 if s >= 10 else 56.0) if s % 2 == 0 \
            else _cc_line(at, "claude-fable-5-1", 4.0, 60.0)
        hookshared.limits_append(root, line, now=at.timestamp())
    assert [(x["model"], x["at"][-5:], x["five_hour"]["used"]) for x in _limit_lines(root)] == [
        ("claude-opus-5-5", "00:00", 56.0),
        ("claude-opus-5-5", "00:10", 57.0),      # higher: new
        ("claude-opus-5-5", "06:00", 57.0),      # five minutes on: the heartbeat
    ]


def test_the_writer_skips_lower_readings_of_the_same_reset(root: Path) -> None:
    base = datetime(2026, 11, 1, 14, 0, 0)
    for s, v in enumerate((38.0, 39.0, 26.0, 40.0, 40.0, 39.0)):
        at = base + timedelta(seconds=s)
        hookshared.limits_append(root, _cc_line(at, "claude-opus-5-5", v), now=at.timestamp())
    at = base + timedelta(seconds=10)    # a new window starts at its own reading
    hookshared.limits_append(root, _cc_line(at, "claude-opus-5-5", 1.0, resets=1793569200), now=at.timestamp())
    at = base + timedelta(seconds=11)    # the window before, sent again: old news
    hookshared.limits_append(root, _cc_line(at, "claude-opus-5-5", 40.0), now=at.timestamp())
    assert [x["five_hour"]["used"] for x in _limit_lines(root)] == [38.0, 39.0, 40.0, 1.0]


def test_the_status_line_sweeps_what_a_killed_run_left_once_an_hour(root: Path) -> None:
    import os
    folder = root / ".usage" / "sessions"
    folder.mkdir(parents=True)
    old_tmp, fresh_tmp = folder / ".claude-code-x.json.111.tmp", folder / ".claude-code-y.json.222.tmp"
    week_old = folder / "claude-code-old.json"
    for f in (old_tmp, fresh_tmp, week_old):
        f.write_text("{}", encoding="utf-8")
    t = time.time()
    os.utime(old_tmp, (t - 120, t - 120))
    os.utime(week_old, (t - 8 * 86400, t - 8 * 86400))
    _status_at(root, datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    assert not old_tmp.exists() and not week_old.exists() and fresh_tmp.exists()
    os.utime(fresh_tmp, (t - 120, t - 120))
    _status_at(root, datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    assert fresh_tmp.exists()                    # swept within the hour already: left for the next sweep
    # Killed while the operator's own line runs: its state file is whole, no temp file is left.
    proc = subprocess.Popen([sys.executable, str(_STATUS), "--data-root", str(root), "--then", "sleep 30"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert proc.stdin is not None
    proc.stdin.write(_STATUS_IN.replace(b"sess-1", b"sess-k"))
    proc.stdin.close()
    target = folder / "claude-code-sess-k.json"
    deadline = time.time() + 30
    while not target.exists() and time.time() < deadline:
        time.sleep(0.05)
    proc.kill()
    proc.wait(timeout=30)
    assert json.loads(target.read_text(encoding="utf-8"))["session_id"] == "sess-k"
    assert [f.name for f in folder.glob(".*.tmp")] == [fresh_tmp.name]


def test_the_status_line_runs_the_line_its_side_file_names(root: Path, tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    (folder / ".claude").mkdir(parents=True)
    user = tmp_path / "user-settings.json"
    key = hookshared.statusline_key(folder)
    side = root / ".usage" / "statusline-then" / f"{key}.json"
    side.parent.mkdir(parents=True)
    side.write_text(json.dumps({"from": "user", "command": "echo old", "folder": str(folder),
                                "user_settings": str(user)}), encoding="utf-8")
    run = lambda: _status_at(root, "2026-11-01T14:02:11", b'{"session_id": "s"}', "--then-key", key).stdout.replace(b"\r\n", b"\n")  # noqa: E731
    assert run() == b""                                         # nothing in either settings file now
    user.write_text(json.dumps({"statusLine": {"type": "command", "command": "echo from-user"}}), encoding="utf-8")
    assert run() == b"from-user\n"
    (folder / ".claude" / "settings.json").write_text(
        "﻿" + json.dumps({"statusLine": {"type": "command", "command": "echo from-project"}}), encoding="utf-8")
    assert run() == b"from-project\n"                           # the shared project file outranks the user's
    side.write_text(json.dumps({"from": "local", "command": "echo kept"}), encoding="utf-8")
    assert run() == b"kept\n"
    # Our own line inside the operator's (a script that calls ours): it runs nothing more.
    nested = f'"{sys.executable}" "{_STATUS}" --data-root "{root}" --then-key {key}'
    side.write_text(json.dumps({"from": "local", "command": nested}), encoding="utf-8")
    assert run() == b""
    assert _status_at(root, "2026-11-01T14:02:11", b'{}', "--then-key", "../../etc").returncode == 0


# -- found by Codex's review of this round's diff -----------------------------------------

def test_a_codex_call_kept_under_its_old_key_is_not_kept_twice(root: Path) -> None:
    path = root / "u.jsonl"
    old = {"turn": 3, "at": "2026-11-01T10:00:05", "id": "2026-11-01T10:00:05.000Z", "tool": "codex", "model": "g",
           "new": 12000, "cache_write": 0, "cache": 12000, "output": 3000, "thinking": 500, "ttl": "", "helper": ""}
    path.write_text(json.dumps(old) + "\n", encoding="utf-8")
    assert hookshared.usage_append(path, [{**old, "id": "30000"}]) == []
    assert hookshared.usage_append(path, [{**old, "id": "31000", "output": 1}])    # another call


def test_a_codex_call_with_the_marks_own_time_is_still_read(tmp_path: Path) -> None:
    rollout = tmp_path / "rollout-a.jsonl"
    ts = "2026-11-01T10:00:05.000Z"
    rollout.write_text("\n".join(json.dumps(r) for r in [
        {"timestamp": ts, "type": "event_msg", "payload": {"type": "task_started", "turn_id": "t1"}},
        {"timestamp": ts, "type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"total_tokens": 10}, "last_token_usage": {"input_tokens": 10}}}},
    ]) + "\n", encoding="utf-8")
    lines, _ = hookshared.codex_turn_usage(rollout, since=hookshared.epoch_of(ts))
    assert [x["id"] for x in lines] == ["10"]


def test_helpers_started_in_copied_history_stay_out_with_the_helpers_they_started() -> None:
    first = 1_000_000.0
    lines = [{"at": "a", "id": "h", "helper": "x", "tool_use": "A", "_t": first - 3600},
             {"at": "b", "id": "n", "helper": "y", "tool_use": "N", "_t": first - 3500},
             {"at": "c", "id": "ok", "helper": "z", "tool_use": "B", "_t": first + 5}]
    starts = {"A": {"t": first - 4000, "parent": ""}, "N": {"t": first - 3600, "parent": "A"},
              "B": {"t": first + 1, "parent": ""}}
    calls: dict[str, int] = {}
    out, _ = hookshared.assign_turns(lines, [[1, first, False]], calls=calls, starts=starts, cutoff=first - 60)
    assert [x["id"] for x in out] == ["ok"] and calls == {"B": 1}


def test_setup_again_from_a_moved_data_folder_keeps_the_operators_line(tmp_path: Path, monkeypatch) -> None:
    from backend.routers import setup as setup_mod
    monkeypatch.setattr(setup_mod, "CLAUDE_USER_SETTINGS", tmp_path / "user.json")
    old_root, new_root, folder = tmp_path / "old", tmp_path / "new", tmp_path / "proj"
    for d in (old_root, new_root, folder):
        d.mkdir()
    own = {"type": "command", "command": "echo mine"}
    text, _action, side = setup_mod._statusline_plan(json.dumps({"statusLine": own}), folder, old_root)
    setup_mod._write_side(side)
    text2, _action, side2 = setup_mod._statusline_plan(text, folder, new_root)
    assert side2 is not None and side2[1]["entry"] == own and str(new_root) in str(side2[0])
    assert f'--data-root "{new_root.as_posix()}"' in json.loads(text2)["statusLine"]["command"]
