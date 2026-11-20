"""Diagnostics for stalled Windows terminal requests on this CI snapshot."""

import asyncio
import contextvars
import faulthandler
import functools
import itertools
import sys
import threading
import time
from types import SimpleNamespace

from anyio import to_thread
from anyio._backends._asyncio import WorkerThread

from backend import conpty, file_safety, termlib
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


def _worker_ticket(item):
    if item is None:
        return ""
    context, func, _, future, _ = item
    ticket = context.get(_request_id, 0)
    name = getattr(func, "__qualname__", type(func).__name__)
    return f"request {ticket} future {id(future)} {name}" if ticket else ""


_worker_init = WorkerThread.__init__
_worker_report = WorkerThread._report_result
_worker_stop = WorkerThread.stop


def _trace_worker_init(self, *args):
    _worker_init(self, *args)
    put, get = self.queue.put, self.queue.get

    def traced_put(item, *args, **kwargs):
        if label := _worker_ticket(item):
            _log(f"worker {self.ident} queue {label} root {id(self.root_task)} done={self.root_task.done()}")
        return put(item, *args, **kwargs)

    def traced_get(*args, **kwargs):
        item = get(*args, **kwargs)
        if label := _worker_ticket(item):
            _log(f"worker {self.ident} take {label}")
        return item

    self.queue.put = traced_put
    self.queue.get = traced_get


def _trace_worker_report(self, future, result, exc):
    _log(f"worker {self.ident} report future {id(future)} done={future.done()}")
    return _worker_report(self, future, result, exc)


def _trace_worker_stop(self, root=None):
    _log(f"worker {self.ident} stop task {id(root)} root {id(self.root_task)} done={self.root_task.done()}")
    return _worker_stop(self, root)


WorkerThread.__init__ = _trace_worker_init
WorkerThread._report_result = _trace_worker_report
WorkerThread.stop = _trace_worker_stop


_real_try_lock = file_safety._try_lock
_real_unlock = file_safety._unlock
_lock_owner = {}
_lock_retry = threading.local()


def _observe_lock(fh):
    if not fh.name.endswith("sessions.json.lock"):
        return _real_try_lock(fh)
    ticket = _request_id.get()
    held = _real_try_lock(fh)
    _lock_retry.pending = (not held, ticket)
    if held:
        _lock_owner[fh.name] = (id(fh), ticket)
        _log(f"file lock acquired by {ticket} fd {fh.fileno()}")
    else:
        _log(f"file lock contended by {ticket}, holder {_lock_owner.get(fh.name)}")
    return held


def _observe_unlock(fh):
    if not fh.name.endswith("sessions.json.lock"):
        return _real_unlock(fh)
    try:
        return _real_unlock(fh)
    finally:
        if _lock_owner.get(fh.name, (None,))[0] == id(fh):
            _lock_owner.pop(fh.name, None)
            _log(f"file lock released by {_request_id.get()} fd {fh.fileno()}")


def _observe_lock_sleep(seconds):
    pending, ticket = getattr(_lock_retry, "pending", (False, 0))
    _lock_retry.pending = (False, 0)
    if not pending:
        return time.sleep(seconds)
    start = time.monotonic()
    _log(f"file lock request {ticket} enter sleep({seconds})")
    try:
        return time.sleep(seconds)
    finally:
        _log(f"file lock request {ticket} exit sleep after {time.monotonic() - start:.3f}s")


file_safety._try_lock = _observe_lock
file_safety._unlock = _observe_unlock
file_safety.time = SimpleNamespace(
    monotonic=time.monotonic, sleep=_observe_lock_sleep, strftime=time.strftime,
)


async def _show_waiters(ticket):
    await asyncio.sleep(7)
    _log(f"{ticket} limiter {to_thread.current_default_thread_limiter().statistics()}")
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
