#!/usr/bin/env python3
"""sp.py — start, stop and watch Slightly Parallel, on Linux, macOS and Windows.

    python3 sp.py run [--prod]      in the foreground: dev (backend + Vite
                                         hot reload) or prod (built UI, one port)
    python3 sp.py up [--dev]        in the background, restarted if it crashes
    python3 sp.py down              stop the background one
    python3 sp.py restart           down + up in the same mode
    python3 sp.py status            supervisor · health · terminal
    python3 sp.py logs              follow the server log
    python3 sp.py terminal on|off   the embedded terminal: a setting of
                                         the running server, no restart

`./sp.sh …` and `./run.sh …` (Linux, macOS) and `sp …` (Windows,
sp.cmd) run this file. Configuration comes from .env (see .env.example):
SP_DATA_ROOT (SCAN_DATA_ROOT and DATA_ROOT still read; else the shipped
~/.slightly-parallel), HOST (127.0.0.1), SP_PORT (SCAN_PORT, PORT; 8123),
VITE_PORT (5173). State lives in .sp/ (git-ignored).

Standard library only: it runs before the backend's own environment exists,
and creates it. Requirements: Python 3.11+. A release ships the UI built
(frontend/dist); Node 20+ with npm is needed only to rebuild it, and for
the hot-reload start.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def _home_data_root() -> Path:
    """Mirrors backend.db.home_data_root: ~/.slightly-parallel."""
    return Path.home() / ".slightly-parallel"


STATE = ROOT / ".sp"
PID_FILE = STATE / "supervisor.pid"
MODE_FILE = STATE / "mode"
LOG_FILE = STATE / "server.log"
APP_LOG = STATE / "sp.log"
ENV_FILE = ROOT / ".env"
CHILDREN = STATE / "children"      # the servers of the current run, one pid a line
WINDOWS = os.name == "nt"


def say(msg: str) -> None:
    print(f"[sp] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"[sp] ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


# --------------------------------------------------------------------- .env


def read_env() -> dict[str, str]:
    """KEY=value lines, as bash's `set -a; source .env` reads the simple ones:
    `export` allowed, quotes stripped, # comments, $VAR expanded."""
    out: dict[str, str] = {}
    if not ENV_FILE.exists():
        return out
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            quoted, value = value[0], value[1:-1]
        else:
            quoted = ""
            value = value.split(" #", 1)[0].rstrip()
        if quoted != "'":
            value = os.path.expandvars(value)
        out[key] = value
    return out


def env_set(key: str, value: str) -> None:
    """Upsert one line of .env, keep the rest."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f'{key}="{value}"')
    tmp = STATE / "env.tmp"
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, ENV_FILE)


def settings() -> dict[str, str]:
    """Environment with .env laid over it — .env wins, as when bash sourced it."""
    return {**os.environ, **read_env()}


def base_url() -> str:
    e = settings()
    port = e.get("SP_PORT") or e.get("SCAN_PORT") or e.get("PORT") or "8123"
    return f"http://{e.get('HOST') or '127.0.0.1'}:{port}"


def app_url() -> str:
    return f"http://127.0.0.1:{settings().get('VITE_PORT') or '5173'}"


def health() -> str:
    try:
        with urllib.request.urlopen(f"{base_url()}/api/health", timeout=2) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — no answer is the answer
        return ""


# ---------------------------------------------------------------- processes


def venv_python() -> Path:
    v = ROOT / "backend" / ".venv"
    return v / "Scripts" / "python.exe" if WINDOWS else v / "bin" / "python"


def npm() -> str:
    found = shutil.which("npm")
    if not found:
        fail("npm not found — install Node 20+ (https://nodejs.org) and open a new terminal")
    return found  # type: ignore[return-value]


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if WINDOWS:
        import ctypes
        k = ctypes.windll.kernel32  # type: ignore[attr-defined]
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259          # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_tree(pid: int, force: bool = False) -> None:
    """Stop a process and everything it started."""
    if WINDOWS:
        # taskkill without /F only asks windows to close; console servers have
        # none, so on Windows a stop is always forced.
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    try:
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def spawn(args: list[str], **kw) -> subprocess.Popen:
    """Start one server as the head of its own group, so stopping it stops
    what it started too (npm → sh → node vite → esbuild)."""
    if WINDOWS:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kw["process_group"] = 0
    # Its own group is not the terminal's foreground group, so a read of the
    # keyboard would stop it (Vite reads it for its shortcuts). It gets none.
    kw.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.Popen(args, **kw)


def proc_start(pid: int) -> str:
    """When a process started, as the system counts it. A pid alone is not a
    process: after a restart of the computer the number belongs to someone
    else. "" where it cannot be read."""
    if pid <= 0:
        return ""
    if WINDOWS:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32  # type: ignore[attr-defined]
        h = k.OpenProcess(0x1000, False, pid)
        if not h:
            return ""
        made, a, b, c = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        ok = k.GetProcessTimes(h, ctypes.byref(made), ctypes.byref(a), ctypes.byref(b), ctypes.byref(c))
        k.CloseHandle(h)
        return f"{made.dwHighDateTime}:{made.dwLowDateTime}" if ok else ""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            # "pid (name) state ppid …": the start is the 22nd field, in clock ticks since boot.
            return f.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        pass
    try:
        got = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        return " ".join(got.stdout.split())
    except (OSError, subprocess.SubprocessError):
        return ""


def command_of(pid: int) -> str:
    """The command line a process runs ("" where it cannot be read)."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        pass
    if WINDOWS:
        return ""
    try:
        got = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        return got.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


# What a process of Slightly Parallel's runs — for a pid file written before the start
# time was kept beside the pid.
OUR_COMMANDS = ("sp.py", "backend.server", "npm run dev", "npm run build", "vite")


def stamp(pid: int) -> str:
    """A pid as the state files keep it: with when it started."""
    return f"{pid} {proc_start(pid)}".strip()


def read_pids(path: Path) -> list[tuple[int, str]]:
    """(pid, its recorded start) for each line of a state file."""
    out: list[tuple[int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        pid, _, started = line.strip().partition(" ")
        if pid.isdigit():
            out.append((int(pid), started.strip()))
    return out


def ours(pid: int, started: str) -> bool:
    """Is the live process `pid` the one a state file recorded?

    The files outlive a power cut; the processes do not, and the numbers are
    handed out again. Stopping "pid 4321" then stops whoever has it now —
    and its whole group. So: the same start time as recorded; for a file
    from before starts were recorded, a command line that is Slightly Parallel's.
    """
    if not alive(pid):
        return False
    if started:
        return proc_start(pid) == started
    command = command_of(pid)
    if not command:
        return WINDOWS   # nothing to judge by there: as before, the pid is trusted
    return any(mark in command for mark in OUR_COMMANDS)


def stop_children() -> None:
    """The servers a run left behind — after a forced stop, or a crash of the run itself."""
    pids = [pid for pid, started in read_pids(CHILDREN) if ours(pid, started)]
    for pid in pids:
        stop_tree(pid)
    if pids:
        time.sleep(0.5)
    for pid in pids:
        if alive(pid):
            stop_tree(pid, force=True)
    CHILDREN.unlink(missing_ok=True)


def detached(args: list[str], log: Path) -> int:
    """Start a process that outlives this terminal, in its own group."""
    out = open(log, "ab")  # noqa: SIM115 — the child keeps it
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": out, "stderr": subprocess.STDOUT, "cwd": ROOT}
    if WINDOWS:
        kw["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
                               | subprocess.CREATE_NO_WINDOW)  # type: ignore[attr-defined]
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(args, **kw).pid


def supervisor_pid() -> int:
    """The supervisor's pid; 0 when there is none — a pid file whose process
    is gone, or is someone else's by now, is removed."""
    for pid, started in read_pids(PID_FILE)[:1]:
        if ours(pid, started):
            return pid
    PID_FILE.unlink(missing_ok=True)
    return 0


def running() -> bool:
    return alive(supervisor_pid())


# --------------------------------------------------------------------- run


def port_free(host: str, port: int) -> bool:
    """Nothing listens on `port`. Two checks, as each alone misses a case:
    a bind (with SO_REUSEADDR on Linux and macOS, so a port just released
    counts as free; on Windows that option lets a bind on a busy port
    succeed, so there it is SO_EXCLUSIVEADDRUSE), and a connect, which
    finds a listener on 0.0.0.0 that macOS lets a 127.0.0.1 bind share."""
    import socket
    target = "127.0.0.1" if host in ("", "0.0.0.0") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as c:
        c.settimeout(0.5)
        try:
            if c.connect_ex((target, port)) == 0:
                return False
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if WINDOWS:
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive is not None:
                s.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def prebuilt_ui() -> bool:
    """The UI as a release ships it: built, under frontend/dist."""
    return (ROOT / "frontend" / "dist" / "index.html").is_file()


def node_major() -> tuple[str, int] | None:
    """(the version string, its major) of the node on PATH; None without one."""
    node = shutil.which("node")
    if not node:
        return None
    try:
        version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        return version, int(version.lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return "", 99   # an odd build that answers differently is not stopped here


def builds_ui(dev: bool) -> bool:
    """Whether this start builds the UI: the hot-reload start always; a
    production start only when frontend/dist is missing, or SP_REBUILD_UI
    is set. A release ships the build, and rebuilding it on every start
    would change tracked files under the user's feet (the next git pull
    would refuse)."""
    if dev or not prebuilt_ui():
        return True
    return (settings().get("SP_REBUILD_UI") or "").lower() in ("1", "true", "yes", "on")


def preflight(dev: bool) -> None:
    """What a first start needs, checked before minutes are spent installing:
    each miss is one line that says what to do."""
    if sys.version_info < (3, 11):
        fail(f"Python 3.11+ is needed, this is {sys.version.split()[0]} — install a newer Python and run this with it")
    import tarfile
    if not hasattr(tarfile, "data_filter"):
        # Restoring a backup unpacks it with tarfile's safety filter, which
        # Python 3.11.0–3.11.3 does not have.
        fail(f"Python 3.11.4+ is needed, this is {sys.version.split()[0]} — install a newer Python and run this with it")
    if not venv_python().exists():
        import importlib.util
        # `python -m venv` needs ensurepip to give the environment its pip.
        if not importlib.util.find_spec("ensurepip") or not importlib.util.find_spec("venv"):
            fail("Python's venv module is missing — on Debian or Ubuntu: sudo apt install python3-venv")
    if builds_ui(dev):
        # Node builds the UI; with the release's build in place it is optional.
        npm()
        got = node_major()
        if got is None:
            fail("node not found — install Node 20+ (https://nodejs.org) and open a new terminal")
        if got[1] < 20:
            fail(f"Node 20+ is needed, this is {got[0]} — install a newer Node (https://nodejs.org)")
    e = settings()
    host = e.get("HOST") or "127.0.0.1"
    if host.lower() not in ("127.0.0.1", "localhost", "::1") and (e.get("SP_ALLOW_LAN") or "").lower() not in ("1", "true", "yes", "on"):
        fail(f"HOST={host} opens Slightly Parallel to the network, and Slightly Parallel has no login — leave HOST unset, or add SP_ALLOW_LAN=1 to .env to start anyway")
    port = int(e.get("SP_PORT") or e.get("SCAN_PORT") or e.get("PORT") or "8123")
    if not port_free(host, port):
        fail(f"port {port} is already in use — stop what is using it, or set SP_PORT=<another port> in .env")
    if dev:
        vite = int(e.get("VITE_PORT") or "5173")
        if not port_free("127.0.0.1", vite):
            fail(f"port {vite} (the hot-reload UI) is already in use — stop what is using it, or set VITE_PORT=<another port> in .env")


def backend_packages() -> tuple[Path, Path]:
    """(the exact versions if the repository has them, the ranges they came from)."""
    return ROOT / "backend" / "requirements.lock", ROOT / "backend" / "requirements.txt"


def _mark_text(mark: Path) -> str:
    """What an install mark holds; a mark written under the working title's
    name (.merkhet-…) still counts, so a rename does not reinstall everything."""
    old = mark.with_name(mark.name.replace(".sp-", ".merkhet-", 1))
    for p in (mark, old):
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    return ""


def install_backend() -> bool:
    """The backend's environment: made once, its packages installed once and
    again when the list of them changed — the way the UI's are. (pip ran on
    every start, and on every restart after a crash: seconds each time, and
    a question to the network.) From requirements.lock, the exact versions
    the tests ran on; from requirements.txt when there is no lock, or when
    the lock does not install on this system. True when pip ran."""
    import hashlib
    py = venv_python()
    fresh = not py.exists()
    if fresh:
        print("[run] creating backend/.venv ...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / "backend" / ".venv")], check=True)
    lock, ranges = backend_packages()
    source = lock if lock.is_file() else ranges
    mark = ROOT / "backend" / ".venv" / ".sp-requirements"
    want = hashlib.sha256(source.read_bytes()).hexdigest()
    have = _mark_text(mark)
    if not fresh and want == have:
        return False
    print("[run] installing backend packages (a minute on the first start) ...", flush=True)
    if fresh:
        subprocess.run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    # pip's own lines (Collecting, Downloading, Installing) show that it is
    # going; its progress bars only in a terminal, not in a log.
    shown = [] if sys.stdout.isatty() else ["--progress-bar", "off"]
    try:
        subprocess.run([str(py), "-m", "pip", "install", *shown, "-r", str(source)], check=True)
    except subprocess.CalledProcessError:
        if source == ranges:
            raise
        print("[run] requirements.lock did not install here — using requirements.txt", flush=True)
        subprocess.run([str(py), "-m", "pip", "install", *shown, "-r", str(ranges)], check=True)
    mark.write_text(want, encoding="utf-8")
    return True


def prepare(ui: bool = True) -> dict[str, str]:
    """The backend's environment and the UI's packages, made once; the
    variables the backend reads, resolved."""
    install_backend()
    # The UI's packages: installed once, and again when the list of them
    # changed — after a `git pull` that added one, the build would fail.
    modules = ROOT / "frontend" / "node_modules"
    lock = ROOT / "frontend" / "package-lock.json"
    mark = modules / ".sp-lock"
    import hashlib
    want = hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else ""
    have = _mark_text(mark)
    if ui and (not modules.is_dir() or (want and want != have)):
        print("[run] installing frontend packages ...", flush=True)
        # `npm ci` installs exactly what the lockfile says and never rewrites it.
        verb = "ci" if lock.is_file() else "install"
        subprocess.run([npm(), verb, "--no-audit", "--no-fund"], cwd=ROOT / "frontend", check=True)
        if want:
            mark.write_text(want, encoding="utf-8")

    env = settings()
    # SP_DATA_ROOT > SCAN_DATA_ROOT (former name) > DATA_ROOT > ~/.slightly-parallel
    data = env.get("SP_DATA_ROOT") or env.get("SCAN_DATA_ROOT") or env.get("DATA_ROOT") or ""
    if not data:
        # The server fills it with the demo data on the first start (backend.db.seed_data_root).
        data = str(_home_data_root())
        if not Path(data).exists():
            print(f"[run] first start: the demo data goes to {data} — set SP_DATA_ROOT in .env to use another folder", flush=True)
    if not (Path(data) / "projects").is_dir():
        print(f"[run] WARN: {Path(data) / 'projects'} does not exist.", flush=True)
        print("[run]       A data root holds the ledgers (tasks.csv, decisions.csv, …) and one folder", flush=True)
        print("[run]       per observed project under projects/<code>/. An empty folder is fine: Setup fills it.", flush=True)
    env["DATA_ROOT"] = data
    env["HOST"] = env.get("HOST") or "127.0.0.1"
    env["PORT"] = env.get("PORT") or env.get("SP_PORT") or env.get("SCAN_PORT") or "8123"
    return env


def cmd_run(args: list[str]) -> None:
    prod = bool(args) and args[0] in ("--prod", "prod")
    preflight(dev=not prod)
    build = builds_ui(dev=not prod)
    env = prepare(ui=build)
    backend = [str(venv_python()), "-m", "backend.server"]
    if prod:
        if build:
            print("[run] building frontend ...", flush=True)
            subprocess.run([npm(), "run", "build"], cwd=ROOT / "frontend", check=True, env=env)
        else:
            print("[run] UI: the build in frontend/dist (SP_REBUILD_UI=1 in .env rebuilds it; needs Node 20+)", flush=True)
        print(f"[run] launching Slightly Parallel on http://{env['HOST']}:{env['PORT']}", flush=True)
        procs = [spawn(backend, cwd=ROOT / "backend", env=env)]
    else:
        print(f"[run] dev — backend on :{env['PORT']}, Vite on :{env.get('VITE_PORT') or 5173}", flush=True)
        procs = [
            spawn(backend, cwd=ROOT / "backend", env=env),
            spawn([npm(), "run", "dev"], cwd=ROOT / "frontend", env=env),
        ]
        print(f"\n  Backend:  http://{env['HOST']}:{env['PORT']}      (docs: /docs, health: /api/health)")
        print(f"  App:      {app_url()}   (dev server with hot reload)\n", flush=True)

    CHILDREN.write_text("\n".join(stamp(p.pid) for p in procs), encoding="utf-8")

    def shutdown(*_: object) -> None:
        print("\n[run] shutting down...", flush=True)
        for p in procs:
            stop_tree(p.pid)
        deadline = time.time() + 10
        for p in procs:
            try:
                p.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                stop_tree(p.pid, force=True)
        # A group outlives its head (vite under npm): make sure it is gone.
        for p in procs:
            stop_tree(p.pid, force=True)
        CHILDREN.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    try:
        # One of the pair ending ends the run, so the supervisor restarts both.
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()
    shutdown()


# -------------------------------------------------------------- supervisor


RESTART_MIN = 2          # seconds before a crashed server is started again
RESTART_MAX = 60         # … at most, when it keeps falling over at the start
RESTART_STABLE = 60      # a run that lasted this long was running: the wait starts over
LOG_CAP = 5 * 1024 * 1024    # server.log is cut back to its end past this
LOG_KEEP = 1024 * 1024


def next_delay(delay: int, ran_for: float) -> int:
    """How long to wait before the next start. A server that ran and then
    crashed is started again at once; one that fell over while starting (a
    port taken, a package that will not install) will do so again — each
    wait is twice the last, up to a minute, instead of every two seconds
    for ever."""
    if ran_for >= RESTART_STABLE:
        return RESTART_MIN
    return min(max(delay, RESTART_MIN) * 2, RESTART_MAX)


def trim_log(path: Path | None = None, cap: int = LOG_CAP, keep: int = LOG_KEEP) -> bool:
    """Cut the supervisor's log back to its last `keep` bytes once it is past
    `cap`. In place: the servers hold the file open to append, and go on
    writing at its new end. True when it was cut."""
    path = path or LOG_FILE
    try:
        if path.stat().st_size <= cap:
            return False
        with open(path, "r+b") as f:
            f.seek(-keep, os.SEEK_END)
            tail = f.read()
            tail = tail[tail.find(b"\n") + 1:]   # from the first whole line
            f.seek(0)
            f.truncate()
            f.write(b"[sp] (older lines of this log were dropped)\n" + tail)
        return True
    except (OSError, ValueError):
        return False


def run_options(log) -> dict:
    """How the supervisor starts `sp.py run`: its output into server.log,
    and on Windows no console window of its own (the supervisor has none
    to share, so Windows would open a visible one). The servers it starts
    share that hidden console."""
    kw: dict = {"cwd": ROOT, "stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT}
    if WINDOWS:
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return kw


def cmd_supervise(args: list[str]) -> None:
    mode = args[0] if args else "prod"
    stop_children()
    delay = RESTART_MIN
    while True:
        trim_log()
        print(f"[sp] {time.strftime('%F %T')} starting server (mode: {mode})", flush=True)
        run = [sys.executable, str(Path(__file__).resolve()), "run", *(["--prod"] if mode == "prod" else [])]
        began = time.time()
        with open(LOG_FILE, "ab") as log:
            proc = subprocess.Popen(run, **run_options(log))
        try:
            while True:
                try:
                    proc.wait(timeout=60)
                    break
                except subprocess.TimeoutExpired:
                    trim_log()
        except KeyboardInterrupt:
            return
        stop_children()
        ran_for = time.time() - began
        delay = RESTART_MIN if ran_for >= RESTART_STABLE else delay
        print(f"[sp] {time.strftime('%F %T')} server exited — restarting in {delay}s", flush=True)
        time.sleep(delay)
        delay = next_delay(delay, ran_for)


def cmd_up(args: list[str]) -> None:
    mode = "dev" if args and args[0] in ("--dev", "dev") else "prod"
    if running():
        fail(f"already running (supervisor pid {supervisor_pid()}) — use restart")
    if health():
        fail(f"something already serves {base_url()} outside the supervisor — stop it first")
    preflight(dev=mode == "dev")
    MODE_FILE.write_text(mode)
    LOG_FILE.write_text("")
    pid = detached([sys.executable, str(Path(__file__).resolve()), "__supervise", mode], LOG_FILE)
    PID_FILE.write_text(stamp(pid), encoding="utf-8")
    say(f"supervised start (mode: {mode}, supervisor pid {pid})")
    say(f"log: {LOG_FILE.relative_to(ROOT)}")
    # A first start installs the backend's packages and the UI's, and a prod
    # start builds the UI: give it minutes, and stop waiting if it died.
    first = not venv_python().exists() or not (ROOT / "frontend" / "node_modules").is_dir()
    for _ in range(600 if first or mode == "prod" else 120):
        if health():
            say(f"healthy — {base_url()}" + (f" · app: {app_url()}" if mode == "dev" else ""))
            return
        if not alive(pid):
            fail(f"the supervisor stopped — see {LOG_FILE.relative_to(ROOT)}")
        time.sleep(1)
    fail("no healthy response yet — see: sp logs")


def cmd_down(_: list[str] | None = None) -> None:
    pid = supervisor_pid()
    if not pid:
        say("not running (no live supervisor)")
        stop_children()
        PID_FILE.unlink(missing_ok=True)
        return
    # The supervisor leads its own group: stopping the group stops it, the
    # run, and both servers.
    stop_tree(pid)
    for _ in range(10):
        if not alive(pid):
            break
        time.sleep(1)
    if alive(pid):
        stop_tree(pid, force=True)
    stop_children()
    PID_FILE.unlink(missing_ok=True)
    say("stopped")


def cmd_restart(_: list[str] | None = None) -> None:
    mode = MODE_FILE.read_text().strip() if MODE_FILE.exists() else "prod"
    cmd_down()
    time.sleep(1)
    cmd_up(["--dev"] if mode == "dev" else [])


def cmd_status(_: list[str] | None = None) -> None:
    if running():
        mode = MODE_FILE.read_text().strip() if MODE_FILE.exists() else "?"
        say(f"supervisor: running (pid {supervisor_pid()}, mode: {mode})")
    else:
        say("supervisor: not running")
    h = health()
    if h:
        try:
            import json
            d = json.loads(h)
            say(f"backend: healthy — projects={d['projects']} agents={d['agents']} data_root={d['data_root']}")
        except (ValueError, KeyError):
            say("backend: healthy")
    else:
        say(f"backend: no response on {base_url()}")
    t = None
    if h:
        try:
            with urllib.request.urlopen(f"{base_url()}/api/terminal/state", timeout=2) as r:
                t = r.read().decode()
        except OSError:
            t = None
    if t:
        try:
            import json
            d = json.loads(t)
            say(f"terminal: {'on' if d.get('enabled') else 'off'}{' (forced by .env)' if d.get('forced') else ''}"
                f"{' · tmux' if d.get('tmux') else ''}")
        except ValueError:
            pass
    # For scripts and CI: status fails when nothing answers.
    if not h:
        sys.exit(1)


def cmd_logs(_: list[str] | None = None) -> None:
    """The server's own log (every request) and the supervisor's beside it, followed."""
    files = [f for f in (APP_LOG, LOG_FILE) if f.exists()]
    if not files:
        fail("no log yet — start it with: sp up")
    handles = []
    for f in files:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]
        print(f"==> {f.relative_to(ROOT)} <==")
        print("\n".join(lines), flush=True)
        h = open(f, encoding="utf-8", errors="replace")  # noqa: SIM115
        h.seek(0, os.SEEK_END)
        handles.append(h)
    try:
        while True:
            for h in handles:
                chunk = h.read()
                if chunk:
                    print(chunk, end="", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def operator_cookie() -> str:
    """The cookie the server hands its own pages (server.OperatorCookie). A
    setting is the operator's write, and this command is the operator."""
    import urllib.request
    req = urllib.request.Request(f"{base_url()}/api/health", headers={"Sec-Fetch-Site": "same-origin"})
    with urllib.request.urlopen(req, timeout=5) as r:
        got = r.headers.get("Set-Cookie", "")
    return got.split(";", 1)[0]


def cmd_terminal(args: list[str]) -> None:
    """The terminal is a setting now (terminal.enabled): no token to paste.

    `on` / `off` set it through the running server; the drawer's switch and
    Settings › Terminal do the same. SP_ENABLE_TERMINAL in .env still
    forces it on, for whoever set it that way.
    """
    what = args[0] if args else "status"
    if what in ("on", "off"):
        if not running():
            fail("start Slightly Parallel first (sp up), or switch it in Settings › Terminal")
        import json
        import urllib.request
        body = json.dumps({"values": {"terminal.enabled": what == "on"}}).encode()
        req = urllib.request.Request(f"{base_url()}/api/settings", data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Cookie": operator_cookie()})
        urllib.request.urlopen(req, timeout=5).read()
        say(f"terminal {what} — the ` key opens it on any page")
        if what == "off" and settings().get("SP_ENABLE_TERMINAL") == "1":
            say("note: SP_ENABLE_TERMINAL=1 in .env still forces it on; remove it to switch off")
    else:
        cmd_status()


COMMANDS = {
    "run": cmd_run, "up": cmd_up, "down": cmd_down, "restart": cmd_restart, "status": cmd_status,
    "logs": cmd_logs, "terminal": cmd_terminal, "__supervise": cmd_supervise,
}


def main(argv: list[str]) -> None:
    STATE.mkdir(exist_ok=True)
    if not argv or argv[0] not in COMMANDS:
        print(__doc__.split("\n\n")[1])
        sys.exit(1)
    COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
