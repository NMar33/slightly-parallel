"""The one resolver of chat folders (backend/backend/chatstore.py,
tk_d1d25a4d step 1): its listings give what the globs they replaced gave, the
hook's fallback names the same folder, and a hook that cannot load it still
writes the turn."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend import chatstore

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _hook(name: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# The listings mirror glob
# ---------------------------------------------------------------------------

@pytest.fixture()
def odd_root(tmp_path: Path) -> Path:
    """A data root with the cases glob treats its own way: a hidden project
    and chat, a symlinked chat folder, a broken symlink for meta.json, a file
    where a chat folder would be, a project without chats."""
    root = tmp_path / "data"
    for project, agent in (("alpha", "cc-b"), ("alpha", "cc-a"), ("alpha", ".cc-hidden"), (".hid", "cc-h"),
                           ("beta", "codex-1"), ("beta", "cc-a-b")):
        d = root / "projects" / project / "chats" / agent
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"project": project}), encoding="utf-8")
        (d / "chat.md").write_text("# Chat log\n", encoding="utf-8")
    (root / "projects" / "gamma").mkdir()
    (root / "projects" / "alpha" / "chats" / "stray.txt").write_text("x", encoding="utf-8")
    broken = root / "projects" / "beta" / "chats" / "cc-broken"
    broken.mkdir()
    (broken / "meta.json").symlink_to(broken / "nowhere.json")
    (root / "projects" / "beta" / "chats" / "cc-link").symlink_to(root / "projects" / "alpha" / "chats" / "cc-a")
    (root / "projects" / "beta" / "chats" / "cc-empty").mkdir()
    return root


def test_iter_chats_lists_what_the_globs_listed(odd_root: Path) -> None:
    # A broken symlink: glob matched it on 3.12+, not on 3.11; chatstore
    # lists it on every version (checked apart, then left out of the match).
    def sound(paths):
        return [p for p in paths if p.exists()]

    for has in ("meta.json", "chat.md"):
        globbed = sound(odd_root.glob(f"projects/*/chats/*/{has}"))
        listed = [f / has for _p, _a, f in chatstore.iter_chats(odd_root, has=has, sort=False)]
        assert sound(listed) == globbed, has                            # the same order too
        assert sound(f / has for _p, _a, f in chatstore.iter_chats(odd_root, has=has)) == sorted(globbed)
        one = [f / has for _p, _a, f in chatstore.iter_chats(odd_root, "beta", has=has, sort=False)]
        assert sound(one) == sound((odd_root / "projects" / "beta" / "chats").glob(f"*/{has}"))
    broken = chatstore.folder(odd_root, "beta", "cc-broken")
    assert broken in [f for _p, _a, f in chatstore.iter_chats(odd_root, has="meta.json")]
    assert broken not in [f for _p, _a, f in chatstore.iter_chats(odd_root, has="chat.md")]
    # Every folder, with or without files: what glob("*/*") walked into.
    every = sorted({p.parent for p in odd_root.glob("projects/*/chats/*/*")})
    assert [f for _p, _a, f in chatstore.iter_chats(odd_root) if any(f.iterdir())] == every
    assert ("beta", "cc-empty") in {(p, a) for p, a, _f in chatstore.iter_chats(odd_root)}


def test_the_names_come_from_the_folders(odd_root: Path) -> None:
    got = {(p, a) for p, a, f in chatstore.iter_chats(odd_root)}
    assert ("alpha", ".cc-hidden") in got and (".hid", "cc-h") in got and ("beta", "cc-link") in got
    assert not any(a == "stray.txt" for _p, a in got)
    for p, a, f in chatstore.iter_chats(odd_root):
        assert f == chatstore.folder(odd_root, p, a)
    assert list(chatstore.iter_chats(odd_root / "nowhere")) == []
    assert list(chatstore.iter_chats(odd_root, "nope")) == []


def test_folders_in_is_iterdir_with_the_same_filters(odd_root: Path) -> None:
    chats = chatstore.chats_root(odd_root, "beta")
    assert chatstore.folders_in(chats) == sorted(p for p in chats.iterdir() if p.is_dir())
    assert chatstore.folders_in(chats, skip_symlinks=True) == sorted(
        p for p in chats.iterdir() if p.is_dir() and not p.is_symlink())
    assert chatstore.folders_in(odd_root / "projects" / "gamma" / "chats") == []


def test_folders_of_finds_an_agent_in_every_project(odd_root: Path) -> None:
    globbed = sorted(odd_root.glob("projects/*/chats/cc-a/meta.json"))
    assert [f / "meta.json" for _p, f in chatstore.folders_of(odd_root, "cc-a", has="meta.json")] == globbed
    assert [p for p, _f in chatstore.folders_of(odd_root, "cc-broken", has="meta.json")] == ["beta"]
    assert list(chatstore.folders_of(odd_root, "cc-none")) == []


def test_project_of_reads_meta_first_then_the_folder(tmp_path: Path) -> None:
    f = chatstore.folder(tmp_path, "home", "cc-1")
    f.mkdir(parents=True)
    assert chatstore.project_of(f) == "home"                            # no meta.json
    (f / "meta.json").write_text(json.dumps({"project": "named"}), encoding="utf-8")
    assert chatstore.project_of(f) == "named"
    assert chatstore.project_of(f, {"project": ""}) == "home"           # the old `meta.get("project") or <folder>`
    assert chatstore.project_of(f, {}) == "home"
    (f / "meta.json").write_text("[]", encoding="utf-8")
    assert chatstore.project_of(f) == "home"


# ---------------------------------------------------------------------------
# The hook
# ---------------------------------------------------------------------------

ODD_NAMES = ["plain", "with space", "dollar$HOME", "$", unicodedata.normalize("NFD", "café"),
             unicodedata.normalize("NFC", "café"), "C:", "C:\\x", "ünï code", "a.b-c_d"]


def test_the_hook_fallback_names_the_folder_chatstore_names(tmp_path: Path) -> None:
    capture = _hook("sp_capture_chatstore_parity")
    roots = [str(tmp_path), str(tmp_path) + os.sep, str(tmp_path / "with space"), str(tmp_path / "$dollar"),
             str(tmp_path / unicodedata.normalize("NFD", "é")), "C:/data", "relative/root/"]
    for root in roots:
        for project in ODD_NAMES:
            for agent in ODD_NAMES:
                want = chatstore.folder(root, project, agent)
                got = capture._fallback_folder(Path(root), project, agent)
                assert got == want and str(got) == str(want), (root, project, agent)
    # And the hook, loaded whole, takes chatstore's.
    cap = capture.TurnCapture(tmp_path / "data", "p$q", "cc-x")
    assert cap.folder == chatstore.folder(tmp_path / "data", "p$q", "cc-x")


def _yesterday_chat(root: Path, project: str) -> None:
    then = datetime.now() - timedelta(days=1)
    d = chatstore.folder(root, project, "cc-yest0001")
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"agent_id": "cc-yest0001"}), encoding="utf-8")
    at = then.replace(hour=10, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%S")
    (d / "chat.md").write_text(f"# Chat log\n\n---\n\n## Turn 1 · {at}\n**User**: make it\n**Agent**: done\n",
                               encoding="utf-8")


def _hook_without_chatstore(monkeypatch: pytest.MonkeyPatch, name: str):
    """The hook loaded while backend/backend/chatstore.py does not load."""
    real = importlib.util.spec_from_file_location

    def refuse(mod_name, location=None, *args, **kwargs):
        if location is not None and Path(location).name == "chatstore.py":
            raise ImportError("chatstore.py refused by the test")
        return real(mod_name, location, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "spec_from_file_location", refuse)
    try:
        return _hook(name)
    finally:
        monkeypatch.setattr(importlib.util, "spec_from_file_location", real)


def test_a_hook_without_chatstore_still_writes_the_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "data"
    root.mkdir()
    _yesterday_chat(root, "ALPHA")

    # The control: with chatstore, the nudge comes and no error is kept.
    ok = _hook("sp_capture_with_chatstore")
    assert ok.chatstore is not None and ok._CHATSTORE_ERROR is None
    cap = ok.TurnCapture(root, "ALPHA", "cc-control")
    assert cap.open_turn("good morning")["standup_due"] is not None
    cap.complete_turn("hi")
    assert not (root / ".capture" / "errors.jsonl").exists()

    other = tmp_path / "other"
    other.mkdir()
    _yesterday_chat(other, "ALPHA")
    before = sorted(p.relative_to(other).as_posix() for p in other.rglob("*"))
    broken = _hook_without_chatstore(monkeypatch, "sp_capture_without_chatstore")
    assert broken.chatstore is None and "refused by the test" in (broken._CHATSTORE_ERROR or "")
    # Nothing written at import.
    assert sorted(p.relative_to(other).as_posix() for p in other.rglob("*")) == before

    cap = broken.TurnCapture(other, "ALPHA", "cc-nochat1")
    assert cap.folder == chatstore.folder(other, "ALPHA", "cc-nochat1")
    signals = cap.open_turn("good morning")
    assert signals["standup_due"] is None                               # the nudge skipped
    cap.complete_turn("the answer")
    chat = (chatstore.folder(other, "ALPHA", "cc-nochat1") / "chat.md").read_text(encoding="utf-8")
    assert "**User**: good morning" in chat and "**Agent**: the answer" in chat
    lines = (other / ".capture" / "errors.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, lines
    row = json.loads(lines[0])
    assert row["agent_id"] == "cc-nochat1" and row["project"] == "ALPHA" and "chatstore" in row["error"]
    # Not marked asked: the next turn with chatstore back asks again.
    meta = json.loads((chatstore.folder(other, "ALPHA", "cc-nochat1") / "meta.json").read_text(encoding="utf-8"))
    assert "standup_asked" not in meta


def test_is_chat_file_places_a_file_in_the_chats_area() -> None:
    """What ViewStore._area gave with ``parts[2] == "chats"`` before."""
    from backend.db import ViewStore

    cases = {
        "projects/alpha/chats/cc-1/chat.md": True,
        "projects/alpha/chats/cc-1": True,
        "projects/alpha/chats": True,
        "projects/alpha/goals.csv": False,
        "projects/alpha": False,
        "projects/chats/x": False,
        "chats/alpha/chats": False,
        "tasks.csv": False,
    }
    for rel, want in cases.items():
        assert chatstore.is_chat_file(rel) is want, rel
        assert chatstore.is_chat_file(Path(rel)) is want, rel
        assert (ViewStore._area(Path(rel)) == "chats") is want, rel
