"""Wake a loaded Codex thread on its local app-server without touching its TUI."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import UUID

from websockets.exceptions import WebSocketException
from websockets.sync.client import unix_connect

from . import msgledger


class Rejected(Exception):
    """The app-server returned an explicit JSON-RPC error."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class Client:
    def __init__(self, connection):
        self.connection = connection
        self.serial = 0
        self.deadline = time.monotonic() + 5

    def call(self, method, params):
        self.serial += 1
        self.connection.send(
            json.dumps({"id": self.serial, "method": method, "params": params})
        )
        while True:
            reply = json.loads(
                self.connection.recv(timeout=max(0, self.deadline - time.monotonic()))
            )
            if reply.get("id") != self.serial or "method" in reply:
                continue
            if "error" in reply:
                raise Rejected(
                    str(reply["error"].get("message", "request rejected")),
                    reply["error"].get("code"),
                )
            return reply["result"]

    def pages(self, method, params):
        cursor = None
        while True:
            result = self.call(method, {**params, "cursor": cursor})
            yield from result["data"]
            cursor = result.get("nextCursor")
            if not cursor:
                return


def _seen(client, thread, envelope):
    def contains(turns):
        return any(
            part.get("text") == envelope
            for turn in turns
            for item in turn.get("items", [])
            if item.get("type") == "userMessage"
            for part in item.get("content", [])
        )

    try:
        return contains(
            client.pages(
                "thread/turns/list",
                {"threadId": thread, "itemsView": "full", "limit": 8},
            )
        )
    except Rejected:
        return contains(
            client.call("thread/read", {"threadId": thread, "includeTurns": True})[
                "thread"
            ]["turns"]
        )


def _operation(client, thread):
    params = {"threadId": thread}
    data = client.call("thread/read", params)["thread"]
    status = data["status"]["type"]
    if status == "idle":
        return "turn/start", params
    if status == "active":
        try:
            turns = client.call(
                "thread/turns/list", {**params, "limit": 1, "sortDirection": "desc"}
            )["data"]
        except Rejected:
            turns = client.call("thread/read", {**params, "includeTurns": True})[
                "thread"
            ]["turns"][-1:]
        if turns and turns[0]["status"] == "inProgress":
            return "turn/steer", {**params, "expectedTurnId": turns[0]["id"]}
    raise Rejected("thread has no addressable turn")


def try_delivery(root, row, meta):
    if os.name != "posix":
        return False, "local Unix socket unavailable"
    thread = row["codex_thread"] or str(meta.get("session_ref") or "")
    try:
        if str(UUID(thread)) != thread or row["to_agent"] != "codex-" + thread[-8:]:
            return False, "unverified Codex thread"
    except ValueError:
        return False, "unknown Codex thread"
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    sock = home / "app-server-control" / "app-server-control.sock"
    envelope = msgledger.wake_text(row)
    try:
        with unix_connect(
            str(sock.resolve()),
            open_timeout=1,
            close_timeout=1,
            max_size=16 * 1024 * 1024,
            proxy=None,
        ) as ws:
            client = Client(ws)
            client.call(
                "initialize",
                {"clientInfo": {"name": "slightly_parallel", "version": "1"}},
            )
            ws.send(json.dumps({"method": "initialized"}))
            if row["codex_thread"]:
                if _seen(client, thread, envelope):
                    msgledger.finish_codex(root, row["id"], confirmed=True)
                else:
                    msgledger.checked_absent(root, row["id"])
                return False, "awaiting confirmation of the earlier send"
            matches = [
                t
                for t in client.pages("thread/loaded/list", {})
                if t.endswith(thread[-8:])
            ]
            if matches != [thread]:
                return False, "thread absent or ambiguous"
            method, params = _operation(client, thread)
            if not msgledger.claim_codex(root, row["id"], thread):
                return False, "already claimed"
            for attempt in range(2):
                try:
                    client.call(
                        method,
                        {**params, "input": [{"type": "text", "text": envelope}]},
                    )
                    break
                except Rejected as exc:
                    stale = "active turn" in str(exc).lower()
                    if stale and not attempt:
                        try:
                            method, params = _operation(client, thread)
                            continue
                        except (
                            Rejected,
                            OSError,
                            WebSocketException,
                            ValueError,
                            KeyError,
                        ):
                            msgledger.finish_codex(root, row["id"], confirmed=False)
                            raise
                    if stale or exc.code in (-32601, -32602):
                        msgledger.finish_codex(root, row["id"], confirmed=False)
                    raise
            msgledger.finish_codex(root, row["id"], confirmed=True)
            return True, ""
    except (OSError, WebSocketException, Rejected, ValueError, KeyError) as exc:
        # A write can have reached Codex even if its reply was lost. The saved
        # claim survives a restart; a later pass only searches the thread.
        return False, str(exc)
