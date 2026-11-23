import subprocess
from pathlib import Path
from runpy import run_path


def test_cli_package_resolution_freezes_the_latest_version(monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "agent_packages.py"
    specs = run_path(str(script))
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] <= 15
        return subprocess.CompletedProcess(args, 0, '"2.1.400"\n', "")

    monkeypatch.setattr(subprocess, "run", run)
    package = specs["package_spec"]
    assert package("pinned", "claude-code", freeze=True) == "@anthropic-ai/claude-code@2.1.330"
    assert package("latest", "claude-code") == "@anthropic-ai/claude-code@latest"
    assert package("latest", "claude-code", freeze=True) == "@anthropic-ai/claude-code@2.1.400"
    assert calls == [["npm", "view", "@anthropic-ai/claude-code@latest", "version", "--json"]]
