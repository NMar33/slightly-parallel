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
