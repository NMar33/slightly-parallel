"""Prepare the exact pytest interpreter and Git identity used by agent core."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parents[2] / "backend" / "requirements-dev.txt"
INSTALL_TIMEOUT_S = 60
VERIFY_TIMEOUT_S = 15


def prepare(*, check_only: bool = False) -> None:
    matches = re.findall(r"(?m)^pytest==([^\s;]+)$", REQUIREMENTS.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise RuntimeError("requirements-dev.txt must pin exactly one pytest version")
    version = matches[0]
    if not check_only:
        subprocess.run([sys.executable, "-m", "pip", "install", f"pytest=={version}"],
                       check=True, timeout=INSTALL_TIMEOUT_S)
    result = subprocess.run([sys.executable, "-m", "pytest", "--version"], check=True,
                            timeout=VERIFY_TIMEOUT_S, capture_output=True, encoding="utf-8")
    if result.stdout.strip() != f"pytest {version}":
        raise RuntimeError("the core runner's Python did not report the pinned pytest version")
    for identity in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        subprocess.run(["git", "var", identity], check=True, timeout=VERIFY_TIMEOUT_S, stdout=subprocess.DEVNULL)
    print(f"Core toolchain ready: {sys.executable} with pytest {version}; Git author and committer configured", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="verify an already prepared environment")
    prepare(check_only=parser.parse_args().check_only)
