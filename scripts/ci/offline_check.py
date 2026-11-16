#!/usr/bin/env python3
"""CI: the network off, the app on, on the runner's own system.

``python scripts/ci/offline_check.py`` — with the server running
(``sp.py up``): turns outgoing traffic off with the system's firewall,
keeping 127.0.0.1, and checks that

- the firewall really blocks (a connection to 1.1.1.1 fails);
- every page and the main reads answer, each within its time-out;
- Monitor reports no connection (the ping fails, the "No connection" event
  is open);
- in a browser, the pages open and ask nothing of another host, and
  Monitor shows "No connection" (offline_pages.mjs).

Then it turns the network on again. ``python scripts/ci/offline_check.py on``
only turns it on (the workflow's always() step, in case this was killed).

How the network goes off, by system:

- Linux: an iptables chain (and ip6tables) that drops new outgoing TCP
  connections, UDP and ICMP, except on the loopback;
- macOS: pf rules doing the same; pf's earlier state is put back after;
- Windows: a firewall rule that blocks outgoing traffic of the Python
  programs (the server and this check), except to 127.0.0.1 and ::1. Not the
  whole machine: Windows checks the connections already open against a new
  rule, and the runner's own connection to GitHub would be cut.

Run from the repository folder, as a user that may use sudo (Linux, macOS)
or as an administrator (Windows): GitHub's runners are both.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = f"http://127.0.0.1:{os.environ.get('SP_PORT') or 8123}"
SYSTEM = sys.platform
STATE = Path(tempfile.gettempdir()) / "sp-offline-state.json"
RULE = "SP offline check"
#: How long one read may take with the network off. The server answers these
#: from its own files in well under a second; a read that waits on the
#: network would wait for a connection's time-out first.
READ_SECONDS = 15
#: The monitor pings every 10 s and calls three misses in a row no
#: connection; the event is open by the third miss.
MONITOR_SECONDS = 120


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    print(f"$ {' '.join(args)}" + (f"\n{(done.stdout + done.stderr).strip()}" if (done.stdout + done.stderr).strip() else ""), flush=True)
    if check and done.returncode != 0:
        raise SystemExit(f"failed: {' '.join(args)}")
    return done


def powershell(script: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check)


def python_programs() -> list[str]:
    """The Python programs the server and this check run as (Windows). A
    venv's python.exe starts the base one, which is the process that connects."""
    found = {str(Path(sys.executable).resolve()), str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())}
    venv = ROOT / "backend" / ".venv"
    cfg = venv / "pyvenv.cfg"
    if cfg.is_file():
        home = next((ln.split("=", 1)[1].strip() for ln in cfg.read_text(encoding="utf-8").splitlines()
                     if ln.split("=", 1)[0].strip() == "home"), "")
        if home:
            found.add(str(Path(home) / "python.exe"))
        found.add(str(venv / "Scripts" / "python.exe"))
    return sorted(p for p in found if Path(p).exists())


def network_off() -> None:
    if SYSTEM.startswith("linux"):
        for tool in ("iptables", "ip6tables"):
            run(["sudo", tool, "-N", "SP_OFFLINE"])
            run(["sudo", tool, "-A", "SP_OFFLINE", "-o", "lo", "-j", "RETURN"])
            run(["sudo", tool, "-A", "SP_OFFLINE", "-p", "tcp", "--syn", "-j", "DROP"])
            run(["sudo", tool, "-A", "SP_OFFLINE", "-p", "udp", "-j", "DROP"])
            if tool == "iptables":   # ICMPv6 carries the neighbour discovery open connections need
                run(["sudo", tool, "-A", "SP_OFFLINE", "-p", "icmp", "-j", "DROP"])
            run(["sudo", tool, "-I", "OUTPUT", "1", "-j", "SP_OFFLINE"])
    elif SYSTEM == "darwin":
        was = "Status: Enabled" in run(["sudo", "pfctl", "-s", "info"], check=False).stdout
        rules = Path(tempfile.gettempdir()) / "sp-offline.pf"
        rules.write_text("pass out quick on lo0 all\n"
                         "block drop out quick proto tcp all flags S/SA\n"
                         "block drop out quick proto udp all\n"
                         "block drop out quick proto icmp all\n", encoding="utf-8")
        done = run(["sudo", "pfctl", "-E", "-f", str(rules)])
        token = next((ln.split(":", 1)[1].strip() for ln in (done.stdout + done.stderr).splitlines() if "Token" in ln), "")
        STATE.write_text(json.dumps({"pf_was_enabled": was, "token": token}), encoding="utf-8")
    elif SYSTEM == "win32":
        profiles = powershell("Get-NetFirewallProfile | Select-Object Name, Enabled | ConvertTo-Json").stdout
        STATE.write_text(json.dumps({"profiles": json.loads(profiles)}), encoding="utf-8")
        programs = python_programs()
        print("blocked programs:", programs, flush=True)
        remote = '"0.0.0.0-126.255.255.255","128.0.0.0-255.255.255.255","::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"'
        lines = ["Set-NetFirewallProfile -All -Enabled True"] + [
            f'New-NetFirewallRule -DisplayName "{RULE}" -Group "{RULE}" -Direction Outbound -Action Block '
            f'-Program "{p}" -RemoteAddress {remote} | Out-Null' for p in programs]
        powershell("; ".join(lines))
    else:
        raise SystemExit(f"no firewall known for {SYSTEM}")


def network_on() -> None:
    """Idempotent: whatever network_off left, removed."""
    if SYSTEM.startswith("linux"):
        for tool in ("iptables", "ip6tables"):
            while run(["sudo", tool, "-D", "OUTPUT", "-j", "SP_OFFLINE"], check=False).returncode == 0:
                pass
            run(["sudo", tool, "-F", "SP_OFFLINE"], check=False)
            run(["sudo", tool, "-X", "SP_OFFLINE"], check=False)
    elif SYSTEM == "darwin":
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}
        run(["sudo", "pfctl", "-f", "/etc/pf.conf"], check=False)
        if state.get("token"):
            run(["sudo", "pfctl", "-X", state["token"]], check=False)
        if not state.get("pf_was_enabled", False):
            run(["sudo", "pfctl", "-d"], check=False)
    elif SYSTEM == "win32":
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}
        lines = [f'Remove-NetFirewallRule -Group "{RULE}" -ErrorAction SilentlyContinue']
        profiles = state.get("profiles") or []
        for p in profiles if isinstance(profiles, list) else [profiles]:
            # Enabled comes back as 1/0 (GpoBoolean) or true/false.
            on = p.get("Enabled") in (1, True, "True")
            lines.append(f"Set-NetFirewallProfile -Name {p.get('Name')} -Enabled {'True' if on else 'False'}")
        powershell("; ".join(lines), check=False)
    STATE.unlink(missing_ok=True)


def reaches(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


_cookie = ""


def call(path: str, body: dict | None = None, timeout: float = READ_SECONDS) -> tuple[int, bytes, float]:
    """One request as the page makes it: status, body, seconds."""
    global _cookie
    if not _cookie:
        req = urllib.request.Request(BASE + "/api/health", headers={"Sec-Fetch-Site": "same-origin"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _cookie = (r.headers.get("Set-Cookie") or "").split(";", 1)[0]
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Cookie": _cookie, **({"Content-Type": "application/json"} if data else {})}
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=headers), timeout=timeout) as r:
        return r.status, r.read(), time.time() - t


def checks() -> list[str]:
    failed: list[str] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail != "" else ""), flush=True)
        if not ok:
            failed.append(name)

    check("the firewall blocks: 1.1.1.1:443 and 8.8.8.8:53 do not answer",
          not reaches("1.1.1.1", 443) and not reaches("8.8.8.8", 53))
    check("127.0.0.1 still answers", reaches("127.0.0.1", int(BASE.rsplit(":", 1)[1])))
    if failed:
        return failed

    reads = [("GET", "/api/health"), ("GET", "/api/snapshot"), ("GET", "/api/monitor/now"), ("GET", "/api/monitor/events"),
             ("GET", "/api/usage"), ("GET", "/api/usage/limits"), ("POST", "/api/usage/limits/refresh"),
             ("GET", "/api/sessions"), ("GET", "/api/stats/tasks"), ("GET", "/api/backup"), ("GET", "/api/setup/info"),
             ("GET", "/api/settings"), ("GET", f"/api/checkup?{urllib.parse.urlencode({'cwd': str(ROOT)})}"),
             ("GET", "/api/diagnostics/report"), ("GET", "/"), ("GET", "/monitor"), ("GET", "/usage"), ("GET", "/kanban")]
    for method, path in reads:
        try:
            status, _, took = call(path, {} if method == "POST" else None)
            check(f"{method} {path.split('?')[0]} answers within {READ_SECONDS} s", status == 200, f"{took:.2f} s")
        except Exception as exc:
            check(f"{method} {path.split('?')[0]} answers within {READ_SECONDS} s", False, exc)

    start = time.time()
    now: dict = {}
    while time.time() - start < MONITOR_SECONDS:
        now = json.loads(call("/api/monitor/now")[1])
        sample = now.get("sample") or {}
        if sample.get("ping_ok") is False and any(e.get("key") == "net.down" for e in now.get("open") or []):
            break
        time.sleep(2)
    sample = now.get("sample") or {}
    down = [e for e in now.get("open") or [] if e.get("key") == "net.down"]
    check("Monitor reports no connection: the ping fails", sample.get("ping_ok") is False, (sample.get("ping_host"), sample.get("ping_ok")))
    check(f"…and the event \"No connection\" is open ({time.time() - start:.0f} s)", bool(down),
          down[0].get("title") if down else [e.get("key") for e in now.get("open") or []])

    node = shutil.which("node")
    if not node:
        check("node for the browser half", False, "node is not on PATH")
        return failed
    t = time.time()
    done = subprocess.run([node, str(ROOT / "scripts" / "ci" / "offline_pages.mjs")], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)
    print((done.stdout + done.stderr).strip(), flush=True)
    check(f"in a browser the pages open, ask no other host, and Monitor says No connection ({time.time() - t:.0f} s)",
          done.returncode == 0)
    return failed


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "on":
        network_on()
        print("network on", flush=True)
        return 0
    try:
        call("/api/health")
    except OSError as exc:
        sys.exit(f"start the server first (sp.py up): {exc}")
    network_off()
    try:
        failed = checks()
    finally:
        network_on()
    back = any(reaches("1.1.1.1", 443) for _ in range(5))
    print(f"network on again: {'1.1.1.1 answers' if back else '1.1.1.1 does not answer'}", flush=True)
    if failed:
        sys.exit("failed: " + ", ".join(failed))
    print("all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
