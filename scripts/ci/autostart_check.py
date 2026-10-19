#!/usr/bin/env python3
"""CI: start at login and the shortcut, for real, on the runner's system.

There is no login in CI, so this does what the system does at login: reads
the command out of the entry ``sp autostart on`` wrote (the .desktop Exec
line, the LaunchAgent's ProgramArguments, the Startup .cmd), runs it, and
waits for the server to answer. The shortcut is read back the same way
(the .lnk through Windows itself). Then both are turned off, and nothing of
them may be left. Run from the repository folder, with the server stopped.
"""

from __future__ import annotations

import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"


def sp(*args: str) -> str:
    done = subprocess.run([sys.executable, str(ROOT / "sp.py"), *args], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    print(f"$ sp {' '.join(args)}\n{done.stdout}{done.stderr}", flush=True)
    if done.returncode != 0:
        sys.exit(f"sp {' '.join(args)} failed")
    return done.stdout


def record() -> dict[str, list[str]]:
    return json.loads((ROOT / ".sp" / "autostart.json").read_text(encoding="utf-8"))


def healthy(seconds: int) -> bool:
    for _ in range(seconds):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{os.environ.get('SP_PORT') or 8123}/api/health", timeout=2)
            return True
        except OSError:
            time.sleep(1)
    return False


def login_command(entry: Path) -> list[str]:
    """What the system runs at login, read from the entry."""
    if entry.suffix == ".desktop":
        line = next(x for x in entry.read_text(encoding="utf-8").splitlines() if x.startswith("Exec="))
        return shlex.split(line[len("Exec="):])
    if entry.suffix == ".plist":
        return list(plistlib.loads(entry.read_bytes())["ProgramArguments"])
    return ["cmd", "/c", str(entry)]


def lnk_target(lnk: str) -> str:
    script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
              "Write-Output ($s.TargetPath + ' ' + $s.Arguments)")
    return subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=60).stdout.strip()


def main() -> int:
    if healthy(1):
        sys.exit("stop the server first: this starts it the way a login does")

    sp("autostart", "on")
    (entry,) = [Path(p) for p in record()["autostart"]]
    assert entry.exists(), entry
    if entry.suffix == ".plist" and shutil.which("plutil"):
        subprocess.run(["plutil", "-lint", str(entry)], check=True)
    if entry.suffix == ".desktop" and shutil.which("desktop-file-validate"):
        subprocess.run(["desktop-file-validate", str(entry)], check=True)
    command = login_command(entry)
    print("at login:", command, flush=True)
    subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not healthy(600):
        log = ROOT / ".sp" / "server.log"
        print(log.read_text(encoding="utf-8", errors="replace")[-4000:] if log.exists() else "no server.log")
        sys.exit("the login command did not start the server")
    print("the login command started the server", flush=True)
    sp("down")

    sp("shortcut")
    paths = record()["shortcut"]
    assert paths and all(Path(p).exists() for p in paths), paths
    for p in paths:
        if p.endswith(".lnk"):
            target = lnk_target(p)
            print(p, "->", target)
            assert "sp.py" in target and target.endswith("open"), target
        elif p.endswith(".desktop"):
            assert login_command(Path(p))[-1] == "open"
        else:   # the macOS app
            launcher = Path(p) / "Contents" / "MacOS" / "open-slightly-parallel"
            assert os.access(launcher, os.X_OK) and launcher.read_text(encoding="utf-8").rstrip().endswith("open")

    sp("autostart", "off")
    sp("shortcut", "off")
    left = [p for kind in record().values() for p in kind] + [str(entry)] + paths
    still = [p for p in left if Path(p).exists()]
    if still:
        sys.exit(f"turned off, still there: {still}")
    print("on, started, read back, off: all of it", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
