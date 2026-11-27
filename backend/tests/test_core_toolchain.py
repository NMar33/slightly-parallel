from pathlib import Path
from runpy import run_path
from types import SimpleNamespace


def test_core_prerequisite_checks_pinned_pytest_and_both_git_identities(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    prepare = run_path(str(root / "scripts" / "ci" / "prepare_core_toolchain.py"))["prepare"]
    requirements = tmp_path / "requirements-dev.txt"
    requirements.write_text("pytest==9.1.1\npytest-xdist==3.8.0\n", encoding="utf-8")
    namespace = prepare.__globals__
    monkeypatch.setitem(namespace, "REQUIREMENTS", requirements)
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="pytest 9.1.1\n")

    monkeypatch.setattr(namespace["subprocess"], "run", run)
    prepare()
    python = namespace["sys"].executable
    assert [args for args, _ in calls] == [
        [python, "-m", "pip", "install", "pytest==9.1.1"],
        [python, "-m", "pytest", "--version"],
        ["git", "var", "GIT_AUTHOR_IDENT"],
        ["git", "var", "GIT_COMMITTER_IDENT"],
    ]
    assert all(options["check"] and options["timeout"] > 0 for _, options in calls)
