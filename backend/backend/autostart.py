"""Start at login, and a shortcut that opens the app — on Linux, macOS and
Windows, each the way the system does it, without administrator rights.

* **at login**: ``sp.py up`` (the background server, restarted if it falls
  over). Linux: an XDG autostart entry (``~/.config/autostart``), read by
  every desktop session. macOS: a LaunchAgent. Windows: a command file in
  the Startup folder.
* **shortcut**: ``sp.py open`` (starts the server when it is not running,
  then opens the page). Linux: an application entry, in the menu and on the
  desktop. macOS: a small app on the desktop. Windows: a shortcut on the
  desktop and in the Start menu.

Standard library only: ``sp.py`` loads this file by path, before the
backend's own environment exists, and the server imports it for the Setup
and Settings switches. Every file written is listed in ``.sp/autostart.json``
in the app's folder, so turning a thing off removes exactly what turning it
on wrote. Server memory for the Setup text: docs/performance.md.
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

NAME = "Slightly Parallel"
SLUG = "slightly-parallel"
LABEL = "dev.slightly-parallel.server"
KINDS = ("autostart", "shortcut")


def platform_key(plat: str | None = None) -> str:
    p = plat or sys.platform
    return "windows" if p.startswith("win") else "mac" if p == "darwin" else "linux"


def launcher_python(root: Path) -> str:
    """The interpreter sp.py last ran with (it writes it on every run): the
    one that made the backend's environment. Else this one."""
    try:
        got = (root / ".sp" / "python").read_text(encoding="utf-8").strip()
        if got and Path(got).exists():
            return got
    except OSError:
        pass
    return sys.executable


def _record_path(root: Path) -> Path:
    return root / ".sp" / "autostart.json"


def _read(root: Path) -> dict[str, list[str]]:
    try:
        data = json.loads(_record_path(root).read_text(encoding="utf-8"))
        return {k: [str(p) for p in data.get(k) or []] for k in KINDS}
    except (OSError, ValueError, AttributeError):
        return {k: [] for k in KINDS}


def _write(root: Path, record: dict[str, list[str]]) -> None:
    path = _record_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def status(root: Path) -> dict[str, Any]:
    """Each kind: on when every file it wrote is still there."""
    record = _read(root)
    out: dict[str, Any] = {}
    for kind in KINDS:
        paths = record[kind]
        out[kind] = {"on": bool(paths) and all(Path(p).exists() for p in paths), "paths": paths}
    return out


# ---------------------------------------------------------------------------
# What each system reads
# ---------------------------------------------------------------------------


def _desktop_arg(arg: str) -> str:
    """One argument of a .desktop Exec line: quoted, with the four
    characters the specification escapes inside quotes."""
    for ch in ("\\", '"', "`", "$"):
        arg = arg.replace(ch, "\\" + ch)
    return f'"{arg}"'


def _desktop_entry(root: Path, python: str, command: str, comment: str, *, hidden: bool) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={NAME}",
        f"Comment={comment}",
        f"Exec={_desktop_arg(python)} {_desktop_arg(str(root / 'sp.py'))} {command}",
        f"Path={root}",
        f"Icon={root / 'frontend' / 'public' / 'app-icon.png'}",
        "Terminal=false",
        "Categories=Development;",
    ]
    if hidden:
        lines += ["NoDisplay=true", "X-GNOME-Autostart-enabled=true"]
    return "\n".join(lines) + "\n"


def _xdg_config(home: Path) -> Path:
    env = os.environ.get("XDG_CONFIG_HOME", "")
    return Path(env) if env and Path(env).is_absolute() else home / ".config"


def _linux_desktop_dir(home: Path) -> Path:
    """The desktop folder by the user's own name for it (it is translated:
    "Рабочий стол"), from user-dirs.dirs; ~/Desktop otherwise."""
    try:
        for line in (_xdg_config(home) / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
            if line.startswith("XDG_DESKTOP_DIR="):
                value = line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(home))
                if value:
                    return Path(value)
    except OSError:
        pass
    return home / "Desktop"


def _trust(path: Path) -> None:
    """GNOME's desktop asks "Allow launching?" of a new desktop file until it
    is marked trusted; the operator turned it on, so it is. Without gio
    (another desktop) there is nothing to mark."""
    gio = shutil.which("gio")
    if gio:
        subprocess.run([gio, "set", str(path), "metadata::trusted", "true"],
                       capture_output=True, timeout=10, check=False)


def _launch_agent(root: Path, python: str) -> bytes:
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [python, str(root / "sp.py"), "up"],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        # sp.py up starts the server and returns: what it started stays.
        "AbandonProcessGroup": True,
        "StandardOutPath": str(root / ".sp" / "autostart.log"),
        "StandardErrorPath": str(root / ".sp" / "autostart.log"),
        # launchd gives no shell PATH: without Homebrew's folders a server
        # started at login found neither tmux, node nor claude.
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
    })


def _mac_app(app: Path, root: Path, python: str) -> None:
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleName": NAME, "CFBundleDisplayName": NAME,
        "CFBundleIdentifier": "dev.slightly-parallel.open", "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "open-slightly-parallel", "CFBundleShortVersionString": "1.0",
    }))
    launcher = contents / "MacOS" / "open-slightly-parallel"
    launcher.write_text(f'#!/bin/sh\ncd "{root}" && exec "{python}" "{root / "sp.py"}" open\n', encoding="utf-8")
    launcher.chmod(0o755)


def _windowless(python: str) -> str:
    """pythonw beside python, when there is one: no console window."""
    w = Path(python).with_name("pythonw.exe")
    return str(w) if w.exists() else python


def _windows_startup_cmd(root: Path, python: str) -> str:
    return (
        "@echo off\r\n"
        # The file is UTF-8 and cmd reads a batch file in the OEM code page:
        # a user folder with a non-ASCII letter started nothing, silently.
        "chcp 65001 >nul\r\n"
        f'cd /d "{root}"\r\n'
        f'start "" /b "{_windowless(python)}" "{root / "sp.py"}" up\r\n'
    )


def windows_shortcut_script(root: Path, python: str, folder: str) -> str:
    """PowerShell that makes the .lnk in a known folder
    ("Desktop", "Programs"): the folder is asked of Windows, which knows
    where a OneDrive-moved desktop is. It prints the path."""
    def q(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"
    lines = [
        f"$p = Join-Path ([Environment]::GetFolderPath({q(folder)})) {q(NAME + '.lnk')}",
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($p)",
        f"$s.TargetPath = {q(_windowless(python))}",
        f"$s.Arguments = {q(chr(34) + str(root / 'sp.py') + chr(34) + ' open')}",
        f"$s.WorkingDirectory = {q(str(root))}",
        f"$s.IconLocation = {q(str(root / 'frontend' / 'public' / 'favicon.ico'))}",
        f"$s.Description = {q('Opens ' + NAME + ', and starts it when it is not running')}",
        "$s.Save()",
        "Write-Output $p",
    ]
    return "; ".join(lines)


def _powershell(script: str) -> str:
    # UTF-8 out, both sides: a desktop path in another language ("Рабочий
    # стол") came back in the console's code page otherwise.
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=30, check=False)
    if done.returncode != 0:
        raise OSError(done.stderr.strip() or "PowerShell refused")
    return done.stdout.strip().splitlines()[-1]


# ---------------------------------------------------------------------------
# On and off
# ---------------------------------------------------------------------------


def enable(root: Path, kind: str, *, home: Path | None = None, plat: str | None = None,
           python: str | None = None) -> list[str]:
    """Write what ``kind`` needs; returns the files written. Writing it again
    writes the same files: a moved folder or a new Python is picked up."""
    if kind not in KINDS:
        raise ValueError(f"unknown: {kind}")
    home = home or Path.home()
    python = python or launcher_python(root)
    system = platform_key(plat)
    written: list[str] = []
    if system == "linux":
        if kind == "autostart":
            path = _xdg_config(home) / "autostart" / f"{SLUG}.desktop"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_desktop_entry(root, python, "up", "Starts the Slightly Parallel server at login",
                                           hidden=True), encoding="utf-8")
            written.append(str(path))
        else:
            entry = _desktop_entry(root, python, "open", "Opens Slightly Parallel, and starts it when it is not running",
                                   hidden=False)
            menu = home / ".local" / "share" / "applications" / f"{SLUG}.desktop"
            for path in (menu, _linux_desktop_dir(home) / f"{SLUG}.desktop"):
                if path.parent != menu.parent and not path.parent.is_dir():
                    continue   # no desktop folder: the menu entry is the shortcut
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(entry, encoding="utf-8")
                path.chmod(0o755)   # a desktop launches only an executable entry
                if path.parent != menu.parent:
                    _trust(path)
                written.append(str(path))
    elif system == "mac":
        if kind == "autostart":
            path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_launch_agent(root, python))
            written.append(str(path))
        else:
            app = home / "Desktop" / f"{NAME}.app"
            _mac_app(app, root, python)
            written.append(str(app))
    else:
        if kind == "autostart":
            appdata = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
            path = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{NAME}.cmd"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_windows_startup_cmd(root, python), encoding="utf-8", newline="")
            written.append(str(path))
        else:
            for folder in ("Desktop", "Programs"):
                written.append(_powershell(windows_shortcut_script(root, python, folder)))
    record = _read(root)
    record[kind] = written
    _write(root, record)
    return written


def disable(root: Path, kind: str, *, plat: str | None = None) -> list[str]:
    """Remove what ``kind`` wrote, and only that; returns what was removed."""
    if kind not in KINDS:
        raise ValueError(f"unknown: {kind}")
    record = _read(root)
    removed: list[str] = []
    for raw in record[kind]:
        path = Path(raw)
        try:
            if path.is_dir() and path.suffix == ".app":
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            else:
                continue
            removed.append(raw)
        except OSError:
            continue
    record[kind] = []
    _write(root, record)
    return removed
