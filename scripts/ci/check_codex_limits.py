#!/usr/bin/env python3
"""Verify Codex limits, or the exact signed-out RPC response in CI."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

CHILD_EXIT_CHECK_DELAY_S = 3

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import psutil  # noqa: E402

from backend import codexlimits  # noqa: E402

SIGNED_OUT_LIMITS_ERROR = "codex account authentication required to read rate limits"


def codex_processes() -> dict[int, str]:
    """The running processes of Codex, with their command lines."""
    out: dict[int, str] = {}
    for p in psutil.process_iter(["pid", "cmdline"]):
        line = " ".join(p.info["cmdline"] or [])
        if "codex" in line.lower() and "app-server" in line and p.info["pid"] != os.getpid():
            out[p.info["pid"]] = line[:160]
    return out


def signed_out_reply(exe: str | None) -> bool:
    if not exe:
        return False
    try:
        answers = codexlimits._rpc(exe, codexlimits.READ_TIMEOUT_S)
    except (OSError, ValueError, TimeoutError):
        return False
    init, account, limits = (answers.get(key) for key in (1, 2, 3))
    if not isinstance(init, dict) or not isinstance(account, dict) or not isinstance(limits, dict):
        return False
    identity = account.get("result")
    error = limits.get("error")
    return ("result" in init and isinstance(identity, dict) and "account" in identity and identity["account"] is None
            and isinstance(error, dict) and error.get("code") == -32600 and error.get("message") == SIGNED_OUT_LIMITS_ERROR)


def main(*, expect_signed_out: bool = False) -> int:
    found = codexlimits.detect()
    print(f"codex: {found['exe'] or 'not found'}  home: {found['home']}")
    before = codex_processes()
    if expect_signed_out:
        failed = not signed_out_reply(found["exe"])
        print("FAILED: the expected signed-out limits RPC response did not arrive" if failed else
              "Codex returned the expected signed-out response for account/rateLimits/read")
    else:
        got = codexlimits.read()
        failed = not got["ok"]
        if failed:
            print(f"FAILED: no limits reading: {got['cause']}")
        else:
            line = got["limits_line"]
            print(f"limits: plan {line.get('plan', '')}, 5-hour {line.get('five_hour')}, weekly {line.get('seven_day')}")
            print(f"account usage: {'read' if got.get('usage') else 'not read'}")
    time.sleep(CHILD_EXIT_CHECK_DELAY_S)
    left = {k: v for k, v in codex_processes().items() if k not in before}
    if left:
        print(f"FAILED: left running: {left}")
        failed = True
    print("failed" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-signed-out", action="store_true")
    sys.exit(main(expect_signed_out=parser.parse_args().expect_signed_out))
