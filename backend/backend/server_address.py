"""The default server address, also read by the Electron window."""

import json
from pathlib import Path

_DEFAULTS = json.loads(Path(__file__).with_name("server_defaults.json").read_text(encoding="utf-8"))
DEFAULT_HOST: str = _DEFAULTS["host"]
DEFAULT_PORT: int = _DEFAULTS["port"]


def loopback_url(port: int | str = DEFAULT_PORT, *, host: str = DEFAULT_HOST) -> str:
    return f"http://{host}:{port}"
