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
import re
import sys
from http.server import ThreadingHTTPServer
from uuid import uuid4

import stub_agent_turn
from sp_stub_http import LoggedStubHandler

REPLY = "Stub reply."


def _events(reply: str = REPLY, tool: tuple[str, str, dict] | None = None) -> list[dict]:
    marker = uuid4().hex
    message_id = "msg_" + marker
    response_id = "resp_" + marker
    item = {"type": "message", "id": message_id, "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": reply, "annotations": []}]}
    preview = {**item, "status": "in_progress", "content": []}
    delta = {"type": "response.output_text.delta", "output_index": 0, "content_index": 0,
             "item_id": message_id, "delta": reply}
    if tool:
        namespace, name, arguments = tool
        item = {"type": "function_call", "id": "fc_" + marker, "call_id": "call_" + marker,
                "name": name, "arguments": json.dumps(arguments), "status": "completed"}
        if namespace:
            item["namespace"] = namespace
        preview = {**item, "status": "in_progress", "arguments": ""}
        delta = {"type": "response.function_call_arguments.delta", "output_index": 0,
                 "item_id": item["id"], "delta": item["arguments"]}
    usage = {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 5,
             "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 15}
    return [
        {"type": "response.created", "response": {"id": response_id, "object": "response", "status": "in_progress", "output": []}},
        {"type": "response.output_item.added", "output_index": 0, "item": preview},
        delta,
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": {"id": response_id, "object": "response", "status": "completed",
                                                    "output": [item], "usage": usage}},
    ]


class Handler(LoggedStubHandler):
    interactive = False
    core = None
    def do_GET(self) -> None:
        self._note({"method": "GET", "path": self.path})
        body = json.dumps({"object": "list", "data": [], "models": []}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        req = self._read_request()
        tools = {}
        for entry in req.get("tools") or []:
            if not isinstance(entry, dict) or not isinstance(name := entry.get("name"), str):
                continue
            if entry.get("type") == "namespace":
                for member in entry.get("tools", []):
                    if isinstance(member, dict) and isinstance(child := member.get("name"), str):
                        tools[f"{name}_{child}"] = (name, child)
            else:
                tools[name] = ("", name)
        selected = (self.core(req.get("input") or [], list(tools)) if self.core else
                    stub_agent_turn.choose(req.get("input") or [], list(tools)) if self.interactive else None)
        reply = stub_agent_turn.REPLY if self.interactive else REPLY
        if self.core and (marker := re.search(r"sp-reply-[0-9a-f]{12}", json.dumps(req.get("input")))):
            reply = marker[0] if not selected and self.core.policy_name() == "hello" else reply
        tool = (*tools[selected[0]], selected[1]) if selected else None
        self._note({"method": "POST", "path": self.path, "model": req.get("model"), "reasoning": req.get("reasoning"),
                    "tools": list(tools), "called_tool": selected[0] if selected else None})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for e in _events(reply, tool):
            self.wfile.write(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode())
            self.wfile.flush()


def serve(port: int, log_file: str, *, interactive: bool = False, core=None) -> ThreadingHTTPServer:
    handler = type("ResponsesHandler", (Handler,), {"log_file": log_file, "interactive": interactive, "core": core})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


if __name__ == "__main__":
    serve(int(sys.argv[1]), sys.argv[2]).serve_forever()
