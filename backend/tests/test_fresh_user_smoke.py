"""First-run dialogs that would otherwise eat the first operator prompt."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(("dialog", "keys", "action"), [
    ("Do you want to use this API key? Yes ❯ No (recommended)", ["\x1b[A", "\r"], "accepted CI API key"),
    ("❯ 1. No, exit\n2. Yes, I trust this folder", ["\x1b[B", "\r"], "project folder trusted"),
    ("1. Yes, I trust this folder\n❯ 2. No, exit", ["\x1b[A", "\r"], "project folder trusted"),
])
def test_claude_onboarding_reaches_the_prompt(monkeypatch, dialog, keys, action) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from agents import tools
    from interactive import _ready

    class Screen:
        text = ""
        keys = []
        frames = deque([dialog, "❯ Try writing a test"])

        def read(self):
            if self.frames:
                self.text = self.frames.popleft()

        def send(self, key):
            self.keys.append(key)

    screen = Screen()
    answered: list[str] = []
    assert _ready(screen, tools()["claude-code"], 2, answered)
    assert screen.keys == keys
    assert answered == [f"Claude Code {action}"]


def test_new_cards_include_a_late_duplicate(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    import common

    answers = iter([[{"id": "previous"}, {"id": "first"}], [{"id": "previous"}, {"id": "repeated"}]])
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(common, "get", lambda _space, _path: next(answers))
    monkeypatch.setattr(common, "time", SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _: None))
    cards = common.new_task_rows(common.Space(Path(), 1), "calc", {"previous"})
    assert [row["id"] for row in cards] == ["first", "repeated"]


def test_codex_waits_for_folder_and_hook_trust_after_the_composer_first_draws(monkeypatch, tmp_path) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from agents import tools
    from interactive import _ready

    config = tmp_path / "config.toml"

    class Screen:
        text = ""
        keys = []
        frames = deque(["Ask Codex to do anything", "Folder access. Trust this folder?",
                        "Review hooks. Trust all and continue", "Ask Codex to do anything"])

        def read(self):
            if self.frames:
                self.text = self.frames.popleft()
                if not self.frames:
                    config.write_text('trusted_hash = "example"\n', encoding="utf-8")

        def send(self, key):
            self.keys.append(key)

    screen = Screen()
    answered: list[str] = []
    assert _ready(screen, tools()["codex"], 3, answered, config)
    assert screen.keys == ["\r", "\x1b[B", "\r"]
    assert answered == ["Codex project folder trusted", "Codex project hooks trusted"]
