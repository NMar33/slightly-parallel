"""#entrypoint makes nothing until the operator chooses the topic
(entrypointask.py): the agent asks with a proposed name, the server finds
the candidates of the chat's project (from the message, from this chat's
work, from the tasks named in it) and holds the numbered line; the
operator's next message, read by the server, chooses. Every refusal writes
nothing; a retry makes nothing twice."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import entrypointask as A
from backend import entrypointlib as E
from backend import keeplib
from backend.server import create_app
from backend.sessions import Turn, _keeps_of
from tests.conftest import choose_new_topic, make_chat

ME = "cc-epask001"       # the chat the operator types the command in
OLD = "cc-epask002"      # the chat that kept the existing topics
BETA = "cc-epask003"     # a chat of another project
HELPER = "cc-epask004"   # a helper chat (a claude -p another chat started)
OTHER = "cc-epask005"    # another chat of ALPHA
THIRD = "cc-epask006"    # a third chat of ALPHA
CMD = "2026-09-10T10:00:00"


def _hook():
    path = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture.py"
    spec = importlib.util.spec_from_file_location("capture_hook_epask", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["capture_hook_epask"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _snapshot(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(".lock") and "projects" not in p.parts:
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture()
def app(data_root: Path):
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        c.headers["X-SP-Via"] = "mcp"
        from tests.conftest import _mark_only_agent_writes
        c.event_hooks["request"].append(_mark_only_agent_writes)
        yield c, data_root


def _store(c: TestClient):
    return c.app.state.store  # type: ignore[attr-defined]


def _topic(c: TestClient, root: Path, project: str, turn_at: str, text: str, name: str = "", agent: str = OLD,
           stop: str = "") -> str:
    """An existing topic of ``project``, kept in ``agent``'s chat; named
    unless ``name`` is "-" (then unnamed); with one stop when given."""
    turns = [(turn_at, f"#entrypoint {text}", "noted")]
    eid = choose_new_topic(_store(c), root, project, agent, turns, name=name if name != "-" else "x")
    if name == "-":
        E._rewrite_entry(_store(c), eid, {"topic": ""})
    if stop:
        r = c.post(f"/api/entrypoints/{eid}/stops", json={"actor": "operator", "text": stop})
        assert r.status_code == 201, r.text
    _store(c).rebuild()
    return eid


def _say(c: TestClient, root: Path, agent: str, turns: list[tuple[str, str]], project: str = "ALPHA") -> None:
    make_chat(root, project, agent, [(at, user, "ok") for at, user in turns])
    _store(c).rebuild()


def _ask(c: TestClient, agent: str, turn: int, name: str = "Text console", project: str = "ALPHA"):
    kid = keeplib.keep_id("entrypoint", project, agent, turn)
    return kid, c.post("/api/entrypoints/ask", json={"agent_id": agent, "id": kid, "name": name})


def _answer(c: TestClient, agent: str, number, name: str = ""):
    body = {"agent_id": agent, "number": number}
    if name:
        body["name"] = name
    return c.post("/api/entrypoints/answer", json=body)


@pytest.fixture()
def board(app):
    """ALPHA has three topics, BETA one whose words match the command."""
    c, root = app
    site = _topic(c, root, "ALPHA", "2026-09-01T10:00:00", "the site: deploy and the search texts", "Site and SEO",
                  stop="Deployed; the text console is half done.")
    films = _topic(c, root, "ALPHA", "2026-09-02T10:00:00", "the install film", "Install film", agent="cc-epask0f1")
    notes = _topic(c, root, "ALPHA", "2026-09-03T10:00:00", "release notes for the store", "-", agent="cc-epask0n1")
    beta = _topic(c, root, "BETA", "2026-09-04T10:00:00", "the site deploy and the search texts", "Site", agent=BETA)
    return c, root, {"site": site, "films": films, "notes": notes, "beta": beta}


# ---------------------------------------------------------------------------


def test_nothing_is_made_before_the_answer(board) -> None:
    c, root, ids = board
    _say(c, root, ME, [(CMD, "#entrypoint the site deploy and the search texts")])
    before = {t["id"] for t in c.get("/api/entrypoints/desk?project=ALPHA").json()["topics"]}
    kid, r = _ask(c, ME, 1)
    assert r.status_code == 200, r.text
    asked = r.json()
    assert asked["asked"] is True and asked["command"] == kid
    after = {t["id"] for t in c.get("/api/entrypoints/desk?project=ALPHA").json()["topics"]}
    assert after == before and kid not in after
    assert E.command_of(_store(c), kid)["how"] == "pending"  # type: ignore[index]
    seen = c.get(f"/api/entrypoints/{kid}/command").json()
    assert seen["opened"] == "pending" and "entrypoint_ask" in seen["next"]
    # The record cannot be written for a command with no topic.
    snap = _snapshot(root)
    r = c.post(f"/api/entrypoints/{kid}/interpretation", json={"agent_id": ME, "text": "## What\nx"})
    assert r.status_code == 409 and "has not chosen" in r.json()["detail"]
    assert _snapshot(root) == snap


def test_the_candidates_come_from_the_text_and_another_project_is_never_offered(board) -> None:
    c, root, ids = board
    _say(c, root, ME, [(CMD, "#entrypoint the site deploy and the search texts")])
    _kid, r = _ask(c, ME, 1)
    lines = r.json()["lines"]
    assert lines[0]["id"] == ids["site"] and lines[0]["why"] == "text"
    assert ids["beta"] not in [x.get("id") for x in lines]
    assert lines[-1] == {"n": len(lines), "kind": "new", "name": "Text console"}
    show = r.json()["show"]
    assert show.startswith("Is this one of the topics? 1) Site and SEO — last stop ")
    assert ": Deployed; the text console is half done." in show and show.endswith("A new topic: «Text console»")
    assert "Show the operator this line as it is" in r.json()["next"]


def test_the_candidates_come_from_the_chats_tasks(board) -> None:
    c, root, ids = board
    r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:05", "project": "ALPHA",
                                  "agent_id": "operator", "title": "Voice the film", "status": "todo"})
    tid = r.json()["metadata"]["id"]
    assert c.post(f"/api/tasks/{tid}/topic", json={"actor": "operator", "entrypoint_id": ids["films"]}).status_code == 200
    _say(c, root, ME, [("2026-09-10T09:00:00", f"work on {tid}"), (CMD, "#entrypoint")])
    _kid, r = _ask(c, ME, 2, "Voice work")
    lines = r.json()["lines"]
    assert [(x.get("id"), x.get("why")) for x in lines] == [(ids["films"], "task"), (None, None)]


def test_the_candidates_come_from_the_chats_past_work(board) -> None:
    c, root, ids = board
    _say(c, root, ME, [("2026-09-10T09:00:00", "hello")])
    assert c.post(f"/api/entrypoints/{ids['notes']}/stops", json={"agent_id": ME, "text": "Drafted."}).status_code == 201
    _say(c, root, ME, [("2026-09-10T09:00:00", "hello"), (CMD, "#entrypoint")])
    _kid, r = _ask(c, ME, 2, "Store notes")
    lines = r.json()["lines"]
    assert [(x.get("id"), x.get("why")) for x in lines] == [(ids["notes"], "work"), (None, None)]
    # An unnamed topic shows its first line.
    assert r.json()["show"].startswith("Is this one of the topics? 1) release notes for the store — last stop ")


def test_at_most_three_candidates_one_from_each_source_in_turn(board) -> None:
    c, root, ids = board
    r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:05", "project": "ALPHA",
                                  "agent_id": "operator", "title": "Voice the film", "status": "todo"})
    tid = r.json()["metadata"]["id"]
    c.post(f"/api/tasks/{tid}/topic", json={"actor": "operator", "entrypoint_id": ids["films"]})
    _say(c, root, ME, [("2026-09-10T09:00:00", f"work on {tid}")])
    c.post(f"/api/entrypoints/{ids['notes']}/stops", json={"agent_id": ME, "text": "Drafted."})
    _say(c, root, ME, [("2026-09-10T09:00:00", f"work on {tid}"), (CMD, "#entrypoint the site deploy")])
    _kid, r = _ask(c, ME, 2)
    lines = r.json()["lines"]
    assert [(x.get("id"), x.get("why")) for x in lines] == [
        (ids["site"], "text"), (ids["notes"], "work"), (ids["films"], "task"), (None, None)]


def test_the_numbers_must_match_and_a_refusal_writes_nothing(board) -> None:
    c, root, ids = board
    _say(c, root, ME, [(CMD, "#entrypoint the site deploy and the search texts")])
    kid, r = _ask(c, ME, 1)
    assert r.json()["lines"][0]["id"] == ids["site"]
    _say(c, root, ME, [(CMD, "#entrypoint the site deploy and the search texts"), ("2026-09-10T10:01:00", "1")])
    snap = _snapshot(root)
    r = _answer(c, ME, 2)
    assert r.status_code == 409 and "chose 1" in r.json()["detail"]
    assert _answer(c, ME, 0).status_code == 409
    assert _snapshot(root) == snap
    got = _answer(c, ME, 1).json()
    assert got["opened"] == "version" and got["id"] == ids["site"] and got["writer"] == ME
    assert E.command_of(_store(c), kid)["how"] == "chosen"  # type: ignore[index]
    assert "Say in one line that «Site and SEO»" in got["next"] and "version 1" in got["next"]
    # This chat writes the record now; the chat that kept it does not.
    rec = "## What\nThe site.\n\n## State\nThe console works."
    assert c.post(f"/api/entrypoints/{kid}/interpretation", json={"agent_id": ME, "text": rec}).status_code == 200
    assert c.post(f"/api/entrypoints/{ids['site']}/interpretation",
                  json={"agent_id": OLD, "text": rec + "\nmore"}).status_code == 422


def test_a_number_with_a_name_makes_the_new_topic_with_that_name(board) -> None:
    c, root, ids = board
    turns = [(CMD, "#entrypoint the site deploy and the search texts")]
    _say(c, root, ME, turns)
    kid, r = _ask(c, ME, 1)
    n = len(r.json()["lines"])
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", f"{n} Консоль текстов")])
    got = _answer(c, ME, n).json()
    assert got["opened"] == "new" and got["id"] == kid and got["name"] == "Консоль текстов"
    row = E.entry_of(_store(c), kid)
    assert row is not None and row["topic"] == "Консоль текстов" and row["source_turn"] == "1"
    assert row["agent_id"] == ME and row["l1"] == "the site deploy and the search texts"
    assert "the new topic «Консоль текстов»" in got["next"]


def test_the_agents_name_must_be_in_the_operators_answer(board) -> None:
    c, root, _ids = board
    turns = [(CMD, "#entrypoint the site deploy and the search texts")]
    _say(c, root, ME, turns)
    _kid, r = _ask(c, ME, 1)
    n = len(r.json()["lines"])
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", f"{n}, call it Text console")])
    snap = _snapshot(root)
    r = _answer(c, ME, n, "Site texts")
    assert r.status_code == 409 and "is not in the operator's answer" in r.json()["detail"]
    assert _snapshot(root) == snap
    assert _answer(c, ME, n, "Text console").json()["name"] == "Text console"


def test_yes_with_one_line_makes_the_proposed_topic_in_an_empty_project(app) -> None:
    c, root = app
    turns = [(CMD, "#entrypoint")]
    _say(c, root, ME, turns)
    kid, r = _ask(c, ME, 1, "Text console")
    assert r.json()["show"] == "A new topic: «Text console»?" and len(r.json()["lines"]) == 1
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", "да")])
    got = _answer(c, ME, 1).json()
    assert got["opened"] == "new" and got["name"] == "Text console"
    row = E.entry_of(_store(c), kid)
    assert row is not None and row["l1"] == "Text console"     # the command alone: the name is its line


def test_a_name_alone_answers_the_one_line(app) -> None:
    c, root = app
    turns = [(CMD, "#entrypoint the console for the texts")]
    _say(c, root, ME, turns)
    _ask(c, ME, 1, "Text console")
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", "Консоль текстов")])
    assert _answer(c, ME, 1).json()["name"] == "Консоль текстов"


def test_an_unnamed_topic_chosen_takes_the_name_given_a_named_one_keeps_its_own(board) -> None:
    c, root, ids = board
    _say(c, root, ME, [("2026-09-10T09:00:00", "hello")])
    c.post(f"/api/entrypoints/{ids['notes']}/stops", json={"agent_id": ME, "text": "Drafted."})
    turns = [("2026-09-10T09:00:00", "hello"), (CMD, "#entrypoint")]
    _say(c, root, ME, turns)
    _ask(c, ME, 2, "Store notes")
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", "1 Store release notes")])
    got = _answer(c, ME, 1).json()
    assert got["id"] == ids["notes"] and got["name"] == "Store release notes"
    assert "now has this name" in got["next"]
    assert E.entry_of(_store(c), ids["notes"])["topic"] == "Store release notes"  # type: ignore[index]
    # A named topic keeps its name.
    turns2 = [(CMD, "#entrypoint the site deploy and the search texts")]
    _say(c, root, THIRD, turns2)
    _ask(c, THIRD, 1)
    _say(c, root, THIRD, [*turns2, ("2026-09-10T10:01:00", "1 Website")])
    got = _answer(c, THIRD, 1).json()
    assert got["id"] == ids["site"] and got["name"] == "Site and SEO" and "keeps its name" in got["next"]


@pytest.mark.parametrize("reply, state", [
    ("#task fix the console", "dropped"),
    ("which one is the console?", "question"),
    ("1 or 2", "unclear"),
    ("7", "unclear"),
    ("no", "dropped"),
])
def test_a_command_a_question_or_an_unclear_answer_chooses_nothing(board, reply: str, state: str) -> None:
    c, root, ids = board
    turns = [(CMD, "#entrypoint the site deploy and the search texts")]
    _say(c, root, ME, turns)
    kid, _r = _ask(c, ME, 1)
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", reply)])
    topics = {t["id"] for t in c.get("/api/entrypoints/desk?project=ALPHA").json()["topics"]}
    got = _answer(c, ME, 0).json()
    assert got["state"] == state and got["opened"] == "nothing" and got["chosen"] is None
    assert {t["id"] for t in c.get("/api/entrypoints/desk?project=ALPHA").json()["topics"]} == topics
    assert E.command_of(_store(c), kid)["how"] == ("dropped" if state == "dropped" else "pending")  # type: ignore[index]
    if state != "dropped":
        # Asked again, the next message answers.
        _kid, r = _ask(c, ME, 1)
        assert r.json()["rev"] == 2
        _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", reply), ("2026-09-10T10:02:00", "1")])
        assert _answer(c, ME, 1).json()["id"] == ids["site"]
    else:
        assert c.post("/api/entrypoints/ask", json={"agent_id": ME, "id": kid, "name": "x"}).json()["opened"] == "nothing"


def test_a_retry_makes_nothing_twice_and_asking_again_replaces_the_line(board) -> None:
    c, root, _ids = board
    turns = [(CMD, "#entrypoint the site deploy and the search texts")]
    _say(c, root, ME, turns)
    kid, r1 = _ask(c, ME, 1, "Old name")
    _kid, r2 = _ask(c, ME, 1, "Text console")              # before the answer: replaced
    assert r2.json()["rev"] == 2 and r2.json()["lines"][-1]["name"] == "Text console"
    assert len([r for r in A.rows(_store(c)) if r["id"] == kid]) == 1
    n = len(r2.json()["lines"])
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", str(n))])
    # Answered but not read yet: asking again is refused, so the answer is not skipped.
    r = _ask(c, ME, 1)[1]
    assert r.status_code == 409 and "call entrypoint_answer" in r.json()["detail"]
    first = _answer(c, ME, n).json()
    snap = _snapshot(root)
    again = _answer(c, ME, n).json()
    assert again["id"] == first["id"] == kid and again["existing"] is True and _snapshot(root) == snap
    assert [r["id"] for r in E.entries(_store(c), "ALPHA")].count(kid) == 1
    # The command adopted again (another read) makes nothing either.
    keeplib.adopt(_store(c))
    assert [r["id"] for r in E.entries(_store(c), "ALPHA")].count(kid) == 1
    assert c.post("/api/entrypoints/ask", json={"agent_id": ME, "id": kid, "name": "x"}).json()["opened"] == "new"


def test_a_topic_archived_after_the_question_is_not_chosen(board) -> None:
    c, root, ids = board
    turns = [(CMD, "#entrypoint the site deploy and the search texts")]
    _say(c, root, ME, turns)
    _ask(c, ME, 1)
    E._rewrite_entry(_store(c), ids["site"], {"archived_at": "2026-09-10T10:00:30"})
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", "1")])
    got = _answer(c, ME, 1).json()
    assert got["state"] == "unclear" and "archived" in got["next"]


def test_the_chat_that_chose_last_writes_even_when_its_command_was_older(board) -> None:
    c, root, ids = board
    early = [(CMD, "#entrypoint the site deploy and the search texts")]
    _say(c, root, ME, early)
    _ask(c, ME, 1)
    # Another chat chooses the same topic in between.
    late = [("2026-09-10T10:05:00", "#entrypoint the site deploy and the search texts")]
    _say(c, root, OTHER, late)
    _ask(c, OTHER, 1)
    _say(c, root, OTHER, [*late, ("2026-09-10T10:06:00", "1")])
    assert _answer(c, OTHER, 1).json()["writer"] == OTHER
    _say(c, root, ME, [*early, ("2026-09-10T10:10:00", "1")])
    assert _answer(c, ME, 1).json()["writer"] == ME


def test_a_helper_chat_makes_nothing(app) -> None:
    c, root = app
    make_chat(root, "ALPHA", HELPER, [(CMD, "You are a critic.\n#entrypoint the console", "ok")])
    meta = root / "projects" / "ALPHA" / "chats" / HELPER / "meta.json"
    meta.write_text(json.dumps({**json.loads(meta.read_text()), "helper": True, "helper_kind": "claude-p"}))
    _store(c).rebuild()
    keeplib.adopt(_store(c))
    kid, r = _ask(c, HELPER, 1)
    assert r.status_code in (404, 409)
    assert c.get("/api/entrypoints/desk?project=ALPHA").json()["topics"] == []
    assert E.command_of(_store(c), kid) is None
    # The hook keeps nothing from a helper's message either (test_helper_chats); its answer is refused too.
    assert _answer(c, HELPER, 1).status_code == 409


def test_another_chat_cannot_ask_or_answer_for_the_command(board) -> None:
    c, root, _ids = board
    _say(c, root, ME, [(CMD, "#entrypoint the site deploy")])
    kid = keeplib.keep_id("entrypoint", "ALPHA", ME, 1)
    r = c.post("/api/entrypoints/ask", json={"agent_id": OLD, "id": kid, "name": "x"})
    assert r.status_code == 409 and "another chat" in r.json()["detail"]


def test_the_exact_name_of_a_named_topic_skips_the_question_an_unnamed_or_twice_used_one_does_not(board) -> None:
    c, root, ids = board
    _say(c, root, ME, [(CMD, "#entrypoint Site and SEO: the console")])
    kid, r = _ask(c, ME, 1)
    got = r.json()
    assert got["asked"] is False and got["opened"] == "version" and got["id"] == ids["site"]
    assert "nothing was asked" in got["next"]
    # The unnamed topic's first line is not a name.
    _say(c, root, OTHER, [(CMD, "#entrypoint release notes for the store")])
    _kid, r = _ask(c, OTHER, 1)
    assert r.json()["asked"] is True
    # Two topics of one name: the operator chooses.
    E._rewrite_entry(_store(c), ids["films"], {"topic": "Site and SEO"})
    _say(c, root, THIRD, [(CMD, "#entrypoint Site and SEO")])
    _kid, r = _ask(c, THIRD, 1)
    assert r.json()["asked"] is True


def test_the_hook_and_the_server_keep_the_command_alone_the_same() -> None:
    hook = _hook()
    for text, kinds in [("#entrypoint", ["entrypoint"]), ("#entrypoint(Text console)", ["entrypoint"]),
                        ("#vision", []), ("#entrypoint #vision", ["entrypoint"]),
                        ("#entrypoint the console", ["entrypoint"])]:
        kept = hook._kept(text, "ALPHA", ME, 3)
        marks = _keeps_of("s1", "ALPHA", ME, [Turn(number=3, at=datetime(2026, 9, 10, 10), line=1, user_summary=text)])
        assert [k["kind"] for k in kept] == [m["kind"] for m in marks] == kinds, text
        assert [k["id"] for k in kept] == [keeplib.keep_id(m["kind"], "ALPHA", ME, 3) for m in marks]
    (mark,) = _keeps_of("s1", "ALPHA", ME, [Turn(number=3, at=datetime(2026, 9, 10, 10), line=1,
                                                   user_summary="#entrypoint(Text console)")])
    assert mark["title"] == "Text console" and mark["body"] == ""


@pytest.mark.parametrize("text, offered, kind, number, rest", [
    ("2", 3, "number", 2, ""),
    ("3 Консоль текстов", 3, "number", 3, "Консоль текстов"),
    ("да, 3 — Консоль текстов", 3, "number", 3, "Консоль текстов"),
    ("2 please", 3, "number", 2, ""),
    ("1 and 3", 3, "unclear", 0, ""),
    ("0", 3, "unclear", 0, ""),
    ("4", 3, "unclear", 0, ""),
    ("yes", 1, "yes", 0, ""),
    ("думаю да", 1, "yes", 0, ""),
    ("ок", 1, "yes", 0, ""),
    ("да", 1, "yes", 0, ""),
    ("I think so", 1, "yes", 0, ""),
    ("наверное да, давай", 1, "yes", 0, ""),
    ("ok sure", 1, "yes", 0, ""),
    ("нет", 2, "no", 0, ""),
    ("is 2 the console?", 3, "question", 0, ""),
    ("#done", 3, "command", 0, ""),
    ("2 ###now-todo the console", 3, "command", 0, ""),
    ("Text console v2", 1, "text", 0, "Text console v2"),
    ("on 2026-11-05 we did it", 3, "text", 0, "on 2026-11-05 we did it"),
])
def test_the_answer_is_read_from_the_operators_words(text, offered, kind, number, rest) -> None:
    got = A.read_choice(text, offered)
    assert (got["kind"], got["number"], got["rest"]) == (kind, number, rest)


def test_the_contract_says_the_steps() -> None:
    root = Path(__file__).resolve().parents[2]
    part = (root / "prompts" / "contract" / "56-entrypoint.md").read_text(encoding="utf-8")
    for words in ("entrypoint_ask", "entrypoint_answer", "nothing is made", "last stop"):
        assert words in part, words
    whole = (root / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")
    assert "entrypoint_ask {id, name}" in whole and "entrypoint_answer {number, name?}" in whole


@pytest.mark.parametrize("reply", [
    "да", "думаю да", "ага", "ок", "окей", "давай", "Да!", "yes", "yep", "yeah", "ok", "okay", "OK", "sure", "go",
    "I think so", "sounds good", "yes please", "+", "👍", "да, sure", "ok, давай", "думаю yes"])
def test_a_yes_word_answer_keeps_the_offered_name(app, reply: str) -> None:
    """The operator's first use: one line, «думаю да», and the topic was named «думаю да»."""
    c, root = app
    turns = [(CMD, "#entrypoint лента проверки для агентов")]
    _say(c, root, ME, turns)
    kid, r = _ask(c, ME, 1, "Лента проверки для агентов")
    assert r.json()["show"] == "A new topic: «Лента проверки для агентов»?"
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", reply)])
    got = _answer(c, ME, 1).json()
    assert got["name"] == "Лента проверки для агентов"
    assert E.entry_of(_store(c), kid)["topic"] == "Лента проверки для агентов"  # type: ignore[index]


def test_the_answer_names_the_steps_after_the_record(board) -> None:
    c, root, ids = board
    r = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:05", "project": "ALPHA",
                                  "agent_id": "operator", "title": "The review feed", "status": "doing"})
    tid = r.json()["metadata"]["id"]
    turns = [("2026-09-10T09:00:00", f"work on {tid}"), (CMD, "#entrypoint the review feed")]
    _say(c, root, ME, turns)
    _kid, r = _ask(c, ME, 2, "Review feed")
    n = len(r.json()["lines"])
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", str(n))])
    nxt = _answer(c, ME, n).json()["next"]
    steps = [nxt.index(x) for x in ("interpret {", "(1) each way in", "entrypoint_way", "(2) one message",
                                    "entrypoint_stop", "(3) for each way in that is up", "entrypoint_shot",
                                    "(4) the topic of", "task_topic")]
    assert steps == sorted(steps)
    assert tid in nxt and "/ports" in nxt
    # The exact-name path names them too.
    _say(c, root, OTHER, [(CMD, "#entrypoint Site and SEO")])
    got = _ask(c, OTHER, 1)[1].json()
    assert got["asked"] is False and "(3) for each way in that is up" in got["next"]


def test_the_hook_notice_and_the_contract_name_the_steps_after_the_record() -> None:
    hook = _hook()
    note = hook.format_signals({"kept": hook._kept("#entrypoint", "ALPHA", ME, 2)})
    for tool in ("entrypoint_way", "entrypoint_stop", "entrypoint_shot", "task_topic"):
        assert tool in note.splitlines()[0], tool
    part = (Path(__file__).resolve().parents[2] / "prompts" / "contract" / "56-entrypoint.md").read_text(encoding="utf-8")
    order = [part.index(x) for x in ("1. each way in", "2. one message", "3. a screenshot", "4. the topic of")]
    assert order == sorted(order)


@pytest.mark.parametrize("text, kind, rest", [
    ("yes, call it Review feed", "yes", "Review feed"),
    ("да, назови Лента проверки", "yes", "Лента проверки"),
    ("ok — Review feed", "yes", "Review feed"),
    ("1, call it Консоль текстов", "number", "Консоль текстов"),
    ("1 Консоль текстов", "number", "Консоль текстов"),
    ("нет", "no", ""),
    ("no", "no", ""),
    ("nope, no", "no", ""),
    ("not this one", "unclear", ""),
    ("нет, не эту", "unclear", ""),
    ("not 1", "unclear", ""),
    ("а что это?", "question", ""),
    ("what is it?", "question", ""),
    ("wait", "text", "wait"),
])
def test_agreement_names_and_no_in_both_languages(text: str, kind: str, rest: str) -> None:
    got = A.read_choice(text, 1)
    assert (got["kind"], got["rest"]) == (kind, rest)


@pytest.mark.parametrize("reply, name", [
    ("yes, call it Review feed", "Review feed"),
    ("да, назови Лента проверки", "Лента проверки"),
])
def test_a_yes_with_a_name_takes_that_name(app, reply: str, name: str) -> None:
    c, root = app
    turns = [(CMD, "#entrypoint лента проверки для агентов")]
    _say(c, root, ME, turns)
    _ask(c, ME, 1, "Лента проверки для агентов")
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", reply)])
    assert _answer(c, ME, 1).json()["name"] == name


@pytest.mark.parametrize("reply, state", [
    ("нет", "dropped"), ("no", "dropped"), ("not this one", "unclear"), ("что это значит?", "question"),
    ("what does it hold?", "question"),
])
def test_a_negative_or_a_question_is_no_choice_and_never_a_name(app, reply: str, state: str) -> None:
    c, root = app
    turns = [(CMD, "#entrypoint лента проверки для агентов")]
    _say(c, root, ME, turns)
    kid, _r = _ask(c, ME, 1, "Лента проверки для агентов")
    _say(c, root, ME, [*turns, ("2026-09-10T10:01:00", reply)])
    if state != "question":
        assert _answer(c, ME, 1).status_code == 409         # the agent cannot turn it into a choice
    got = _answer(c, ME, 0 if state != "question" else 1).json()
    assert got["state"] == state and got["opened"] == "nothing"
    assert E.entry_of(_store(c), kid) is None
