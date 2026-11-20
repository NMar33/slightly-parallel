"""A Windows pseudo console (ConPTY) for a plain terminal, through pywinpty.

The Unix side of routers/terminal.py forks a pty; Windows has none. This is
the whole Windows path, kept in one place: a shell started in a pseudo
console, its output read on a worker thread, typed input, a resize, its
exit, and closing it with every process under it.

pywinpty (``winpty.PTY``, pywinpty 3.x; installed on Windows only, see
requirements.txt) is used at its low level:

- ``PTY(cols, rows, backend)`` makes the pseudo console; sizes are 16-bit
  (a COORD of two signed shorts), so the caller clamps them;
- ``spawn(appname, cmdline, cwd, env)`` starts the program in it — ``env`` is
  one string of ``NAME=value`` pairs, each ended by a NUL;
- ``read(blocking=True)`` waits, with the GIL released, for the next output
  as text; it returns "" when its reader has stopped and raises
  ``WinptyError`` ("Standard out reached EOF") once the program has ended
  and its output is drained;
- ``write(text)``, ``set_size(cols, rows)``, ``isalive()``, ``pid``,
  ``cancel_io()`` (a blocked read returns).

The ``PTY`` object closes the pseudo console when it is dropped — so it is
dropped only once nothing reads it any more (``release``), the same rule the
Unix side keeps for its file descriptor.

Closing a pseudo console (ClosePseudoConsole, in the drop) waits for its
console host — OpenConsole.exe or conhost.exe, a child of this server — to
end, and the host may first wait to hand its last screen to an output pipe
nobody reads any more. A terminal is therefore ended host and all
(``kill``): the shell's tree, then the host, so the drop has nothing to wait
for; and the drop runs on a thread of its own, so a close that still waits
holds only that thread, never the event loop (the bench on Windows froze the
whole server for an hour closing 20 terminals).

Nothing here has run on Windows from this repository's own machines: CI
(windows-latest) is its first run — tests/test_conpty.py.
"""

from __future__ import annotations

import importlib
import logging
import os
import subprocess
import threading
import time
from typing import Any

log = logging.getLogger("sp.terminal")

#: What the page says when the package is missing (routers/terminal.py, 501).
MISSING = ("The terminal on Windows needs the pywinpty package. Install it into Slightly Parallel's "
           "environment (backend\\.venv\\Scripts\\python -m pip install pywinpty), then restart.")

_winpty: Any = None

#: The console host of a pseudo console, by its program name.
HOST_NAMES = {"openconsole", "conhost"}


def _hosts() -> dict[int, Any]:
    """This server's console hosts of pseudo consoles (started --headless), by pid."""
    try:
        import psutil
        me = psutil.Process(os.getpid())
        kids = me.children()
    except Exception:  # noqa: BLE001 — no psutil or no process table: no host known
        return {}
    out = {}
    for k in kids:
        try:
            name = os.path.basename(k.name() or "").lower()
            name = name[:-4] if name.endswith(".exe") else name
            if name in HOST_NAMES and "--headless" in k.cmdline():
                out[k.pid] = k
        except Exception:  # noqa: BLE001 — gone between the listing and the look
            continue
    return out


def load() -> Any:
    """The pywinpty module, or None when it is not installed (or not Windows).
    Imported by name: pyright on Linux has no such package to resolve."""
    global _winpty
    if _winpty is None:
        try:
            _winpty = importlib.import_module("winpty")
        except ImportError:
            return None
    return _winpty


def available() -> bool:
    return os.name == "nt" and load() is not None


def env_block(env: dict[str, str]) -> str:
    """The environment as pywinpty's spawn takes it: NAME=value pairs, each
    ended by a NUL (pywinpty adds the block's final one). Sorted by name
    without case, the order Windows keeps an environment block in."""
    return "".join(f"{k}={v}\0" for k, v in sorted(env.items(), key=lambda kv: kv[0].upper())
                   if k and "=" not in k and "\0" not in k + v)


class ConPty:
    """One shell in a pseudo console. Every call but ``read`` is quick; ``read``
    blocks, on one of the router's pump threads."""

    #: Consecutive read errors with the shell still alive before the output
    #: is given up as ended (a transient error is retried).
    MAX_ERRORS = 50

    def __init__(self, argv: list[str], cwd: str, cols: int, rows: int, env: dict[str, str],
                 module: Any = None):
        winpty = module or load()
        if winpty is None:
            raise RuntimeError(MISSING)
        self._error = getattr(winpty, "WinptyError", Exception)
        # The host is the console host that appears with this pseudo console.
        # The router makes one pty at a time (under its lock); two new ones
        # at once leave the host unknown rather than guessed.
        before = _hosts()
        try:
            pty = winpty.PTY(cols, rows, backend=winpty.Backend.ConPTY)
        except self._error:
            # Windows before 10 1809 has no ConPTY: pywinpty's own choice (winpty).
            pty = winpty.PTY(cols, rows)
        exe = argv[0]
        cmdline = subprocess.list2cmdline(argv[1:]) if len(argv) > 1 else None
        if not pty.spawn(exe, cmdline=cmdline, cwd=cwd or None, env=env_block(env)):
            raise OSError(f"the shell did not start: {exe}")
        self._pty: Any = pty
        self.pid: int = int(pty.pid or 0)
        new = [proc for pid, proc in _hosts().items() if pid not in before]
        # Kept as the process itself: psutil will not kill another program that got its pid later.
        self._host: Any = new[0] if len(new) == 1 else None
        self.host_pid: int = self._host.pid if self._host is not None else 0
        self.closed = False
        self._errors = 0

    # ------------------------------------------------------------- output
    def read(self) -> bytes:
        """The next output as UTF-8, b"" at the end. Blocks."""
        while True:
            pty = self._pty
            if pty is None or self.closed:
                return b""
            try:
                text = pty.read(blocking=True)
            except self._error as exc:
                if self.closed or "EOF" in str(exc) or not self._alive(pty):
                    return b""
                self._errors += 1
                if self._errors > self.MAX_ERRORS:
                    log.warning("terminal: the pseudo console keeps failing to read (%s); ended", exc)
                    return b""
                time.sleep(0.02)
                continue
            self._errors = 0
            if text:
                # Lone surrogates (a UTF-8 sequence cut at a read's edge) become "?".
                return text.encode("utf-8", "replace")
            # "": pywinpty's reader has stopped. Ended, unless the shell lives on.
            if self.closed or not self._alive(pty):
                return b""
            time.sleep(0.01)

    # -------------------------------------------------------------- input
    def write(self, data: bytes) -> None:
        pty = self._pty
        if pty is None or self.closed:
            return
        try:
            pty.write(data.decode("utf-8", "replace"))
        except self._error:
            pass

    def resize(self, cols: int, rows: int) -> None:
        pty = self._pty
        if pty is None or self.closed:
            return
        try:
            pty.set_size(cols, rows)
        except self._error:
            pass

    # ---------------------------------------------------------------- life
    def _alive(self, pty: Any) -> bool:
        try:
            return bool(pty.isalive())
        except self._error:
            return False

    def alive(self) -> bool:
        pty = self._pty
        return pty is not None and not self.closed and self._alive(pty)

    def kill(self) -> None:
        """End the shell and everything it started (an agent, a dev server),
        then its console host (closing the pseudo console waits for nothing
        then), then wake a read blocked on its output."""
        self.closed = True
        kill_tree(self.pid)
        host, self._host = self._host, None
        if host is not None:
            try:
                host.kill()
            except Exception:  # noqa: BLE001 — ended with the shell already
                pass
        pty = self._pty
        if pty is not None:
            try:
                pty.cancel_io()
            except self._error:
                pass

    def release(self) -> None:
        """Drop the pseudo console (pywinpty closes it then). Only when no read
        is in flight: the caller's rule, as for a Unix fd. The drop runs on a
        thread of its own: the caller may be the event loop, and a close can
        wait for its console host."""
        pty, self._pty = self._pty, None
        if pty is None:
            return
        held = [pty]
        del pty
        # The list holds the last reference: cleared on the thread, the drop happens there.
        threading.Thread(target=held.clear, name=f"conpty-close-{self.pid}", daemon=True).start()

    def foreground(self) -> str:
        from .termlib import foreground_of_pid
        return foreground_of_pid(self.pid) if self.pid else ""


def kill_tree(pid: int) -> None:
    """Kill a process and every process under it, children first."""
    if not pid:
        return
    try:
        import psutil
        root = psutil.Process(pid)
        procs = root.children(recursive=True) + [root]
    except Exception:  # noqa: BLE001 — gone already, or no psutil: nothing to kill
        return
    for p in procs:
        try:
            p.kill()
        except Exception:  # noqa: BLE001 — one already gone is fine
            pass
