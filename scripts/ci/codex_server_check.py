#!/usr/bin/env python3
"""CI: the plan limits' read of the real Codex, asked for the way the Usage
page asks, from the real server.

check_codex_limits.py calls the reading code itself. This starts the server
(``python -m backend.server``) on an empty data folder and a free port, sends
``POST /api/usage/limits/refresh`` as the page's "Read now" does, and reads
``GET /api/usage/limits`` until the Codex row has an answer. Then:

- the row returns a successful reading, or exactly "not signed in" when
  CI explicitly exercises the logged-out path;
- no codex or node process started during the read is left running
  (Windows: codex.cmd starts node, which starts codex.exe);
- the data folder's ``.usage`` holds no temporary file (``.units.json.*``,
  ``*.tmp``, ``*.part``): every write there finished or was cleaned up.

Run from the repository folder, with the backend's packages and Codex
installed and logged in. Spends no tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import psutil

API_REQUEST_TIMEOUT_S = 30
OPERATOR_COOKIE_TIMEOUT_S = 10
HEALTH_REQUEST_TIMEOUT_S = 3
CHILD_EXIT_CHECK_DELAY_S = 3
SERVER_EXIT_TIMEOUT_S = 15

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Server:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.cookie = ""

    def call(self, path: str, body: dict | None = None, timeout: float = API_REQUEST_TIMEOUT_S) -> dict:
        if not self.cookie:
            # The cookie the server hands its own pages: this stands in for the page.
            req = urllib.request.Request(self.base + "/api/health", headers={"Sec-Fetch-Site": "same-origin"})
            with urllib.request.urlopen(req, timeout=OPERATOR_COOKIE_TIMEOUT_S) as r:
                self.cookie = (r.headers.get("Set-Cookie") or "").split(";", 1)[0]
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Cookie": self.cookie, **({"Content-Type": "application/json"} if data else {})}
        with urllib.request.urlopen(urllib.request.Request(self.base + path, data=data, headers=headers), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))


def codex_or_node() -> dict[int, str]:
    """Running codex processes, and node processes running Codex, with their
    command lines. Another node (the runner's own) is not counted."""
    out: dict[int, str] = {}
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        name = (p.info["name"] or "").lower()
        line = " ".join(p.info["cmdline"] or [name])
        if p.info["pid"] != os.getpid() and (name.startswith("codex") or name.startswith("node") and "codex" in line.lower()):
            out[p.info["pid"]] = line[:200]
    return out


def temporary_files(usage: Path) -> list[str]:
    if not usage.is_dir():
        return []
    return sorted(p.name for p in usage.iterdir()
                  if p.name.startswith(".units.json.") or p.suffix in (".tmp", ".part") or ".tmp" in p.name)


def poll_answered(poll: dict, *, expect_signed_out: bool) -> bool:
    if expect_signed_out:
        return poll.get("cause") == "not signed in" and not poll.get("last_success")
    return bool(poll.get("last_success")) and not poll.get("cause")


def main(*, expect_signed_out: bool = False) -> int:
    data = Path(tempfile.mkdtemp(prefix="sp codex ü-")).resolve()
    port = free_port()
    before = codex_or_node()
    log = open(data.parent / f"{data.name}.log", "w", encoding="utf-8")
    env = {**os.environ, "SP_DATA_ROOT": str(data), "SP_PORT": str(port), "PYTHONUTF8": "1", "SP_EXAMPLE": "0"}
    flags: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, "-m", "backend.server"], cwd=ROOT / "backend", env=env,
                            stdout=log, stderr=subprocess.STDOUT, **flags)
    server = Server(port)
    failed: list[str] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail != "" else ""), flush=True)
        if not ok:
            failed.append(name)

    try:
        up = False
        for _ in range(180):
            if proc.poll() is not None:
                break
            try:
                server.call("/api/health", timeout=HEALTH_REQUEST_TIMEOUT_S)
                up = True
                break
            except OSError:
                time.sleep(1)
        if not up:
            log.flush()
            print(Path(log.name).read_text(encoding="utf-8", errors="replace")[-4000:])
            sys.exit("the server did not start")
        print(f"server on {server.base}, data folder {data}", flush=True)

        asked = server.call("/api/usage/limits/refresh", {})
        print("refresh:", asked, flush=True)
        check("the server finds Codex", asked.get("why") != "absent", asked)

        # The page reads the limits again a few seconds after "Read now". The
        # read ends within its own time-out (codexlimits.READ_TIMEOUT_S, 15 s,
        # and 5 s to end the process): the state says when it did.
        poll: dict = {}
        limits: list = []
        for _ in range(60):
            got = server.call("/api/usage/limits")
            poll, limits = got.get("codex_poll") or {}, got.get("limits") or []
            if poll.get("last_attempt") and (poll.get("last_success") or poll.get("cause")):
                break
            time.sleep(1)
        print("codex_poll:", json.dumps(poll), flush=True)
        print("limits:", json.dumps(limits)[:600], flush=True)
        cause = str(poll.get("cause") or "")
        check("the Codex row shows the expected limits result", poll_answered(poll, expect_signed_out=expect_signed_out), cause or poll)
        if cause:
            print(f"  info Codex says: {cause}", flush=True)

        time.sleep(CHILD_EXIT_CHECK_DELAY_S)
        left = {k: v for k, v in codex_or_node().items() if k not in before}
        check("no codex or node process from the read is left", not left, left)
        tmp = temporary_files(data / ".usage")
        check("no temporary file in the data folder's .usage", not tmp, tmp)
        print("  info .usage holds:", sorted(p.name for p in (data / ".usage").iterdir()) if (data / ".usage").is_dir() else "nothing", flush=True)
    finally:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(proc.pid, 15)
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=SERVER_EXIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
    if failed:
        sys.exit("failed: " + ", ".join(failed))
    print("all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-signed-out", action="store_true")
    sys.exit(main(expect_signed_out=parser.parse_args().expect_signed_out))
