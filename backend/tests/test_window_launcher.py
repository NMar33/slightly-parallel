"""`sp.py window`: the menu entry, and whether Chromium's sandbox can start here."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _sp():
    spec = importlib.util.spec_from_file_location("sp_launcher", ROOT / "sp.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_menu_entry_runs_the_launcher(tmp_path, monkeypatch) -> None:
    sp = _sp()
    text = sp.window_entry("/usr/bin/python3")
    assert "Name=Slightly Parallel Terminal" in text and "Terminal=false" in text
    assert f'Exec="/usr/bin/python3" "{ROOT / "sp.py"}" "window"' in text
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(sp, "WINDOWS", False)
    monkeypatch.setattr(sp.sys, "platform", "linux")
    sp.cmd_window(["menu"])
    entry = tmp_path / "applications" / sp.WINDOW_ENTRY
    assert entry.read_text() == sp.window_entry(sp.sys.executable)
    sp.cmd_window(["off"])
    assert not entry.exists()


def test_the_window_is_electron_in_the_desktop_folder() -> None:
    sp = _sp()
    assert sp.DESKTOP == ROOT / "desktop" and (sp.DESKTOP / "main.js").exists() and (sp.DESKTOP / "preload.js").exists()
    # Electron's own program: npm's launcher is a Node script, and the
    # applications menu starts things without nvm's Node on the PATH.
    assert sp.DESKTOP / "node_modules" / "electron" / "dist" in sp.electron_bin().parents
    assert ".bin" not in sp.electron_bin().parts


def test_a_sandbox_helper_that_is_not_roots_cannot_start_the_sandbox(tmp_path, monkeypatch) -> None:
    sp = _sp()
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    assert sp.sandbox_usable(tmp_path) is True
    monkeypatch.setattr(sp.sys, "platform", "linux")
    restricted = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
    if restricted.exists() and restricted.read_text().strip() == "1":
        assert sp.sandbox_usable(tmp_path) is False            # no helper at all
        (tmp_path / "chrome-sandbox").write_text("x")
        assert sp.sandbox_usable(tmp_path) is False            # ours, not root's
    else:
        assert sp.sandbox_usable(tmp_path) is True
