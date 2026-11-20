"""Data-root settings shared by the server and standalone maintenance tools."""

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
