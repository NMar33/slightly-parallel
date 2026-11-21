"""Readers for the output ladder. Each trial runs in a separate process."""
from __future__ import annotations

import base64
import contextlib
import errno
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

FIRST = b"SP_BENCH_OUTPUT_FIRST"
LAST = b"SP_BENCH_OUTPUT_LAST"
CHUNK_BYTES = 64 * 1024
READ_TIMEOUT_S = 120
NATIVE_TIMEOUT_S = 100
FILE_POLL_S = 0.1
WINDOWS = sys.platform == "win32"
POWER_SHELL = shutil.which("pwsh") or shutil.which("powershell.exe")
SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parents[3] / "backend"))


def emit(payload: Path) -> None:
    if WINDOWS:
        import ctypes

        # Let the console interpret the same ANSI sequences as the shell.
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.restype = ctypes.c_void_p
        handle = ctypes.c_void_p(kernel.GetStdHandle(-11))
        mode = ctypes.c_ulong()
        if kernel.GetConsoleMode(handle, ctypes.byref(mode)) and not kernel.SetConsoleMode(handle, mode.value | 4):
            raise ctypes.WinError(ctypes.get_last_error())
    output = sys.stdout.buffer
    output.write(FIRST + b"\n")
    with payload.open("rb") as source:
        shutil.copyfileobj(source, output, CHUNK_BYTES)
    output.write(LAST + b"\n")
    output.flush()


def drain(read: Callable[[], bytes], started: float) -> dict:
    """Compare the same stream boundaries even when the PTY rewrites bytes."""
    tail = b""
    offset = 0
    first = None
    first_end = 0
    while chunk := read():
        now = time.perf_counter()
        batch = tail + chunk
        base = offset - len(tail)
        offset += len(chunk)
        if first is None:
            index = batch.find(FIRST)
            if index >= 0:
                first = now
                first_end = base + index + len(FIRST)
        if first is not None:
            match = batch.find(LAST, max(0, first_end - base))
            if match >= 0:
                return {
                    "reader_ms": (now - first) * 1000,
                    "first_ms": (first - started) * 1000,
                    "stream_bytes": base + match - first_end,
                }
        tail = batch[-max(len(FIRST), len(LAST)) + 1:]
    raise RuntimeError(f"end of stream before both markers ({offset} bytes)")


def powershell_file(path: Path) -> list[str]:
    if not POWER_SHELL:
        raise RuntimeError("PowerShell is unavailable")
    command = path.read_text(encoding="utf-8-sig")
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    return [POWER_SHELL, "-NoLogo", "-NoProfile", "-EncodedCommand", encoded]


def pipe(payload: Path) -> dict:
    started = time.perf_counter()
    with subprocess.Popen([sys.executable, "-u", str(SCRIPT), "emit", str(payload)], stdout=subprocess.PIPE) as child:
        assert child.stdout is not None
        try:
            result = drain(lambda: os.read(child.stdout.fileno(), CHUNK_BYTES), started)
            if child.wait(timeout=READ_TIMEOUT_S):
                raise RuntimeError(f"producer exited {child.returncode}")
            return result
        finally:
            if child.poll() is None:
                child.kill()


def unix_pty(argv: list[str], cols: int, rows: int) -> dict:
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    child = None
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        started = time.perf_counter()
        child = subprocess.Popen(argv, stdout=slave, stderr=slave)
        os.close(slave)
        slave = -1

        def read() -> bytes:
            try:
                return os.read(master, CHUNK_BYTES)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    return b""
                raise

        result = drain(read, started)
        if child.wait(timeout=READ_TIMEOUT_S):
            raise RuntimeError(f"pty producer exited {child.returncode}")
        return result
    finally:
        os.close(master)
        if slave >= 0:
            os.close(slave)
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait()


def pseudo_console(argv: list[str], cwd: Path, cols: int, rows: int) -> dict:
    if not WINDOWS:
        return unix_pty(argv, cols, rows)
    from backend.conpty import ConPty

    started = time.perf_counter()
    console = ConPty(argv, str(cwd), cols, rows, os.environ.copy())
    try:
        return drain(console.read, started)
    finally:
        console.kill()
        console.release()


def websocket(config: dict) -> dict:
    from urllib.request import Request, urlopen

    from websockets.sync.client import connect

    url = config["url"]
    port = url.rsplit(":", 1)[1]
    cookie = f"sp_operator_{port}=" + Path(config["token_file"]).read_text(encoding="utf-8").strip()
    headers = {"Cookie": cookie}
    with urlopen(Request(url + "/api/terminal/state", headers=headers), timeout=READ_TIMEOUT_S) as response:
        token = json.load(response)["token"]
    address = (
        f"ws{url[4:]}/ws/terminal/{config['session']}"
        f"?token={token}&cols={config['cols']}&rows={config['rows']}"
    )
    with connect(address, origin=url, additional_headers=headers, proxy=None, max_size=None) as ws:
        ws.recv(timeout=READ_TIMEOUT_S)  # wait for the plain shell to draw
        started = time.perf_counter()
        ws.send(json.dumps({"type": "input", "typed": True, "data": config["command"] + "\r"}))

        def read() -> bytes:
            value = ws.recv(timeout=READ_TIMEOUT_S)
            return value if isinstance(value, bytes) else value.encode()

        return drain(read, started)


def native_window(kind: str, script: Path, result: Path, cols: int, rows: int) -> dict:
    argv = powershell_file(script)
    if kind == "conhost":
        host = [str(Path(os.environ["SystemRoot"]) / "System32" / "conhost.exe")]
    else:
        executable = os.environ.get("SP_BENCH_OUTPUT_WT") or shutil.which("wt.exe")
        if not executable:
            raise RuntimeError(os.environ.get("SP_BENCH_OUTPUT_WT_REASON") or "Windows Terminal is unavailable")
        host = [executable, "-w", "new", "--size", f"{cols},{rows}", "new-tab"]
    with subprocess.Popen([*host, *argv], creationflags=subprocess.CREATE_NEW_CONSOLE) as child:
        try:
            deadline = time.monotonic() + NATIVE_TIMEOUT_S
            while time.monotonic() < deadline:
                if result.exists():
                    try:
                        return json.loads(result.read_text(encoding="utf-8-sig"))
                    except json.JSONDecodeError:
                        pass  # the shell just opened the result file
                if child.poll() not in (None, 0):
                    raise RuntimeError(f"{kind} launcher exited {child.returncode}")
                time.sleep(FILE_POLL_S)
            raise RuntimeError(f"{kind} produced no timing file; an interactive desktop may be unavailable")
        finally:
            if child.poll() is None:
                with contextlib.suppress(OSError):
                    child.terminate()


def trial(config: dict) -> dict:
    kind = config["kind"]
    payload = Path(config["payload"])
    cols, rows = config["cols"], config["rows"]
    if kind == "pipe":
        return pipe(payload)
    if kind == "pty_program":
        argv = [sys.executable, "-u", str(SCRIPT), "emit", str(payload)]
    elif kind in {"pty_powershell", "pty_console_write"}:
        argv = powershell_file(Path(config["script"]))
    elif kind == "pty_cmd":
        argv = [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", Path(config["script"]).name]
    elif kind.startswith("ws_"):
        return websocket(config)
    else:
        return native_window(kind, Path(config["script"]), Path(config["result"]), cols, rows)
    return pseudo_console(argv, payload.parent, cols, rows)


if __name__ == "__main__":
    if sys.argv[1] == "emit":
        emit(Path(sys.argv[2]))
    else:
        try:
            print(json.dumps(trial(json.loads(sys.argv[1]))))
        except (OSError, RuntimeError, TimeoutError) as exc:
            print(json.dumps({"error": str(exc)}))
            sys.exit(1)
