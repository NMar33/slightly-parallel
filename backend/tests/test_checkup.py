"""#sp: the checks for this chat and folder (backend/checkup.py, GET
/api/checkup, the MCP tool checkup)."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend import checkup


def test_a_folder_that_is_not_connected_is_a_concern_and_unknowns_are_never_fine(client: TestClient, tmp_path: Path) -> None:
    del client.headers["X-SP-Via"]                 # the suite marks every call as the MCP's
    r = client.get("/api/checkup", params={"cwd": str(tmp_path)})
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {f["id"]: f for f in body["findings"]}
    assert by_id["folder"]["status"] == "concern" and "Setup" in by_id["folder"]["next"]
    assert by_id["chat"]["status"] == "unknown" and by_id["mcp"]["status"] == "unknown"
    assert not body["verdict"].startswith("All fine")
    # The worst come first: concerns, then what could not be checked.
    order = [f["status"] for f in body["findings"]]
    assert order == sorted(order, key=lambda s: checkup.ORDER[s])
    for f in body["findings"]:
        assert {"id", "reason", "area", "status", "title", "evidence", "next"} <= set(f)
    # What is not fine carries its reason and recipe, and the answer the rules.
    assert by_id["folder"]["reason"] == "folder.not_integrated" and "**Who:** operator" in by_id["folder"]["recipe"]
    assert "Ask before you change anything" in body["rules"]


def test_through_mcp_the_call_itself_proves_mcp(client: TestClient) -> None:
    r = client.get("/api/checkup", headers={"x-sp-via": "mcp"})
    mcp = next(f for f in r.json()["findings"] if f["id"] == "mcp")
    assert mcp["status"] == "ok"


def test_this_chat_is_recorded_when_its_last_message_is_recent(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    from datetime import datetime
    from backend import sessions
    at = datetime(2026, 10, 20, 12, 0)
    monkeypatch.setattr(sessions, "chat_path", lambda store, aid: tmp_path / "chat.md" if aid == "cc-here0001" else None)
    monkeypatch.setattr(sessions, "parse_turns", lambda path: [sessions.Turn(number=1, at=at, line=1)])
    store = client.app.state.store
    assert checkup.this_chat(store, "cc-here0001", now=at.timestamp() + 60)["status"] == "ok"
    assert checkup.this_chat(store, "cc-here0001", now=at.timestamp() + checkup.CAPTURE_GRACE_S + 60)["status"] == "concern"
    assert checkup.this_chat(store, "cc-nobody00", now=time.time())["status"] == "concern"


def test_a_check_that_breaks_is_unknown_not_fine(client: TestClient, monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(checkup, "disk", boom)
    got = checkup.run(client.app.state.store, cwd="")
    broken = [f for f in got["findings"] if f["title"] == "A check failed to run"]
    assert broken and broken[0]["status"] == "unknown"


def test_a_guessed_chat_is_unknown_not_a_concern(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    """A chat found by a shared terminal or as the folder's newest is a guess:
    an old guessed chat said "this message was not recorded" when the caller
    was a script. Only the chat's own tool, or a caller naming it, is sure."""
    from datetime import datetime
    from backend import sessions
    monkeypatch.setattr(sessions, "chat_path", lambda store, aid: tmp_path / "chat.md")
    monkeypatch.setattr(sessions, "parse_turns", lambda path: [sessions.Turn(number=1, at=datetime(2026, 10, 18), line=1)])
    store, now = client.app.state.store, datetime(2026, 10, 20).timestamp()
    for source in ("shared-parent", "folder", ""):
        got = checkup.this_chat(store, "cc-other001", now, source)
        assert got["status"] == "unknown" and "cc-other001" in got["evidence"]
    sure = checkup.this_chat(store, "cc-other001", now, "process")
    assert sure["status"] == "concern" and sure["title"].startswith("No message recorded in this chat for")
    assert checkup.mcp(True, "folder")["title"] == "MCP answers this caller"
    assert checkup.mcp(True, "process")["title"] == "MCP answers from this chat"


def test_every_reason_a_check_can_give_has_a_recipe_that_says_who_acts() -> None:
    """checkup_fixes.md is the one source of recipes: a reason added to a
    check without its recipe fails here, and so does a recipe for a reason
    no check gives any more."""
    import re
    src = Path(checkup.__file__).read_text(encoding="utf-8")
    given = {m.replace(":", ".") for m in re.findall(r'"([a-z]+:[a-z_]+)"', src)}
    book = checkup.recipes()
    recipes = {k for k in book if not k.startswith("_")}
    assert given == recipes, (sorted(given - recipes), sorted(recipes - given))
    for reason in recipes:
        assert "**Applies:**" in book[reason] and "**Who:**" in book[reason], reason
    assert "Ask before you change anything" in book["_rules"]


def test_the_commands_and_files_a_recipe_names_exist() -> None:
    import re
    repo = Path(checkup.__file__).resolve().parents[2]
    text = checkup.FIXES.read_text(encoding="utf-8")
    sp = (repo / "sp.py").read_text(encoding="utf-8")
    for cmd in set(re.findall(r"python sp\.py ([a-z]+)", text)):
        assert f'"{cmd}": cmd_' in sp, f"sp.py has no {cmd}"
    assert (repo / "docs" / "performance.md").is_file()


def test_a_recipe_is_served_by_its_reason(client: TestClient) -> None:
    r = client.get("/api/checkup/fix/hooks.script_missing")
    assert r.status_code == 200 and "Re-integrate" in r.json()["recipe"] and r.json()["rules"]
    assert client.get("/api/checkup/fix/nope.nothing").status_code == 404


def test_the_hook_checked_is_the_one_of_this_chats_tool(monkeypatch, tmp_path: Path) -> None:
    """A folder wired for Claude Code only is not fine for a Codex chat."""
    from backend import folderstate
    monkeypatch.setattr(folderstate, "integration_status", lambda p: "fresh")
    monkeypatch.setattr(folderstate, "missing_hook_scripts", lambda p: [])
    monkeypatch.setattr(folderstate, "tools_wired", lambda p: {"claude": True, "codex": False, "opencode": False, "cursor": False})
    hooks = lambda aid: next(f for f in checkup.integration("alpha", str(tmp_path), aid) if f["id"] == "hooks")  # noqa: E731
    assert hooks("cc-1234abcd")["status"] == "ok"
    codex = hooks("codex-1234abcd")
    assert codex["status"] == "concern" and codex["reason"] == "hooks.not_installed" and "codex" in codex["title"]


def test_the_report_cuts_query_strings_and_long_lines(tmp_path: Path) -> None:
    from backend import diagnostics
    assert "secret-words" not in diagnostics._clean("GET /api/search?q=secret-words → 200")
    assert len(diagnostics._clean("x" * 5000)) <= diagnostics.LINE_MAX + 2
    capped = diagnostics._cap(["y" * 1000] * 100, limit=5000)
    assert len(capped) < 10 and capped[-1].startswith("… cut")


def test_an_mcp_call_that_does_not_say_how_it_found_the_chat_is_a_guess(client: TestClient) -> None:
    """An MCP server from before the identity source was sent: its chat is
    not known for sure, and neither is MCP for this chat."""
    by = {f["id"]: f for f in client.get("/api/checkup", params={"agent_id": "cc-old00001"},
                                          headers={"x-sp-via": "mcp"}).json()["findings"]}
    assert by["chat"]["status"] == "unknown" and by["mcp"]["title"] == "MCP answers this caller"
