"""The Windows workflow shell guard rejects a masked native failure."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


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
