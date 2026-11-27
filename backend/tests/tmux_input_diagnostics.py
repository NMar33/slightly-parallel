"""Optional timestamps for the two real tmux WebSocket tests in diagnostic CI."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest
from starlette.testclient import WebSocketTestSession

from backend import termlib
from backend.routers import terminal


@pytest.fixture(autouse=True)
def trace_tmux_input(monkeypatch, request):
    if request.node.name not in (
        "test_a_wrapped_line_above_does_not_shift_the_lines_cut_out",
        "test_lines_are_cut_out_by_their_absolute_ids",
    ):
        return
    trace_path = os.environ.get("TMUX_TEST_TRACE_FILE")
    started = time.monotonic_ns()
    seen = set()
    active_write = threading.local()

    def note(event, **fields):
        record = dict(case=request.node.name, event=event, us=(time.monotonic_ns() - started) // 1000, **fields)
        line = json.dumps(record, sort_keys=True)
        if trace_path:
            with Path(trace_path).open("a", encoding="utf-8") as log:
                log.write(line + "\n")
        else:
            print("TMUX_TRACE " + line, flush=True)

    def first(event, **fields):
        if event not in seen:
            seen.add(event)
            note(event, **fields)

    enter = WebSocketTestSession.__enter__
    send_text = WebSocketTestSession.send_text
    wait = termlib.wait_for_prompt
    tmux_read = termlib.tmux_read
    tmux = termlib.tmux
    capture = termlib.capture
    raw = terminal.PtySession.in_raw_mode
    write = terminal.PtySession.write
    write_fd = terminal.os.write
    waiting_for_prompt = False
    previous_screen = ""

    def websocket_open(ws):
        result = enter(ws)
        note("websocket-open")
        return result

    def input_sent(ws, data):
        payload = json.loads(data)
        if payload.get("type") != "input":
            return send_text(ws, data)
        note("input-frame-sent", size=len(payload["data"]))
        result = send_text(ws, data)
        note("input-frame-enqueued")
        return result

    def prompt_wait(root, sid, *args, **kwargs):
        nonlocal waiting_for_prompt
        waiting_for_prompt = True
        try:
            return wait(root, sid, *args, **kwargs)
        finally:
            waiting_for_prompt = False
            note("prompt-wait-returned", observed="pane-prompt-stable" in seen)

    def read_tmux(root, *args, **kwargs):
        nonlocal previous_screen
        result = tmux_read(root, *args, **kwargs)
        if waiting_for_prompt and args[0] == "capture-pane":
            text = result.stdout.rstrip()
            if text and text == previous_screen and text.splitlines()[-1].rstrip().endswith(("$", "#", "%", ">", "❯")):
                first("pane-prompt-stable")
            previous_screen = text
        return result

    def run_tmux(root, *args, **kwargs):
        result = tmux(root, *args, **kwargs)
        if args[0] == "pipe-pane":
            note("pipe-pane-attached", status=result.returncode)
        return result

    def pane_capture(root, sid, *args, **kwargs):
        result = capture(root, sid, *args, **kwargs)
        try:
            pipe = (root / "pane-bytes.log").read_bytes()
        except FileNotFoundError:
            pipe = b""
        if pipe:
            first("pipe-first-bytes", size=len(pipe))
        if b"printf" in pipe or b"A2" in pipe:
            first("pipe-first-command-byte")
        if "printf" in result["text"] or "A2" in result["text"]:
            first("pane-first-command-visible")
        return result

    def raw_mode(session):
        ready = raw(session)
        first("tmux-client-raw" if ready else "tmux-client-not-raw")
        return ready

    def write_to_client(session, data):
        first("server-start-write", size=len(data))
        active_write.fd = session.fd
        try:
            return write(session, data)
        finally:
            active_write.fd = None

    def write_to_pty(fd, data):
        if fd != getattr(active_write, "fd", None):
            return write_fd(fd, data)
        try:
            written = write_fd(fd, data)
        except OSError as exc:
            first("pty-write-error", errno=exc.errno)
            raise
        first("pty-write-return", written=written)
        return written

    monkeypatch.setattr(WebSocketTestSession, "__enter__", websocket_open)
    monkeypatch.setattr(WebSocketTestSession, "send_text", input_sent)
    monkeypatch.setattr(termlib, "wait_for_prompt", prompt_wait)
    monkeypatch.setattr(termlib, "tmux_read", read_tmux)
    monkeypatch.setattr(termlib, "tmux", run_tmux)
    monkeypatch.setattr(termlib, "capture", pane_capture)
    monkeypatch.setattr(terminal.PtySession, "in_raw_mode", raw_mode)
    monkeypatch.setattr(terminal.PtySession, "write", write_to_client)
    monkeypatch.setattr(terminal.os, "write", write_to_pty)
