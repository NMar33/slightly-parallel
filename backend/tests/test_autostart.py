"""Start at login and the shortcut (backend/autostart.py), each system's way,
written into a temporary home: never the real login or desktop."""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import autostart

PY = "/usr/bin/python3"
# The Linux entries are written on Linux only: a Windows path holds
# backslashes (escaped in an Exec line) and no file there is executable.
posix = pytest.mark.skipif(os.name == "nt", reason="Linux entries are written on Linux")


@pytest.fixture()
def where(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData" / "Roaming"))
    root = tmp_path / "my apps" / "slightly-parallel"     # a space, as on the author's machine
    root.mkdir(parents=True)
    return root, tmp_path / "home"


@posix
def test_linux_starts_it_at_login_and_turns_it_off_again(where) -> None:
    root, home = where
    written = autostart.enable(root, "autostart", home=home, plat="linux", python=PY)
    entry = home / ".config" / "autostart" / "slightly-parallel.desktop"
    assert written == [str(entry)]
    text = entry.read_text(encoding="utf-8")
    assert f'Exec="{PY}" "{root / "sp.py"}" up' in text and "Hidden" not in text
    assert autostart.status(root)["autostart"]["on"] is True
    assert autostart.disable(root, "autostart") == [str(entry)]
    assert not entry.exists() and autostart.status(root)["autostart"]["on"] is False


@posix
def test_linux_shortcut_goes_to_the_menu_and_the_desktop_by_its_own_name(where) -> None:
    root, home = where
    desk = home / "Рабочий стол"
    desk.mkdir(parents=True)
    (home / ".config").mkdir(parents=True)
    (home / ".config" / "user-dirs.dirs").write_text('XDG_DESKTOP_DIR="$HOME/Рабочий стол"\n', encoding="utf-8")
    written = autostart.enable(root, "shortcut", home=home, plat="linux", python=PY)
    assert written == [str(home / ".local/share/applications/slightly-parallel.desktop"),
                       str(desk / "slightly-parallel.desktop")]
    assert "sp.py\" open" in Path(written[1]).read_text(encoding="utf-8")
    assert Path(written[1]).stat().st_mode & 0o100


def test_a_desktop_entry_escapes_what_the_specification_says() -> None:
    assert autostart._desktop_arg('/a b/$x"y') == '"/a b/\\$x\\"y"'


def test_mac_writes_a_launch_agent_and_an_app(where) -> None:
    root, home = where
    (agent,) = autostart.enable(root, "autostart", home=home, plat="darwin", python=PY)
    plist = plistlib.loads(Path(agent).read_bytes())
    assert plist["ProgramArguments"] == [PY, str(root / "sp.py"), "up"] and plist["RunAtLoad"] is True
    assert plist["AbandonProcessGroup"] is True    # sp.py up returns; the server stays
    (app,) = autostart.enable(root, "shortcut", home=home, plat="darwin", python=PY)
    assert app.endswith("Slightly Parallel.app")
    assert "open" in (Path(app) / "Contents" / "MacOS" / "open-slightly-parallel").read_text(encoding="utf-8")
    assert autostart.disable(root, "shortcut") == [app] and not Path(app).exists()


def test_windows_writes_a_startup_command_and_a_shortcut_script(where) -> None:
    root, home = where
    (cmd,) = autostart.enable(root, "autostart", home=home, plat="win32", python=PY)
    assert Path(cmd).parent.name == "Startup" and "sp.py\" up" in Path(cmd).read_text(encoding="utf-8")
    script = autostart.windows_shortcut_script(root, "C:\\Py\\python.exe", "Desktop")
    assert "GetFolderPath('Desktop')" in script and "open'" in script and "favicon.ico" in script


def test_turning_off_removes_only_what_it_wrote(where) -> None:
    root, home = where
    mine = home / ".config" / "autostart" / "other-app.desktop"
    mine.parent.mkdir(parents=True)
    mine.write_text("[Desktop Entry]\n", encoding="utf-8")
    autostart.enable(root, "autostart", home=home, plat="linux", python=PY)
    autostart.disable(root, "autostart")
    assert mine.exists()


def test_setup_switches_it_and_a_test_server_refuses(client: TestClient, monkeypatch) -> None:
    c = client
    if True:
        info = c.get("/api/setup/info").json()["computer"]
        assert info["autostart"]["on"] is False and info["shortcut"]["on"] is False
        got = c.post("/api/setup/computer", json={"autostart": True}).json()["computer"]
        assert got["autostart"]["on"] is True
        assert c.post("/api/setup/computer", json={"autostart": False}).json()["computer"]["autostart"]["on"] is False
        from backend.routers import setup as setup_router
        monkeypatch.setenv("SP_SANDBOX", "1")
        monkeypatch.setattr(setup_router, "AUTOSTART_HOME", None)   # the real home: refused
        r = c.post("/api/setup/computer", json={"autostart": True})
        assert r.status_code == 409 and "SP_SANDBOX" in r.json()["detail"]


def test_integrate_turns_them_on_when_ticked_and_never_off(client: TestClient, tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    body = {"project_code": "proj", "project_dir": str(proj), "write_claude_hooks": False, "autostart": True}
    preview = client.post("/api/setup/integrate", json={**body, "dry_run": True}).json()["results"]
    assert {"file": "start at login", "action": "would turn on", "content": ""} in preview
    rows = client.post("/api/setup/integrate", json=body).json()["results"]
    assert any(r["action"] == "start at login" for r in rows)
    # Integrating again with the box clear leaves it on: Settings turns it off.
    client.post("/api/setup/integrate", json={**body, "autostart": False})
    assert client.get("/api/setup/info").json()["computer"]["autostart"]["on"] is True
