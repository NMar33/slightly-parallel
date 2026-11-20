"""Diagnostics for stalled Windows terminal requests on this CI snapshot."""

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


def _log(message):
    print(f"terminal probe {time.monotonic():.3f} [{threading.get_ident()}] {message}",
          file=sys.stderr, flush=True)


def _trace(owner, name):
    original = getattr(owner, name)
    label = f"{owner.__name__}.{name}"

    @functools.wraps(original)
    def traced(*args, **kwargs):
        ticket = next(_ids)
        _log(f"{ticket} begin {label}")
        try:
            return original(*args, **kwargs)
        finally:
            _log(f"{ticket} end {label}")

    setattr(owner, name, traced)


for owner, names in ((conpty.ConPty, ("__init__", "kill", "release")),
                     (terminal, ("open_pty",)),
                     (termlib, ("open_session", "close"))):
    for name in names:
        _trace(owner, name)


async def app(scope, receive, send):
    if scope["type"] != "http" or not scope["path"].startswith("/api/terminal/sessions"):
        await backend_app(scope, receive, send)
        return
    ticket = next(_ids)
    method, path = scope["method"], scope["path"]
    _log(f"{ticket} enter {method} {path}")
    watches_post = method == "POST" and (path == "/api/terminal/sessions" or path.endswith("/close"))
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

    try:
        await backend_app(scope, trace_receive, trace_send)
    finally:
        _log(f"{ticket} leave {method} {path}")
        if watches_post:
            _pending_posts.discard(ticket)
            if not _pending_posts:
                faulthandler.cancel_dump_traceback_later()
