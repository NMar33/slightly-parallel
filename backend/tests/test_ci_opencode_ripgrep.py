"""The live and offline OpenCode jobs provision the native skill dependency."""

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "scripts/ci/setup_opencode_ripgrep.py"


@pytest.mark.parametrize(("workflow", "job", "install_step"), [
    ("ci.yml", "interactive-cli", "Install the pinned CLI and PTY dependencies"),
    ("agents.yml", "agent", "OpenCode"),
])
def test_opencode_workflows_provision_rg_before_the_scenario(workflow, job, install_step):
    document = yaml.safe_load((ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8"))
    steps = document["jobs"][job]["steps"]
    index = next(index for index, step in enumerate(steps) if step.get("name") == install_step)
    install = steps[index]
    assert "!inputs.expect_failure" in install["if"]
    assert "python scripts/ci/setup_opencode_ripgrep.py" in install["run"]
    if workflow == "ci.yml":
        assert 'if [[ "$CLI" == opencode ]]; then' in install["run"]
        assert any("test_interactive_cli_captures_turns_and_board_commands[$CLI]" in step.get("run", "")
                   for step in steps[index + 1:])
    else:
        assert "matrix.tool == 'opencode'" in install["if"]
        assert any("python scripts/fresh_user/run.py" in step.get("run", "") for step in steps[index + 1:])


@pytest.mark.parametrize(("system", "binary", "package_commands"), [
    ("Linux", "rg", [["sudo", "apt-get", "update"], ["sudo", "apt-get", "install", "-y", "ripgrep"]]),
    ("Darwin", "rg", [["brew", "install", "ripgrep"]]),
    ("Windows", "rg.exe", [["choco", "install", "ripgrep", "--yes", "--no-progress"]]),
])
def test_setup_installs_native_rg_and_exports_the_discovered_directory(monkeypatch, tmp_path, system, binary, package_commands):
    setup = run_path(str(SETUP))["setup"]
    homebrew, chocolatey = tmp_path / "homebrew", tmp_path / "Chocolatey"
    github_path = tmp_path / "github-path"
    directory = {"Linux": Path("/usr/bin"), "Darwin": homebrew / "bin", "Windows": chocolatey / "bin"}[system]
    executable = str(directory / binary)
    searched = []
    ran = []

    def which(name, *, path=None):
        searched.append((name, path))
        return executable if path == str(directory) else None

    def run(command, *, check):
        assert check
        ran.append(command)

    def check_output(command, *, text):
        assert system == "Darwin" and command == ["brew", "--prefix"] and text
        return str(homebrew) + "\n"

    monkeypatch.setitem(setup.__globals__, "os", SimpleNamespace(environ={
        "GITHUB_PATH": str(github_path), "ChocolateyInstall": str(chocolatey),
    }))
    monkeypatch.setitem(setup.__globals__, "shutil", SimpleNamespace(which=which))
    monkeypatch.setitem(setup.__globals__, "subprocess", SimpleNamespace(run=run, check_output=check_output))
    setup(system)
    assert searched == [(binary, None), (binary, None), (binary, str(directory))]
    assert ran == [*package_commands, [executable, "--version"]]
    assert github_path.read_text(encoding="utf-8").splitlines() == [str(directory.absolute())]


def test_setup_fails_if_the_package_manager_does_not_provide_rg(monkeypatch):
    setup = run_path(str(SETUP))["setup"]
    monkeypatch.setitem(setup.__globals__, "shutil", SimpleNamespace(which=lambda *_args, **_kwargs: None))
    monkeypatch.setitem(setup.__globals__, "subprocess", SimpleNamespace(run=lambda *_args, **_kwargs: None))
    with pytest.raises(SystemExit, match="requires rg, but the package manager did not provide it"):
        setup("Linux")
