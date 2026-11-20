"""Shared HTTP framing for the two local model stubs."""

import json
from http.server import BaseHTTPRequestHandler


class LoggedStubHandler(BaseHTTPRequestHandler):
    log_file = ""

    def log_message(self, *args) -> None:
        pass

    def _note(self, line: dict) -> None:
        with open(self.log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")

    def _read_request(self):
        size = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(size) if size else b""
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {}
