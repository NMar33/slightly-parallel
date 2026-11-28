"""The filename format shared by terminal snapshots and legacy backup readers."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

_PREFIX = "terminal-"
_SUFFIX = ".json"
_STAMP = "%Y%m%dT%H%M%S%fZ"
_NONCE_BYTES = 4
_STAMP_PATTERN = re.sub(r"[0-9]", "[0-9]", datetime(2000, 1, 1).strftime(_STAMP))
_FILENAME = re.compile(
    rf"{re.escape(_PREFIX)}{_STAMP_PATTERN}-[A-Za-z0-9_.-]{{1,80}}-[0-9a-f]{{{2 * _NONCE_BYTES}}}{re.escape(_SUFFIX)}"
)


def snapshot_filename(sid: str) -> str:
    stamp = datetime.now(UTC).strftime(_STAMP)
    file_sid = sid.replace(":", "_")
    return f"{_PREFIX}{stamp}-{file_sid}-{secrets.token_hex(_NONCE_BYTES)}{_SUFFIX}"


def is_snapshot_filename(name: str) -> bool:
    return _FILENAME.fullmatch(name) is not None
