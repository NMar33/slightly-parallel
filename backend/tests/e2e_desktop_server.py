"""Windows desktop E2E server with a stack for stalled terminal requests."""

import faulthandler
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from backend.routers import terminal

from backend.server import app as backend_app


profile_path = os.environ.get("SP_BENCH_OUTPUT_PROFILE_PATH")
read_stats: dict[str, dict] = {}


def record(stats: dict, size: int, elapsed: int) -> None:
    bucket = next((str(bound) for bound in (128, 1024, 4096, 16384, 65536) if size <= bound), ">65536")
    stats["sizes"][bucket] += 1
    stats["bytes"] += size
    stats["total_ns"] += elapsed
    stats["max_ns"] = max(stats["max_ns"], elapsed)


def counters() -> dict:
    return {"bytes": 0, "total_ns": 0, "max_ns": 0, "sizes": Counter()}


if profile_path:
    read_session = terminal._read_session

    async def profiled_read(session: terminal.PtySession) -> bytes:
        started = time.perf_counter_ns()
        data = await read_session(session)
        if data:
            stats = read_stats.get(session.session_id)
            if stats is not None:
                record(stats, len(data), time.perf_counter_ns() - started)
        return data

    terminal._read_session = profiled_read


async def profile_terminal_socket(scope, receive, send, destination: str) -> None:
    session = scope["path"].rsplit("/", 1)[-1]
    reads, sends = counters(), counters()
    read_stats[session] = reads
    extensions = [
        value.decode("latin1") for key, value in scope["headers"]
        if key == b"sec-websocket-extensions"
    ]

    async def profiled_send(message):
        data = message.get("bytes")
        if message["type"] != "websocket.send" or not data:
            await send(message)
            return
        started = time.perf_counter_ns()
        await send(message)
        record(sends, len(data), time.perf_counter_ns() - started)

    try:
        await backend_app(scope, receive, profiled_send)
    finally:
        read_stats.pop(session, None)
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8") as report:
            report.write(json.dumps({"session": session, "read": reads, "send": sends,
                                     "extensions_offered": extensions}) + "\n")


async def app(scope, receive, send):
    if profile_path and scope["type"] == "websocket" and scope["path"].startswith("/ws/terminal/"):
        await profile_terminal_socket(scope, receive, send, profile_path)
        return
    terminal_request = scope["type"] == "http" and scope["path"].startswith("/api/terminal/sessions") and (
        scope["path"] == "/api/terminal/sessions" or scope["path"].endswith("/close")
    )
    if terminal_request:
        print(f"Terminal fixture entered {scope['method']} {scope['path']}", file=sys.stderr, flush=True)
        faulthandler.dump_traceback_later(10)
    try:
        await backend_app(scope, receive, send)
    finally:
        if terminal_request:
            faulthandler.cancel_dump_traceback_later()
