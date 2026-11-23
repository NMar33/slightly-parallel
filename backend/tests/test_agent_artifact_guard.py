import json
from pathlib import Path
from runpy import run_path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "guard_agent_artifacts.py"


@pytest.mark.parametrize("leak", ["wrapped known key", "tail in JSON", "masked prefix in a log", "invalid JSON"])
def test_unsafe_artifacts_never_reach_the_upload_directory(monkeypatch, tmp_path, leak):
    module = run_path(str(SCRIPT))
    suffix = "Q7aZ8wR9sZ1xK2yD3fB4"
    key = "sk-ant-api03-fakeSecret" + suffix
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    source = tmp_path / "source"
    logs = source / "logs"
    logs.mkdir(parents=True)
    report = source / "report.json"
    report.write_text('{"passed":false}', encoding="utf-8")
    if leak == "wrapped known key":
        value = key[:2] + "\n" + key[2:]
    elif leak == "tail in JSON":
        report.write_text(json.dumps({"detail": suffix[:7] + "\n" + suffix[7:] + " is invalid"}), encoding="utf-8")
        value = "expected use of the plan"
    elif leak == "invalid JSON":
        report.write_text('{"unclosed"', encoding="utf-8")
        value = "no JSON content here"
    else:
        value = "sk-a\x1b[31mnt-..\n.XY0123 · denied"
    (logs / "pty.log").write_text(value, encoding="utf-8")

    output = tmp_path / "audited"
    with pytest.raises(ValueError) as raised:
        module["stage_artifacts"](source, output)
    assert key not in str(raised.value) and suffix not in str(raised.value)
    assert not output.exists()


def test_upload_directory_contains_only_audited_text(tmp_path):
    stage = run_path(str(SCRIPT))["stage_artifacts"]
    source = tmp_path / "source"
    (source / "logs").mkdir(parents=True)
    (source / "screens").mkdir()
    (source / "screens" / "before.png").write_bytes(b"excluded from credentialed CI")
    (source / "logs" / "terminal.log").write_text("L1 unknown screen\n[redacted]", encoding="utf-8")
    (source / "report.json").write_text('{"passed":false}', encoding="utf-8")

    output = tmp_path / "audited"
    assert stage(source, output) == 2
    assert sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()) == [
        "logs/terminal.log", "report.json",
    ]


def test_codex_redaction_only_key_is_removed_from_the_subprocess_environment(monkeypatch):
    key = "sk-proj-SyntheticOpenAIKey1234567890"
    monkeypatch.setenv("SP_DIAGNOSTIC_OPENAI_KEY", key)
    namespace = run_path(str(SCRIPT.parents[1] / "fresh_user" / "common.py"), run_name="__main__")
    assert namespace["redact_diagnostics"](key[-20:]) == "[redacted]"
    assert "SP_DIAGNOSTIC_OPENAI_KEY" not in namespace["os"].environ
