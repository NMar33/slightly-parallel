"""The Windows workflow shell guard rejects a masked native failure."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PWSH_GUARD = "$ErrorActionPreference = 'Stop'\n$PSNativeCommandUseErrorActionPreference = $true\n"


@pytest.fixture
def issues(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts" / "ci"))
    from check_windows_shells import unsafe_steps

    return unsafe_steps


def test_every_windows_workflow_guards_native_failures(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts" / "ci"))
    from check_windows_shells import check

    assert check(ROOT / ".github" / "workflows") == []


@pytest.mark.parametrize(("shell", "script", "unsafe"), [
    ("", "python -m pytest\npython validate.py", True),
    ("pwsh", "$ErrorActionPreference = 'Stop'\npython -m pytest\npython validate.py", True),
    ("pwsh", "python -m pytest\n$ErrorActionPreference = 'Stop'\n$PSNativeCommandUseErrorActionPreference = $true", True),
    ("pwsh -File {0}", "$ErrorActionPreference = 'Stop'\n$PSNativeCommandUseErrorActionPreference = $true", True),
    ("pwsh", "$ErrorActionPreference = 'Stop'\n$PSNativeCommandUseErrorActionPreference = $true\npython -m pytest", False),
    ("bash", "python -m pytest\npython validate.py", False),
])
def test_windows_matrix_rejects_unsafe_shells(monkeypatch, shell, script, unsafe):
    monkeypatch.syspath_prepend(str(ROOT / "scripts" / "ci"))
    from check_windows_shells import unsafe_steps

    workflow = {"jobs": {"test": {
        "runs-on": "${{ matrix.host }}",
        "strategy": {"matrix": {"host": ["ubuntu-latest"], "include": [{"host": "windows-latest"}]}},
        "defaults": {"run": {"shell": shell}},
        "steps": [{"name": "test suite", "run": script}],
    }}}
    assert bool(unsafe_steps(workflow)) is unsafe


@pytest.mark.parametrize("source", ["workflow", "job", "step"])
@pytest.mark.parametrize("runner", ["ubuntu-latest", "macos-latest"])
def test_pwsh_is_guarded_on_every_runner(issues, source, runner):
    step = {"run": "python -m pytest\npython validate.py"}
    job = {"runs-on": runner, "steps": [step]}
    workflow = {"jobs": {"test": job}}
    if source == "step":
        step["shell"] = "pwsh"
    else:
        (workflow if source == "workflow" else job)["defaults"] = {"run": {"shell": "pwsh"}}
    assert issues(workflow)
    step["run"] = PWSH_GUARD + step["run"]
    assert issues(workflow) == []


@pytest.mark.parametrize("script", [
    "$script:ErrorActionPreference = 'Continue'",
    "$global:PSNativeCommandUseErrorActionPreference=$false",
    "Set-Variable -Name ErrorActionPreference -Value SilentlyContinue",
    "Remove-Variable PSNativeCommandUseErrorActionPreference",
    "Set-Item variable:ErrorActionPreference Continue",
    "$PSDefaultParameterValues['*:ErrorAction'] = 'SilentlyContinue'",
    "Write-Error 'bad' -ErrorAction SilentlyContinue",
    "python -m pytest || exit 0",
    "exit 0\npython -m pytest",
])
def test_pwsh_cannot_undo_the_guard(issues, script):
    assert issues({"jobs": {"test": {
        "runs-on": "windows-latest", "steps": [{"shell": "pwsh", "run": PWSH_GUARD + script}],
    }}})


@pytest.mark.parametrize(("script", "unsafe"), [
    ("set +e\npython -m pytest\npython validate.py", True),
    ("set +o pipefail; python -m pytest | tee pytest.log", True),
    ("python -m pytest || true\npython validate.py", True),
    ("python -m pytest || :\npython validate.py", True),
    ("python -m pytest || :; python validate.py", True),
    ("! command -v node\npython validate.py", True),
    ("exit 0\npython -m pytest", True),
    ("if ! command -v node; then python validate.py; fi", False),
    ("if command -v node; then echo 'unexpected node'; exit 1; fi", False),
    ("python -m pytest && python validate.py", False),
    ("set +x\npython -m pytest", False),
    ("set -euo pipefail\npython -m pytest", False),
    ("tool ${{ runner.os == 'Linux' && '--abc' || '' }}", False),
])
def test_bash_cannot_mask_standalone_failures(issues, script, unsafe):
    assert bool(issues({"jobs": {"test": {
        "runs-on": "ubuntu-latest", "steps": [{"shell": "bash", "run": script}],
    }}})) is unsafe


@pytest.mark.parametrize(("value", "unsafe"), [(True, True), (False, False), ("${{ matrix.optional }}", True)])
@pytest.mark.parametrize("scope", ["job", "step"])
def test_continue_on_error_is_rejected_for_required_work(issues, value, unsafe, scope):
    step = {"run": "python -m pytest", "shell": "bash"}
    job = {"runs-on": "ubuntu-latest", "steps": [step]}
    (step if scope == "step" else job)["continue-on-error"] = value
    assert bool(issues({"jobs": {"test": job}})) is unsafe


def test_only_the_named_benchmark_job_can_continue_on_error(issues):
    step = {"run": "npm run bench", "shell": "bash"}
    job = {"runs-on": "windows-latest", "steps": [step], "continue-on-error": "${{ !inputs.expect_failure }}"}
    assert issues({"jobs": {"bench": job}}, workflow_name="terminal-bench.yml") == []
    assert issues({"jobs": {"other": job}}, workflow_name="terminal-bench.yml")
    assert issues({"jobs": {"bench": job}}, workflow_name="ci.yml")
    step["continue-on-error"] = True
    assert issues({"jobs": {"bench": job}}, workflow_name="terminal-bench.yml")
    del step["continue-on-error"]
    job["continue-on-error"] = True  # The native failure probe must still fail this job.
    assert issues({"jobs": {"bench": job}}, workflow_name="terminal-bench.yml")


@pytest.mark.parametrize("runner", [
    ["self-hosted", "win32"],
    {"group": "ci", "labels": ["win32"]},
])
def test_win32_runner_labels_require_an_explicit_guarded_shell(issues, runner):
    assert issues({"jobs": {"test": {"runs-on": runner, "steps": [{"run": "python -m pytest"}]}}})


@pytest.mark.parametrize("shell", ["${{ matrix.shell }}", "powershell", "pwsh -File {0}"])
def test_unreviewed_powershell_templates_are_rejected_even_on_linux(issues, shell):
    assert issues({"jobs": {"test": {
        "runs-on": "ubuntu-latest", "steps": [{"shell": shell, "run": PWSH_GUARD + "python -m pytest"}],
    }}})


def test_unreviewed_local_composite_and_reusable_actions_fail_closed(issues):
    workflow = {"jobs": {
        "test": {"runs-on": "ubuntu-latest", "steps": [
            {"uses": "actions/checkout@v7"},
            {"uses": "./.github/actions/test-tool"},
        ]},
        "reuse": {"uses": "./.github/workflows/reuse.yml"},
    }}
    assert len(issues(workflow)) == 2
