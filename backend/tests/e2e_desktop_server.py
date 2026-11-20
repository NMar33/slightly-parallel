"""Windows desktop E2E server with a stack for stalled terminal requests."""

import faulthandler
import sys

from backend.server import app as backend_app


async def app(scope, receive, send):
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
