"""Delivery via the real API and a sandbox Unix-socket Codex protocol peer."""

import json
import os
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from websockets.sync.server import unix_serve

from backend import msgdeliver, msgledger
from backend.server import create_app


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(socket, "AF_UNIX"), reason="requires Unix sockets"
)


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(home))
    sock = home / "app-server-control" / "app-server-control.sock"
    sock.parent.mkdir(parents=True)
    root = tmp_path / "sp"
    target, other = str(uuid4()), str(uuid4())
    agent = "codex-" + target[-8:]
    meta = root / "projects" / "demo" / "chats" / agent
    meta.mkdir(parents=True)
    (meta / "meta.json").write_text(
        json.dumps(dict(tool="codex", session_ref=target, project="demo"))
    )
    state = dict(
        loaded=[other, target],
        busy=False,
        drop=False,
        stale=False,
        sends=[],
        attempts=[],
        history=[],
    )

    def peer(ws):
        for raw in ws:
            r = json.loads(raw)
            method, p = r["method"], r.get("params", {})
            if "id" not in r:
                continue
            if method == "initialize":
                response = {}
            elif method == "thread/loaded/list":
                response = dict(data=state["loaded"], nextCursor=None)
            elif method == "thread/read":
                response = dict(
                    thread=dict(
                        id=target,
                        status=dict(type="active" if state["busy"] else "idle"),
                        turns=state["history"],
                    )
                )
            elif method == "thread/turns/list":
                response = dict(data=state["history"][::-1], nextCursor=None)
            elif method in ("turn/start", "turn/steer"):
                assert p["threadId"] == target
                state["attempts"].append(method)
                if state["stale"]:
                    state.update(stale=False, busy=False)
                    ws.send(
                        json.dumps(
                            dict(
                                id=r["id"],
                                error=dict(
                                    code=-32600,
                                    message="expected active turn id but found no active turn",
                                ),
                            )
                        )
                    )
                    continue
                if method == "turn/steer":
                    assert p["expectedTurnId"] == "active"
                state["sends"].append((method, p["input"][0]["text"]))
                state["history"].append(
                    dict(
                        id="active",
                        status="inProgress",
                        items=[dict(type="userMessage", content=p["input"])],
                    )
                )
                if state["drop"]:
                    ws.close()
                    return
                response = (
                    dict(turnId="active")
                    if method == "turn/steer"
                    else dict(turn=dict(id="active"))
                )
            else:
                raise AssertionError(method)
            ws.send(json.dumps(dict(id=r["id"], result=response)))

    with (
        TemporaryDirectory() as short,
        unix_serve(peer, str(Path(short) / "socket")) as server,
    ):
        sock.symlink_to(Path(short) / "socket")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TestClient(
                create_app(data_root=root, watch=False, run_monitor=False)
            ) as c:
                yield root, c, state, agent, target, sock
        finally:
            server.shutdown()
            thread.join()


@pytest.mark.parametrize(
    "busy,drop,stale", [(False, False, False), (True, True, False), (True, False, True)]
)
def test_direct_wake_and_single_inbox_read(delivery, busy, drop, stale):
    root, c, state, agent, target, _ = delivery
    state.update(busy=busy, drop=drop, stale=stale)
    if busy:
        state["history"].append(dict(id="active", status="inProgress", items=[]))
    result = c.post("/api/messages", json=dict(to=agent, text="#done")).json()
    mid = result["message"]["id"]
    msgdeliver.retry_waiting(root)
    assert [m for m, _ in state["sends"]] == [
        "turn/steer" if busy and not stale else "turn/start"
    ]
    if stale:
        assert state["attempts"] == ["turn/steer", "turn/start"]
    assert mid in state["sends"][0][1] and "#done" not in state["sends"][0][1]
    assert msgledger.find(root, mid)["delivered_via"] == "codex"
    assert msgledger.claim_for_hook(root, agent) == []
    assert [r["text"] for r in msgledger.inbox(root, agent)["unread"]] == ["#done"]
    assert not msgledger.inbox(root, agent)["unread"]
    assert msgdeliver.retry_waiting(root) == 0


@pytest.mark.parametrize("reason", ["missing", "ambiguous", "unreachable"])
def test_cannot_address_codex_leaves_message_for_hook(delivery, reason):
    root, c, state, agent, target, sock = delivery
    if reason == "missing":
        state["loaded"].remove(target)
    elif reason == "ambiguous":
        state["loaded"].append(str(uuid4())[:-8] + target[-8:])
    else:
        sock.unlink()
    row = c.post("/api/messages", json=dict(to=agent, text="hello")).json()["message"]
    assert not state["sends"] and not row["delivered_via"]
    assert [r["id"] for r in msgledger.claim_for_hook(root, agent)] == [row["id"]]


def test_reserved_before_crash_requires_history_check_before_fallback(delivery):
    root, _, state, agent, target, _sock = delivery
    row = msgledger.add(
        root, project="demo", from_agent="operator", to_agent=agent, text="interrupted"
    )
    assert msgledger.claim_codex(root, row["id"], target)
    assert not msgledger.claim_for_hook(root, agent)
    assert not msgledger.inbox(root, agent)["unread"]
    msgdeliver.retry_waiting(root)
    msgdeliver.retry_waiting(root)
    assert not state["attempts"]
    assert [r["id"] for r in msgledger.claim_for_hook(root, agent)] == [row["id"]]
    assert [r["id"] for r in msgledger.inbox(root, agent)["unread"]] == [row["id"]]
    assert not msgledger.inbox(root, agent)["unread"]
