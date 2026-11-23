"""First-run dialogs that would otherwise eat the first operator prompt."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(("dialog", "keys", "action"), [
    ("Do you want to use this API key? Yes ❯ No (recommended)", ["\x1b[A", "\r"], "accepted CI API key"),
    ("❯ 1. No, exit\n2. Yes, I trust this folder", ["\x1b[B", "\r"], "project folder trusted"),
    ("1. Yes, I trust this folder\n❯ 2. No, exit", ["\x1b[A", "\r"], "project folder trusted"),
])
def test_claude_onboarding_reaches_the_prompt(monkeypatch, dialog, keys, action) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from agents import tools
    from interactive import _ready

    class Screen:
        text = ""
        keys = []
        frames = deque([dialog])
        if "I trust this folder" in dialog:
            frames.extend([dialog, "1. No, exit\n❯ 2. Yes, I trust this folder"])
        frames.append("❯ Try writing a test\nctrl+g to edit in VS Code")

        def read(self):
            if self.frames:
                self.text = self.frames.popleft()

        def send(self, key):
            self.keys.append(key)

    screen = Screen()
    answered: list[str] = []
    assert _ready(screen, tools()["claude-code"], 2, answered)
    assert screen.keys == keys
    assert answered == [f"Claude Code {action}"]


def test_claude_menu_cursor_is_not_the_composer(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from agents import tools
    from interactive import _ready

    screen = SimpleNamespace(text="Settings\n❯ Personal profile\n  Project profile", read=lambda: None)
    assert not _ready(screen, tools()["claude-code"], 2, [])


def test_new_cards_include_a_late_duplicate(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import common

    answers = iter([[{"id": "previous"}, {"id": "first"}], [{"id": "previous"}, {"id": "repeated"}]])
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(common, "get", lambda _space, _path: next(answers))
    monkeypatch.setattr(common, "time", SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _: None))
    cards = common.new_task_rows(common.Space(Path(), 1), "calc", {"previous"})
    assert [row["id"] for row in cards] == ["first", "repeated"]


def test_codex_waits_for_folder_and_hook_trust_after_the_composer_first_draws(monkeypatch, tmp_path) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from agents import tools
    from interactive import _ready

    config = tmp_path / "config.toml"

    class Screen:
        text = ""
        keys = []
        frames = deque(["› Ask Codex to do anything · ? for shortcuts", "Folder access. Trust this folder? Trust and continue",
                        "› 1. Review hooks 2. Trust all and continue", "1. Review hooks › 2. Trust all and continue",
                        "› Ask Codex to do anything · ? for shortcuts"])

        def read(self):
            if self.frames:
                self.text = self.frames.popleft()
                if not self.frames:
                    config.write_text('trusted_hash = "example"\n', encoding="utf-8")

        def send(self, key):
            self.keys.append(key)

    screen = Screen()
    answered: list[str] = []
    assert _ready(screen, tools()["codex"], 3, answered, config)
    assert screen.keys == ["\r", "\x1b[B", "\r"]
    assert answered == ["Codex project folder trusted", "Codex project hooks trusted"]


def test_upgrade_stage_without_its_requested_base_is_red(monkeypatch, tmp_path) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import run

    scratch = tmp_path / "fresh"
    scratch.mkdir()
    monkeypatch.setattr(run.tempfile, "mkdtemp", lambda **_: str(scratch))
    monkeypatch.setattr(run, "OUT", tmp_path / "reports")
    monkeypatch.setattr(run, "free_port", lambda: 1)
    monkeypatch.setattr(run.stages, "install", lambda *_: object())
    monkeypatch.setattr(run.stages, "sh", lambda *_: SimpleNamespace(returncode=1))
    for name in ("readme", "screens", "setup", "second_project", "stop", "cleanup"):
        monkeypatch.setattr(run.stages, name, lambda *_: None)

    assert run.main(["--stages", "upgrade", "--upgrade-from", "missing-tag"]) == 1


@pytest.mark.parametrize(("new_text", "passes"), [
    (None, False),
    ("Keep unittest instead of pytest.", False),
    ("Use pytest for the calculator tests.", True),
])
def test_decision_requires_a_new_entry_matching_the_operator_choice(monkeypatch, tmp_path, new_text, passes) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import scenario
    from common import Report, Space

    space = Space(tmp_path, 1)
    report = Report()
    state = scenario.State("calc", tmp_path, scenario.tools()["claude-code"])
    state.agent = "cc-test"
    decisions = [{"id": "dec_previous", "agent_id": state.agent, "decision_text": "Use pytest for the calculator tests."}]
    monkeypatch.setattr(scenario, "get", lambda *_: {"decisions": decisions})
    monkeypatch.setattr(scenario, "eventually", lambda read: read())

    assert '"Use pytest for the calculator tests."' in scenario.step_prompt(space, state, scenario.DECISION)
    if new_text is not None:
        decisions.append({"id": "dec_new", "agent_id": state.agent, "decision_text": new_text})
    scenario.after_decision(space, report, "core", state)

    assert (not report.failed()) is passes


def test_screen_diagnostic_hides_the_visible_suffix_of_a_masked_key(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from interactive import _screen_tail

    suffix = "dummyVisibleTail1234"
    text = f"Claude Code API key sk-ant-… {suffix}\nDo you want to use this API key?"
    assert _screen_tail(SimpleNamespace(rendered=text, history="")) == (
        "Claude Code API key [redacted]\nDo you want to use this API key?"
    )


def test_claude_login_menu_is_named_in_startup_evidence(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from interactive import _startup_failure

    menu = "Select login method:\n❯ Claude account\n  Anthropic Console\n  Cloud provider"
    screen = SimpleNamespace(rendered=menu, text=menu)
    assert _startup_failure(screen) == "L1 Claude Code requires login:\n" + menu


@pytest.mark.parametrize(("menu", "name"), [
    ("Do you want to use this API key?", "Claude Code API key confirmation"),
    ("Trust this folder? Trust and continue", "Codex project folder trust"),
    ("Review hooks\n❯ Trust all and continue", "Codex project hooks trust"),
])
def test_startup_evidence_names_known_dialogs(monkeypatch, menu, name) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from interactive import _startup_failure

    assert _startup_failure(SimpleNamespace(rendered=menu, text=menu)) == f"L1 {name}:\n{menu}"


def test_claude_approves_the_ci_key_in_its_disposable_profile(monkeypatch, tmp_path):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from agents import give_login, tools
    from common import Space
    import stages

    key = "sk-ant-api03-testOnlyABCDEFGHIJKLMNOPQRST"
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    space = Space(tmp_path / "scratch", 1)
    space.home.mkdir(parents=True)
    config = space.home / ".claude.json"
    config.write_text(json.dumps({"theme": "dark", "customApiKeyResponses": {
        "approved": ["old-synthetic-tail"], "rejected": [key[-20:]],
    }}), encoding="utf-8")
    env = {}
    assert give_login(tools()["claude-code"], tmp_path / "real-home", space, env) == "$ANTHROPIC_API_KEY"
    text = config.read_text(encoding="utf-8")
    assert key not in text
    assert json.loads(text) == {"theme": "dark", "customApiKeyResponses": {
        "approved": ["old-synthetic-tail", key[-20:]], "rejected": [],
    }}
    monkeypatch.setattr(stages, "stray", lambda _: [])
    stages.cleanup(space, keep=True)
    assert not config.exists() and space.home.exists()


def test_ci_reports_failed_check_details_only_in_the_report(monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from common import Report

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    report = Report()
    report.add("startup", "CLI ready", False, "private diagnostic")
    printed = capsys.readouterr().out
    assert "CLI ready" in printed and "private diagnostic" not in printed
    assert report.failed()[0].detail == "private diagnostic"


def test_onboarding_uses_the_rendered_composer_after_the_menu_is_gone(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import interactive
    from agents import tools

    terminal = SimpleNamespace(text="select login method:", rendered="Claude Code\n❯\n? for shortcuts",
                               read=lambda: None)
    ticks = iter([0, 0, 0, 1, 1])
    monkeypatch.setattr(interactive, "time", SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _: None))
    assert interactive._ready(terminal, tools()["claude-code"], 10, [])


@pytest.mark.parametrize("ready", [False, True])
def test_canary_reports_startup_capture_and_task_verdicts(monkeypatch, tmp_path, ready):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import json
    import re
    import interactive
    from agents import tools
    from common import Report, Space

    space = Space(tmp_path, 1)
    tool = tools()["claude-code"]
    card = {"id": "tk_a123abcd", "project": "calc", "status": "agent", "agent_id": "cc-abcd1234"}
    chat = space.data / "projects/calc/chats/cc-abcd1234/chat.md"
    chat.parent.mkdir(parents=True)
    chat.with_name("meta.json").write_text(json.dumps({"session_ref": tool.session}), encoding="utf-8")
    inputs: list[str] = []

    class Screen:
        text = history = rendered = ""

        def __init__(self, *args, **kwargs):
            pass

        def send(self, line):
            if line != interactive.ENTER:
                inputs.append(line)
                return
            prompt = inputs[-1]
            card["title"] = re.search(r"sp-task-[0-9a-f]+", prompt).group()
            reply = re.search(r"sp-reply-[0-9a-f]+", prompt).group()
            chat.write_text(f"# Chat\n## Turn 1\n**User**: {prompt}\n**Agent**: {reply}\n", encoding="utf-8")

        def close(self):
            pass

        def save_frame(self, _):
            pass

    monkeypatch.setattr(tool, "installed", lambda: True)
    monkeypatch.setattr(interactive, "Screen", Screen)
    monkeypatch.setattr(interactive, "give_login", lambda *_: True)
    monkeypatch.setattr(interactive, "_ready", lambda *_: ready)
    monkeypatch.setattr(interactive, "_wait_for_turn", lambda screen, check, seconds: "" if check() else "failure")
    monkeypatch.setattr(interactive, "get", lambda _, path: {"tasks": []} if path.startswith("/api/tasks") else {
        "agents": [{"agent_id": card["agent_id"], "session_ref": tool.session}],
    })
    monkeypatch.setattr(interactive, "new_task_rows", lambda *args: [card])
    report = Report()
    result = interactive.smoke(space, report, "calc", tmp_path, tool, "stub", tmp_path, 10, one_turn=True)
    layers = report.notes["interactive:claude-code layers"]
    profile = json.loads((space.home / ".claude.json").read_text(encoding="utf-8"))
    assert profile["projects"][str(tmp_path.resolve())]["hasTrustDialogAccepted"] is True
    settings = json.loads((space.home / "settings.json").read_text(encoding="utf-8"))
    assert settings["enableAllProjectMcpServers"] is True
    if ready:
        assert result.task == card["id"]
        assert len(inputs) == 1 and inputs[0].startswith("#task ") and not report.failed()
        assert layers == {"L1": "pass", "L2": "pass", "L3": "pass"}
    else:
        assert result is None and not inputs and report.failed()
        assert layers == {"L1": "fail", "L2": "blocked by L1", "L3": "blocked by L2"}


def test_canary_uses_setup_api_without_installing_or_opening_a_browser(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import run
    from common import Report, Space

    space = Space(tmp_path, 8124)
    seen = []
    monkeypatch.setattr(run.stages, "make_sample", lambda _: seen.append("commit sample"))
    def start(_, command, log, env, *, cwd):
        assert command[-2:] == ["-m", "backend.server"] and cwd.name == "backend"
        assert env["SP_DATA_ROOT"] == str(space.data)
        seen.append("server")
        return SimpleNamespace(poll=lambda: None)

    def setup(url, body):
        assert url.endswith("/api/setup/integrate") and body["write_codex_hooks"]
        assert not body["write_claude_hooks"]
        seen.append("setup API")

    def smoke(_, report, code, folder, tool, model, home, seconds, *, one_turn):
        assert tool.name == "codex" and one_turn
        seen.append("one turn")

    monkeypatch.setattr(run.stages, "start", start)
    monkeypatch.setattr(run.stages, "install", lambda *_: pytest.fail("canary has no install stage"))
    monkeypatch.setattr(run.stages, "screens", lambda *_: pytest.fail("canary has no browser stage"))
    monkeypatch.setattr(run, "wait_for", lambda *_: True)
    monkeypatch.setattr(run, "http", setup)
    monkeypatch.setattr(run, "smoke", smoke)
    monkeypatch.setattr(run, "get", lambda *_: {"totals": {}})
    monkeypatch.setattr(run, "finish", lambda *_: 0)
    assert run.canary(space, Report(), SimpleNamespace(model="stub", turn_seconds=10), ["codex"], 0) == 0
    assert seen == ["commit sample", "server", "setup API", "one turn"]



def test_canary_cleans_up_and_records_unexpected_setup_error(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import run
    from common import Report, Space

    space = Space(tmp_path / "test-machine", 8124)
    out = tmp_path / "report"
    monkeypatch.setattr(run, "OUT", out)
    monkeypatch.setattr(run.stages, "stop", lambda _: None)

    def fail(_):
        space.home.mkdir()
        (space.home / ".claude.json").write_text("simulated login", encoding="utf-8")
        raise RuntimeError("private diagnostics")

    monkeypatch.setattr(run.stages, "make_sample", fail)
    args = SimpleNamespace(model="stub", turn_seconds=10, keep=False, agent_runs=1)
    assert run.canary(space, Report(), args, ["claude-code"], 0) == 1
    assert not space.root.exists()
    report = (out / "report.json").read_text(encoding="utf-8")
    assert "RuntimeError" in report
    assert "private diagnostics" not in report


def test_finish_cleans_up_if_the_report_cannot_be_written(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import run
    from common import Report, Space

    space = Space(tmp_path / "test-machine", 8124)
    space.home.mkdir(parents=True)
    report = Report()
    monkeypatch.setattr(run, "OUT", tmp_path / "report")

    def fail(_):
        raise OSError("unwritable report")

    monkeypatch.setattr(report, "write", fail)
    with pytest.raises(OSError, match="unwritable report"):
        run.finish(space, report, SimpleNamespace(keep=False, agent_runs=1), 0, space.root / "screens")
    assert not space.root.exists()



def test_report_redacts_nested_diagnostic_notes(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import json
    from common import PLANTED_KEY, Report

    report = Report(notes={"fixture": [{PLANTED_KEY: ("notice " + PLANTED_KEY, 12)}]})
    destination = tmp_path / "report.json"
    report.write(destination)
    raw = destination.read_text(encoding="utf-8")
    assert PLANTED_KEY not in raw
    assert json.loads(raw)["notes"]["fixture"] == [{"[redacted]": ["notice [redacted]", 12]}]



def test_actions_canary_cannot_start_an_agent_without_provider_preflight(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import run
    from common import Report, Space

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("SP_AGENT_PREFLIGHT_RESULT", "failure")
    monkeypatch.setattr(run.stages, "make_sample", lambda *_: pytest.fail("the canary started before L0 passed"))
    monkeypatch.setattr(run, "OUT", tmp_path / "report")
    space = Space(tmp_path / "test-machine", 8124)
    args = SimpleNamespace(model="stub", turn_seconds=10, keep=False, agent_runs=1)
    report = Report()
    assert run.canary(space, report, args, ["codex"], 0) == 1
    assert report.notes["canary layers"] == dict.fromkeys(("L1", "L2", "L3"), "blocked by L0")
    assert [check.name for check in report.failed()] == ["L0 provider preflight"]
