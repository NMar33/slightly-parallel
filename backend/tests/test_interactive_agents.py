"""The pinned agent CLIs, driven through their actual interactive PTYs."""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from contextlib import ExitStack
from pathlib import Path

import pytest
import uvicorn

from backend.routers import setup
from backend.server import create_app

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.environ.get("SP_REAL_INTERACTIVE") != "1",
                                reason="the pinned interactive CLI CI job owns this check")


def _serve(stack, server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(server.server_close)
    stack.callback(server.shutdown)
    return server.server_address[1]


@pytest.mark.parametrize("cli", ["claude-code", "codex", "opencode", "opencode-run"])
def test_interactive_cli_captures_turns_and_board_commands(cli, monkeypatch, tmp_path):
    for folder in (REPO / "scripts" / "ci", REPO / "scripts" / "fresh_user"):
        monkeypatch.syspath_prepend(str(folder))
    import stub_agent_turn as plan
    import stub_model
    import stub_responses
    from agents import give_login, tools
    from common import Space, chatstore, eventually, free_port, get, http, wait_for
    from interactive import CLAUDE_MCP_ACCEPTED, _last_reply, _ready, _wait_for_turn
    from screen import ENTER, Screen, codex_pty_args
    from stages import make_sample

    headless = cli == "opencode-run"
    if headless:
        cli = "opencode"
        adapter = tmp_path / "slow-capture.py"
        adapter.write_text(
            "import runpy, sys, time\n"
            "if sys.argv[sys.argv.index('--phase') + 1] == 'complete':\n"
            "    time.sleep(2)\n"
            f"sys.argv[0] = {str(setup._CAPTURE_CLI)!r}\n"
            "runpy.run_path(sys.argv[0], run_name='__main__')\n", encoding="utf-8",
        )
        monkeypatch.setattr(setup, "_CAPTURE_CLI", adapter)
    drive_trust = cli == "claude-code" and os.environ.get("SP_TEST_CLAUDE_TRUST") == "1"
    space = Space(tmp_path, free_port())
    space.home.mkdir()
    space.data.mkdir()
    make_sample(space)
    tool = tools()[cli]
    binary = shutil.which(tool.binary)
    assert binary, f"{cli} must be installed for this test"
    monkeypatch.setenv("SP_PORT", str(space.port))
    # Setup's global Codex path must stay in the throwaway profile even when
    # the product server and the test share the same interpreter.
    codex_config = space.home / ".codex" / "config.toml"
    monkeypatch.setattr(setup, "CODEX_CONFIG_PATH", codex_config)
    monkeypatch.setattr(setup, "_MCP_PYTHON", Path(sys.executable))
    monkeypatch.setenv("CODEX_HOME", str(codex_config.parent))
    model_log, trace = tmp_path / "model.jsonl", tmp_path / "terminal.log"
    with ExitStack() as stack:
        provider = stub_responses if cli == "codex" else stub_model
        port = _serve(stack, provider.serve(0, str(model_log), interactive=True))
        endpoint = f"http://127.0.0.1:{port}"
        app = create_app(data_root=space.data, watch=True, run_monitor=False)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=space.port, log_level="error"))
        web = threading.Thread(target=server.run, daemon=True)
        web.start()

        def stop_app():
            server.should_exit = True
            web.join(timeout=10)

        stack.callback(stop_app)
        assert wait_for(space, "/api/health", 15), "Slightly Parallel did not start"
        http(space.url + "/api/setup/integrate", {"project_code": "cli", "project_dir": str(space.sample),
                                                tool.integrate_flag: True, "write_claude_hooks": cli == "claude-code",
                                                "write_claude_statusline": False})
        env = space.env()
        env.update(HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", ALL_PROXY="http://127.0.0.1:9",
                   NO_PROXY="127.0.0.1,localhost,registry.npmjs.org")
        args = [binary]
        if cli == "codex":
            codex_config.parent.mkdir(exist_ok=True)
            mcp = codex_config.read_text(encoding="utf-8")
            codex_config.write_text('model = "stub-model"\nmodel_provider = "stub"\n'
                                    'disable_paste_burst = true\n'
                                    '[model_providers.stub]\nname = "stub"\nwire_api = "responses"\n'
                                    f'base_url = "{endpoint}/v1"\n\n{mcp}',
                                    encoding="utf-8")
            args = codex_pty_args(binary)
        elif cli == "claude-code":
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sp-local-model-test-credential")
            give_login(tool, space.home, space, env)
            profile = space.home / ".claude.json"
            values = json.loads(profile.read_text(encoding="utf-8"))
            project = space.sample.resolve()
            values.update(theme="dark", hasCompletedOnboarding=True, projects={})
            if not drive_trust:
                values["projects"] = {path: {"hasTrustDialogAccepted": True}
                                      for path in {str(project), project.as_posix()}}
            profile.write_text(json.dumps(values), encoding="utf-8")
            if not drive_trust:
                (space.home / "settings.json").write_text('{"enableAllProjectMcpServers":true}', encoding="utf-8")
            env.update(CLAUDE_CONFIG_DIR=str(space.home), ANTHROPIC_BASE_URL=endpoint, DISABLE_TELEMETRY="1",
                       CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", ENABLE_TOOL_SEARCH="false")
            args += ["--session-id", tool.session, "--mcp-config", ".mcp.json", "--permission-mode", "default",
                     "--allowedTools", "mcp__slightly-parallel"]
        else:
            tool.prepare_interactive(space, space.sample, env)
            model = "anthropic/claude-sonnet-4-5"
            path = space.sample / "opencode.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            config.update(provider={"anthropic": {"options": {"baseURL": f"{endpoint}/v1"}}},
                          enabled_providers=["anthropic"], autoupdate=False, model=model, small_model=model)
            path.write_text(json.dumps(config), encoding="utf-8")
            env.update(ANTHROPIC_API_KEY="sp-local-model-test-credential", OPENCODE_DISABLE_MODELS_FETCH="1")
            env.update(tool.extra_env())
            args += ["--model", model]

        if headless:
            prompt = "Say hello for sp-stub-hello."
            turn = tool.say(prompt, model, space, env, 40)
            assert turn.ok and turn.text == plan.REPLY, turn.error or turn.text
            agent = f"oc-{tool.session[-8:].lower()}"
            chat = chatstore.folder(space.data, "cli", agent) / "chat.md"
            assert _last_reply(chat, prompt) == plan.REPLY
            assert chat.read_text(encoding="utf-8").count("\n## Turn ") == 1
            meta = json.loads(chat.with_name("meta.json").read_text(encoding="utf-8"))
            assert meta["helper_kind"] == "opencode-run"
            return

        terminal = Screen(args, space.sample, env, trace=trace, reply_to_kitty_query=cli != "claude-code")
        stack.callback(terminal.close)
        layer = "L1"
        verdicts: dict[str, str] = {}
        try:
            answered: list[str] = []
            assert _ready(terminal, tool, 40, answered, codex_config if cli == "codex" else None), terminal.rendered
            if drive_trust:
                assert "Claude Code project folder trusted" in answered, answered
                assert CLAUDE_MCP_ACCEPTED in answered, answered
            verdicts[layer] = "pass"
            layer = "L2"
            chats = space.data / "projects/cli/chats"
            chat = None

            def prompt(text):
                nonlocal chat
                terminal.send(text)
                # ConPTY writes a whole string in one call. Wait for the new
                # input to reach the composer before pressing the submit key.
                if cli == "codex" and os.name == "nt":
                    assert terminal.wait_for(text, 8), (
                        f"Codex did not display the prompt: {terminal.rendered}"
                    )
                terminal.send(ENTER)
                approved = False

                def captured():
                    nonlocal chat, approved
                    frame = terminal.rendered if cli == "codex" and not approved else ""
                    if ("› 1. Allow" in frame and any(
                        f'Allow the slightly-parallel MCP server to run tool "{name}"?' in frame
                        for name in ("write_entry", "task_done")
                    )):
                        approved = True
                        terminal.send(ENTER)
                        return False
                    matches = [path for path in chats.glob(f"{tool.id_prefix}*/chat.md")
                               if _last_reply(path, text) == plan.REPLY]
                    if len(matches) != 1 or (chat is not None and matches[0] != chat):
                        return False
                    chat = matches[0]
                    return True

                assert not (error := _wait_for_turn(terminal, captured, 40)), f"{error}: {text}\n{terminal.rendered}"

            prompt("Say hello for sp-stub-hello.")
            verdicts[layer] = "pass"
            layer = "L3"
            prompt(f"#task {plan.TITLE}. sp-stub-task")
            cards = get(space, "/api/tasks?project=cli")["tasks"]
            assert len(cards) == 1 and cards[0]["title"] == plan.TITLE and cards[0]["agent_id"] == chat.parent.name
            prompt(f"#decision {plan.DECISION} sp-stub-decision")
            decisions = get(space, "/api/decisions?project=cli")["decisions"]
            assert len(decisions) == 1 and decisions[0]["decision_text"] == plan.DECISION
            assert decisions[0]["agent_id"] == chat.parent.name
            rules_before = {row["id"] for row in get(space, "/api/rules?project=cli")["rules"]}
            prompt(f"#rule {plan.RULE}")
            rules = eventually(lambda: [row for row in get(space, "/api/rules?project=cli")["rules"]
                                        if row["id"] not in rules_before], seconds=8)
            assert len(rules) == 1 and rules[0]["l1"] == plan.RULE, rules
            # The operator's prompt hook moves the task. The MCP call reads
            # the result and acknowledges it, without moving another task.
            prompt(f"#done {cards[0]['id']} sp-stub-done {cards[0]['id']}")
            final = get(space, "/api/tasks?project=cli")["tasks"]
            assert len(final) == 1 and final[0]["id"] == cards[0]["id"] and final[0]["status"] == "done"
            assert sum('"method": "POST"' in line for line in model_log.read_text(encoding="utf-8").splitlines()) >= 5
            verdicts[layer] = "pass"
        except BaseException:
            verdicts[layer] = "fail"
            for later in ("L1", "L2", "L3"):
                verdicts.setdefault(later, f"blocked by {layer}")
            raise
        finally:
            print(f"{cli}: {json.dumps(verdicts)}", flush=True)
            terminal.save_frame("last frame")
            if output := os.environ.get("SP_INTERACTIVE_ARTIFACTS"):
                folder = Path(output) / cli
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "layers.json").write_text(json.dumps(verdicts, indent=2) + "\n", encoding="utf-8")
                for path in (trace, model_log):
                    if path.is_file():
                        shutil.copy2(path, folder / path.name)


def test_codex_runs_full_core_against_the_local_model(monkeypatch, tmp_path):
    for folder in (REPO / "scripts" / "ci", REPO / "scripts" / "fresh_user"):
        monkeypatch.syspath_prepend(str(folder))
    import stub_responses
    from agents import tools
    from common import Report, Space, free_port, get, http, wait_for
    from core_mcp import Plan
    from interactive import smoke
    from stages import make_sample

    space = Space(tmp_path, free_port())
    space.home.mkdir()
    space.data.mkdir()
    make_sample(space)
    config = space.home / ".codex" / "config.toml"
    monkeypatch.setattr(setup, "CODEX_CONFIG_PATH", config)
    monkeypatch.setattr(setup, "_MCP_PYTHON", Path(sys.executable))
    monkeypatch.setenv("SP_PORT", str(space.port))
    monkeypatch.setenv("CODEX_HOME", str(config.parent))

    from stub_core import CoreModel

    with ExitStack() as stack:
        app = create_app(data_root=space.data, watch=True, run_monitor=False)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=space.port, log_level="error"))
        web = threading.Thread(target=server.run, daemon=True)
        web.start()

        def stop():
            server.should_exit = True
            web.join(timeout=10)

        stack.callback(stop)
        assert wait_for(space, "/api/health", 15)
        http(space.url + "/api/setup/integrate", {"project_code": "calc", "project_dir": str(space.sample),
                                                 "write_codex_hooks": True, "write_claude_hooks": False})
        policy = Plan(space.root)
        model = CoreModel(policy, lambda rule: get(space, f"/api/rules?project={rule['project']}")["rules"])
        port = _serve(stack, stub_responses.serve(0, str(tmp_path / "stub-core.jsonl"), interactive=True, core=model))
        report = Report()
        result = smoke(space, report, "calc", space.sample, tools()["codex"], "stub-model", space.home,
                       40, core=True, offline_provider=f"http://127.0.0.1:{port}/v1")
        assert result and not report.failed(), [(c.name, c.detail) for c in report.failed()]
        messages = [json.loads(line) for line in policy.trace.read_text(encoding="utf-8").splitlines()]
        assert [row["request"]["params"]["name"] for row in messages] == [
            "write_entry", "write_entry", "interpret", "scan_material", "write_entry",
            "write_entry", "write_entry", "checkup", "task_done", "task_report",
        ]
        assert all(row["result"] == "accepted" for row in messages)
        task = messages[0]["request"]["params"]["arguments"]
        assert task["lens"] == "task"
        assert set(task["fields"]) == {"title", "description", "tags"}
        assert task["fields"]["description"] == "Verify the disposable calculator task is recorded."
        if output := os.environ.get("SP_INTERACTIVE_ARTIFACTS"):
            target = Path(output) / "codex-core"
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(policy.trace, target / policy.trace.name)
