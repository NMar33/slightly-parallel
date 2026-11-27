import json
import sys
import zipfile
from pathlib import Path
from runpy import run_path

import pytest


def test_machine_keeps_the_unicode_pty_diagnostic_in_a_redirected_log(tmp_path, monkeypatch) -> None:
    machine = Path(__file__).resolve().parents[2] / "scripts" / "machine" / "run.py"
    run = run_path(str(machine))["run"]
    monkeypatch.setitem(run.__globals__, "OUT", tmp_path)
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    screen = "❯ Пользователь · ü"
    assert run("pty", [sys.executable, "-c", f"print({ascii(screen)})"], cwd=tmp_path)
    assert (tmp_path / "pty.log").read_text(encoding="utf-8").strip() == screen


@pytest.mark.parametrize("unsafe", [False, True])
def test_machine_archive_stages_only_checked_text(monkeypatch, tmp_path, unsafe):
    guard = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "guard_agent_artifacts.py"
    stage = run_path(str(guard))["stage_machine_archives"]
    key = "sk-ant-api03-fakeSecretQ7aZ8wR9sZ1xK2yD3fB4"
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    source = tmp_path / "source"
    source.mkdir()
    archive = source / "sp-machine-runner.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        detail = key[-20:-6] + "\n› " + key[-6:] + " is invalid" if unsafe else "the original text"
        bundle.writestr("chats/test/work.jsonl", json.dumps({"detail": detail}) + "\n")
        bundle.writestr("run/steps.json", '[{"ok": true}]')
        bundle.writestr("fresh-user/screens/before.png", b"not audited")

    output = tmp_path / "audited"
    if unsafe:
        with pytest.raises(ValueError):
            stage(source, output)
        assert not output.exists()
    else:
        assert stage(source, output) == 2
        with zipfile.ZipFile(output / archive.name) as bundle:
            assert sorted(bundle.namelist()) == ["chats/test/work.jsonl", "run/steps.json"]
            assert b"the original text" in bundle.read("chats/test/work.jsonl")


def test_machine_archive_keeps_chat_files_from_distinct_projects(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    make_archive = run_path(str(root / "scripts" / "machine" / "run.py"))["bundle"]
    stage = run_path(str(root / "scripts" / "ci" / "guard_agent_artifacts.py"))["stage_machine_archives"]
    fresh = tmp_path / "fresh"
    for project in ("first", "second"):
        chat = fresh / "data" / "projects" / project / "chats" / "cc-f0e1d2c3"
        chat.mkdir(parents=True)
        (chat / "meta.json").write_text(json.dumps({"project": project}), encoding="utf-8")

    out = tmp_path / "run"
    out.mkdir()
    env = make_archive.__globals__
    monkeypatch.setitem(env, "REPO", tmp_path)
    monkeypatch.setitem(env, "OUT", out)
    monkeypatch.setitem(env, "versions", dict)
    monkeypatch.setitem(env, "secrets", list)
    monkeypatch.setenv("SP_ARCHIVE_DIR", str(tmp_path / "raw"))

    archive = make_archive(fresh)
    audited = tmp_path / "audited"
    assert stage(archive.parent, audited) == 3
    with zipfile.ZipFile(audited / archive.name) as checked:
        for project in ("first", "second"):
            assert json.loads(checked.read(f"projects/{project}/chats/cc-f0e1d2c3/meta.json")) == {"project": project}


@pytest.mark.parametrize("outcome", ["success", "timeout", "wrong-version"])
def test_pinned_sdk_prerequisite_records_bounded_redacted_diagnostics(monkeypatch, tmp_path, outcome):
    script = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "prepare_opencode_sdk.py"
    prepare = run_path(str(script))["prepare"]
    ns = prepare.__globals__
    seed = tmp_path / "seed"
    report = tmp_path / "results" / "opencode-sdk.json"
    secret = "sk-proj-SyntheticOpenAIKey1234567890"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setattr(ns["shutil"], "which", lambda name: name)

    calls = []

    class Npm:
        pid = 1789

        def __init__(self, argv, *, stderr, env, **_kwargs):
            assert argv[-2:] == [str(seed), "@opencode-ai/plugin@1.19.3"]
            assert "OPENAI_API_KEY" not in env
            stderr.write((f"npm error registry 503 {secret}\n").encode("utf-8"))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def wait(self, timeout):
            assert timeout == 60
            if outcome == "timeout":
                raise ns["subprocess"].TimeoutExpired("npm", timeout)
            package = seed / "node_modules" / "@opencode-ai" / "plugin" / "package.json"
            package.parent.mkdir(parents=True)
            package.write_text(json.dumps({"version": "1.19.4" if outcome == "wrong-version" else "1.19.3"}), encoding="utf-8")
            (seed / "package.json").write_text("{}", encoding="utf-8")
            (seed / "package-lock.json").write_text("{}", encoding="utf-8")
            return 0

        def kill(self):
            calls.append("kill")

    monkeypatch.setattr(ns["subprocess"], "Popen", Npm)
    monkeypatch.setattr(ns["subprocess"], "run", lambda argv, **_kwargs: calls.append(argv[0]))
    assert prepare(seed, report, "1.19.3") is (outcome == "success")
    text = report.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["timeout_seconds"] == 60
    assert data["elapsed_seconds"] >= 0
    assert data["status"] == {"success": "ready", "timeout": "timed out", "wrong-version": "invalid seed"}[outcome]
    assert "registry 503" in data["stderr_tail"]
    assert secret not in text
    if outcome == "timeout":
        assert calls[-1] == "kill"


def test_windows_machine_seeds_opencode_before_running_fresh_user(monkeypatch, tmp_path):
    machine = Path(__file__).resolve().parents[2] / "scripts" / "machine" / "run.py"
    fresh = run_path(str(machine))["run_fresh_user"]
    ns = fresh.__globals__
    monkeypatch.setitem(ns, "WINDOWS", True)
    monkeypatch.setitem(ns, "OUT", tmp_path / "reports")
    calls = []
    steps_ok = True

    def run(name, argv, **kwargs):
        calls.append((name, argv, kwargs))
        return steps_ok

    monkeypatch.setitem(ns, "run", run)
    fresh("codex,opencode", "haiku")
    (preparation, command, _), (stage, _, options) = calls
    assert "Prepare pinned OpenCode SDK" in preparation and "60" in preparation
    assert command[1] == "scripts/ci/prepare_opencode_sdk.py"
    assert stage == "fresh-user"
    assert options["env"]["SP_OPENCODE_SDK_SEED"] == command[command.index("--seed") + 1]
    assert command[command.index("--report") + 1] == str(tmp_path / "reports" / "opencode-sdk.json")

    calls.clear()
    fresh("codex", "haiku")
    assert [name for name, _, _ in calls] == ["fresh-user"]

    calls.clear()
    steps_ok = False
    assert not fresh("opencode", "haiku")
    assert [name for name, _, _ in calls] == [preparation]
