"""The real Codex CLI against a local stub of the Responses API: no tokens.

``codex exec`` runs in a folder registered with Slightly Parallel, its
model provider pointing at scripts/ci/stub_responses.py and its legacy
``notify`` at the capture adapter (codex-capture.py; the per-project hooks
need Codex's own trust step, a screen of its own). What must follow from
what the real program writes: the run is recorded as a helper (its session
file's first line says ``exec``), its parent is the Claude Code chat named
in the environment it inherited, the commands in its prompt act on nothing,
and its tokens carry the reasoning effort its turn ran with.

Runs only where SP_REAL_CODEX=1 (the CI job that installs a pinned Codex);
elsewhere it is skipped by name.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from backend import hookshared
from backend.db import ViewStore
from tests.conftest import need

REPO = Path(__file__).resolve().parents[2]
PARENT = "ca77654e-a6ba-48c9-8221-caaa2475a406"
pytestmark = pytest.mark.skipif(os.environ.get("SP_REAL_CODEX") != "1",
                                reason="the real Codex runs in its own CI job (SP_REAL_CODEX=1)")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stub(log: Path):
    spec = importlib.util.spec_from_file_location("stub_responses", REPO / "scripts" / "ci" / "stub_responses.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    port = _port()
    server = mod.serve(port, str(log))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _toml(s: str) -> str:
    """A TOML literal string (no escapes: a Windows path stays as it is)."""
    assert "'" not in s
    return f"'{s}'"


def test_codex_exec_is_recorded_as_a_helper_of_the_chat_that_started_it(tmp_path: Path) -> None:
    codex = shutil.which("codex")
    if not codex:
        need("the codex CLI (npm i -g @openai/codex)")
    root, work, home = tmp_path / "data", tmp_path / "work", tmp_path / "codexhome"
    for d in (root / "projects", work, home):
        d.mkdir(parents=True)
    (root / "integrations.csv").write_text(f"project,path,created_date\ncx,{work},2611-11\n", encoding="utf-8")
    stub, port = _stub(tmp_path / "model.jsonl")
    notify = [sys.executable, str(REPO / "scripts" / "hooks" / "codex-capture.py"), "--data-root", str(root)]
    (home / "config.toml").write_text("\n".join([
        'model = "stub-model"',
        'model_provider = "stub"',
        'model_reasoning_effort = "high"',
        f"notify = [{', '.join(_toml(x) for x in notify)}]",
        "[model_providers.stub]",
        'name = "stub"',
        f'base_url = "http://127.0.0.1:{port}/v1"',
        'wire_api = "responses"',
        f"[projects.{_toml(str(work))}]",
        'trust_level = "trusted"',
    ]) + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CODEX", "CLAUDE", "OPENAI"))}
    # As a Claude Code chat's Bash tool hands it to the programs it starts.
    env.update(CODEX_HOME=str(home), CLAUDE_CODE_SESSION_ID=PARENT, CLAUDE_CODE_ENTRYPOINT="cli")
    prompt = "You are a critic. Review it.\n#entrypoint the critic run #now review it"
    try:
        r = subprocess.run([codex, "exec", "--skip-git-repo-check", prompt], cwd=str(work), env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
    finally:
        stub.shutdown()
    sent = (tmp_path / "model.jsonl").read_text(encoding="utf-8") if (tmp_path / "model.jsonl").exists() else ""
    seen = f"exit {r.returncode}\nstdout: {r.stdout[-1500:]}\nstderr: {r.stderr[-1500:]}\nmodel saw: {sent[-1500:]}"
    assert r.returncode == 0, seen
    assert '"effort": "high"' in sent, seen
    chats = list((root / "projects" / "cx" / "chats").glob("codex-*"))
    assert len(chats) == 1, "no chat recorded: notify did not run\n" + seen
    meta = json.loads((chats[0] / "meta.json").read_text(encoding="utf-8"))
    assert meta.get("helper") is True and meta["helper_kind"] == "codex-exec", (meta, seen)
    assert meta["helper_of"] == "cc-" + hookshared.session_key("claude-code", PARENT) and meta["helper_of_by"] == "env"
    chat = (chats[0] / "chat.md").read_text(encoding="utf-8")
    assert "You are a critic." in chat and "Stub reply." in chat, chat[-1500:]
    usage = [json.loads(x) for x in (chats[0] / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert usage and all(x["effort"] == "high" for x in usage), usage
    store = ViewStore(data_root=root)
    store.rebuild()
    for table in ("keep_marks", "now_tags"):
        assert store.query(f"SELECT count(*) AS n FROM {table}")[0]["n"] == 0, table
