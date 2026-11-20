"""Data-root settings shared by the server and standalone maintenance tools."""

import os
from collections.abc import Mapping
from pathlib import Path

DATA_ROOT_ENV_KEYS = ("SP_DATA_ROOT", "SCAN_DATA_ROOT", "DATA_ROOT")
DOTENV_ROOT_KEYS = DATA_ROOT_ENV_KEYS[:2]


def named_data_root(env: Mapping[str, str]) -> str:
    return next((env[key] for key in DATA_ROOT_ENV_KEYS if env.get(key)), "")


def home_data_root() -> Path:
    return Path.home() / ".slightly-parallel"


def read_data_root_env(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    for raw in lines:
        line = raw.strip().removeprefix("export ").strip()
        key, _, value = line.partition("=")
        if key.strip() in DOTENV_ROOT_KEYS and value.strip():
            return value.strip().strip("'\"")
    return ""


def read_launcher_env(path: Path) -> dict[str, str]:
    """KEY=value lines, as bash's `set -a; source .env` reads the simple ones:
    `export` allowed, quotes stripped, # comments, $VAR expanded."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    text = path.read_text(encoding="utf-8-sig")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            quoted, value = value[0], value[1:-1]
        else:
            quoted = ""
            value = value.split(" #", 1)[0].rstrip()
        if quoted != "'":
            value = os.path.expandvars(value)
        out[key] = value
    return out
