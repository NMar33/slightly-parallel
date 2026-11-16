"""#entrypoint typed again in another chat of the project for a topic that
exists: no second entry point, a new version of that topic's record written
by that chat's agent (entrypointlib: the command, the gate, the chat of each
version). The topic is the one the operator chooses (entrypointask.py,
tests/test_entrypoint_ask.py); only the exact name of a named topic skips
the question. Without the command an agent is refused, a topic of another
project is refused, and the other kept lenses keep their rule. Every
refusal writes nothing."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import entrypointask as A
from backend import entrypointlib as E
from backend import keeplib
from backend.server import create_app
from tests.conftest import choose_new_topic, make_chat

FIRST = "cc-epv00001"    # the chat the operator kept the topic in
SECOND = "cc-epv00002"   # a later chat of ALPHA where the operator types it again
THIRD = "cc-epv00003"    # a chat of ALPHA with no command
BETA = "cc-epv00004"     # a chat of another project
RECORD = (
    "## What\nThe install film.\n\n## Where\n- brand/films/install.mp4\n\n## How\n`npm run dev`\n\n"
    "## State\nVoiced.\n\n## Next\n- upload\n"
)
SECOND_RECORD = RECORD.replace("- brand/films/install.mp4", "- brand/films/install.mp4\n- brand/films/upload.md").replace(
    "Voiced.", "Uploaded; the description waits for the operator.")


def _hook():
    path = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture.py"
    spec = importlib.util.spec_from_file_location("capture_hook_epv", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["capture_hook_epv"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _snapshot(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(".lock") and "projects" not in p.parts:
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _say(c: TestClient, root: Path, project: str, agent: str, turns: list[tuple[str, str, str]]) -> None:
    make_chat(root, project, agent, turns)
    c.app.state.store.rebuild()  # type: ignore[attr-defined]
    keeplib.adopt(c.app.state.store)  # type: ignore[attr-defined]


def _topics(c: TestClient, project: str = "ALPHA") -> list[dict]:
    return c.get(f"/api/entrypoints/desk?project={project}").json()["topics"]


def _write(c: TestClient, item_id: str, agent: str, text: str):
    return c.post(f"/api/entrypoints/{item_id}/interpretation", json={"agent_id": agent, "text": text})


@pytest.fixture()
def world(data_root: Path):
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as c:
        c.headers["X-SP-Via"] = "mcp"
        from tests.conftest import _mark_only_agent_writes
        c.event_hooks["request"].append(_mark_only_agent_writes)
        eid = choose_new_topic(app.state.store, data_root, "ALPHA", FIRST, [
            ("2026-09-01T10:00:00", "one", "a1"),
            ("2026-09-01T10:01:00", "#entrypoint the install film: the video work and its page", "noted"),
        ], name="Install film")
        assert _write(c, eid, FIRST, RECORD).status_code == 200
        yield c, data_root, eid


def _answer(c: TestClient, root: Path, project: str, agent: str, turns: list[tuple[str, str, str]],
            reply: str, number: int, name: str = "a new topic") -> dict:
    """The command (the last turn), the question, the operator's reply."""
    _say(c, root, project, agent, turns)
    kid = keeplib.keep_id("entrypoint", project, agent, len(turns))
    asked = c.post("/api/entrypoints/ask", json={"agent_id": agent, "id": kid, "name": name})
    assert asked.status_code == 200, asked.text
    _say(c, root, project, agent, [*turns, ("2026-09-30T23:59:00", reply, "ok")])
    got = c.post("/api/entrypoints/answer", json={"agent_id": agent, "number": number})
    assert got.status_code == 200, got.text
    return {"asked": asked.json(), **got.json()}


def test_the_names_are_compared_exactly_never_by_likeness() -> None:
    assert E.same_name("The Install Film", "the install film")
    assert E.same_name("INSTALL film!", "install film")
    assert E.same_name("Install film: put the video work in", "Install film")
    assert E.same_name("install film — the new cut", "Install film")
    assert E.same_name("Тексты сайта", "тексты  сайта")
    assert not E.same_name("the install film", "install film")      # one word more is a question
    assert not E.same_name("Site's texts!", "site texts")
    assert not E.same_name("launch films", "films launch")
    assert not E.same_name("", "")


def test_the_exact_name_in_another_chat_versions_the_topic_at_once_and_that_chat_writes_it(world) -> None:
    c, root, eid = world
    _say(c, root, "ALPHA", SECOND, [
        ("2026-09-05T09:00:00", "hello", "hi"),
        ("2026-09-05T09:10:00", "#entrypoint Install film", "noted"),
    ])
    # No second entry point, no question.
    assert [t["id"] for t in _topics(c)] == [eid]
    # The id the hook names for this message is the command; the server reads it as the topic.
    kid = _hook().keep_id("entrypoint", "ALPHA", SECOND, 2)
    assert kid != eid and keeplib.keep_id("entrypoint", "ALPHA", SECOND, 2) == kid
    asked = c.post("/api/entrypoints/ask", json={"agent_id": SECOND, "id": kid, "name": "Install film"}).json()
    assert asked["asked"] is False and asked["id"] == eid and asked["opened"] == "version"
    assert "nothing was asked" in asked["next"] and "«Install film»" in asked["next"]
    assert [r["id"] for r in A.rows(c.app.state.store)] == [eid]  # type: ignore[attr-defined]  # the first chat's only
    seen = c.get(f"/api/entrypoints/{kid}/command").json()
    assert seen["id"] == eid and seen["opened"] == "version" and seen["writer"] == SECOND
    assert seen["record"].startswith("## What") and "version 2" in seen["next"] and "Where and How" in seen["next"]
    # The topic's own id answers its last command, the same.
    by_topic = c.get(f"/api/entrypoints/{eid}/command").json()
    assert (by_topic["command"], by_topic["opened"], by_topic["writer"]) == (kid, "version", SECOND)
    # This chat's agent writes the version, by the hook's id or the topic's.
    r = _write(c, kid, SECOND, SECOND_RECORD)
    assert r.status_code == 200, r.text
    assert r.json()["metadata"]["id"] == eid and r.json()["metadata"]["versions_n"] == 2
    # The chat that kept it no longer writes the record: the last command was elsewhere.
    before = _snapshot(root)
    r = _write(c, eid, FIRST, RECORD + "\nmore")
    assert r.status_code == 422 and SECOND in r.json()["detail"] and "#entrypoint" in r.json()["detail"]
    assert _snapshot(root) == before
    # The second command's turn is one of the topic's turns.
    chats = E.context(c.app.state.store, eid)["chats"]  # type: ignore[attr-defined]
    assert SECOND in [ch["id"] for ch in chats]


def test_each_version_carries_the_chat_that_wrote_it(world) -> None:
    c, root, eid = world
    _say(c, root, "ALPHA", SECOND, [("2026-09-05T09:10:00", "#entrypoint install film", "noted")])
    assert _write(c, eid, SECOND, SECOND_RECORD).status_code == 200
    assert c.post(f"/api/entrypoints/{eid}/interpretation", json={"actor": "operator", "text": SECOND_RECORD + "\nfixed"}).status_code == 200
    kept = c.get(f"/api/entrypoints/{eid}").json()["kept"]
    assert [(v["n"], v["how"], v["by"]) for v in kept["versions"]] == [
        (1, "interpreted", FIRST), (2, "interpreted", SECOND), (3, "edited", "operator")]
    assert kept["versions"][1]["command"] == keeplib.keep_id("entrypoint", "ALPHA", SECOND, 1)
    assert kept["current"]["by"] == "operator"


def test_without_the_command_an_agent_of_the_project_is_refused_and_writes_nothing(world) -> None:
    c, root, eid = world
    _say(c, root, "ALPHA", THIRD, [("2026-09-06T09:00:00", "how is the install film going", "fine")])
    before = _snapshot(root)
    r = _write(c, eid, THIRD, SECOND_RECORD)
    assert r.status_code == 422 and "entrypoint_stop" in r.json()["detail"]
    assert _snapshot(root) == before
    # A stop and a way in stay open to any chat of the project.
    assert c.post(f"/api/entrypoints/{eid}/stops", json={"agent_id": THIRD, "text": "Voiced."}).status_code == 201


def test_another_projects_topic_is_never_offered_and_is_refused_and_nothing_is_written(world) -> None:
    c, root, eid = world
    got = _answer(c, root, "BETA", BETA, [("2026-09-06T09:00:00", "#entrypoint install film", "noted")],
                  "yes", 1, name="Install film")
    # The same name in another project is a question of that project: ALPHA's topic is not on it.
    assert [x["kind"] for x in got["asked"]["lines"]] == ["new"]
    beta = _topics(c, "BETA")
    assert [t["id"] for t in beta] == [got["id"]] and got["id"] != eid and [t["id"] for t in _topics(c)] == [eid]
    before = _snapshot(root)
    r = _write(c, eid, BETA, SECOND_RECORD)
    assert r.status_code == 422 and "ALPHA" in r.json()["detail"] and "BETA" in r.json()["detail"]
    assert _snapshot(root) == before
    assert c.get(f"/api/entrypoints/{eid}").json()["metadata"]["versions_n"] == 1


def test_a_different_name_asks_and_the_new_line_makes_a_new_entry_point(world) -> None:
    c, root, eid = world
    got = _answer(c, root, "ALPHA", SECOND, [("2026-09-05T09:10:00", "#entrypoint the release notes", "noted")],
                  "1", 1, name="Release notes")
    assert got["asked"]["show"] == "Start the topic «Release notes»? Answer «yes» or give your own name."
    topics = _topics(c)
    assert len(topics) == 2
    new = next(t for t in topics if t["id"] != eid)
    assert new["id"] == keeplib.keep_id("entrypoint", "ALPHA", SECOND, 1) == got["id"]
    assert new["name"] == "Release notes"
    seen = c.get(f"/api/entrypoints/{new['id']}/command").json()
    assert seen["opened"] == "new" and seen["writer"] == SECOND
    assert _write(c, new["id"], SECOND, RECORD).status_code == 200
    # The first topic is the first chat's still.
    assert _write(c, eid, SECOND, RECORD).status_code == 422


def test_a_name_only_like_a_topic_offers_it_and_choosing_it_opens_a_version(world) -> None:
    c, root, eid = world
    got = _answer(c, root, "ALPHA", SECOND, [("2026-09-05T09:10:00", "#entrypoint the install film page", "noted")],
                  "1", 1)
    lines = got["asked"]["lines"]
    assert [(x["kind"], x.get("id"), x.get("why")) for x in lines] == [("topic", eid, "text"), ("new", None, None)]
    show = got["asked"]["show"]
    assert show.startswith("Where should this entry point go?\n\n1) Install film · active\n")
    assert "Where it stopped: no messages yet" in show and "\n\n2) New topic «" in show
    assert got["opened"] == "version" and got["id"] == eid and got["writer"] == SECOND
    assert [t["id"] for t in _topics(c)] == [eid]                 # nothing else was made
    assert _write(c, eid, SECOND, SECOND_RECORD).status_code == 200


def test_an_old_topic_without_commands_is_written_by_the_chat_that_kept_it(data_root: Path) -> None:
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        eid = choose_new_topic(c.app.state.store, data_root, "ALPHA", FIRST,  # type: ignore[attr-defined]
                               [("2026-09-01T10:01:00", "#entrypoint the install film", "noted")])
        # As before the commands were written down: the ledger is not there.
        (data_root / E.COMMANDS_FILE).unlink()
        assert _write(c, eid, FIRST, RECORD).status_code == 200
        assert _write(c, eid, SECOND, RECORD).status_code == 422


def test_other_kept_lenses_keep_their_rule(data_root: Path) -> None:
    """A #vision typed twice is two visions, and any chat writes an interpretation as before."""
    make_chat(data_root, "ALPHA", FIRST, [("2026-09-01T10:01:00", "#vision the install film", "noted")])
    make_chat(data_root, "ALPHA", SECOND, [("2026-09-02T10:01:00", "#vision the install film", "noted")])
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        rows = c.get("/api/visions?project=ALPHA").json()
        visions = rows.get("visions") or rows.get("items") or []
        assert len(visions) == 2
        vid = keeplib.keep_id("vision", "ALPHA", FIRST, 1)
        r = c.post(f"/api/visions/{vid}/interpretation", json={"agent_id": SECOND, "text": "A film."})
        assert r.status_code == 200, r.text
        assert "by" not in r.json()["kept"]["versions"][0]
        assert not (data_root / E.COMMANDS_FILE).exists() and not (data_root / E.AUTHORS_FILE).exists()


def test_the_hook_sends_the_agent_to_ask_first() -> None:
    hook = _hook()
    kept = hook._kept("#entrypoint install film", "ALPHA", SECOND, 2)
    note = hook.format_signals({"kept": kept})
    first = note.splitlines()[0]
    assert first.startswith("[slightly-parallel] #entrypoint — the server keeps this command as ")
    assert f'entrypoint_ask {{id: "{kept[0]["id"]}", name:' in first and "nothing is made" in first
    assert "entrypoint_answer {number, name?}" in first and 'interpret {lens: "entrypoint"' in first
    assert 'select:mcp__slightly-parallel__entrypoint_ask"' in note
