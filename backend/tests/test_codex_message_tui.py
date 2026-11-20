"""Two real Codex TUIs, one isolated daemon, and an in-process SP HTTP server."""

from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from websockets.sync.client import unix_connect

from backend import codexdelivery, mcp
from backend.server import create_app


def eventually(check, detail=lambda: ""):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if result := check():
            return result
        time.sleep(0.1)
    pytest.fail(f"Timed out waiting for {check}: {detail()}")


@pytest.mark.slow
@pytest.mark.skipif(
    os.name != "posix" or not shutil.which("codex") or not shutil.which("tmux"),
    reason="requires Codex with Unix app-server and tmux",
)
def test_sp_delivers_in_two_real_tuis(tmp_path, monkeypatch):
    seen = []
    gate = threading.Event()
    gate.set()

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            seen.append(body)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            response_id = "resp_" + uuid4().hex
            item = dict(
                id="msg_" + uuid4().hex,
                type="message",
                role="assistant",
                status="completed",
                content=[
                    dict(type="output_text", text="fixture finished", annotations=[])
                ],
            )

            def event(kind, **data):
                self.wfile.write(
                    ("data: " + json.dumps(dict(type=kind, **data)) + "\n\n").encode()
                )
                self.wfile.flush()

            try:
                event(
                    "response.created",
                    response=dict(id=response_id, status="in_progress", output=[]),
                )
                gate.wait(25)
                event(
                    "response.output_item.added",
                    output_index=0,
                    item={**item, "content": []},
                )
                event("response.output_item.done", output_index=0, item=item)
                event(
                    "response.completed",
                    response=dict(id=response_id, status="completed", output=[item]),
                )
            except (BrokenPipeError, ConnectionResetError):
                pass  # steer closes the old model stream

    with ExitStack() as stack:
        home = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        sock = home / "app-server-control" / "app-server-control.sock"
        sock.parent.mkdir()
        monkeypatch.setenv("CODEX_HOME", str(home))
        monkeypatch.setenv("HOME", str(home))
        for name in ("OPENAI_API_KEY", "CODEX_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        provider = stack.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), Provider))
        threading.Thread(target=provider.serve_forever, daemon=True).start()
        stack.callback(provider.shutdown)
        config = (
            f'name="Fixture",base_url="http://127.0.0.1:{provider.server_port}/v1",'
            'wire_api="responses",requires_openai_auth=false'
        )
        endpoint = f"unix://{sock}"
        (home / "config.toml").write_text("check_for_update_on_startup = false\n")
        log_path = tmp_path / "app-server.log"
        daemon = subprocess.Popen(
            [
                "codex",
                "-c",
                'model="sp-test"',
                "-c",
                'model_provider="fixture"',
                "-c",
                "model_providers.fixture={" + config + "}",
                "app-server",
                "--listen",
                endpoint,
            ],
            cwd=tmp_path,
            stdout=subprocess.DEVNULL,
            stderr=stack.enter_context(log_path.open("w")),
        )
        stack.callback(daemon.wait, 10)
        stack.callback(daemon.terminate)
        eventually(sock.is_socket)
        socket_name = str(home / "tmux")
        tmux = ["tmux", "-S", socket_name, "-f", "/dev/null"]
        stack.callback(subprocess.run, [*tmux, "kill-server"], capture_output=True)

        def tm(*args):
            return subprocess.check_output([*tmux, *args], text=True)

        def screen(pane):
            return tm("capture-pane", "-pt", pane)

        def thread_for(pane):
            probe.deadline = time.monotonic() + 5
            for tid in probe.pages("thread/loaded/list", {}):
                try:
                    history = probe.call(
                        "thread/read", dict(threadId=tid, includeTurns=True)
                    )
                except codexdelivery.Rejected:
                    continue
                if "BASELINE-" + pane in json.dumps(history):
                    return tid
            return None

        ws = stack.enter_context(unix_connect(str(sock.resolve()), proxy=None))
        probe = codexdelivery.Client(ws)
        probe.call(
            "initialize", dict(clientInfo=dict(name="test_observer", version="1"))
        )
        ws.send(json.dumps(dict(method="initialized")))
        ids = {}
        for pane in ("a", "b"):
            tm(
                "new-session",
                "-d",
                "-s",
                pane,
                "-x",
                "135",
                "-y",
                "40",
                "-c",
                str(tmp_path),
                shlex.join(["codex", "--remote", endpoint, "--no-alt-screen"]),
            )
            eventually(lambda pane=pane: "›" in screen(pane))
            tm("send-keys", "-t", pane, "-l", "BASELINE-" + pane)
            time.sleep(0.7)  # let Codex finish reading the input burst before Enter
            tm("send-keys", "-t", pane, "Enter")
            eventually(
                lambda pane=pane: "fixture finished" in screen(pane),
                lambda pane=pane: (
                    f"{screen(pane)} requests={len(seen)} daemon={daemon.poll()} log={log_path.read_text()[-2000:]}"
                ),
            )
            ids[pane] = eventually(lambda pane=pane: thread_for(pane))
            tm("send-keys", "-t", pane, "-l", "DRAFT-" + pane)
            eventually(lambda pane=pane: "DRAFT-" + pane in screen(pane))
        assert ids["a"] != ids["b"]
        root = tmp_path / "sp-data"
        agent = "codex-" + ids["a"][-8:]
        folder = root / "projects" / "demo" / "chats" / agent
        folder.mkdir(parents=True)
        (folder / "meta.json").write_text(
            json.dumps(dict(tool="codex", session_ref=ids["a"], project="demo"))
        )
        http = stack.enter_context(
            TestClient(create_app(data_root=root, watch=False, run_monitor=False))
        )
        gate.clear()
        stack.callback(gate.set)
        markers = []
        for body in ("idle #done", "busy #done"):
            result = http.post("/api/messages", json=dict(to=agent, text=body)).json()
            assert result["delivered_via"] == "codex", result
            mid = result["message"]["id"]
            markers.append(mid)
            eventually(lambda mid=mid: any(mid in request for request in seen))
        gate.set()
        for mid in markers:
            eventually(lambda mid=mid: mid in screen("a"))
            assert mid not in screen("b")
        for pane in ("a", "b"):
            assert "DRAFT-" + pane in screen(pane)
            assert "#done" not in screen(pane)
            probe.deadline = time.monotonic() + 5
            history = probe.call(
                "thread/read", {"threadId": ids[pane], "includeTurns": True}
            )["thread"]["turns"]
            assert len(history) == (2 if pane == "a" else 1)
            assert all(
                json.dumps(history).count(mid) == (1 if pane == "a" else 0)
                for mid in markers
            )
        headers = {mcp.VIA_HEADER: mcp.VIA_VALUE}

        def inbox():
            return http.post(
                "/api/messages/inbox", json={"agent_id": agent}, headers=headers
            ).json()["unread"]

        assert [r["text"] for r in inbox()] == ["idle #done", "busy #done"]
        assert inbox() == []
