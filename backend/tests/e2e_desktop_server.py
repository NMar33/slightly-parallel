"""Windows desktop E2E server with a stack for stalled terminal requests."""

import faulthandler
import functools
import json
import sys
import time

from backend import watcher
from backend.db import ViewStore
from backend.server import app as backend_app


def _log(message):
    print(f"rhythm probe {time.monotonic():.3f} {message}", file=sys.stderr, flush=True)


_original_event = watcher.DebouncedHandler.on_any_event


def _trace_event(self, event):
    if "cc-e2e-rhythm-" in str(event.src_path) or "cc-e2e-rhythm-" in str(getattr(event, "dest_path", "")):
        _log(f"watch {event.event_type}: {event.src_path}")
    return _original_event(self, event)


watcher.DebouncedHandler.on_any_event = _trace_event
_original_rebuild = ViewStore.rebuild


@functools.wraps(_original_rebuild)
def _trace_rebuild(self, *args, **kwargs):
    _log("rebuild begin")
    try:
        return _original_rebuild(self, *args, **kwargs)
    finally:
        _log(f"rebuild end; rhythm agents = {[a.get('agent_id') for a in self.agents() if 'e2e-rhythm-' in str(a.get('agent_id'))]}")


ViewStore.rebuild = _trace_rebuild


async def app(scope, receive, send):
    terminal_request = scope["type"] == "http" and scope["path"].startswith("/api/terminal/sessions") and (
        scope["path"] == "/api/terminal/sessions" or scope["path"].endswith("/close")
    )
    if terminal_request:
        print(f"Terminal fixture entered {scope['method']} {scope['path']}", file=sys.stderr, flush=True)
        faulthandler.dump_traceback_later(10)
    if scope["type"] == "http" and scope["path"] == "/api/terminal/tabs":
        original_send = send
        chunks = bytearray()

        async def trace_tabs(message):
            if message["type"] == "http.response.body":
                chunks.extend(message.get("body", b""))
                if not message.get("more_body"):
                    try:
                        tabs = json.loads(chunks).get("tabs", {})
                        _log(f"tabs ids={[(sid, tab.get('agent_id'), bool(tab.get('chat'))) for sid, tab in tabs.items()]}")
                    except (UnicodeError, ValueError):
                        _log("tabs response is not plain JSON")
            await original_send(message)

        send = trace_tabs
    try:
        await backend_app(scope, receive, send)
    finally:
        if terminal_request:
            faulthandler.cancel_dump_traceback_later()
