"""Importing the server writes nothing into the home folder.

A bare ``pytest`` on an operator's machine imports backend.server; if the
module built its app on import, that app would settle on
``~/.slightly-parallel`` and write the operator token, examples and skills
there. The import runs in a child whose home is a fresh folder and whose
environment names no data root.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_importing_the_server_creates_nothing_in_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ("SP_DATA_ROOT", "SCAN_DATA_ROOT", "DATA_ROOT", "SP_SANDBOX")}
    env.update({"HOME": str(home), "USERPROFILE": str(home)})
    proc = subprocess.run(
        [sys.executable, "-c",
         "import backend.server, pathlib; print(pathlib.Path.home())"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert Path(proc.stdout.strip()) == home
    assert not (home / ".slightly-parallel").exists()
    assert list(home.iterdir()) == []
