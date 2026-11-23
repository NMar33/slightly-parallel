import json
import re
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


@pytest.mark.parametrize("prefix", ["▌", "›", ">", "⎿", "|"])
def test_row_prefixes_do_not_hide_known_fragments_from_the_redactor_or_guard(monkeypatch, prefix):
    run_path(str(SCRIPT))
    from common import contains_diagnostic_key, redact_diagnostics

    tail = "Q7aZ8wR9sZ1xK2yD3fB4"
    key = "sk-ant-api03-fakeSecret" + tail
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    for value in (key, tail):
        for split in range(1, len(value)):
            wrapped = f"{prefix} {value[:split]}\n{prefix} {value[split:]} keep"
            assert contains_diagnostic_key(wrapped)
            assert redact_diagnostics(wrapped) == f"{prefix} [redacted] keep"


@pytest.mark.parametrize("prefix", ["12 ", "- ", "a-", "⎿ 3 "])
@pytest.mark.parametrize("provider", ["ANTHROPIC", "OPENAI"])
def test_key_alphabet_prefixes_do_not_interrupt_matches(monkeypatch, prefix, provider):
    run_path(str(SCRIPT))
    from common import contains_diagnostic_key, redact_diagnostics

    tail = "Q7aZ8wR9sZ1xK2yD3fB4"
    key = ("sk-ant-api03-" if provider == "ANTHROPIC" else "sk-proj-") + "fakeSecret" + tail
    monkeypatch.setenv(f"{provider}_API_KEY", key)
    for value in (key, tail):
        for split in range(1, len(value)):
            wrapped = f"{prefix}{value[:split]}\n{prefix}{value[split:]} keep"
            assert contains_diagnostic_key(wrapped), split
            assert redact_diagnostics(wrapped) == f"{prefix}[redacted] keep", split


def test_guard_distinguishes_wrapped_prefixes_from_normal_words():
    run_path(str(SCRIPT))
    from common import contains_diagnostic_key, redact_diagnostics

    for text in ("disk-test-runner", "task-live-check", "risk-…", "sk-learn-compatible-tools"):
        assert not contains_diagnostic_key(text)
        assert redact_diagnostics(text) == text
    assert contains_diagnostic_key("sk-pr\n▌ oj-")
    display = "Incorrect key: sk-proj-abc**\n▌ ***TAIL. Keep this text."
    assert contains_diagnostic_key(display)
    assert redact_diagnostics(display) == "Incorrect key: [redacted]. Keep this text."


def test_numbered_rows_can_continue_a_key_across_several_lines(monkeypatch):
    run_path(str(SCRIPT))
    from common import contains_diagnostic_key, redact_diagnostics

    key = "sk-proj-M6jJ7pQ0zR5tW9yT4fE8eU3pZ1xC4mV7bH2eK9yT3fD8uC4bB2"
    monkeypatch.setenv("OPENAI_API_KEY", key)
    for width in range(20, 60):
        for column in range(width - 3):
            text = "x" * column + key + " keep"
            wrapped = "\n".join(f"{number:02} {text[i:i + width - 3]}"
                                for number, i in enumerate(range(0, len(text), width - 3), start=12))
            assert contains_diagnostic_key(wrapped), (width, column)
            clean = redact_diagnostics(wrapped)
            assert "[redacted]" in clean and not contains_diagnostic_key(clean), (width, column)
            assert re.sub(r"(?m)^\d+ ", "", clean).replace("\n", "").endswith("keep"), (width, column)
