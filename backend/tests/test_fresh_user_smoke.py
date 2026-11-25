"""First-run dialogs that would otherwise eat the first operator prompt."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def scripted_onboarding(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import interactive

    # These screens advance on read(), so only the poll interval matters.
    now = 0.0

    def sleep(seconds):
        nonlocal now
        now += seconds

    monkeypatch.setattr(interactive, "time", SimpleNamespace(monotonic=lambda: now, sleep=sleep))
    return interactive


@pytest.mark.parametrize(("dialog", "keys", "action"), [
    ("Do you want to use this API key? Yes ❯ No (recommended)", ["\x1b[A", "\r"], "accepted CI API key"),
    ("❯ 1. No, exit\n2. Yes, I trust this folder", ["\x1b[B", "\r"], "project folder trusted"),
    ("1. Yes, I trust this folder\n❯ 2. No, exit", ["\x1b[A", "\r"], "project folder trusted"),
])
def test_claude_onboarding_reaches_the_prompt(scripted_onboarding, dialog, keys, action) -> None:
    from agents import tools

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
    assert scripted_onboarding._ready(screen, tools()["claude-code"], 2, answered)
    assert screen.keys == keys
    assert answered == [f"Claude Code {action}"]


def test_claude_accepts_windows_folder_trust_only_after_yes_is_selected(scripted_onboarding) -> None:
    from agents import tools

    interactive = scripted_onboarding

    menu = (
        "Accessing workspace:\n C:/Users/runneradmin/AppData/Local/Temp/sp-fresh-ü/sample\n"
        " Quick safety check: Is this a project you created or one you trust?\n"
        "  > No, exit\n    Yes, I trust this folder\n Enter to confirm · Esc to cancel"
    )

    class Screen:
        rendered = menu
        keys = []

        def read(self):
            pass

        def send(self, key):
            self.keys.append(key)
            if key == interactive.DOWN:
                self.rendered = menu.replace("  > No, exit\n    Yes", "    No, exit\n  > Yes")
            elif key == interactive.ENTER:
                assert "  > Yes, I trust this folder" in self.rendered
                self.rendered = "Claude Code\n❯\n? for shortcuts"

    screen = Screen()
    answered = []
    assert interactive._ready(screen, tools()["claude-code"], 3, answered)
    assert screen.keys == [interactive.DOWN, interactive.ENTER]
    assert answered == ["Claude Code project folder trusted"]


def test_claude_menu_cursor_is_not_the_composer(scripted_onboarding) -> None:
    from agents import tools

    screen = SimpleNamespace(text="Settings\n❯ Personal profile\n  Project profile", read=lambda: None)
    assert not scripted_onboarding._ready(screen, tools()["claude-code"], 2, [])


@pytest.mark.parametrize(("line", "ready"), [
    ('>\u00a0Try "edit <filepath> to…"', True),
    (">", True),
    ("> Continue without using this MCP server", False),
])
def test_claude_windows_composer_respects_the_ascii_cursor(scripted_onboarding, line, ready):
    from agents import tools

    frame = f"Claude Code v2.1.330\n\n{line}\n\n⏵⏵ auto mode on (shift+tab to cycle)"
    screen = SimpleNamespace(rendered=frame, read=lambda: None)
    assert scripted_onboarding._ready(screen, tools()["claude-code"], 2, []) is ready


@pytest.mark.parametrize("windows", [True, False])
def test_fresh_user_page_walk_limits_browser_load_on_windows(monkeypatch, tmp_path, windows):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import stages
    from common import Report, Space

    (tmp_path / "node_modules" / "@playwright").mkdir(parents=True)
    monkeypatch.setattr(stages, "FRONTEND", tmp_path)
    monkeypatch.setattr(stages, "WINDOWS", windows)
    commands = []

    def shell(args, _cwd, env, **_kwargs):
        commands.append((args, env.get("SP_E2E_PAGE_WALK_BATCH")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(stages, "sh", shell)
    stages.pages(Space(tmp_path, 8010), Report())
    assert len(commands) == 1
    args, reuse = commands[0]
    assert "tests/e2e/every-page.spec.ts" in args
    assert ("--workers=1" in args) is windows
    assert reuse == ("1" if windows else None)
    assert ("--retries=0" in args) is windows


@pytest.mark.parametrize(("server", "cursor", "dropped", "moves", "expected"), [
    ("slightly-parallel", "❯", 0, 2, True),
    ("slightly-parallel", "❯", 1, 3, True),
    ("slightly-parallel", "❯", 20, 3, False),
    ("slightly-parallel", ">", 0, 2, True),
    ("unexpected-server", ">", 0, 0, False),
    ("slightly-parallel\nNew MCP server found in this project: unexpected-server", "❯", 0, 0, False),
])
def test_claude_confirms_only_the_single_expected_mcp_server(scripted_onboarding, server, cursor, dropped, moves, expected):
    from agents import tools

    interactive = scripted_onboarding

    choices = ("Use this MCP server", "Use this and all future MCP servers in this project",
               "Continue without using this MCP server")
    seen = []

    class Screen:
        selected = len(choices) - 1
        confirmed = False
        ignored = dropped

        def read(self):
            if self.confirmed:
                self.text = "Claude Code\n❯\n? for shortcuts"
            else:
                rows = [f"{cursor if i == self.selected else ' '} {text}" for i, text in enumerate(choices)]
                self.text = f"New MCP server found in this project: {server}\n\n" + "\n".join(rows)

        def send(self, key):
            seen.append(key)
            if key == interactive.UP:
                if self.ignored:
                    self.ignored -= 1
                    return
                self.selected -= 1
            elif key == interactive.ENTER:
                assert self.selected == 0
                self.confirmed = True

    report = []
    assert interactive._ready(Screen(), tools()["claude-code"], 10, report) is expected
    assert seen == [interactive.UP] * moves + ([interactive.ENTER] if expected else [])
    assert report == (["Claude Code accepted the Slightly Parallel MCP server"] if expected else [])


def test_new_cards_include_a_late_duplicate(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import common

    answers = iter([[{"id": "previous"}, {"id": "first"}], [{"id": "previous"}, {"id": "repeated"}]])
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(common, "get", lambda _space, _path: next(answers))
    monkeypatch.setattr(common, "time", SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _: None))
    cards = common.new_task_rows(common.Space(Path(), 1), "calc", {"previous"})
    assert [row["id"] for row in cards] == ["first", "repeated"]


def test_codex_waits_for_folder_and_hook_trust_after_the_composer_first_draws(scripted_onboarding, tmp_path) -> None:
    from agents import tools

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
    assert scripted_onboarding._ready(screen, tools()["codex"], 3, answered, config)
    assert screen.keys == ["\r", "\x1b[B", "\r"]
    assert answered == ["Codex project folder trusted", "Codex project hooks trusted"]


@pytest.mark.parametrize("windows", [True, False])
def test_fresh_user_launches_codex_with_the_non_admin_sandbox_on_windows(monkeypatch, tmp_path, windows):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import interactive
    import screen
    from agents import tools
    from common import Report, Space

    tool = tools()["codex"]
    monkeypatch.setattr(tool, "installed", lambda: True)
    monkeypatch.setattr(interactive, "give_login", lambda *_: True)
    monkeypatch.setattr(screen, "WINDOWS", windows)
    monkeypatch.setattr(interactive, "WINDOWS", windows, raising=False)
    monkeypatch.setattr(interactive, "_ready", lambda *_: False)
    args = []

    def fake_screen(command, *_args, **_kwargs):
        args.extend(command)
        return SimpleNamespace(rendered="", text="", save_frame=lambda _: None, close=lambda: None)

    monkeypatch.setattr(interactive, "Screen", fake_screen)
    folder = tmp_path / "sample ü"
    folder.mkdir()
    interactive.smoke(Space(tmp_path, 8124), Report(), "calc", folder, tool, "stub", tmp_path, 1, core=True)
    assert ('windows.sandbox="unelevated"' in args) is windows
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    if windows:
        assert args[args.index("--cd") + 1] == str(folder.resolve())
        entry = next(arg for arg in args if arg.startswith("sandbox_workspace_write.writable_roots="))
        assert json.loads(entry.split("=", 1)[1]) == [str(folder.resolve())]
        assert 'sandbox_mode="workspace-write"' in args
        assert "sandbox_workspace_write.network_access=false" in args
        assert 'approval_policy="never"' in args


def test_windows_stub_shell_uses_workspace_permissions(monkeypatch, tmp_path):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts / "fresh_user"))
    monkeypatch.syspath_prepend(str(scripts / "ci"))
    from core_mcp import Plan
    from stub_core import CoreModel

    plan = Plan(tmp_path)
    plan.start("a plain request", shell=("Get-Content -LiteralPath 'calc.py'",))
    model = CoreModel(plan, lambda _rule: [], workspace_shell=True)
    tool, args = model([{"role": "user"}], {"exec_command"})
    assert tool == "exec_command"
    assert args == {"cmd": "Get-Content -LiteralPath 'calc.py'"}


def test_windows_machine_codex_waits_for_the_pasted_prompt_before_enter(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import interactive
    from agents import tools
    from common import Report, Space

    tool = tools()["codex"]
    monkeypatch.setattr(tool, "installed", lambda: True)
    monkeypatch.setattr(interactive, "give_login", lambda *_: True)
    monkeypatch.setattr(interactive, "WINDOWS", True)
    monkeypatch.setattr(interactive, "_ready", lambda *_: True)
    monkeypatch.setattr(interactive, "_wait_for_turn", lambda *_: "stop after sending")
    events = []
    commands = []

    class Screen:
        rendered = ""
        history = ""

        def __init__(self, command, *_args, **_kwargs):
            commands.extend(command)

        def send(self, value):
            if value == interactive.ENTER:
                assert events[-1][0] == "painted"
            events.append(("send", value))

        def wait_for(self, value, timeout):
            assert events == [("send", value)]
            assert timeout > 0
            events.append(("painted", value))
            return True

        def close(self):
            pass

    monkeypatch.setattr(interactive, "Screen", Screen)
    folder = tmp_path / "sample ü"
    folder.mkdir()
    interactive.smoke(Space(tmp_path, 8124), Report(), "calc", folder, tool, "stub", tmp_path, 1)
    assert events == [("send", events[0][1]), ("painted", events[0][1]), ("send", interactive.ENTER)]
    assert events[0][1].startswith("Reply with exactly sp-reply-")
    assert "disable_paste_burst=true" in commands


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


@pytest.mark.parametrize("windows", [False, True])
def test_interactive_core_scan_gives_the_agent_a_bounded_write_plan(monkeypatch, tmp_path, windows):
    import json
    import subprocess

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import interactive
    import scenario
    from common import Space

    monkeypatch.setattr(interactive, "WINDOWS", windows)
    space = Space(tmp_path, 1)
    space.sample.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=space.sample, check=True)
    for cli in ("codex", "opencode", "claude-code"):
        state = scenario.State("calc", space.sample, scenario.tools()[cli])
        prompt = interactive._operator_core_prompt(space, state, scenario.SCAN)
        assert prompt.startswith("#scan ") and "Call scan_material without arguments" in prompt
        assert "No other MCP calls" in prompt
        directory = tmp_path if cli == "codex" and not windows else space.sample
        fixture = directory / "scan-payloads.json"
        assert json.dumps(str(fixture)) in prompt
        plan = json.loads(fixture.read_text(encoding="utf-8"))
        assert list(plan) == ["scan", "file", "architecture"]
        assert plan["scan"]["files_n"] == "COUNTER"
        assert plan["architecture"]["trigger_id"] == "SCAN_ID"
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=space.sample) == b""


def test_windows_codex_core_asks_for_the_same_calculator_edit(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import interactive
    import scenario
    from common import Space

    monkeypatch.setattr(interactive, "WINDOWS", True)
    space = Space(tmp_path, 1)
    state = scenario.State("calc", space.sample, scenario.tools()["codex"])
    for step in (scenario.EDIT, scenario.WORK):
        assert interactive._operator_core_prompt(space, state, step) == scenario.step_prompt(space, state, step)


@pytest.mark.parametrize("command", ["Get-ChildItem -LiteralPath '.'", "Add-Content -LiteralPath 'calc.py' -Value 'data'"])
def test_windows_edit_never_confirms_shell_escalation(monkeypatch, command):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from interactive import _core_approval

    frame = ("Would you like to run the following command?\n"
             f"Environment: local\n\n$ {command}\n\n› 1. Yes, proceed (y)\n3. No")
    keys = []
    check = _core_approval(SimpleNamespace(rendered=frame, send=keys.append), "a plain request")
    assert check() == "unexpected Codex command approval"
    assert keys == []


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


def test_opencode_keeps_the_pinned_cli_without_updater_output(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from agents import tools

    env = tools()["opencode"].extra_env()
    assert env.get("OPENCODE_DISABLE_AUTOUPDATE") == "1"
    assert env.get("NODE_NO_WARNINGS") == "1"


def test_machine_uses_the_selected_cheap_models_and_the_right_provider_login(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from agents import give_login, model_for, tools
    from common import Space

    monkeypatch.setenv("SP_CLAUDE_MODEL", "claude-haiku-5-5")
    monkeypatch.setenv("CODEX_MODEL", "gpt-6-luna")
    monkeypatch.setenv("SP_OPENCODE_MODEL", "openai/gpt-6-luna")
    assert model_for("claude-code", "haiku") == "claude-haiku-5-5"
    assert model_for("codex", "haiku") == "gpt-6-luna"
    assert model_for("opencode", "haiku") == "openai/gpt-6-luna"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai")
    env = {}
    assert give_login(tools()["opencode"], tmp_path, Space(tmp_path, 1), env) == "$OPENAI_API_KEY"
    assert env == {"OPENAI_API_KEY": "synthetic-openai"}


def test_opencode_prepares_the_pinned_plugin_before_the_interactive_tty(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import agents
    from common import Space

    tool = agents.tools()["opencode"]
    monkeypatch.setattr(tool, "version", lambda: "1.19.3")
    monkeypatch.setattr(agents.shutil, "which", lambda _: "npm")
    calls = []
    monkeypatch.setattr(agents.subprocess, "run", lambda args, **_: calls.append(args))
    space = Space(tmp_path, 1)
    env = {}
    tool.prepare_interactive(space, space.sample, env)
    for directory, command in zip((space.home / ".config" / "opencode", space.sample / ".opencode"), calls, strict=True):
        assert command[-2:] == [str(directory), "@opencode-ai/plugin@1.19.3"]
    assert env["XDG_DATA_HOME"] == str(space.home / ".local" / "share")
    excludes = (space.sample / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert "/.opencode/node_modules/" in excludes


@pytest.mark.parametrize("version", ["1.19.3", "1.19.4"])
def test_opencode_local_model_uses_only_a_matching_preinstalled_sdk(monkeypatch, tmp_path, version):
    import json
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import agents
    from common import Space

    seed = tmp_path / "pinned-sdk"
    sdk = seed / "node_modules" / "@opencode-ai" / "plugin" / "package.json"
    sdk.parent.mkdir(parents=True)
    sdk.write_text(json.dumps({"version": version}), encoding="utf-8")
    (seed / "package.json").write_text("{}", encoding="utf-8")
    (seed / "package-lock.json").write_text("{}", encoding="utf-8")
    tool = agents.tools()["opencode"]
    monkeypatch.setattr(tool, "version", lambda: "1.19.3")
    monkeypatch.setattr(agents.subprocess, "run", lambda *_args, **_kw: pytest.fail("the fixture invoked npm"))
    space = Space(tmp_path / "scratch", 1)
    if version != "1.19.3":
        with pytest.raises(RuntimeError, match="plugin SDK version"):
            tool.prepare_interactive(space, space.sample, {}, sdk_seed=seed)
        return
    tool.prepare_interactive(space, space.sample, {}, sdk_seed=seed)
    for prefix in (space.home / ".config" / "opencode", space.sample / ".opencode"):
        assert (prefix / sdk.relative_to(seed)).read_text(encoding="utf-8") == sdk.read_text(encoding="utf-8")
        assert (prefix / "package-lock.json").is_file()


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
        assert 'tags to ["ag_followup"]' in inputs[0]
        assert layers == {"L1": "pass", "L2": "pass", "L3": "pass"}
    else:
        assert result is None and not inputs and report.failed()
        assert layers == {"L1": "fail", "L2": "blocked by L1", "L3": "blocked by L2"}


@pytest.mark.parametrize("on_actions", [False, True], ids=["local", "actions"])
def test_canary_uses_setup_api_without_installing_or_opening_a_browser(monkeypatch, tmp_path, on_actions):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import run
    from common import Report, Space

    monkeypatch.setenv("GITHUB_ACTIONS", "true" if on_actions else "false")
    if on_actions:
        monkeypatch.setenv("SP_AGENT_PREFLIGHT_RESULT", "success")
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



@pytest.mark.parametrize("on_actions", [False, True], ids=["local", "actions"])
def test_canary_cleans_up_and_records_unexpected_setup_error(monkeypatch, tmp_path, on_actions):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import run
    from common import Report, Space

    monkeypatch.setenv("GITHUB_ACTIONS", "true" if on_actions else "false")
    if on_actions:
        monkeypatch.setenv("SP_AGENT_PREFLIGHT_RESULT", "success")
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



@pytest.mark.parametrize(("server", "operation", "lens", "title", "choice", "allowed"), [
    ("slightly-parallel", "write_entry", "task", "sp-expected", "› 1. Allow", True),
    ("slightly-parallel", "write_entry", "task", "sp-other", "› 1. Allow", False),
    ("slightly-parallel", "write_entry", "task", "sp-expected", "› 3. Always allow", False),
    ("slightly-parallel", "task_done", "task", "sp-expected", "› 1. Allow", False),
    ("slightly-parallel", "write_entry", "decision", "sp-expected", "› 1. Allow", False),
    ("other", "write_entry", "task", "sp-expected", "› 1. Allow", False),
])
def test_codex_only_confirms_the_pending_canary_task(monkeypatch, server, operation, lens, title, choice, allowed):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from interactive import ENTER, _approve_task_write

    frame = (f'Allow the {server} MCP server to run tool "{operation}"?\n'
             f'    fields: {{"title": "{title}", "status": "agent"}}\n'
             f'    lens: {lens}\n\n    {choice} Run the tool and continue')
    keys = []
    assert _approve_task_write(SimpleNamespace(rendered=frame, send=keys.append), "sp-expected") is allowed
    assert keys == ([ENTER] if allowed else [])



@pytest.mark.parametrize(("step", "tool", "arguments", "choice", "allowed"), [
    ("#scan", "scan_material", "", "1. Allow Run the tool and continue", True),
    ("#scan", "scan_material", "  unexpected: true\n", "1. Allow", False),
    ("#scan", "write_entry", "  lens: decision\n", "1. Allow", False),
    ("#done", "task_done", "", "1. Allow Run the tool and continue", True),
    ("#done", "task_done", '  proposals: [{"title":"extra"}]\n', "1. Allow", False),
    ("#rule", "write_entry", '  lens: rule\n', "1. Allow", False),
    ("#decision", "write_entry", '  lens: decision\n'
     '  fields: {"decision": "Use pytest for the calculator tests."}\n', "1. Allow", True),
    ("#decision", "write_entry", '  lens: decision\n'
     '  fields: {"decision": "Use pytest for the calculator tests.", "x...\n', "1. Allow", False),
    ("#decision", "write_entry", '  lens: decision\n'
     '  fields: {"decision": "Use another runner."}\n', "1. Allow", False),
    ("#done", "task_done", "", "3. Always allow", False),
])
def test_codex_core_only_confirms_the_exact_expected_mcp_call(
    monkeypatch, step, tool, arguments, choice, allowed,
):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from interactive import ENTER, _core_approval

    frame = (f'Field 1/1\n  Allow the slightly-parallel MCP server to run tool "{tool}"?\n'
             f'{arguments}\n  › {choice}\n  2. Allow for this session')
    keys = []
    check = _core_approval(SimpleNamespace(rendered=frame, send=keys.append), step)
    assert bool(check()) is not allowed
    assert keys == ([ENTER] if allowed else [])
    if allowed:
        assert check() == "" and keys == [ENTER]



@pytest.mark.parametrize(("in_stderr", "tool", "ending", "refused"), [
    (True, "write_entry", ", so the command did nothing", True),
    (True, "write_entry", " — no task was made", True),
    (True, "write_entry", ".", True),
    (True, "write_entry", "", True),
    (True, "write_entry", "by default", False),
    (False, "write_entry", ", so the command did nothing", False),
    (True, "read_entry", ", so the command did nothing", False),
])
def test_codex_helper_requires_the_actual_mcp_failure(monkeypatch, tmp_path, in_stderr, tool, ending, refused):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import json
    from common import Space
    from helper_smoke import _mcp_refused

    reason = "this chat (codex-fixture) is marked a helper chat (codex-exec); operator commands do not apply here"
    failure = (f"\x1b[31mmcp: slightly-parallel/{tool} (failed)\x1b[0m\n"
               f"\x1b[1mcodex\x1b[0m\n422: {reason}{ending}")
    log = "\n--- stderr ---\n" + failure if in_stderr else failure + "\n--- stderr ---\n"
    space = Space(tmp_path, 1)
    sessions = space.home / ".codex" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "rollout-session.jsonl").write_text(json.dumps({
        "type": "response_item",
        "payload": {"type": "message", "role": "assistant", "content": reason},
    }), encoding="utf-8")
    agent = SimpleNamespace(name="codex", session="session", last_log=lambda _: log)
    assert _mcp_refused(space, agent, reason) is refused


@pytest.mark.parametrize(("tool", "is_error", "status", "refused"), [
    ("write_entry", True, 422, True),
    ("write_entry", False, 422, False),
    ("write_entry", True, 401, False),
    ("read_entry", True, 422, False),
])
def test_codex_helper_requires_the_error_flag_and_number_in_structured_stderr(
    monkeypatch, tmp_path, tool, is_error, status, refused,
):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from common import Space
    from helper_smoke import _mcp_refused

    reason = "this chat (codex-fixture) is marked a helper chat (codex-exec); operator commands do not apply here"
    payload = {"content": [{"type": "text", "text": f"{status}: {reason}, so the #task made no task"}],
               "isError": is_error}
    log = f"\n--- stderr ---\nmcp: slightly-parallel/{tool} (failed)\ncodex\n{json.dumps(payload)}\nhook: Stop"
    agent = SimpleNamespace(name="codex", session="session", last_log=lambda _: log)
    assert _mcp_refused(Space(tmp_path, 1), agent, reason) is refused


def test_helper_refusal_requests_a_valid_task_payload_first(monkeypatch, tmp_path):
    import json

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import helper_smoke
    from common import Report, Space

    prompts = []

    def say(prompt, *_):
        prompts.append(prompt)
        return SimpleNamespace(ok=False, error="probe ended after collecting the prompt")

    monkeypatch.setattr(helper_smoke, "give_login", lambda *_: True)
    monkeypatch.setattr(helper_smoke, "get", lambda *_: {"tasks": []})
    tool = SimpleNamespace(name="codex", installed=lambda: True, say=say)
    space = Space(tmp_path, 1)
    helper_smoke.helper_smoke(space, Report(), "calc", space.sample, tool, "stub", space.home, 1, "codex-operator")
    prompt, = prompts
    payload = json.JSONDecoder().raw_decode(prompt[prompt.index("{"):])[0]
    assert payload == {"title": prompt.split()[1].rstrip("."), "description": "Verify that a helper cannot create a task."}



def test_codex_rule_approval_waits_for_the_new_saved_rule(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from interactive import ENTER, RULE_INTERPRETATION, _core_approval

    keys = []
    current_id = ""
    screen = SimpleNamespace(send=keys.append, rendered=(
        '  Allow the slightly-parallel MCP server to run tool "interpret"?\n'
        '  id: rl_new\n  lens: rule\n'
        f'  text: {RULE_INTERPRETATION}\n\n  › 1. Allow Run the tool and continue'
    ))
    check = _core_approval(screen, "#rule", lambda: current_id)
    assert not check() and not keys
    current_id = "rl_old"
    assert check() == "unexpected Codex MCP approval arguments" and not keys
    current_id = "rl_new"
    assert not check() and keys == [ENTER]



@pytest.mark.parametrize(("operation", "choice", "allowed"), [
    ("git add calc.py test_calc.py && git commit -m 'Add calculator tests'", "1. Yes, proceed (y)", True),
    ("git add calc.py test_calc.py && git commit -m 'Add calculator tests'", "2. Yes, and don't ask again (p)", False),
    ("git add . && git commit -m 'Add calculator tests'", "1. Yes, proceed (y)", False),
    ("git add calc.py test_calc.py && git push", "1. Yes, proceed (y)", False),
])
def test_codex_core_accepts_only_the_exact_local_commit_command(monkeypatch, operation, choice, allowed):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from interactive import ENTER, _core_approval

    keys = []
    frame = (f"  Would you like to run the following command?\n"
             f"  Environment: local\n\n  $ {operation}\n\n"
             f"  › {choice}\n  3. No")
    screen = SimpleNamespace(rendered=frame, send=keys.append)
    check = _core_approval(screen, "the work",
                           command="git add calc.py test_calc.py && git commit -m 'Add calculator tests'")
    assert bool(check()) is not allowed
    assert keys == ([ENTER] if allowed else [])
    if allowed:
        assert not check() and keys == [ENTER]
