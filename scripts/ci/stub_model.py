"""A local stand-in for the Anthropic Messages API, for running the real
Claude Code CLI with no tokens spent (ANTHROPIC_BASE_URL=http://127.0.0.1:<port>).

One deterministic turn: when the request offers the Slightly Parallel
write_entry tool and has no tool result yet, it answers with one call of it
(a decision); then it answers with plain text. Every request is appended to
the log file (path, model, tool names, whether a tool result came back), so a
test can say what the CLI sent.

    python stub_model.py <port> <log file>
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WRITE = "mcp__slightly-parallel__write_entry"
DECISION = {"lens": "decision", "fields": {"decision": "chose the stub model for the CLI test", "why": "no tokens"}}
REPLY = "Logged the decision."


def _events(model: str, block: dict, delta: dict, stop: str) -> list[tuple[str, dict]]:
    return [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_stub", "type": "message", "role": "assistant", "model": model, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": block}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": delta}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                           "usage": {"output_tokens": 5}}),
        ("message_stop", {"type": "message_stop"}),
    ]


class Handler(BaseHTTPRequestHandler):
    log_file = ""

    def log_message(self, *a) -> None:
        pass

    def _note(self, line: dict) -> None:
        with open(self.log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")

    def do_GET(self) -> None:
        self._note({"method": "GET", "path": self.path})
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            req = json.loads(raw or b"{}")
        except ValueError:
            req = {}
        tools = [t.get("name") for t in req.get("tools") or [] if isinstance(t, dict)]
        results = [c for m in req.get("messages") or [] if isinstance(m.get("content"), list)
                   for c in m["content"] if isinstance(c, dict) and c.get("type") == "tool_result"]
        self._note({"method": "POST", "path": self.path, "model": req.get("model"), "tools": tools,
                    "tool_results": [str(r.get("content"))[:400] for r in results]})
        if not self.path.startswith("/v1/messages") or "count_tokens" in self.path:
            return self._json({"input_tokens": 10})
        model = str(req.get("model") or "")
        if WRITE in tools and not results:
            block = {"type": "tool_use", "id": "toolu_stub1", "name": WRITE, "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(DECISION)}
            whole = {**block, "input": DECISION}
            stop = "tool_use"
        else:
            block = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": REPLY}
            whole = {"type": "text", "text": REPLY}
            stop = "end_turn"
        if not req.get("stream"):
            return self._json({"id": "msg_stub", "type": "message", "role": "assistant", "model": model,
                               "content": [whole], "stop_reason": stop, "stop_sequence": None,
                               "usage": {"input_tokens": 10, "output_tokens": 5}})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for name, data in _events(model, block, delta, stop):
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()

    def _json(self, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(port: int, log_file: str) -> ThreadingHTTPServer:
    Handler.log_file = log_file
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    serve(int(sys.argv[1]), sys.argv[2]).serve_forever()
