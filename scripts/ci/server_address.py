"""Find the test server's loopback address from the runner's SP_PORT."""

import os
import runpy
from pathlib import Path

_ADDRESS = runpy.run_path(str(Path(__file__).resolve().parents[2] / "backend" / "backend" / "server_address.py"))


def server_url() -> str:
    return _ADDRESS["loopback_url"](os.environ.get("SP_PORT") or _ADDRESS["DEFAULT_PORT"])
