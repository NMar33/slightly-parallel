"""The real Claude Code CLI against a local stub model: no tokens spent.

Setup wires a folder as a user's would be (hooks, .mcp.json); ``claude -p``
runs there with ANTHROPIC_BASE_URL pointing at scripts/ci/stub_model.py,
which answers one call of write_entry (a decision) and then a line of text.
What must follow, end to end: the prompt and the reply are in the chat's
log (the hooks ran, as the CLI really calls them), the decision is in the
list the page reads, written through the MCP server under the chat's agent
id (the identity came from the hook's breadcrumb).

Runs only where SP_REAL_CLI=1 (the CI job that installs a pinned Claude
Code, and the weekly one with the newest); elsewhere it is skipped by name.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import uvicorn

from backend.server import create_app, operator_cookie
from tests.conftest import need

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.environ.get("SP_REAL_CLI") != "1",
                                reason="the real CLI runs in its own CI job (SP_REAL_CLI=1)")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stub(log: Path):
    spec = importlib.util.spec_from_file_location("stub_model", REPO / "scripts" / "ci" / "stub_model.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    port = _port()
    server = mod.serve(port, str(log))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def test_claude_code_records_the_turn_and_writes_through_mcp(tmp_path: Path, monkeypatch) -> None:
    claude = shutil.which("claude")
    if not claude:
        need("the claude CLI (npm i -g @anthropic-ai/claude-code)")
    root, work, cfg = tmp_path / "data", tmp_path / "work", tmp_path / "claude-config"
    (root / "projects").mkdir(parents=True)
    work.mkdir()
    cfg.mkdir()
    # Project MCP servers need an approval: the user's own setting gives it.
    (cfg / "settings.json").write_text(json.dumps({"enableAllProjectMcpServers": True}), encoding="utf-8")
    port = _port()
    monkeypatch.setenv("SP_PORT", str(port))
    app = create_app(data_root=root, watch=True, run_monitor=False)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    name, value = operator_cookie(app)

    def call(method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json", "Cookie": f"{name}={value}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    stub, stub_port = _stub(tmp_path / "model.jsonl")
    try:
        call("POST", "/api/setup/integrate", {"project_code": "cli", "project_dir": str(work)})
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE"))}
        env.update(HOME=str(tmp_path / "home"), CLAUDE_CONFIG_DIR=str(cfg), ANTHROPIC_API_KEY="sk-stub",
                   ANTHROPIC_BASE_URL=f"http://127.0.0.1:{stub_port}", DISABLE_TELEMETRY="1",
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                   # MCP tools listed with the rest, not loaded through a search first.
                   ENABLE_TOOL_SEARCH="false")
        (tmp_path / "home").mkdir()
        r = subprocess.run([claude, "-p", "log the decision about the stub model", "--model", "claude-sonnet-4-5",
                            "--allowedTools", "mcp__slightly-parallel__write_entry"],
                           cwd=str(work), env=env, capture_output=True, text=True, timeout=180)
        sent = [json.loads(ln) for ln in (tmp_path / "model.jsonl").read_text(encoding="utf-8").splitlines()]
        seen = f"exit {r.returncode}\nstdout: {r.stdout[-1500:]}\nstderr: {r.stderr[-1500:]}\nmodel saw: {sent}"
        assert r.returncode == 0, seen
        assert any("mcp__slightly-parallel__write_entry" in s.get("tools", []) for s in sent), seen
        assert any(s.get("tool_results") for s in sent), seen
        chats = list((root / "projects" / "cli" / "chats").glob("*/chat.md"))
        assert chats, "no chat recorded: the hooks did not run\n" + seen
        log = chats[0].read_text(encoding="utf-8")
        assert "log the decision about the stub model" in log and "Logged the decision." in log, log[-1500:]
        agent = chats[0].parent.name
        decisions = call("GET", "/api/decisions?project=cli")["decisions"]
        mine = [d for d in decisions if "stub model" in str(d.get("decision_text") or d.get("l1") or "")]
        assert mine and mine[0]["agent_id"] == agent, (decisions, agent, seen)
    finally:
        stub.shutdown()
        server.should_exit = True
