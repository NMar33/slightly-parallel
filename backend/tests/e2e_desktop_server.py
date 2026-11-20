"""Diagnostics for stalled Windows terminal requests on this CI snapshot."""

import asyncio
import contextvars
import faulthandler
import functools
import itertools
import sys
import threading
import time

from backend import conpty, termlib
from backend.routers import terminal
from backend.server import app as backend_app

_ids = itertools.count(1)
_pending_posts: set[int] = set()
_request_id = contextvars.ContextVar("terminal_probe_request", default=0)


def _log(message):
    print(f"terminal probe {time.monotonic():.3f} [{threading.get_ident()}] {message}",
          file=sys.stderr, flush=True)


def _trace(owner, name):
    original = getattr(owner, name)
    label = f"{owner.__name__}.{name}"

    @functools.wraps(original)
    def traced(*args, **kwargs):
        ticket = next(_ids)
        _log(f"{ticket} begin {label} for request {_request_id.get()}")
        try:
            return original(*args, **kwargs)
        finally:
            _log(f"{ticket} end {label}")

    setattr(owner, name, traced)


for owner, names in ((conpty.ConPty, ("__init__", "kill", "release")),
                     (terminal, ("open_pty",)),
                     (termlib, ("open_session", "close", "put")),
                     (terminal.anyio_from_thread, ("run_sync",))):
    for name in names:
        _trace(owner, name)


async def _show_waiters(ticket):
    await asyncio.sleep(7)
    for task in asyncio.all_tasks():
        if task is asyncio.current_task() or task.get_context().get(_request_id, 0) != ticket:
            continue
        coroutine = task.get_coro()
        stack = []
        while coroutine is not None:
            frame = getattr(coroutine, "cr_frame", None) or getattr(coroutine, "ag_frame", None)
            if frame is not None:
                stack.append(f"{frame.f_code.co_filename}:{frame.f_lineno} {frame.f_code.co_name}")
            coroutine = getattr(coroutine, "cr_await", None) or getattr(coroutine, "ag_await", None)
        _log(f"{ticket} awaiting {' -> '.join(stack)}")


async def app(scope, receive, send):
    if scope["type"] != "http" or not scope["path"].startswith("/api/terminal/sessions"):
        await backend_app(scope, receive, send)
        return
    ticket = next(_ids)
    method, path = scope["method"], scope["path"]
    _log(f"{ticket} enter {method} {path}")
    watches_post = method == "POST" and (path == "/api/terminal/sessions" or path.endswith("/close"))
    token = _request_id.set(ticket)
    monitor = asyncio.create_task(_show_waiters(ticket)) if watches_post else None
    if watches_post:
        if not _pending_posts:
            faulthandler.dump_traceback_later(8, repeat=True)
        _pending_posts.add(ticket)

    async def trace_receive():
        message = await receive()
        if message["type"] == "http.request" and not message.get("more_body"):
            _log(f"{ticket} request body complete")
        return message

    async def trace_send(message):
        if message["type"] == "http.response.start":
            _log(f"{ticket} response {message['status']}")
        await send(message)
        if message["type"] == "http.response.body" and not message.get("more_body"):
            _log(f"{ticket} sent response body")

    try:
        await backend_app(scope, trace_receive, trace_send)
    finally:
        _log(f"{ticket} leave {method} {path}")
        if monitor is not None:
            monitor.cancel()
        _request_id.reset(token)
        if watches_post:
            _pending_posts.discard(ticket)
            if not _pending_posts:
                faulthandler.cancel_dump_traceback_later()
