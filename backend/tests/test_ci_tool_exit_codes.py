"""A failed native command must make its CI script fail."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("bash"),
    reason="a bash script, run on Linux and macOS",
)


def _executable(folder: Path, name: str, script: str) -> None:
    command = folder / name
    command.write_text(f"#!/bin/bash\n{script}\n", encoding="utf-8")
    command.chmod(0o755)


@pytest.mark.parametrize("login_exit", [0, 23])
def test_noninteractive_bootstrap_preserves_the_codex_login_exit(tmp_path, login_exit):
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (home / ".nvm").mkdir(parents=True)
    (home / ".nvm" / "nvm.sh").write_text("nvm() { return 0; }\n", encoding="utf-8")
    _executable(bin_dir, "uname", "echo Darwin")
    for command in ("brew", "git", "npm"):
        _executable(bin_dir, command, "exit 0")
    _executable(bin_dir, "uv", """case "$1 $2" in
  'python install') exit 0 ;;
  'python find') printf '%s\\n' "$SP_FIXTURE_PYTHON" ;;
  'run --no-project') : > "$SP_FIXTURE_MACHINE_RUN" ;;
  *) exit 99 ;;
esac""")
    _executable(bin_dir, "codex", """[[ $* == 'login --with-api-key' ]] || exit 99
IFS= read -r key
[[ $key == 'bootstrap-fixture-value' ]] || exit 99
: > "$SP_FIXTURE_LOGIN"
exit "$SP_FIXTURE_LOGIN_EXIT"
""")
    login = tmp_path / "login"
    machine_run = tmp_path / "machine-run"
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.defpath}",
        "HOME": str(home),
        "SP_LOCAL": "1",
        "SP_NONINTERACTIVE": "1",
        "OPENAI_API_KEY": "bootstrap-fixture-value",
        "SP_FIXTURE_PYTHON": sys.executable,
        "SP_FIXTURE_MACHINE_RUN": str(machine_run),
        "SP_FIXTURE_LOGIN": str(login),
        "SP_FIXTURE_LOGIN_EXIT": str(login_exit),
    }
    result = subprocess.run(["bash", str(ROOT / "scripts/machine/bootstrap.sh")],
                            env=env, capture_output=True, encoding="utf-8", timeout=15)
    assert login.exists(), result.stderr
    assert result.returncode == login_exit, (result.stdout, result.stderr)
    assert machine_run.exists() is (login_exit == 0)


@pytest.fixture()
def color_guard(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "check-no-raw-hex.sh"
    shutil.copyfile(ROOT / "scripts" / script.name, script)
    frontend = tmp_path / "frontend/src"
    frontend.mkdir(parents=True)
    return script, frontend


@pytest.mark.parametrize(("color", "expected"), [(None, 0), ("#aabbcc", 1)])
def test_color_guard_distinguishes_no_matches_from_raw_colors(color_guard, color, expected):
    script, frontend = color_guard
    (frontend / "styles").mkdir()
    (frontend / "styles/tokens.css").write_text(":root { --color: #abcdef; }\n", encoding="utf-8")
    value = color if color is not None else "var(--color)"
    (frontend / "app.ts").write_text(f"const color = '{value}'\n", encoding="utf-8")
    result = subprocess.run(["bash", str(script)], capture_output=True, encoding="utf-8", timeout=15)
    assert result.returncode == expected, (result.stdout, result.stderr)
    if color is not None:
        assert "app.ts:1:" in result.stdout and color in result.stdout


@pytest.mark.parametrize("broken_grep", ["-rnoE", "-v", "-vE", "-vF"])
def test_color_guard_preserves_errors_at_each_grep_stage(tmp_path, color_guard, broken_grep):
    script, frontend = color_guard
    (frontend / "app.ts").write_text("const color = 'var(--color)'\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir, "grep", """if [[ $1 == "$SP_FIXTURE_BROKEN_GREP" ]]; then
  echo 'grep fixture: input could not be read' >&2
  exit 2
fi
exec "$SP_FIXTURE_GREP" "$@"
""")
    grep = shutil.which("grep")
    assert grep is not None
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
           "SP_FIXTURE_BROKEN_GREP": broken_grep, "SP_FIXTURE_GREP": grep}
    result = subprocess.run(["bash", str(script)], env=env, capture_output=True, encoding="utf-8", timeout=15)
    assert "grep fixture: input could not be read" in result.stderr
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "clean" not in result.stdout
