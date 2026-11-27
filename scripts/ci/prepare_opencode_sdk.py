#!/usr/bin/env python3
"""Install the OpenCode SDK matching the installed CLI before its PTY starts."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fresh_user"))
from agents import OPENCODE_SDK_INSTALL_TIMEOUT_S, OpenCodeSDKError, tools, validate_opencode_sdk  # noqa: E402
from common import redact_diagnostics  # noqa: E402

STDERR_TAIL_BYTES = 4000
UNRELATED_SECRET_ENV = frozenset({
    "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "OPENAI_API_KEY", "CODEX_OPENAI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
})
SECRET_ENV = UNRELATED_SECRET_ENV | {"NODE_AUTH_TOKEN", "NPM_TOKEN"}
SDK_STOP_TIMEOUT_S = 5


def install(argv: list[str], env: dict[str, str], stderr) -> int:
    with subprocess.Popen(argv, env=env, stderr=stderr, stdout=subprocess.DEVNULL) as proc:
        try:
            return proc.wait(timeout=OPENCODE_SDK_INSTALL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                # npm.cmd launches Node as a child. End the tree while this PID
                # still identifies it, before trying to remove the seed.
                try:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=SDK_STOP_TIMEOUT_S)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            proc.kill()
            raise


def prepare(seed: Path, report: Path, version: str) -> bool:
    started = time.monotonic()
    npm = shutil.which("npm")
    status = "ready"
    detail = ""
    with tempfile.TemporaryFile() as stderr:
        try:
            if npm is None:
                status = "npm unavailable"
            elif not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)*", version):
                status = "OpenCode CLI version unavailable"
            else:
                seed.mkdir(parents=True, exist_ok=True)
                env = {key: value for key, value in os.environ.items() if key.upper() not in UNRELATED_SECRET_ENV}
                exit_code = install([npm, "install", "--no-audit", "--no-fund", "--ignore-scripts", "--loglevel=verbose",
                                     "--prefix", str(seed), f"@opencode-ai/plugin@{version}"], env, stderr)
                if exit_code:
                    status, detail = "npm failed", f"exit code {exit_code}"
                else:
                    validate_opencode_sdk(seed, version)
        except subprocess.TimeoutExpired:
            status = "timed out"
        except OpenCodeSDKError as error:
            status, detail = "invalid seed", str(error)
        except OSError as error:
            status, detail = "install error", type(error).__name__
        stderr.seek(max(0, stderr.seek(0, os.SEEK_END) - STDERR_TAIL_BYTES))
        tail = redact_diagnostics(stderr.read().decode("utf-8", errors="replace"))
        tail = re.sub(r"(https?://)[^/\s@]+@", r"\1[redacted]@", tail)
        tail = re.sub(r"(https?://[^\s?#]+)[?#]\S+", r"\1?[redacted]", tail)
        for key in SECRET_ENV:
            if secret := os.environ.get(key):
                tail = redact_diagnostics(tail, known_key=secret)

    elapsed = round(time.monotonic() - started, 2)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"status": status, "detail": detail, "timeout_seconds": OPENCODE_SDK_INSTALL_TIMEOUT_S,
                                  "elapsed_seconds": elapsed, "stderr_tail": tail}, indent=2) + "\n", encoding="utf-8")
    print(f"OpenCode SDK prerequisite: {status} ({elapsed:.2f} seconds, npm limit {OPENCODE_SDK_INSTALL_TIMEOUT_S} seconds)",
          flush=True)
    return status == "ready"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    return 0 if prepare(args.seed, args.report, tools()["opencode"].version()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
