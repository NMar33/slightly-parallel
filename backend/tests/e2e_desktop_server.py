"""Windows desktop E2E server with a stack for a stalled shell start."""

import faulthandler

from backend.server import app as backend_app


async def app(scope, receive, send):
    starting_shell = (scope["type"] == "http" and scope["method"] == "POST"
                      and scope["path"] == "/api/terminal/sessions")
    if starting_shell:
        faulthandler.dump_traceback_later(10)
    try:
        await backend_app(scope, receive, send)
    finally:
        if starting_shell:
            faulthandler.cancel_dump_traceback_later()
