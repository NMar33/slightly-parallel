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
        frames = deque([dialog, "❯ Try writing a test\nctrl+g to edit in VS Code"])

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
