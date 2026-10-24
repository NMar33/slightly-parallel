"""The launcher (sp.py) reads .env the way bash's `source` read it."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[2] / "sp.py"


@pytest.fixture()
def launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("sp_launcher", LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(mod, "STATE", tmp_path)
    return mod


def test_env_lines_read_as_bash_read_them(launcher, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_DIR", "/home/x")
    launcher.ENV_FILE.write_text(
        '# a comment\n'
        'SCAN_DATA_ROOT="/data/with space"\n'
        "export HOST=0.0.0.0\n"
        "SP_PORT=9000  # the port\n"
        "LITERAL='$HOME_DIR/raw'\n"
        'EXPANDED="$HOME_DIR/data"\n'
        "not a line\n", encoding="utf-8")
    env = launcher.read_env()
    assert env == {"SCAN_DATA_ROOT": "/data/with space", "HOST": "0.0.0.0", "SP_PORT": "9000",
                   "LITERAL": "$HOME_DIR/raw", "EXPANDED": "/home/x/data"}
    assert launcher.base_url() == "http://0.0.0.0:9000"


def test_env_set_replaces_one_line_and_keeps_the_rest(launcher) -> None:
    launcher.ENV_FILE.write_text('A="1"\nSP_ENABLE_TERMINAL="0"\nB="2"\n', encoding="utf-8")
    launcher.env_set("SP_ENABLE_TERMINAL", "1")
    assert launcher.read_env() == {"A": "1", "B": "2", "SP_ENABLE_TERMINAL": "1"}


def test_the_venv_python_is_where_each_system_puts_it(launcher, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "WINDOWS", True)
    assert launcher.venv_python().parts[-2:] == ("Scripts", "python.exe")
    monkeypatch.setattr(launcher, "WINDOWS", False)
    assert launcher.venv_python().parts[-2:] == ("bin", "python")


# ---------------------------------------------------------------------------
# A pid in a state file is a process only together with when it started
# ---------------------------------------------------------------------------


@pytest.fixture()
def state(launcher, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The launcher with its state files in a temp folder — never the real ones."""
    monkeypatch.setattr(launcher, "PID_FILE", tmp_path / "supervisor.pid")
    monkeypatch.setattr(launcher, "CHILDREN", tmp_path / "children")
    monkeypatch.setattr(launcher, "LOG_FILE", tmp_path / "server.log")
    return launcher


@pytest.fixture()
def stranger():
    """A process that is not Slightly Parallel's, leading a group of its own."""
    import subprocess
    import sys
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    yield proc
    proc.kill()
    proc.wait()


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="reads /proc")
def test_a_stale_children_file_stops_nobody_elses_process(state, stranger) -> None:
    """After a power cut the file is still there and the numbers are someone
    else's: the next start must not stop that process and its group."""
    import time
    # Recorded with another start time: the number was handed out again.
    state.CHILDREN.write_text(f"{stranger.pid} 12345\n", encoding="utf-8")
    state.stop_children()
    time.sleep(0.2)
    assert stranger.poll() is None
    assert not state.CHILDREN.exists()          # the stale file is gone
    # A file from before starts were recorded: judged by what the process runs.
    state.CHILDREN.write_text(f"{stranger.pid}\n", encoding="utf-8")
    state.stop_children()
    time.sleep(0.2)
    assert stranger.poll() is None
    # The process this file did record is stopped, as before.
    state.CHILDREN.write_text(state.stamp(stranger.pid) + "\n", encoding="utf-8")
    state.stop_children()
    assert stranger.wait(timeout=5) is not None


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="reads /proc")
def test_a_stale_supervisor_pid_is_not_a_running_supervisor(state, stranger) -> None:
    state.PID_FILE.write_text(f"{stranger.pid} 12345", encoding="utf-8")
    assert state.supervisor_pid() == 0 and not state.running()
    assert not state.PID_FILE.exists()
    state.cmd_down()                             # "not running": and nobody was signalled
    assert stranger.poll() is None
    state.PID_FILE.write_text(state.stamp(stranger.pid), encoding="utf-8")
    assert state.supervisor_pid() == stranger.pid and state.running()


def test_a_pid_file_from_before_is_judged_by_its_command(state, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state, "alive", lambda pid: True)
    monkeypatch.setattr(state, "command_of", lambda pid: {
        7: "/repo/backend/.venv/bin/python -m backend.server", 8: "npm run dev",
        9: "python3 /repo/sp.py __supervise dev", 10: "/usr/bin/gnome-shell"}[pid])
    assert [state.ours(pid, "") for pid in (7, 8, 9, 10)] == [True, True, True, False]


# ---------------------------------------------------------------------------
# The backend's packages are installed when their list changed, not at every start
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(state, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A repository of its own for the launcher, with pip only recorded."""
    root = tmp_path / "repo"
    (root / "backend" / ".venv" / "bin").mkdir(parents=True)
    (root / "backend" / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    (root / "backend" / "requirements.txt").write_text("fastapi>=0.1\n", encoding="utf-8")
    monkeypatch.setattr(state, "ROOT", root)
    monkeypatch.setattr(state, "WINDOWS", False)
    calls: list[list[str]] = []
    fail: list[str] = []

    def run(argv, **kw):
        import subprocess
        calls.append([str(a) for a in argv])
        if any(name in calls[-1][-1] for name in fail):
            raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(state.subprocess, "run", run)
    return state, root, calls, fail


def test_pip_runs_once_and_again_when_the_list_changed(repo) -> None:
    launcher, root, calls, _ = repo
    assert launcher.install_backend() is True            # no stamp yet: installed
    assert calls[-1][-2:] == ["-r", str(root / "backend" / "requirements.txt")]
    calls.clear()
    assert launcher.install_backend() is False and calls == []     # every later start: nothing
    (root / "backend" / "requirements.txt").write_text("fastapi>=0.2\n", encoding="utf-8")
    assert launcher.install_backend() is True and len(calls) == 1  # the list changed


def test_the_lock_is_installed_when_there_is_one(repo) -> None:
    launcher, root, calls, fail = repo
    lock = root / "backend" / "requirements.lock"
    lock.write_text("fastapi==0.1.0\n", encoding="utf-8")
    assert launcher.install_backend() is True
    assert calls[-1][-1] == str(lock)
    # A lock that does not install on this system: the ranges it came from.
    lock.write_text("fastapi==0.1.1\n", encoding="utf-8")
    fail.append("requirements.lock")
    calls.clear()
    assert launcher.install_backend() is True
    assert [c[-1] for c in calls] == [str(lock), str(root / "backend" / "requirements.txt")]
    calls.clear()
    assert launcher.install_backend() is False


# ---------------------------------------------------------------------------
# A server that keeps falling over is not restarted every two seconds for ever
# ---------------------------------------------------------------------------


def test_the_wait_before_a_restart_grows_and_starts_over(launcher) -> None:
    delay, waits = launcher.RESTART_MIN, []
    for _ in range(8):                           # fell over at the start, eight times
        waits.append(delay)
        delay = launcher.next_delay(delay, ran_for=1.0)
    assert waits == [2, 4, 8, 16, 32, 60, 60, 60]
    assert launcher.next_delay(60, ran_for=3600.0) == launcher.RESTART_MIN   # it ran: a crash, not a fault


def test_the_supervisors_log_is_cut_back_to_its_end(state) -> None:
    log = state.LOG_FILE
    log.write_bytes(b"".join(b"line %06d\n" % i for i in range(20_000)))
    assert state.trim_log(cap=10**9) is False                 # under the cap: untouched
    with open(log, "ab") as writer:                           # a server holding it open
        assert state.trim_log(cap=100_000, keep=10_000) is True
        writer.write(b"written after the cut\n")
    lines = log.read_bytes().splitlines()
    assert len(log.read_bytes()) < 11_000
    assert lines[0].startswith(b"[sp]") and lines[1].startswith(b"line ")
    assert lines[-2] == b"line 019999" and lines[-1] == b"written after the cut"


def test_a_server_the_launcher_starts_never_reads_the_keyboard(launcher, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vite reads stdin for its shortcuts; in its own process group that read
    stops it dead (SIGTTIN), and the page never answers."""
    import subprocess
    seen: dict = {}

    class Fake:
        pid = 1

    def popen(args, **kw):
        seen.update(kw)
        return Fake()

    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    launcher.spawn(["vite"], cwd="/tmp")
    assert seen["stdin"] is subprocess.DEVNULL


def test_the_supervisor_starts_the_run_into_the_log_without_a_window(launcher, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import subprocess
    with open(tmp_path / "server.log", "ab") as log:
        kw = launcher.run_options(log)
        assert kw["stdout"] is log and kw["stderr"] is subprocess.STDOUT and kw["stdin"] is subprocess.DEVNULL
        assert ("creationflags" in kw) is launcher.WINDOWS   # Windows: no console window; elsewhere nothing
        monkeypatch.setattr(launcher, "WINDOWS", True)
        assert launcher.run_options(log)["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def test_a_production_start_needs_node_only_without_the_shipped_ui(launcher, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """A release ships frontend/dist: a production start with no Node serves
    it; the hot-reload start, or a tree without the build, still asks for Node."""
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    monkeypatch.setattr(launcher, "settings", lambda: {})
    monkeypatch.setattr(launcher, "port_free", lambda host, port: True)
    monkeypatch.setattr(launcher, "venv_python", lambda: Path("/nowhere/python"))
    monkeypatch.setattr(launcher, "prebuilt_ui", lambda: True)
    launcher.preflight(dev=False)                       # no fail: the shipped UI is served
    assert launcher.builds_ui(dev=False) is False
    assert launcher.builds_ui(dev=True) is True
    with pytest.raises(SystemExit):
        launcher.preflight(dev=True)
    assert "Node 20+" in capsys.readouterr().err
    monkeypatch.setattr(launcher, "prebuilt_ui", lambda: False)
    with pytest.raises(SystemExit):
        launcher.preflight(dev=False)
    assert "Node 20+" in capsys.readouterr().err
    assert launcher.builds_ui(dev=False) is True


def test_a_port_someone_listens_on_is_busy(launcher) -> None:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        # Nobody accepts here: port_free connects once per call, and macOS
        # refuses the second connection when the backlog is one.
        srv.listen(5)
        port = srv.getsockname()[1]
        assert launcher.port_free("127.0.0.1", port) is False
        assert launcher.port_free("0.0.0.0", port) is False
    assert launcher.port_free("127.0.0.1", port) is True


def test_a_listener_a_bind_misses_is_still_found_by_connecting(launcher, monkeypatch: pytest.MonkeyPatch) -> None:
    """macOS lets a 127.0.0.1 bind share a port with a 0.0.0.0 listener, and
    Windows with SO_REUSEADDR lets a bind succeed on a busy port: the bind
    alone says free."""
    import socket

    class Sock:
        def __init__(self, *_a):
            self.opts: list = []
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False
        def settimeout(self, _t):
            pass
        def connect_ex(self, _addr):
            return 0                       # someone answers
        def setsockopt(self, *a):
            self.opts.append(a)
        def bind(self, _addr):
            pass                           # the bind "succeeds"

    monkeypatch.setattr(socket, "socket", Sock)
    assert launcher.port_free("127.0.0.1", 8131) is False


def test_on_windows_the_port_check_does_not_reuse_addresses(launcher, monkeypatch: pytest.MonkeyPatch) -> None:
    import socket
    made: list = []

    class Sock:
        def __init__(self, *_a):
            self.opts: list = []
            made.append(self)
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False
        def settimeout(self, _t):
            pass
        def connect_ex(self, _addr):
            return 111                     # refused: nobody listens
        def setsockopt(self, _level, opt, _v):
            self.opts.append(opt)
        def bind(self, _addr):
            pass

    monkeypatch.setattr(socket, "socket", Sock)
    monkeypatch.setattr(socket, "SO_EXCLUSIVEADDRUSE", -5, raising=False)
    monkeypatch.setattr(launcher, "WINDOWS", True)
    assert launcher.port_free("127.0.0.1", 8131) is True
    assert all(socket.SO_REUSEADDR not in s.opts for s in made)
    assert any(-5 in s.opts for s in made)


def test_preflight_refuses_a_python_without_the_tar_safety_filter(launcher, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    import tarfile
    monkeypatch.delattr(tarfile, "data_filter")
    with pytest.raises(SystemExit):
        launcher.preflight(dev=False)
    assert "Python 3.11.4+ is needed" in capsys.readouterr().err


def test_sp_sh_prefers_a_named_newer_python(tmp_path: Path) -> None:
    import os
    import shutil
    if os.name == "nt":
        pytest.skip("sp.sh is the POSIX launcher; Windows has sp.py")
    import subprocess
    root = Path(__file__).resolve().parents[2]
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name in ("python3", "python3.12"):
        stub = bin_ / name
        stub.write_text(f"#!/bin/sh\necho {name}\n")
        stub.chmod(0o755)
    (bin_ / "dirname").symlink_to(shutil.which("dirname"))
    shutil.copy(root / "sp.sh", tmp_path / "sp.sh")
    got = subprocess.run(["/bin/bash", str(tmp_path / "sp.sh")], env={"PATH": str(bin_)},
                         capture_output=True, text=True, timeout=10)
    assert got.stdout.strip() == "python3.12"


def test_sp_cmd_checks_that_python_runs_before_handing_over() -> None:
    """The Microsoft Store alias named `python` exists but runs nothing."""
    text = (Path(__file__).resolve().parents[2] / "sp.cmd").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "goto :python" in ln)
    assert line.index('python -c "import sys"') < line.index("goto :python")


def test_sp_cmd_ends_with_sp_py_s_own_exit_code() -> None:
    """`cmd /c sp.cmd status` returned 0 with nothing running: a script
    could not tell. Each handover ends the batch with sp.py's code."""
    lines = (Path(__file__).resolve().parents[2] / "sp.cmd").read_text(encoding="utf-8").splitlines()
    runs = [i for i, ln in enumerate(lines) if ln.strip().endswith("sp.py %*")]
    # py with a supported version (in the loop), plain py -3, python.
    assert len(runs) == 3 and all(lines[i + 1].strip() in ("exit /b %errorlevel%", "exit /b !errorlevel!") for i in runs)
    assert "EnableDelayedExpansion" in "\n".join(lines)          # !errorlevel! is read inside the loop


def test_the_hot_reload_start_sends_pages_to_the_vite_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """sp.py with no --prod names the Vite UI in SP_UI_DEV: a page asked of
    the backend's port goes there with its path and query; the API stays."""
    from fastapi.testclient import TestClient
    from backend.server import create_app
    monkeypatch.setenv("SP_UI_DEV", "http://127.0.0.1:5181/")
    with TestClient(create_app(data_root=tmp_path / "data", watch=False)) as c:
        r = c.get("/project/alpha?tab=sprints", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "http://127.0.0.1:5181/project/alpha?tab=sprints"
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "http://127.0.0.1:5181/"
        assert c.get("/api/nothing-here").status_code == 404
        assert c.get("/api/health").status_code == 200


def test_the_environment_is_made_with_a_python_the_packages_are_built_for(launcher, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Windows runner whose newest Python was 3.15 built DuckDB from source
    and failed: no wheel past 3.14. Too new a Python looks for a supported
    one; none found is a sentence, not a compiler error."""
    import subprocess as sp
    assert launcher.base_python((3, 13)) == [launcher.sys.executable]
    have = {"python3.13": "/usr/bin/python3.13"}
    monkeypatch.setattr(launcher.os, "name", "posix")
    monkeypatch.setattr(launcher.shutil, "which", lambda name: have.get(name))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: sp.CompletedProcess(a, 0))
    assert launcher.base_python((3, 15)) == ["/usr/bin/python3.13"]
    have.clear()
    with pytest.raises(SystemExit):
        launcher.base_python((3, 15))


def test_too_old_a_python_says_how_to_get_one_on_this_system(launcher, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Ubuntu 22.04 ships 3.10, macOS's own python3 is 3.9: the refusal names
    the install command for the system, not only "a newer Python"."""
    monkeypatch.setattr(launcher, "WINDOWS", True)
    assert "python.org/downloads/windows" in launcher.python_hint()
    monkeypatch.setattr(launcher, "WINDOWS", False)
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    assert "brew install python@3.12" in launcher.python_hint()
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    release = tmp_path / "os-release"
    real = launcher.Path
    monkeypatch.setattr(launcher, "Path", lambda p, *a: release if p == "/etc/os-release" else real(p, *a))
    release.write_text('ID=ubuntu\nVERSION_ID="22.04"\n', encoding="utf-8")
    assert "sudo apt install python3.12 python3.12-venv" in launcher.python_hint()
    assert "deadsnakes" in launcher.python_hint()
    release.write_text("ID=arch\n", encoding="utf-8")
    assert "python.org/downloads" in launcher.python_hint()


def test_an_env_with_a_byte_order_mark_or_in_another_encoding(launcher) -> None:
    """Notepad's BOM made the first key "\\ufeffSP_DATA_ROOT", which nothing
    read; an "ANSI" .env crashed every command with a traceback."""
    launcher.ENV_FILE.write_bytes("\ufeffSP_DATA_ROOT=/data\n".encode("utf-8"))
    assert launcher.read_env() == {"SP_DATA_ROOT": "/data"}
    launcher.ENV_FILE.write_bytes("SP_DATA_ROOT=C:\\Users\\Jörg\\sp\n".encode("cp1252"))
    with pytest.raises(SystemExit, match=r"^\[sp\] \.env is not UTF-8"):
        launcher.read_env()


def test_sp_sh_skips_an_interpreter_that_does_not_run(tmp_path: Path) -> None:
    """A pyenv shim is on PATH for every version pyenv knows and fails for
    one not installed; it used to be taken on its name alone."""
    import os
    import shutil
    if os.name == "nt":
        pytest.skip("sp.sh is the POSIX launcher; Windows has sp.py")
    import subprocess
    root = Path(__file__).resolve().parents[2]
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    shim = bin_ / "python3.14"
    shim.write_text("#!/bin/sh\necho 'pyenv: python3.14: command not found' >&2\nexit 127\n")
    shim.chmod(0o755)
    real = bin_ / "python3.12"
    real.write_text("#!/bin/sh\necho python3.12\n")
    real.chmod(0o755)
    (bin_ / "dirname").symlink_to(shutil.which("dirname"))
    shutil.copy(root / "sp.sh", tmp_path / "sp.sh")
    got = subprocess.run(["/bin/bash", str(tmp_path / "sp.sh")], env={"PATH": str(bin_)},
                         capture_output=True, text=True, timeout=10)
    assert got.stdout.strip() == "python3.12" and got.returncode == 0
