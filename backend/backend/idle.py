"""How long since the operator last touched the computer — any app, not
only Slightly Parallel's tabs.

Slightly Parallel runs on the operator's own laptop, so the server can ask the
desktop directly: GNOME's idle monitor (Wayland and X11), ``xprintidle``
(other X11 desktops), macOS's HID idle time, Windows' last-input tick.
``idle_seconds()`` answers ``None`` when none of them can be read; the
timer then never pauses on its own and says why.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time

_GNOME = ("gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
          "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
          "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime")

_lock = threading.Lock()
_cache: tuple[float, float | None, str] = (0.0, None, "")
_CACHE_SEC = 2.0


def _run(argv: tuple[str, ...] | list[str]) -> str | None:
    try:
        out = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _gnome() -> float | None:
    if not shutil.which("gdbus") or not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return None
    m = re.search(r"uint64 (\d+)", _run(_GNOME) or "")
    return int(m.group(1)) / 1000 if m else None


def _xprintidle() -> float | None:
    if not shutil.which("xprintidle"):
        return None
    raw = (_run(["xprintidle"]) or "").strip()
    return int(raw) / 1000 if raw.isdigit() else None


def _macos() -> float | None:
    m = re.search(r'"HIDIdleTime" = (\d+)', _run(["ioreg", "-c", "IOHIDSystem"]) or "")
    return int(m.group(1)) / 1e9 if m else None


def _windows() -> float | None:  # pragma: no cover — Windows only
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
        return None
    return max(0, ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000  # type: ignore[attr-defined]


def _read() -> tuple[float | None, str]:
    if sys.platform == "win32":
        return _windows(), "windows"
    if sys.platform == "darwin":
        return _macos(), "macos"
    for how, read in (("gnome", _gnome), ("xprintidle", _xprintidle)):
        got = read()
        if got is not None:
            return got, how
    return None, ""


def idle_seconds() -> float | None:
    """Seconds since the last keystroke or mouse move, anywhere; None: unknown."""
    return reading()[0]


def reading() -> tuple[float | None, str]:
    """(idle seconds or None, which source answered: gnome, xprintidle, macos, windows, "")."""
    global _cache
    with _lock:
        at, value, how = _cache
        if time.monotonic() - at < _CACHE_SEC:
            return value, how
    value, how = _read()
    with _lock:
        _cache = (time.monotonic(), value, how)
    return value, how
