from pathlib import Path
from runpy import run_path
import sys


def test_machine_keeps_the_unicode_pty_diagnostic_in_a_redirected_log(tmp_path, monkeypatch) -> None:
    machine = Path(__file__).resolve().parents[2] / "scripts" / "machine" / "run.py"
    run = run_path(str(machine))["run"]
    monkeypatch.setitem(run.__globals__, "OUT", tmp_path)
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    screen = "❯ Пользователь · ü"
    assert run("pty", [sys.executable, "-c", f"print({ascii(screen)})"], cwd=tmp_path)
    assert (tmp_path / "pty.log").read_text(encoding="utf-8").strip() == screen
