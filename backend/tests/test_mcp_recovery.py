"""The MCP translator when the server is not answering well: down, being
restarted, something else on the port, or restarted with new fields. Every
agent write passes here; test_mcp.py covers the server answering well."""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time
from typing import Any

import pytest

from backend import mcp


class _Answers(http.server.BaseHTTPRequestHandler):
    """/plain answers text, /missing a 404 with FastAPI's detail."""

    def do_GET(self) -> None:  # noqa: N802 — the handler's own name
        if self.path == "/plain":
            body, status, kind = b"<html>not us</html>", 200, "text/html"
        else:
            body, status, kind = json.dumps({"detail": "no such task"}).encode(), 404, "application/json"
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture()
def other_server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Answers)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_refusal_carries_the_servers_own_words(other_server) -> None:
    with pytest.raises(mcp.ApiError, match="^404: no such task$"):
        mcp.Api(other_server).get("/missing")


def test_something_else_on_the_port_is_named_not_a_crash(other_server) -> None:
    with pytest.raises(mcp.ApiError, match="did not answer in JSON"):
        mcp.Api(other_server).get("/plain")


def test_no_server_is_named_with_its_address() -> None:
    base = f"http://127.0.0.1:{_free_port()}"
    with pytest.raises(mcp.ApiError, match="cannot reach the Slightly Parallel server at " + base):
        mcp.Api(base).get("/api/schema")


SCHEMA = {"lenses": [{"name": "decision", "base": "decisions", "fields": ["decision", "why"],
                      "text_fields": ["decision", "why"]}], "vocabularies": {}}


class _Restarting(mcp.Api):
    """A server that is down for the first ``down`` calls."""

    def __init__(self, down: int, schema: dict = SCHEMA) -> None:
        super().__init__("http://unused")
        self.down, self.schema, self.calls = down, schema, 0

    def get(self, path: str) -> Any:
        self.calls += 1
        if self.calls <= self.down:
            raise mcp.ApiError("cannot reach the Slightly Parallel server")
        return self.schema


def test_a_server_restarting_at_the_first_call_is_waited_for(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    api = _Restarting(down=3)
    tr = mcp.Translator(api, cwd="/x")   # the first try at start fails quietly
    assert tr.schema is None
    tr.ensure()
    assert tr.lenses["decision"]["base"] == "decisions" and api.calls == 4


def test_a_server_that_stays_down_is_said_after_the_wait(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(mcp, "SCHEMA_RETRY_S", 0.0)
    tr = mcp.Translator(_Restarting(down=10**6), cwd="/x")
    with pytest.raises(mcp.ApiError, match="cannot reach"):
        tr.ensure()


def test_new_fields_after_a_restart_are_read_once_a_minute() -> None:
    api = _Restarting(down=0)
    tr = mcp.Translator(api, cwd="/x")
    api.schema = {**SCHEMA, "lenses": [{**SCHEMA["lenses"][0], "fields": ["decision", "why", "source"]}]}
    assert tr._refresh("decision") is True
    assert "source" in tr.lenses["decision"]["fields"]
    calls = api.calls
    assert tr._refresh("decision") is False and api.calls == calls   # not again within the minute


def test_a_bad_line_on_stdin_does_not_end_the_loop() -> None:
    tr = mcp.Translator(_Restarting(down=0), cwd="/x")
    assert mcp.handle(tr, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert mcp.handle(tr, {"jsonrpc": "2.0", "id": 1, "method": "nope"})["error"]["code"] == -32601
    reply = mcp.handle(tr, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                            "params": {"name": "no_such_tool", "arguments": {}}})
    assert reply["result"]["isError"] is True and "unknown tool" in reply["result"]["content"][0]["text"]
