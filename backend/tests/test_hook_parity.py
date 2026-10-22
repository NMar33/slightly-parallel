"""The capture hook runs with no server, so it keeps small copies of server
facts. Each copy is held equal to its original here: a copy that drifts makes
the hook and the server disagree about the same message."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend import app_settings, sessions, standuplib
from backend.entities import ENTITIES

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _hook():
    spec = importlib.util.spec_from_file_location("sp_capture_parity", _HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_parity"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_task_ids_are_found_the_same_way() -> None:
    capture = _hook()
    text = "take tk_0e571cfa, then tk_alpha_1.2 and dc_98ae726a; not xtk_nope or tk_a"
    server = [m.group(1) for m in sessions._TASK_ID_RE.finditer(text) if m.group(1).startswith("tk_")]
    assert capture._TASK_ID_RE.findall(text) == server == ["tk_0e571cfa", "tk_alpha_1"]


def test_the_standup_claim_lasts_the_same_time() -> None:
    assert _hook().STANDUP_CLAIM_S == standuplib.CLAIM_MINUTES * 60
    assert _hook().STANDUP_STATE == standuplib.STATE_FILE


def test_setting_defaults_match() -> None:
    capture = _hook()
    specs = {s.key: s for s in app_settings.SPECS}
    for key, default in capture._SETTING_DEFAULTS.items():
        assert specs[f"agent.{key}"].default == default, key
    assert specs["standup.model"].default == "opus" and specs["standup.ask"].default is True


def test_kept_tags_go_to_the_servers_routes() -> None:
    capture = _hook()
    for kind, (prefix, route) in capture._KEEP_ROUTES.items():
        ent = ENTITIES[kind]
        assert ent.id_prefix == prefix and ent.list_key.replace("_", "-") == route, kind


def test_both_agree_whether_yesterday_is_owed(client: TestClient) -> None:
    capture = _hook()
    store = client.app.state.store
    root = Path(store.data_root)
    then = datetime.now() - timedelta(days=1)
    day = standuplib.yymm_dd(then)
    chat = root / "projects" / "ALPHA" / "chats" / "cc-parity01"
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": "cc-parity01"}), encoding="utf-8")
    (chat / "chat.md").write_text(
        f"# Chat log\n\n---\n\n## Turn 1 · {then:%Y-%m-%d}T09:00:00\n**User**: hi\n**Agent**: hello\n", encoding="utf-8")
    store.rebuild()

    def server_owed() -> bool:
        st = standuplib.state(store, "ALPHA", day)
        return not (st["standup_id"] or st["claimed_by"] or st["postponed"])

    assert server_owed() and capture._standup_owed(root, "ALPHA") is not None
    standuplib.claim(store, "ALPHA", day, "cc-other")
    assert not server_owed() and capture._standup_owed(root, "ALPHA") is None
    (root / standuplib.STATE_FILE).unlink()
    standuplib.postpone(store, "ALPHA", day, 2)
    assert not server_owed() and capture._standup_owed(root, "ALPHA") is None
    (root / standuplib.STATE_FILE).unlink()
    client.post("/api/standups", json={"created_date": standuplib.yymm_dd(datetime.now()), "project": "ALPHA",
                                       "agent_id": "cc-x", "summary": "Done.", "for_date": day})
    store.rebuild()
    assert not server_owed() and capture._standup_owed(root, "ALPHA") is None


def test_every_command_of_the_contract_has_a_notice() -> None:
    """A command added to the contract without a hook notice fails here."""
    import re as _re

    capture = _hook()
    parts = Path(__file__).resolve().parents[2] / "prompts" / "contract"
    commands = set()
    for path in parts.glob("*.md"):
        for line in _re.findall(r"^command:\s*(.+)$", path.read_text(encoding="utf-8"), _re.M):
            tag = _re.sub(r"<[^>]*>", " ", line.partition("|")[0]).strip().lstrip("#")
            commands.add(" ".join(tag.split()))
    noticed = set(capture._COMMANDS) | set(capture._KEEP_ROUTES) | {"evidence"}
    assert commands <= noticed, sorted(commands - noticed)
    skills = {p.name for p in (Path(__file__).resolve().parents[2] / "templates" / "skills").iterdir()}
    assert {s for s, _ in capture._COMMANDS.values() if s} <= skills     # a named skill exists

    note = capture.format_signals({"commands": ["scan", "problem solved"]})
    assert "#scan — the skill make-a-scan holds the steps. Start with MCP tool scan_material." in note
    assert "#problem solved — MCP tool update_entry" in note


def test_every_notice_names_itself_first() -> None:
    """One shape for every notice: `[slightly-parallel] #<command> — …`, so an agent
    can match a notice to the section that teaches it. A notice with no
    command of its own names itself instead (the refresh)."""
    capture = _hook()
    note = capture.format_signals({
        "standup_due": {"date": "2609-21", "messages_n": 2, "chats_n": 1, "model": "sonnet"},
        "decision_hint": "we go with the translator",
        "contract_refresh_due": True,
        "files_due": "sn_1", "architecture_due": "sn_1",
        "kept": [{"kind": "artifact", "id": "ar_1", "folder": "/root/projects/alpha/artifacts"}],
    })
    named = [line.split(" — ")[0] for line in note.splitlines()]
    assert named == ["[slightly-parallel] #standup", "[slightly-parallel] #decision", "[slightly-parallel] refresh",
                     "[slightly-parallel] #scan", "[slightly-parallel] #architecture", "[slightly-parallel] #artifact",
                     "[slightly-parallel] tools"]
    # And it reads on in lower case after the dash, so the sentence is one.
    for line in note.splitlines():
        after = line.split(" — ", 1)
        if len(after) == 2 and after[1][:1].isalpha():
            assert after[1][0].islower(), line[:60]
    # #artifact has a skill like every other command, and the notice names it.
    assert "make-an-artifact" in note
    assert "/projects/alpha/artifacts/<name>/" in note


def test_a_skill_named_in_the_contract_exists() -> None:
    """A part that hands its steps to a skill must name a skill that ships."""
    import re as _re

    root = Path(__file__).resolve().parents[2]
    skills = {p.name for p in (root / "templates" / "skills").iterdir() if p.is_dir()}
    named = set()
    for path in (root / "prompts" / "contract").glob("*.md"):
        named |= set(_re.findall(r"skill[s]? `?([a-z][a-z0-9-]+)`? holds the steps",
                                 path.read_text(encoding="utf-8")))
    assert named and named <= skills, sorted(named - skills)
    assert "make-an-artifact" in named


def test_a_command_is_found_like_a_tag_and_once(tmp_path) -> None:
    capture = _hook()
    cap = capture.TurnCapture(tmp_path, "alpha", "cc-cmd00001")
    got = cap.open_turn("ok let's #scan, and then #page. #scan again; see docs#scan-notes")
    assert got["commands"] == ["scan", "page"]
    cap.complete_turn("done")
    assert cap.open_turn("#problem solved pb_1")["commands"] == ["problem solved"]


# ---------------------------------------------------------------------------
# What is shared is one copy (hookshared.py); what is copied is held equal
# ---------------------------------------------------------------------------


def test_the_hook_and_the_server_use_one_shared_module() -> None:
    from backend import capturewatch, hookshared, mcp, skilllib

    capture = _hook()
    assert capture.shared.__file__ == hookshared.__file__
    sys.modules.setdefault("capture", capture)
    spec = importlib.util.spec_from_file_location("sp_cc_parity", _HOOKS / "claude-code-capture.py")
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    # The hook's own names are the shared objects, not copies of them.
    shared = cc.shared
    assert cc._SYSTEM_PREFIXES is shared.NOT_OPERATOR
    assert cc._BUILTINS is shared.BUILTIN_COMMANDS
    assert cc.ancestors is shared.ancestors and cc._is_human_prompt is shared.is_human_prompt
    # And so are the server's.
    assert mcp.ancestors is hookshared.ancestors
    assert skilllib.uses_in_record is hookshared.skill_uses and skilllib.local_iso is hookshared.local_iso
    assert sessions._NOT_OPERATOR is hookshared.NOT_OPERATOR
    # One escape for chat.md: the hook writes a message as an import does.
    from backend import sessionimport
    assert capture.escape_content is capture.shared.escape_content
    assert sessionimport.escape_content is hookshared.escape_content
    # One list of who is not the operator: the watchdog skips what the hook skips.
    assert set(hookshared.NOT_OPERATOR) <= set(capturewatch._SYSTEM)
    assert shared.NOT_OPERATOR == hookshared.NOT_OPERATOR


def test_the_copied_patterns_are_equal() -> None:
    capture = _hook()
    assert capture._BOILERPLATE_RE.pattern == sessions._BOILERPLATE_RE.pattern
    assert capture._TASK_CMD_RE.pattern == sessions.TASK_CMD_RE.pattern
    assert capture._BOILERPLATE_RE.flags == sessions._BOILERPLATE_RE.flags
    # The server's pattern also captures the name in the brackets; the same otherwise.
    assert capture._KEEP_TAG_RE.pattern == sessions.KEEP_TAG_RE.pattern.replace("(?:\\(([^)\\n]{1,80})\\))", "(?:\\([^)\\n]{1,80}\\))")
    assert capture._EVIDENCE_RE.flags == sessions.DONE_TAG_RE.flags


def test_the_shared_module_needs_nothing_but_python() -> None:
    """The hooks load it by path with the operator's own Python: no package
    around it, no third-party import."""
    import ast

    from backend import hookshared

    tree = ast.parse(Path(hookshared.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import cannot be loaded by path"
            names.add((node.module or "").split(".")[0])
    assert names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)


def test_the_model_settings_take_a_typed_model_name() -> None:
    from backend import app_settings
    assert app_settings.coerce("standup.model", "opus") == "opus"
    assert app_settings.coerce("standup.model", " claude-opus-5-5 ") == "claude-opus-5-5"
    assert app_settings.coerce("map.model", "gpt-5.1-codex") == "gpt-5.1-codex"
    for bad in ("", "two words", "x" * 90, "rm -rf /"):
        try:
            app_settings.coerce("standup.model", bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")
    try:
        app_settings.coerce("terminal.agent", "something")   # an ordinary choice stays strict
    except ValueError:
        pass
    else:
        raise AssertionError("an ordinary choice took a free value")


def test_now_with_a_column_is_one_command_with_its_own_notice(tmp_path) -> None:
    """#now-todo is noticed as itself, not as #now: the agent files the
    message there and does not start on it."""
    capture = _hook()
    cap = capture.TurnCapture(tmp_path, "alpha", "cc-nowcol01")
    assert cap.open_turn("the login drops, look later #now-todo")["commands"] == ["now-todo"]
    note = capture.format_signals({"commands": ["now-todo"]})
    assert "#now-todo — the skill write-a-task" in note and "status todo" in note and "not started" in note
    assert "title and tags only" in capture.format_signals({"commands": ["now"]})
