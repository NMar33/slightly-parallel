"""Runtime configuration, resolved from the environment at app-creation time.

All knobs are documented in ``.env.example`` at the repo root. The launcher
(``sp.py``) reads ``.env`` before starting the server, so these variables
arrive as plain environment variables — the backend itself never reads
``.env`` files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .db import default_data_root, home_data_root, make_data_root

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8123",
    "http://127.0.0.1:8123",
)


@dataclass(frozen=True)
class Settings:
    data_root: Path
    host: str = "127.0.0.1"
    port: int = 8123
    cors_origins: tuple[str, ...] = _DEFAULT_CORS_ORIGINS
    # The embedded terminal spawns a real shell: off until switched on.
    # Its token is new at every start; the pages fetch it (routers/terminal.py
    # token_of). SP_TOKEN, which fixed it, is gone: a fixed token stayed
    # valid after it leaked.
    terminal_enabled: bool = False
    reload: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        # The new name first, the product's former name after it: an .env
        # written before the rename keeps working (db.default_data_root does
        # the same for the data root).
        cors_raw = os.environ.get("SP_CORS_ORIGINS") or os.environ.get("SCAN_CORS_ORIGINS", "")
        port = int(os.environ.get("SP_PORT") or os.environ.get("SCAN_PORT") or os.environ.get("PORT") or "8123")
        # The Vite dev server's port, when it is not the default: its pages
        # are Slightly Parallel's too.
        vite = (os.environ.get("VITE_PORT") or "").strip()
        own = [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]
        if vite.isdigit():
            own += [f"http://localhost:{vite}", f"http://127.0.0.1:{vite}"]
        origins = (
            tuple(o.strip() for o in cors_raw.split(",") if o.strip())
            if cors_raw
            # The defaults, and the server's own ports: a Slightly Parallel on any port
            # trusts its own pages (every other origin is refused).
            else tuple(dict.fromkeys((*_DEFAULT_CORS_ORIGINS, *own)))
        )
        root = default_data_root()
        if root == home_data_root():
            make_data_root(root)
        return cls(
            data_root=root,
            host=os.environ.get("HOST", "127.0.0.1"),
            port=port,
            cors_origins=origins,
            terminal_enabled=_env_flag("SP_ENABLE_TERMINAL"),
            reload=_env_flag("RELOAD"),
        )


_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def lan_refusal(host: str) -> str:
    """Why the server will not start on ``host``, or '' when it may.

    Slightly Parallel has no login. On a loopback address only this computer reaches
    it; on any other, every machine on the network would read every chat.
    ``SP_ALLOW_LAN=1`` is the owner saying they know."""
    if host.strip().lower() in _LOOPBACK or _env_flag("SP_ALLOW_LAN"):
        return ""
    return (
        f"HOST={host} opens Slightly Parallel to the network, and Slightly Parallel has no login: "
        "anyone who can reach this address reads every chat and changes every setting. "
        "Leave HOST unset (127.0.0.1), or set SP_ALLOW_LAN=1 to start anyway."
    )


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
