#!/usr/bin/env python3
"""CI: start at login and the shortcut, for real, on the runner's system.

There is no login in CI, so this does what the system does at login: reads
the command out of the entry ``sp autostart on`` wrote (the .desktop Exec
line, the LaunchAgent's ProgramArguments, the Startup .cmd), runs it, and
waits for the server to answer. The shortcut is read back the same way
(the .lnk through Windows itself), then opened as a double click would:
the .lnk through Windows, the .desktop's Exec line, the macOS app's own
program. With the server down it starts it, the page answers and a browser
is asked to open it; with the server up it only asks the browser (the
supervisor stays the same process). The browser is a stand-in named in
BROWSER that writes down the address it was given. Then both are turned
off, and nothing of them may be left. Run from the repository folder, with
the server stopped.
"""

from __future__ import annotations

import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
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


def supervisor() -> str:
    pid = ROOT / ".sp" / "supervisor.pid"
    return pid.read_text(encoding="utf-8").strip() if pid.is_file() else ""


def open_shortcut(path: str) -> None:
    """What a double click on the shortcut runs."""
    if path.endswith(".lnk"):
        os.startfile(path)  # type: ignore[attr-defined]  # Windows only
    elif path.endswith(".desktop"):
        subprocess.Popen(login_command(Path(path)), cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:   # the macOS app: `open` would start it without this environment, so its program is run
        subprocess.Popen([str(Path(path) / "Contents" / "MacOS" / "open-slightly-parallel")], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def opened(log: Path, count: int, seconds: int) -> list[str]:
    """The addresses the stand-in browser was given, once there are `count`."""
    lines: list[str] = []
    for _ in range(seconds):
        lines = log.read_text(encoding="utf-8").split() if log.is_file() else []
        if len(lines) >= count:
            break
        time.sleep(1)
    return lines


def shortcut_opens(path: str) -> None:
    """Down: the shortcut starts the server and opens the page. Up: it only opens."""
    work = Path(tempfile.mkdtemp(prefix="sp-browser-"))
    log = work / "opened.txt"
    fake = work / "browser.py"
    fake.write_text("import os, sys\n"
                    "with open(os.environ['SP_CI_BROWSER_LOG'], 'a', encoding='utf-8') as f:\n"
                    "    f.write(sys.argv[1] + '\\n')\n", encoding="utf-8")
    # webbrowser splits BROWSER like a shell: forward slashes keep a Windows path whole.
    os.environ["BROWSER"] = f'"{Path(sys.executable).as_posix()}" "{fake.as_posix()}" %s'
    os.environ["SP_CI_BROWSER_LOG"] = str(log)

    assert not healthy(1), "the server should be down before the shortcut is opened"
    open_shortcut(path)
    if not healthy(600):
        server_log = ROOT / ".sp" / "server.log"
        print(server_log.read_text(encoding="utf-8", errors="replace")[-4000:] if server_log.exists() else "no server.log")
        sys.exit("the shortcut did not start the server")
    first = opened(log, 1, 120)
    page = urllib.request.urlopen(f"http://127.0.0.1:{os.environ.get('SP_PORT') or 8123}/", timeout=30)
    body = page.read().decode("utf-8", "replace")
    print(f"down: the shortcut started the server and opened {first}; the page answers {page.status}", flush=True)
    assert first and first[0].startswith("http://127.0.0.1:"), f"the browser was not asked to open the app: {first}"
    assert page.status == 200 and "<div id=\"root\"" in body, body[:300]

    before = supervisor()
    open_shortcut(path)
    second = opened(log, 2, 120)
    print(f"up: the shortcut opened {second[1:]}; supervisor {before} -> {supervisor()}", flush=True)
    assert len(second) == 2 and second[1] == first[0], f"the browser was not asked again: {second}"
    assert before and supervisor() == before, "the shortcut started a second server"
    sp("down")
    shutil.rmtree(work, ignore_errors=True)


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
    # The one a person double-clicks: the desktop's on Linux and Windows, the app on macOS.
    shortcut_opens(next((p for p in paths if "Desktop" in p or p.endswith(".app")), paths[0]))

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
