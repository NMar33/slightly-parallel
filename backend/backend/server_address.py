"""The default server address, also read by the Electron window."""

import json
from collections.abc import Mapping
from pathlib import Path

_DEFAULTS = json.loads(Path(__file__).with_name("server_defaults.json").read_text(encoding="utf-8"))
DEFAULT_HOST: str = _DEFAULTS["host"]
DEFAULT_PORT: int = _DEFAULTS["port"]
PORT_ENVIRONMENT: tuple[str, ...] = tuple(_DEFAULTS["portEnvironment"])


def server_port(env: Mapping[str, str], *, prefer_port: bool = False) -> str:
    if prefer_port and env.get("PORT"):
        return env["PORT"]
    return next((env[key] for key in PORT_ENVIRONMENT if env.get(key)), str(DEFAULT_PORT))


def loopback_url(port: int | str = DEFAULT_PORT, *, host: str = DEFAULT_HOST) -> str:
    return f"http://{host}:{port}"
