"""A local stand-in for OpenAI's Responses API, for running the real Codex
CLI with no tokens spent (a ``model_provider`` whose ``base_url`` is
http://127.0.0.1:<port>/v1, ``wire_api = "responses"``).

Every request is answered with one assistant message, "Stub reply.", and
appended to the log file (path, model, the reasoning it was asked for), so
a test can say what Codex sent. Checked with Codex 0.163.

    python stub_responses.py <port> <log file>
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLY = "Stub reply."


def _events() -> list[dict]:
    item = {"type": "message", "id": "msg_stub", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": REPLY, "annotations": []}]}
    usage = {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 5,
             "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 15}
    return [
        {"type": "response.created", "response": {"id": "resp_stub", "object": "response", "status": "in_progress", "output": []}},
        {"type": "response.output_item.added", "output_index": 0, "item": {**item, "status": "in_progress", "content": []}},
        {"type": "response.output_text.delta", "output_index": 0, "content_index": 0, "item_id": "msg_stub", "delta": REPLY},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": {"id": "resp_stub", "object": "response", "status": "completed",
                                                    "output": [item], "usage": usage}},
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
        body = json.dumps({"object": "list", "data": [], "models": []}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            req = json.loads(raw or b"{}")
        except ValueError:
            req = {}
        self._note({"method": "POST", "path": self.path, "model": req.get("model"), "reasoning": req.get("reasoning")})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for e in _events():
            self.wfile.write(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode())
            self.wfile.flush()


def serve(port: int, log_file: str) -> ThreadingHTTPServer:
    Handler.log_file = log_file
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    serve(int(sys.argv[1]), sys.argv[2]).serve_forever()
