"""The pinned agent CLIs, driven through their actual interactive PTYs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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


@pytest.mark.parametrize("cli", ["claude-code", "codex", "opencode"])
def test_interactive_cli_captures_turns_and_board_commands(cli, monkeypatch, tmp_path):
    for folder in (REPO / "scripts" / "ci", REPO / "scripts" / "fresh_user"):
        monkeypatch.syspath_prepend(str(folder))
    import stub_agent_turn as plan
    import stub_model
    import stub_responses
    from agents import give_login, tools
    from common import Space, eventually, free_port, get, http, wait_for
    from interactive import _last_reply, _ready, _wait_for_turn
    from screen import ENTER, Screen
    from stages import make_sample

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
                                    '[model_providers.stub]\nname = "stub"\nwire_api = "responses"\n'
                                    f'base_url = "{endpoint}/v1"\n\n{mcp}', encoding="utf-8")
            args += ["--no-daemon", "-c", "check_for_update_on_startup=false"]
        elif cli == "claude-code":
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sp-local-model-test-credential")
            give_login(tool, space.home, space, env)
            profile = space.home / ".claude.json"
            values = json.loads(profile.read_text(encoding="utf-8"))
            values.update(theme="dark", hasCompletedOnboarding=True)
            profile.write_text(json.dumps(values), encoding="utf-8")
            (space.home / "settings.json").write_text('{"enableAllProjectMcpServers":true}', encoding="utf-8")
            env.update(CLAUDE_CONFIG_DIR=str(space.home), ANTHROPIC_BASE_URL=endpoint, DISABLE_TELEMETRY="1",
                       CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", ENABLE_TOOL_SEARCH="false")
            args += ["--session-id", tool.session, "--mcp-config", ".mcp.json", "--permission-mode", "default",
                     "--allowedTools", "mcp__slightly-parallel"]
        else:
            # Install the SDK that OpenCode otherwise fetches during TUI boot.
            npm = shutil.which("npm")
            assert npm, "OpenCode's plugin SDK requires npm"
            config_root = space.home / ".config"
            for directory in (config_root / "opencode", space.sample / ".opencode"):
                directory.mkdir(parents=True, exist_ok=True)
                subprocess.run([npm, "install", "--no-audit", "--no-fund", "--ignore-scripts",
                                "--prefix", str(directory), f"@opencode-ai/plugin@{tool.version()}"],
                               env=space.env(), check=True, timeout=60, capture_output=True)
            model = "anthropic/claude-sonnet-4-5"
            path = space.sample / "opencode.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            config.update(provider={"anthropic": {"options": {"baseURL": f"{endpoint}/v1"}}},
                          enabled_providers=["anthropic"], autoupdate=False, model=model, small_model=model)
            path.write_text(json.dumps(config), encoding="utf-8")
            env.update(ANTHROPIC_API_KEY="sp-local-model-test-credential", OPENCODE_DISABLE_MODELS_FETCH="1",
                       OPENCODE_DISABLE_AUTOUPDATE="1", NODE_NO_WARNINGS="1",
                       XDG_CONFIG_HOME=str(config_root), XDG_DATA_HOME=str(space.home / ".local/share"),
                       XDG_CACHE_HOME=str(space.home / ".cache"), XDG_STATE_HOME=str(space.home / ".local/state"))
            args += ["--model", model]

        terminal = Screen(args, space.sample, env, trace=trace)
        stack.callback(terminal.close)
        layer = "L1"
        verdicts: dict[str, str] = {}
        try:
            assert _ready(terminal, tool, 40, [], codex_config if cli == "codex" else None), terminal.rendered
            verdicts[layer] = "pass"
            layer = "L2"
            chats = space.data / "projects/cli/chats"
            chat = None

            def prompt(text):
                nonlocal chat
                terminal.send(text)
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
