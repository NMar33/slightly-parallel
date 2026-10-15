"""The MCP translator, end to end: a real server, a real subprocess, the
real wire protocol. The success measure:
correct entries from a client that never read SLIGHTLY-PARALLEL.md, refusals before a
request exists, identity stamped rather than asked for."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from backend.routers.schema_api import breadcrumb_path
from backend.server import create_app

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def live_api(tmp_path: Path):
    """A real uvicorn on a free port over a scratch data root."""
    root = tmp_path / "root"
    (root / "projects" / "alpha").mkdir(parents=True)
    # The breadcrumb the hook would have written for this "session".
    crumb = breadcrumb_path(root, str(tmp_path))
    crumb.parent.mkdir(parents=True, exist_ok=True)
    crumb.write_text(json.dumps({
        "agent_id": "cc-testsess", "project": "alpha",
        "session_id": "testsess-full", "cwd": str(tmp_path), "at": time.time(),
    }), encoding="utf-8")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = create_app(data_root=root, watch=False)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    import urllib.request
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", root, tmp_path
    server.should_exit = True
    thread.join(timeout=5)


class Stdio:
    """Drive the translator subprocess over its real transport."""

    def __init__(self, base_url: str, cwd: Path):
        env = {**os.environ, "SP_API": base_url,
               "PYTHONPATH": str(REPO / "backend")}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "backend.mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=str(cwd), env=env, text=True,
        )
        self._id = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, f"translator died: {self.proc.stderr.read() if self.proc.stderr else ''}"
        return json.loads(line)

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=5)


@pytest.fixture()
def mcp(live_api):
    base, root, cwd = live_api
    client = Stdio(base, cwd)
    yield client, base, root
    client.close()


def _text(reply: dict) -> str:
    return reply["result"]["content"][0]["text"]


def test_the_whole_conversation(mcp) -> None:
    client, base, root = mcp

    # initialize → the handshake a host performs
    init = client.request("initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {}, "clientInfo": {"name": "test", "version": "0"},
    })
    assert init["result"]["serverInfo"]["name"] == "slightly-parallel"
    assert init["result"]["protocolVersion"] == "2025-06-18"

    # tools/list → generated from the live schema, enums inlined
    tools = {t["name"]: t for t in client.request("tools/list")["result"]["tools"]}
    from backend.mcp import TOOLS
    assert set(tools) == set(TOOLS)      # the one list is what is really served
    assert "doing" in tools["task_update"]["inputSchema"]["properties"]["status"]["enum"]

    # write_entry: identity stamped, entry lands, id minted
    made = client.request("tools/call", {"name": "write_entry", "arguments": {
        "lens": "decision", "fields": {
            "decision": "Use the translator design",
            "why": "Thin process over the API; revisit if latency hurts.",
            "alternatives": ["direct file writes — rejected: two lock disciplines"],
        },
    }})
    assert made["result"]["isError"] is False
    row = json.loads(_text(made))["metadata"]
    assert row["id"].startswith("dc_")
    assert row["agent_id"] == "cc-testsess"     # stamped, never supplied
    assert row["project"] == "alpha"
    assert row["decision_text"] == "Use the translator design"

    # the vocabulary gate fires in the translator — before any HTTP request
    bad = client.request("tools/call", {"name": "task_update", "arguments": {
        "id": "tk_whatever", "status": "doig",
    }})
    assert bad["result"]["isError"] is True
    assert "todo" in _text(bad)                  # names the allowed values

    # tasks default to the session's project
    t = client.request("tools/call", {"name": "write_entry", "arguments": {
        "lens": "task", "l1": "board item",
        "fields": {"title": "board item", "tags": "ag_idea"},
    }})
    assert t["result"]["isError"] is False
    listing = json.loads(_text(client.request("tools/call", {"name": "tasks", "arguments": {}})))
    assert listing["total"] == 1

    # status belongs to the operator: the translator stamps the agent as
    # actor, and the API refuses the move on a task without auto-manage.
    tid = listing["tasks"][0]["id"]
    moved = client.request("tools/call", {"name": "task_update", "arguments": {
        "id": tid, "status": "doing",
    }})
    assert moved["result"]["isError"] is True
    assert "report" in _text(moved)

    # the honest path: report done — recorded, never moved without auto.
    reported = client.request("tools/call", {"name": "task_report", "arguments": {
        "id": tid, "summary": "board item wired",
    }})
    assert reported["result"]["isError"] is False
    rep = json.loads(_text(reported))
    assert rep["recorded"] is True and rep["moved"] is False

    # a non-status edit still passes the mutable-fields gate.
    retitled = client.request("tools/call", {"name": "task_update", "arguments": {
        "id": tid, "title": "board item, renamed",
    }})
    assert retitled["result"]["isError"] is False

    # update_entry refuses fields outside the lens's mutable set
    frozen = client.request("tools/call", {"name": "update_entry", "arguments": {
        "lens": "decision", "id": row["id"], "changes": {"decision_text": "rewrite"},
    }})
    assert frozen["result"]["isError"] is True
    assert "cannot change" in _text(frozen)

    # resources: contract + live schema
    res = client.request("resources/list")["result"]["resources"]
    assert {r["uri"] for r in res} >= {"sp://contract", "sp://schema"}
    contract = client.request("resources/read", {"uri": "sp://contract"})
    assert "Slightly Parallel agent contract" in contract["result"]["contents"][0]["text"][:2000]

    # prompts: the contract's commands as invocable structure
    prompts = {p["name"] for p in client.request("prompts/list")["result"]["prompts"]}
    assert {"scan", "decision", "problem", "standup", "evidence", "artifact",
            "problem-solved"} <= prompts          # built from the contract's command lines
    assert not any("<" in name or name.endswith("-or") for name in prompts)
    scan = client.request("prompts/get", {"name": "scan"})
    scan_text = scan["result"]["messages"][0]["content"]["text"]
    assert "write_entry" in scan_text and "architecture" in scan_text

    # doctor reachable through the same pipe
    doc = json.loads(_text(client.request("tools/call", {"name": "doctor", "arguments": {}})))
    assert doc["ok"] is True

    # unknown method → JSON-RPC error, loop survives
    nope = client.request("nonsense/method")
    assert nope["error"]["code"] == -32601
    assert client.request("ping")["result"] == {}


def test_no_breadcrumb_means_a_clear_refusal(live_api, tmp_path) -> None:
    base, root, _cwd = live_api
    stranger = tmp_path / "elsewhere"
    stranger.mkdir()
    client = Stdio(base, stranger)
    try:
        client.request("initialize", {"protocolVersion": "2025-06-18",
                                      "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
        reply = client.request("tools/call", {"name": "write_entry", "arguments": {
            "lens": "note", "l1": "orphan", "fields": {"title": "orphan"},
        }})
        assert reply["result"]["isError"] is True
        assert "hook" in _text(reply)            # the message says what to fix
    finally:
        client.close()


def test_the_task_the_contract_teaches_passes_the_name_gate(client) -> None:
    """#task sends title, description, tags and status: every one must be a
    field the translator knows, or the agent is refused before any request."""
    from backend import mcp as translator

    schema = client.get("/api/schema").json()
    spec = next(l for l in schema["lenses"] if l["name"] == "task")
    tr = translator.Translator.__new__(translator.Translator)
    tr.lenses = {l["name"]: l for l in schema["lenses"]}
    tr._check_names("task", spec, {"title": "Architecture form without a scan", "status": "agent",
                                   "tags": "ag_followup", "description": "the form accepts an empty trigger_id"})


def _tools_from(client) -> dict:
    """The tool definitions the translator builds from this server's schema."""
    from backend import mcp as translator

    schema = client.get("/api/schema").json()
    tr = translator.Translator.__new__(translator.Translator)
    tr.schema = schema
    tr.lenses = {l["name"]: l for l in schema["lenses"]}
    tr.vocab = schema.get("vocabularies", {})
    return {t["name"]: t for t in tr.tool_defs()}


def test_the_lens_picker_offers_only_lenses_an_agent_may_write(client) -> None:
    """A lens the server refuses an agent must not be in the enum: the picker
    and the refusal came apart once, and the agent read the larger list."""
    from backend.routers.lenses import OPERATOR_ONLY

    tools = _tools_from(client)
    offered = set(tools["write_entry"]["inputSchema"]["properties"]["lens"]["enum"])
    assert offered and not (offered & set(OPERATOR_ONLY))
    assert {"scan", "file", "architecture", "decision", "problem", "standup", "task"} <= offered
    assert not (set(tools["update_entry"]["inputSchema"]["properties"]["lens"]["enum"])
                & set(OPERATOR_ONLY))

    # And an operator-only lens says so where an agent reads it.
    schema = client.get("/api/schema").json()
    for lens in schema["lenses"]:
        refused = OPERATOR_ONLY.get(lens["name"])
        assert lens["agent_write"] is not bool(refused)
        if refused:
            assert refused in lens["when_to_use"]


def test_what_an_agent_reads_has_no_levels_and_no_goals(client) -> None:
    """`l1…l4` and the goal lens are retired; neither may come back through
    sp://schema or a tool description."""
    schema = client.get("/api/schema").json()
    for lens in schema["lenses"]:
        when = lens["when_to_use"].lower()
        assert not any(f"l{n}" in when for n in (1, 2, 3, 4)), lens["name"]
        if lens["name"] == "goal":
            assert when == ""
    for tool in _tools_from(client).values():
        text = tool["description"]
        assert "l2" not in text and "l3" not in text and "l4" not in text, tool["name"]


def test_the_tools_state_one_path_one_limit_and_one_required_summary(client) -> None:
    tools = _tools_from(client)
    assert "<data_root>/projects/<project>/artifacts/<name>/" in tools["artifact_write"]["description"]
    assert tools["task_report"]["inputSchema"]["required"] == ["id", "summary"]
    from backend.routers.evidence import MAX_ITEMS
    assert f"At most {MAX_ITEMS} items" in tools["task_evidence"]["description"]
    # Planning fields are the operator's: the tool does not offer them.
    assert "sprint_id" not in tools["task_update"]["inputSchema"]["properties"]


def test_every_tool_the_agent_texts_name_is_a_tool_the_server_serves() -> None:
    """A skill that names a tool nobody serves sends an agent at a wall.

    The skills and the contract parts tell an agent to call a tool by
    writing it as ``tool_name {``. Each of those has to be a key of
    ``mcp.TOOLS``, which another test holds equal to what ``tool_defs()``
    really serves.
    """
    import re

    from backend import mcp

    root = Path(__file__).resolve().parents[2]
    texts = sorted((root / "templates" / "skills").glob("*/SKILL.md")) + sorted(
        (root / "prompts" / "contract").glob("*.md")
    )
    assert texts, "no agent-facing text found"

    named: dict[str, str] = {}
    for path in texts:
        for call in re.findall(r"`([a-z][a-z0-9_]*) \{", path.read_text(encoding="utf-8")):
            named.setdefault(call, path.name)

    assert named, "no tool call found in the agent texts"
    missing = {tool: where for tool, where in named.items() if tool not in mcp.TOOLS}
    assert not missing, f"named in the agent texts but not served: {missing}"


def test_the_storage_slots_are_no_way_in(client) -> None:
    """write_entry and update_entry take fields by name only: a raw l2/l4,
    the side door a session with a stale schema once used, is refused."""
    import pytest
    from backend.mcp import ApiError, Translator
    t = Translator.__new__(Translator)
    t.lenses = {"standup": {"name": "standup", "fields": {"summary": {}, "story": {}, "detail": {}},
                            "text_fields": ["summary", "story", "detail"], "mutable": [], "base": "standups"}}
    t._refreshed_at = 10 ** 12          # no schema refresh in this unit test
    with pytest.raises(ApiError):
        t._check_names("standup", t.lenses["standup"], {"l4": "### The day\nx"})
    with pytest.raises(ApiError):
        t._check_names("standup", t.lenses["standup"], {"body": "x"})


def test_the_mcp_server_speaks_utf8_whatever_the_locale(tmp_path: Path) -> None:
    """On Windows a pipe takes the locale's code page (cp1252), where a
    Cyrillic character in an answer ended the server."""
    from backend.routers.setup import mcp_server_entry

    assert mcp_server_entry("http://127.0.0.1:1")["env"]["PYTHONUTF8"] == "1"
    env = {**os.environ, "SP_API": "http://127.0.0.1:1", "PYTHONPATH": str(REPO / "backend"),
           "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    # Escaped on the way in, so the answer is the first place it is encoded.
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "метод"})
    done = subprocess.run([sys.executable, "-m", "backend.mcp"], input=(msg + "\n").encode("utf-8"),
                          capture_output=True, cwd=str(tmp_path), env=env, timeout=30)
    reply = json.loads(done.stdout.decode("utf-8"))
    assert reply["error"]["message"] == "method not found: метод", done.stderr
