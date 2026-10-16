"""The capture core + tool adapters — automatic verbatim chat capture."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


capture = _load("sp_capture", "capture.py")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    # Setup makes the data root; the hook refuses to build one itself.
    (tmp_path / "data").mkdir(exist_ok=True)
    return tmp_path / "data"


def test_two_phase_turn_is_verbatim_and_multiline(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", "cc-abc12345")
    signals = cap.open_turn("First line of the question\nSecond line, verbatim")
    assert signals["turn_number"] == 1
    cap.complete_turn("The answer.\n\nWith paragraphs.")

    chat = (root / "projects/alpha/chats/cc-abc12345/chat.md").read_text(
        encoding="utf-8"
    )
    assert "**User**: First line of the question\nSecond line, verbatim" in chat
    assert "**Agent**: The answer.\n\nWith paragraphs." in chat

    meta = json.loads(
        (root / "projects/alpha/chats/cc-abc12345/meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta["message_count"] == 1
    assert "pending_turn" not in meta
    assert meta["capture"] == "hooks"


def test_multiline_turns_round_trip_through_sessions_parser(root: Path) -> None:
    from backend.sessions import parse_turns

    cap = capture.TurnCapture(root, "alpha", "cc-x")
    cap.open_turn("Q one\nwith detail")
    cap.complete_turn("A one\nlonger answer")
    cap.open_turn("Q two")
    cap.complete_turn("A two")

    turns = parse_turns(root / "projects/alpha/chats/cc-x/chat.md")
    assert len(turns) == 2
    assert turns[0].user_summary == "Q one\nwith detail"
    assert turns[0].agent_summary == "A one\nlonger answer"
    assert turns[1].agent_summary == "A two"


def test_decision_hint_and_refresh_signals(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", "cc-y")
    signals = cap.open_turn("we decided to use Redis for counters")
    assert signals["decision_hint"] is not None

    (root / "settings.json").write_text(
        json.dumps({"agent": {"contract_refresh_turns": 2}}), encoding="utf-8"
    )
    cap.complete_turn("ok")
    signals = cap.open_turn("second turn")
    assert signals["contract_refresh_due"] is True


def test_full_turn_one_shot(root: Path) -> None:
    cap = capture.TurnCapture(root, "beta", "codex-t1")
    cap.full_turn("the input", "the final message")
    chat = (root / "projects/beta/chats/codex-t1/chat.md").read_text(
        encoding="utf-8"
    )
    assert "**User**: the input" in chat
    assert "**Agent**: the final message" in chat


def test_claude_code_adapter_end_to_end(root: Path, tmp_path: Path) -> None:
    script = _HOOKS / "claude-code-capture.py"

    def run(payload: dict) -> str:
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha",
             "--data-root", str(root)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        assert proc.returncode == 0
        return proc.stdout

    out = run({
        "hook_event_name": "UserPromptSubmit",
        "session_id": "sess1234abcd",
        "prompt": "let's use postgres for this",
    })
    # The decision phrase surfaces as an injected context notice.
    assert "[slightly-parallel]" in out

    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        "\n".join([
            json.dumps({"type": "user", "message": {"content": "hi"}}),
            json.dumps({
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "name": "Bash"},
                    {"type": "text", "text": "Interim thought"},
                ]},
            }),
            json.dumps({
                "type": "assistant",
                "message": {"content": [
                    {"type": "text", "text": "Final answer, verbatim."},
                ]},
            }),
            # /rename or /branch <name> — the user's own name for the chat.
            json.dumps({"type": "custom-title", "customTitle": "postgres switch",
                        "sessionId": "sess1234abcd"}),
        ]),
        encoding="utf-8",
    )
    run({
        "hook_event_name": "Stop",
        "session_id": "sess1234abcd",
        "transcript_path": str(transcript),
    })

    chat = (root / "projects/alpha/chats/cc-sess1234/chat.md").read_text(
        encoding="utf-8"
    )
    assert "**User**: let's use postgres for this" in chat
    assert "**Agent**: Final answer, verbatim." in chat
    meta = json.loads(
        (root / "projects/alpha/chats/cc-sess1234/meta.json").read_text(encoding="utf-8")
    )
    assert meta["chat_title"] == "postgres switch"
    assert meta["agent_name"] == "cc-sess1234"  # the title never overwrites the name


def test_codex_project_resolution(root: Path, tmp_path: Path) -> None:
    codex = _load("sp_codex", "codex-capture.py")
    outer = tmp_path / "code"
    inner = outer / "my-app"
    inner.mkdir(parents=True)
    root.mkdir(parents=True, exist_ok=True)
    (root / "integrations.csv").write_text(
        "project,path,created_date\n"
        f"outer,{outer},2608-14\n"
        f"my-app,{inner},2608-14\n",
        encoding="utf-8",
    )
    # Longest prefix wins; unregistered folders resolve to nothing.
    assert codex.resolve_project(root, str(inner / "src")) == "my-app"
    assert codex.resolve_project(root, str(outer)) == "outer"
    assert codex.resolve_project(root, str(tmp_path / "elsewhere")) == ""


def test_system_payloads_are_not_turns(root: Path, tmp_path: Path) -> None:
    script = _HOOKS / "claude-code-capture.py"

    def run(payload: dict) -> None:
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha",
             "--data-root", str(root)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        assert proc.returncode == 0

    # A background-task notification fires the same prompt event…
    run({
        "hook_event_name": "UserPromptSubmit",
        "session_id": "sys12345",
        "prompt": "<task-notification>\n<task-id>x</task-id>\n</task-notification>",
    })
    # …and its Stop must not create a phantom user-less turn either.
    transcript = tmp_path / "t2.jsonl"
    transcript.write_text(
        json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "No response requested."}]},
        }),
        encoding="utf-8",
    )
    run({
        "hook_event_name": "Stop",
        "session_id": "sys12345",
        "transcript_path": str(transcript),
    })

    assert not (root / "projects/alpha/chats/cc-sys12345").exists()


def test_pasted_structure_is_escaped_and_round_trips(root: Path) -> None:
    from backend.sessions import parse_turns

    cap = capture.TurnCapture(root, "alpha", "cc-esc")
    pasted = "look at this:\n## Turn 1 · 2026-08-14T09:00:00\n**User**: quoted\n**Agent**: quoted too"
    cap.open_turn(pasted)
    cap.complete_turn("noted — that quoted turn is content, not structure")

    turns = parse_turns(root / "projects/alpha/chats/cc-esc/chat.md")
    assert len(turns) == 1  # the quoted header did NOT become a turn
    assert "## Turn 1 · 2026-08-14T09:00:00" in turns[0].user_summary
    assert "**User**: quoted" in turns[0].user_summary


def test_duplicate_pending_message_captured_once(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", "cc-dup")
    first = cap.open_turn("same message")
    second = cap.open_turn("same message")  # resend before any answer
    assert first["turn_number"] == second["turn_number"] == 1
    chat = (root / "projects/alpha/chats/cc-dup/chat.md").read_text(
        encoding="utf-8"
    )
    assert chat.count("same message") == 1

    # After an answer, the same text is a legitimate new turn.
    cap.complete_turn("answered")
    third = cap.open_turn("same message")
    assert third["turn_number"] == 2


def test_agent_rename_endpoint(root: Path) -> None:
    from fastapi.testclient import TestClient
    from backend.server import create_app

    cap = capture.TurnCapture(root, "alpha", "cc-rename01")
    cap.open_turn("hello")
    cap.complete_turn("hi")

    app = create_app(data_root=root, watch=False)
    with TestClient(app) as client:
        r = client.post(
            "/api/agents/cc-rename01/rename", json={"name": "auth refactor"}
        )
        assert r.status_code == 200
        agents = {
            a["agent_id"]: a for a in client.get("/api/snapshot").json()["agents"]
        }
        assert agents["cc-rename01"]["agent_name"] == "auth refactor"

        # A later captured turn preserves the chosen name.
        cap.open_turn("next")
        cap.complete_turn("ok")
        r2 = client.get("/api/agent/cc-rename01")
        assert r2.json()["agent"]["agent_name"] == "auth refactor"

        assert client.post(
            "/api/agents/nope/rename", json={"name": "x"}
        ).status_code == 404
        assert client.post(
            "/api/agents/cc-rename01/rename", json={"name": ""}
        ).status_code == 422


def test_origin_is_recorded_and_served(root: Path, tmp_path: Path) -> None:
    """The hook records tool/session/cwd; the API serves them on the agent."""
    script = _HOOKS / "claude-code-capture.py"
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "abcd1234-full-session-id",
        "cwd": "/home/user/projects/alpha",
        "prompt": "hello",
    }
    proc = subprocess.run(
        [sys.executable, str(script), "--project", "alpha", "--data-root", str(root)],
        input=json.dumps(payload), capture_output=True, text=True,
    )
    assert proc.returncode == 0
    meta = json.loads(
        (root / "projects/alpha/chats/cc-abcd1234/meta.json").read_text(encoding="utf-8")
    )
    assert meta["tool"] == "claude-code"
    assert meta["session_ref"] == "abcd1234-full-session-id"
    assert meta["cwd"] == "/home/user/projects/alpha"

    from fastapi.testclient import TestClient
    from backend.server import create_app
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as client:
        a = client.get("/api/project/alpha").json()["agents"][0]
        assert (a["tool"], a["session_ref"], a["cwd"]) == (
            "claude-code", "abcd1234-full-session-id", "/home/user/projects/alpha"
        )


# ---------------------------------------------------------------------------
# The Stop hook anchors the reply to the prompt, never to the end of the file
# ---------------------------------------------------------------------------


def _rec(kind: str, content) -> str:
    return json.dumps({"type": kind, "message": {"content": content}})


def _text(t: str) -> list:
    return [{"type": "text", "text": t}]


def test_stop_reads_only_text_written_after_the_last_prompt(tmp_path: Path) -> None:
    cc = _load("sp_cc_anchor", "claude-code-capture.py")
    t = tmp_path / "t.jsonl"
    # An earlier turn's answer, then a new prompt with nothing after it yet.
    t.write_text("\n".join([
        _rec("user", "first question"),
        _rec("assistant", _text("first answer")),
        _rec("user", "second question"),
    ]), encoding="utf-8")
    assert cc.read_transcript(str(t))[0] == ""  # not "first answer"

    # A tool result is not a human prompt: text after it still belongs to the turn.
    t.write_text("\n".join([
        _rec("user", "first question"),
        _rec("assistant", _text("first answer")),
        _rec("user", "second question"),
        _rec("assistant", [{"type": "tool_use", "name": "Bash"}]),
        _rec("user", [{"type": "tool_result", "content": "ok"}]),
        _rec("assistant", [{"type": "thinking", "thinking": "…"}]),
        _rec("assistant", _text("second answer")),
    ]), encoding="utf-8")
    assert cc.read_transcript(str(t))[0] == "second answer"


def test_stop_without_a_persisted_reply_closes_the_turn_as_a_gap(root: Path, tmp_path: Path) -> None:
    cc = _load("sp_cc_gap", "claude-code-capture.py")
    cc._STOP_RETRIES = 1
    cc._STOP_RETRY_S = 0.01
    script = _HOOKS / "claude-code-capture.py"
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join([
        _rec("user", "send me a link"),
        _rec("assistant", _text("http://example/link")),
        _rec("user", "write the press release"),
        _rec("assistant", [{"type": "thinking", "thinking": "…"}]),  # the text never landed
    ]), encoding="utf-8")

    def run(payload: dict) -> None:
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha", "--data-root", str(root)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr

    run({"hook_event_name": "UserPromptSubmit", "session_id": "gap12345", "prompt": "write the press release"})
    run({"hook_event_name": "Stop", "session_id": "gap12345", "transcript_path": str(t)})

    chat = (root / "projects/alpha/chats/cc-gap12345/chat.md").read_text(encoding="utf-8")
    assert "**Agent**: (reply not in transcript)" in chat
    assert "http://example/link" not in chat  # the previous answer was not inherited
    meta = json.loads((root / "projects/alpha/chats/cc-gap12345/meta.json").read_text(encoding="utf-8"))
    assert "pending_turn" not in meta  # the next turn starts clean

    # The next turn is unaffected by the gap before it.
    t.write_text(t.read_text(encoding="utf-8") + "\n" + "\n".join([
        _rec("user", "and now?"),
        _rec("assistant", _text("now this")),
    ]), encoding="utf-8")
    run({"hook_event_name": "UserPromptSubmit", "session_id": "gap12345", "prompt": "and now?"})
    run({"hook_event_name": "Stop", "session_id": "gap12345", "transcript_path": str(t)})
    chat = (root / "projects/alpha/chats/cc-gap12345/chat.md").read_text(encoding="utf-8")
    assert chat.count("**Agent**: ") == 2 and chat.rstrip().endswith("**Agent**: now this")


def test_stop_prefers_the_reply_in_the_payload_over_the_transcript(root: Path, tmp_path: Path) -> None:
    """The transcript may lack the final text entirely; the payload has it."""
    script = _HOOKS / "claude-code-capture.py"
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join([
        _rec("user", "write the press release"),
        _rec("assistant", [{"type": "thinking", "thinking": "…"}]),  # text record never written
        json.dumps({"type": "custom-title", "customTitle": "pr"}),
    ]), encoding="utf-8")

    def run(payload: dict) -> None:
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha", "--data-root", str(root)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr

    run({"hook_event_name": "UserPromptSubmit", "session_id": "pay12345", "prompt": "write the press release"})
    run({"hook_event_name": "Stop", "session_id": "pay12345", "transcript_path": str(t),
         "last_assistant_message": "## 1.1 What got built\n\nthe whole thing"})

    folder = root / "projects/alpha/chats/cc-pay12345"
    chat = (folder / "chat.md").read_text(encoding="utf-8")
    assert "**Agent**: ## 1.1 What got built\n\nthe whole thing" in chat
    assert "reply not in transcript" not in chat
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["chat_title"] == "pr"  # the title still comes from the transcript
    assert meta["last_stop"]["found_text"] is True
    assert "last_assistant_message" in meta["last_stop"]["keys"]


# ---------------------------------------------------------------------------
# Codex — the legacy notify event and the hooks path
# ---------------------------------------------------------------------------


def test_codex_notify_reads_the_real_field_names_and_keys_the_agent_by_thread(root: Path, tmp_path: Path) -> None:
    script = _HOOKS / "codex-capture.py"
    proj = tmp_path / "my-app"
    proj.mkdir()
    root.mkdir(parents=True, exist_ok=True)
    (root / "integrations.csv").write_text(
        f"project,path,created_date\nmy-app,{proj},2608-29\n", encoding="utf-8"
    )

    def run(event: dict) -> None:
        proc = subprocess.run(
            [sys.executable, str(script), "--data-root", str(root), json.dumps(event)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr

    # Two turns of one thread — Codex's real kebab-case payload.
    for turn, (q, a) in enumerate([("first?", "first."), ("second?", "second.")], 1):
        run({
            "type": "agent-turn-complete", "thread-id": "thread-abcdef12", "turn-id": f"turn-{turn}",
            "cwd": str(proj), "input-messages": [q], "last-assistant-message": a,
        })
    chats = sorted(p.name for p in (root / "projects/my-app/chats").iterdir())
    assert chats == ["codex-abcdef12"]  # one agent per thread, named by the end of its id
    chat = (root / "projects/my-app/chats/codex-abcdef12/chat.md").read_text(encoding="utf-8")
    assert "**User**: first?\n**Agent**: first." in chat
    assert "**User**: second?\n**Agent**: second." in chat
    meta = json.loads((root / "projects/my-app/chats/codex-abcdef12/meta.json").read_text(encoding="utf-8"))
    assert meta["tool"] == "codex" and meta["session_ref"] == "thread-abcdef12"


def test_hooks_adapter_serves_codex_with_its_own_prefix_and_no_stdout(root: Path, tmp_path: Path) -> None:
    script = _HOOKS / "claude-code-capture.py"

    def run(payload: dict) -> str:
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha", "--data-root", str(root), "--tool", "codex"],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    out = run({"hook_event_name": "UserPromptSubmit", "session_id": "0195c0de-1234", "cwd": str(tmp_path),
               "prompt": "let's use postgres for this"})
    assert out == ""  # Codex reads stdout as control JSON, so nothing is printed
    run({"hook_event_name": "Stop", "session_id": "0195c0de-1234", "transcript_path": None,
         "last_assistant_message": "Done."})
    folder = root / "projects/alpha/chats/codex-c0de1234"
    chat = (folder / "chat.md").read_text(encoding="utf-8")
    assert "**User**: let's use postgres for this\n**Agent**: Done." in chat
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["tool"] == "codex"
    crumbs = list((root / ".sessions").glob("*.json"))
    assert crumbs and json.loads(crumbs[0].read_text(encoding="utf-8"))["agent_id"] == "codex-c0de1234"


def test_opencode_plugin_is_valid_and_uses_the_hook_and_the_fetch() -> None:
    src = (_HOOKS / "slightly-parallel-opencode.js").read_text(encoding="utf-8")
    assert "'chat.message'" in src and "session.idle" in src and "client.session.messages" in src
    assert "--close-if-missing" in src
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    proc = subprocess.run([node, "--input-type=module", "--check"], input=src, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr



def test_evidence_notice_names_the_task(tmp_path):
    """#evidence is typed by hand, so the hook says which task it means."""
    root = tmp_path / "data"
    root.mkdir()
    (root / "tasks.csv").write_text("id,title\ntk_0e571cfa,Evidences evolution\n", encoding="utf-8")
    cap = capture.TurnCapture(root, "alpha", "cc-ev000001")

    # No task named yet in this chat.
    none = capture.format_signals(cap.open_turn("let's #evidence"))
    assert "no task named in this chat" in none
    cap.complete_turn("which task?")

    # A task is handed over; later #evidence means that one.
    cap.open_turn("tk_0e571cfa · Evidences evolution\nplease do it")
    cap.complete_turn("done")
    later = capture.format_signals(cap.open_turn("ok, #evidence"))
    assert '#evidence for tk_0e571cfa · Evidences evolution' in later
    assert 'task_evidence_ask {id: "tk_0e571cfa"}' in later
    cap.complete_turn("posted")

    # An id in the message itself wins over the remembered one.
    exact = capture.format_signals(cap.open_turn("#evidence tk_aaaaaaaa"))
    assert "#evidence for tk_aaaaaaaa" in exact

    # A word that only contains the tag is not the command.
    cap.complete_turn("ok")
    assert "#evidence" not in capture.format_signals(cap.open_turn("see docs#evidence-panel"))


def test_task_and_now_notices_carry_the_lane_the_board_has(root: Path) -> None:
    """#task {lane} / #now {lane}: the notice names the lane as the board spells
    it, or says it is not there and lists the board's lanes."""
    import csv
    with open(root / "tasks.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "project", "title", "status", "lane", "assignee", "archived_at"])
        w.writerow(["tk_1", "alpha", "a", "todo", "Bugs", "Bugs", ""])
        w.writerow(["tk_2", "alpha", "b", "todo", "", "Kanban Board", ""])
        w.writerow(["tk_3", "alpha", "c", "todo", "Gone", "Gone", "2026-09-01T10:00:00"])
        w.writerow(["tk_4", "beta", "d", "todo", "Other", "Other", ""])
    cap = capture.TurnCapture(root, "alpha", "cc-lane0001")
    now = capture.format_signals(cap.open_turn("#now {bugs} fix the login timeout"))
    line = next(x for x in now.splitlines() if x.startswith("[slightly-parallel] #now"))
    assert "write-a-task" in line and "status doing" in line and "The lane: Bugs" in line
    cap.complete_turn("ok")
    task = capture.format_signals(cap.open_turn("#task {ux} the form accepts an empty trigger_id"))
    line = next(x for x in task.splitlines() if x.startswith("[slightly-parallel] #task"))
    assert "'ux' is not on the board" in line and "Bugs, Kanban Board" in line and "Gone" not in line and "Other" not in line
    assert "ask the operator" in line
    cap.complete_turn("which lane?")
    plain = capture.format_signals(cap.open_turn("#now fix it"))
    assert "lane" not in next(x for x in plain.splitlines() if x.startswith("[slightly-parallel] #now")).lower().split("start with")[1]


def test_every_answered_turn_stamps_its_start_and_end(root: Path) -> None:
    cap = capture.TurnCapture(root, "alpha", "cc-abc12345")
    cap.open_turn("one")
    cap.complete_turn("first answer")
    cap.open_turn("two")
    cap.complete_turn("")          # no reply text: still open, nothing stamped
    folder = root / "projects/alpha/chats/cc-abc12345"
    lines = [json.loads(x) for x in (folder / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(x["turn"], x["source"]) for x in lines] == [(1, "hook")]
    assert lines[0]["start"] <= lines[0]["end"]
    # The unanswered turn keeps its start until it closes.
    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["pending_started"]
    cap.complete_turn("", close_if_missing=True)
    lines = (folder / "turns.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["turn"] == 2
    assert "pending_started" not in json.loads((folder / "meta.json").read_text(encoding="utf-8"))


def test_the_hook_times_the_answer_and_its_helpers_from_the_transcript(root: Path, tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timedelta

    cap = capture.TurnCapture(root, "alpha", "cc-abc12345")
    cap.open_turn("do it")
    meta_path = root / "projects/alpha/chats/cc-abc12345/meta.json"
    started = datetime.fromisoformat(json.loads(meta_path.read_text(encoding="utf-8"))["pending_started"])
    z = lambda m: (started + timedelta(minutes=m)).astimezone().isoformat()  # noqa: E731
    session = tmp_path / "sess.jsonl"
    session.write_text("".join(json.dumps(r) + "\n" for r in [
        {"type": "user", "timestamp": z(0), "message": {"content": "do it"}},
        {"type": "assistant", "timestamp": z(1), "message": {"content": []}},
    ]), encoding="utf-8")
    helpers = tmp_path / "sess" / "subagents"
    helpers.mkdir(parents=True)
    for name in ("agent-a", "agent-b"):   # two helpers, the same ten minutes
        (helpers / f"{name}.jsonl").write_text("".join(
            json.dumps({"type": "assistant", "timestamp": z(m)}) + "\n" for m in (1, 6, 11)), encoding="utf-8")
    # The answer lands at +12 min (the hook's clock is now; move it there).
    monkeypatch.setattr(capture, "now_iso", lambda: (started + timedelta(minutes=12)).isoformat())
    cap.complete_turn("done", transcript=str(session))
    line = json.loads((root / "projects/alpha/chats/cc-abc12345/turns.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert line["helper_sec"] == 2 * 10 * 60            # the work: both helpers, added up
    [[a, b]] = line["busy"]                              # busy for you: one stretch
    assert (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() == 12 * 60


def test_a_tool_without_a_session_file_hands_its_times_over(root: Path, monkeypatch) -> None:
    # OpenCode's plugin: epoch-ms times of its messages, and of a child session.
    from datetime import datetime, timedelta

    cap = capture.TurnCapture(root, "alpha", "oc-1234abcd")
    cap.open_turn("go")
    meta = json.loads((root / "projects/alpha/chats/oc-1234abcd/meta.json").read_text(encoding="utf-8"))
    started = datetime.fromisoformat(meta["pending_started"])
    ms = lambda m: (started + timedelta(minutes=m)).timestamp() * 1000  # noqa: E731
    monkeypatch.setattr(capture, "now_iso", lambda: (started + timedelta(minutes=10)).isoformat())
    cap.complete_turn("done", times={"points": [ms(1), ms(9)], "helpers": [[ms(2), ms(7)]]})
    line = json.loads((root / "projects/alpha/chats/oc-1234abcd/turns.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert line["helper_sec"] == 5 * 60 and line["active_sec"] == 10 * 60


def test_a_codex_session_file_reads_as_activity(tmp_path: Path) -> None:
    from datetime import datetime

    tt = capture._turntimes()
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text("".join(json.dumps(r) + "\n" for r in [
        {"timestamp": "2026-09-29T08:00:05Z", "type": "session_meta", "payload": {}},
        {"timestamp": "2026-09-29T08:01:00Z", "type": "response_item", "payload": {"type": "message"}},
        {"timestamp": "2026-09-29T08:02:00Z", "type": "event_msg", "payload": {"type": "token_count"}},
    ]), encoding="utf-8")
    got = tt.points_of(rollout)
    assert len(got) == 2 and all(isinstance(p, datetime) for p in got)


def test_a_helper_agents_report_is_not_the_operator_speaking() -> None:
    # Its #tags describe features; captured as the operator's, each one
    # kept a vision, a rule, a problem, a skill and an artifact.
    cc = _load("sp_cc_capture", "claude-code-capture.py")
    report = 'Another Claude session sent a message:\n<agent-message from="a1">\n  #vision, #rule and #skill keep a message.'
    assert cc.is_system_payload(report)
    assert cc.is_system_payload('<agent-message from="a1">#problem …</agent-message>')
    assert not cc.is_system_payload("#vision the board is the spine")


def test_a_chat_keeps_the_folder_it_started_in(root: Path) -> None:
    """The agent moves into a subfolder; the chat is still resumed where it began."""
    script = _HOOKS / "claude-code-capture.py"
    for cwd in ("/home/user/projects/alpha", "/home/user/projects/alpha/frontend"):
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "abcd1234-full-session-id",
                   "cwd": cwd, "prompt": "hello"}
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha", "--data-root", str(root)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        assert proc.returncode == 0
    meta = json.loads(
        (root / "projects/alpha/chats/cc-abcd1234/meta.json").read_text(encoding="utf-8")
    )
    assert meta["cwd"] == "/home/user/projects/alpha"


def test_two_chats_in_one_folder_are_told_apart_by_their_process(root: Path, tmp_path: Path) -> None:
    """Each chat leaves its own file with the processes above its hook; an
    MCP client that shares one gets that chat, not the newest."""
    import time as _time
    from fastapi.testclient import TestClient
    from backend.server import create_app

    cwd = str(tmp_path / "proj")
    script = _HOOKS / "claude-code-capture.py"
    for session in ("aaaa1111-first", "bbbb2222-second"):
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha", "--data-root", str(root)],
            input=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": session, "cwd": cwd, "prompt": "hi"}),
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
    folder = next((root / ".sessions").glob("*/"))
    files = {f.stem: f for f in folder.glob("*.json")}
    assert set(files) == {"aaaa1111-first", "bbbb2222-second"}
    # The hook ran under this test: its parents include this process.
    import os
    assert os.getpid() in json.loads(files["aaaa1111-first"].read_text(encoding="utf-8"))["pids"]

    # Give each chat a tool process of its own, with a shared terminal above both.
    for stem, tool_pid in (("aaaa1111-first", 5001), ("bbbb2222-second", 5002)):
        crumb = json.loads(files[stem].read_text(encoding="utf-8"))
        crumb["pids"] = [9001 if stem.startswith("a") else 9002, tool_pid, 4000]
        files[stem].write_text(json.dumps(crumb), encoding="utf-8")

    app = create_app(data_root=root, watch=False)
    with TestClient(app) as client:
        who = lambda pids: client.get("/api/whoami", params={"cwd": cwd, "pids": pids}).json()["agent_id"]  # noqa: E731
        assert who("5001,4000") == "cc-aaaa1111"       # the first chat's server, though the second is newer
        assert who("5002,4000") == "cc-bbbb2222"
        assert who("7777,4000") == "cc-bbbb2222"       # only the terminal is shared: the newer of the two
        assert who("7777") == "cc-bbbb2222"            # nothing shared: the newest chat in the folder
        assert client.get("/api/whoami", params={"cwd": cwd}).json()["agent_id"] == "cc-bbbb2222"
    assert _time.time() > 0


def test_the_files_a_turns_tools_touched_are_stamped_without_git(root: Path, tmp_path: Path) -> None:
    """A folder with no repository: the work stamp still says which files the
    turn's Edit and Write calls changed, relative to the chat's folder, so a
    scan has a file list where git has nothing."""
    script = _HOOKS / "claude-code-capture.py"
    folder = tmp_path / "nogit"
    (folder / "src").mkdir(parents=True)

    def run(payload: dict) -> None:
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha", "--data-root", str(root)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr

    run({"hook_event_name": "UserPromptSubmit", "session_id": "sessnogit00", "prompt": "fix the parser", "cwd": str(folder)})
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join([
        json.dumps({"type": "user", "message": {"content": "fix the parser"}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": str(folder / "src" / "parser.py"), "old_string": "a", "new_string": "b"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": str(folder / "src" / "other.py")}},
        ]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": str(folder / "README.md"), "content": "x"}},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": str(folder / "src" / "parser.py"), "old_string": "b", "new_string": "c"}},
            {"type": "text", "text": "Done."},
        ]}}),
    ]), encoding="utf-8")
    run({"hook_event_name": "Stop", "session_id": "sessnogit00", "transcript_path": str(transcript), "cwd": str(folder)})

    lines = (root / "projects/alpha/chats/cc-sessnogi/work.jsonl").read_text(encoding="utf-8").splitlines()
    stamp = json.loads(lines[-1])
    assert stamp["head"] == "" and stamp["commits"] == []
    assert stamp["touched"] == ["src/parser.py", "README.md"]      # read is not a touch; a file once


def test_a_helpers_edits_and_a_shell_edit_reach_the_stamp_without_git(root: Path, tmp_path: Path) -> None:
    """A helper agent's Edit lives in its own transcript under the session's
    subagents folder; a file a shell command wrote is named by no tool call.
    Without git, the stamp has the first in `touched` and the second in
    `changed` (the folder walked since the turn began)."""
    script = _HOOKS / "claude-code-capture.py"
    folder = tmp_path / "plain"
    (folder / "src").mkdir(parents=True)
    (folder / "node_modules").mkdir()

    def run(payload: dict) -> None:
        proc = subprocess.run(
            [sys.executable, str(script), "--project", "alpha", "--data-root", str(root)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr

    run({"hook_event_name": "UserPromptSubmit", "session_id": "sesshelper0", "prompt": "split the parser", "cwd": str(folder)})
    import time as _t
    _t.sleep(1.1)
    (folder / "src" / "made-by-sed.py").write_text("x\n", encoding="utf-8")       # a shell edit
    (folder / "node_modules" / "dep.js").write_text("x\n", encoding="utf-8")      # never walked
    transcript = tmp_path / "sess.jsonl"
    transcript.write_text("\n".join([
        json.dumps({"type": "user", "message": {"content": "split the parser"}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}}),
    ]) + "\n", encoding="utf-8")
    helpers = tmp_path / "sess" / "subagents"
    helpers.mkdir(parents=True)
    (helpers / "agent-1.jsonl").write_text(json.dumps({"type": "assistant", "isSidechain": True, "message": {"content": [
        {"type": "tool_use", "name": "Write", "input": {"file_path": str(folder / "src" / "lexer.py"), "content": "y"}},
    ]}}) + "\n", encoding="utf-8")
    run({"hook_event_name": "Stop", "session_id": "sesshelper0", "transcript_path": str(transcript), "cwd": str(folder)})

    chat = root / "projects/alpha/chats/cc-sesshelp"
    stamp = json.loads((chat / "work.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert stamp["touched"] == ["src/lexer.py"]
    assert "src/made-by-sed.py" in stamp["changed"]
    assert not any(p.startswith("node_modules/") for p in stamp["changed"])
    # The helper's file is read once: the next Stop does not count it again.
    run({"hook_event_name": "UserPromptSubmit", "session_id": "sesshelper0", "prompt": "and now?", "cwd": str(folder)})
    with open(transcript, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "message": {"content": "and now?"}}) + "\n")
        fh.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Nothing."}]}}) + "\n")
    run({"hook_event_name": "Stop", "session_id": "sesshelper0", "transcript_path": str(transcript), "cwd": str(folder)})
    stamp = json.loads((chat / "work.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert stamp["touched"] == []


def test_opencode_hands_the_files_its_tools_changed_to_the_capture(root: Path, tmp_path: Path) -> None:
    cli = _HOOKS / "capture-cli.py"
    folder = tmp_path / "oc"
    folder.mkdir()

    def run(*args: str) -> None:
        proc = subprocess.run([sys.executable, str(cli), "--project", "alpha", "--data-root", str(root),
                               "--agent", "oc-12345678", "--tool", "opencode", "--session", "s1", "--cwd", str(folder), *args],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

    run("--phase", "open", "--text", "rename the flag")
    run("--phase", "complete", "--text", "Renamed.", "--touched", json.dumps([str(folder / "flags.ts"), "README.md"]))
    stamp = json.loads((root / "projects/alpha/chats/oc-12345678/work.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert stamp["touched"] == ["flags.ts", "README.md"]


def test_map_asks_the_operator_and_names_the_model_before_anything_runs(root: Path) -> None:
    """#map costs a helper run: the notice tells the agent to ask, naming the
    model Settings give, and to call nothing before the answer."""
    (root / "settings.json").write_text(json.dumps({"map": {"model": "sonnet"}}), encoding="utf-8")
    cap = capture.TurnCapture(root, "alpha", "cc-map")
    text = capture.format_signals(cap.open_turn("please #map the program"))
    line = next(x for x in text.splitlines() if x.startswith("[slightly-parallel] #map"))
    assert "ask the user now" in line and "helper agent on sonnet, or later?" in line
    assert "Do not call map_material" in line
