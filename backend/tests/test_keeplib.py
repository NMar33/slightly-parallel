"""Kept messages: #vision, #rule and #problem, from the chat log into their ledgers.

The message is the record and the chat log is its source, so what is tested
is the tag, the adoption, the id the hook hands out before the server has
seen anything, and the interpretation's versions.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from backend import keeplib
from backend.db import ViewStore
from backend.docs_md import read_detail
from backend.sessions import KEEP_TAG_RE, keep_body
from tests.conftest import make_chat

AGENT = "alpha-lead-2608-01"
_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _hook():
    spec = importlib.util.spec_from_file_location("sp_capture_keep", _HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_keep"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# The tag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,kind,named", [
    ("we should stay local-first #vision", "vision", None),
    ("#rule(no installs) never install packages", "rule", "no installs"),
    ("#problem the build is red", "problem", None),
    ("#skill cut a release", "skill", None),
    ("#VISION in capitals", "vision", None),
])
def test_the_tag_is_found_and_names_the_entry(text, kind, named):
    m = KEEP_TAG_RE.search(text)
    assert m is not None and m.group(1).lower() == kind and m.group(2) == named


@pytest.mark.parametrize("text", [
    "#problem solved pb_1234abcd", "open the #visions page", "see ##rule",
    "https://x.dev/a#rule-1", "#rules apply", "nothing here",
])
def test_the_tag_does_not_fire_on_a_command_or_a_longer_word(text):
    assert KEEP_TAG_RE.search(text) is None


def test_the_message_loses_its_tags_and_nothing_else():
    assert keep_body("#vision #prompt  Stay local-first.\n\nNo cloud.") == "Stay local-first.\n\nNo cloud."


# ---------------------------------------------------------------------------
# Adoption, interpretation, record
# ---------------------------------------------------------------------------


@pytest.fixture()
def kept(data_root: Path) -> ViewStore:
    make_chat(data_root, "ALPHA", AGENT, [
        ("2026-09-01T10:00:00", "one", "a1"),
        ("2026-09-01T10:01:00", "two", "a2"),
        ("2026-09-01T10:02:00", "three", "a3"),
        ("2026-09-01T10:03:00", "four", "a4"),
        ("2026-09-01T10:04:00", "#vision(local first) Everything runs on the laptop.", "noted"),
        ("2026-09-01T10:05:00", "#rule Never install packages without asking.", "ok"),
        ("2026-09-01T10:06:00", "#problem The build is red on main. #vision", "looking"),
        ("2026-09-01T10:07:00", "#problem solved pb_x", "closed"),
        ("2026-09-01T10:08:00", "eight", "a8"),
        ("2026-09-01T10:09:00", "#rule", "a tag alone keeps nothing"),
    ])
    store = ViewStore(data_root=data_root)
    store.rebuild()
    return store


def test_each_tagged_turn_joins_its_ledger(kept):
    assert len(keeplib.adopt(kept)) == 4

    visions = kept.query(
        "SELECT * FROM visions_mutual WHERE source = 'captured' ORDER BY source_turn")
    assert [(v["l1"], v["source_turn"]) for v in visions] == [
        ("local first", 5), ("The build is red on main.", 7)]
    rule = kept.query_one("SELECT * FROM rules_mutual WHERE source = 'captured'")
    assert rule["status"] == "active" and rule["source_turn"] == 6 and rule["versions_n"] == 0
    problem = kept.query_one("SELECT * FROM problems_mutual WHERE source = 'captured'")
    assert problem["status"] == "open" and problem["l1"] == "The build is red on main."

    _l2, _l3, l4 = read_detail(kept.data_root, rule["md_ref"])
    assert l4 == "Never install packages without asking."


def test_harvesting_twice_adopts_nothing_new(kept):
    assert len(keeplib.adopt(kept)) == 4
    assert keeplib.adopt(kept) == []


def test_the_hook_hands_out_the_id_the_server_mints(kept):
    keeplib.adopt(kept)
    rule = kept.query_one("SELECT id FROM rules_mutual WHERE source = 'captured'")
    assert _hook().keep_id("rule", "ALPHA", AGENT, 6) == rule["id"]


def test_the_hook_tells_the_agent_where_to_write(tmp_path):
    capture = _hook()
    cap = capture.TurnCapture(tmp_path / "data", "alpha", "cc-abc12345")
    signals = cap.open_turn("#vision Everything local. #problem solved pb_1")
    vid = capture.keep_id("vision", "alpha", "cc-abc12345", 1)
    assert signals["kept"] == [{"kind": "vision", "id": vid, "route": "visions"}]
    notice = capture.format_signals(signals)
    assert f'MCP tool interpret {{lens: "vision", id: "{vid}", text}}' in notice

    cap.complete_turn("ok")
    assert cap.open_turn("#rule")["kept"] == []
    cap.complete_turn("ok")
    assert cap.open_turn("no tag")["kept"] == []


def test_the_interpretation_is_versioned_and_becomes_l2(kept):
    keeplib.adopt(kept)
    sql = "SELECT * FROM visions_mutual WHERE source_turn = 5"
    keeplib.interpret(kept, "vision", kept.query_one(sql),
                      "Slightly Parallel stays on one laptop.", by_agent=True)
    keeplib.interpret(kept, "vision", kept.query_one(sql),
                      "Slightly Parallel stays on one laptop.", by_agent=False)
    keeplib.interpret(kept, "vision", kept.query_one(sql),
                      "One laptop, no server.", "shorter", by_agent=False)

    row = kept.query_one(sql)
    versions = keeplib.read_versions(kept, row["id"])
    assert [(v.n, v.how, v.note) for v in versions] == [
        (1, "interpreted", ""), (2, "edited", "shorter")]
    assert row["versions_n"] == 2
    l2, _l3, l4 = read_detail(kept.data_root, row["md_ref"])
    assert l2 == "One laptop, no server." and l4 == "Everything runs on the laptop."
    with pytest.raises(ValueError):
        keeplib.interpret(kept, "vision", row, "   ", by_agent=True)


def test_the_record_carries_three_turns_either_side(kept):
    keeplib.adopt(kept)
    row = kept.query_one("SELECT * FROM visions_mutual WHERE source_turn = 5")
    rec = keeplib.record(kept, "vision", row)
    assert [t["n"] for t in rec["before"]] == [2, 3, 4]
    assert [t["n"] for t in rec["after"]] == [6, 7, 8]
    assert rec["turn"]["user"].startswith("#vision(local first)")
    assert rec["message"] == "Everything runs on the laptop."
    assert rec["versions"] == [] and rec["current"] is None


# ---------------------------------------------------------------------------
# Over the API
# ---------------------------------------------------------------------------


def test_an_agent_interprets_before_any_list_read_and_reads_the_rule_back(client):
    root = Path(client.app.state.store.data_root)
    make_chat(root, "ALPHA", AGENT, [
        ("2026-09-01T10:00:00", "#rule Never deploy on your own.", "ok"),
    ])
    client.app.state.store.rebuild()
    rid = keeplib.keep_id("rule", "ALPHA", AGENT, 1)

    r = client.post(f"/api/rules/{rid}/interpretation", json={
        "agent_id": "cc-abc12345", "text": "Deploy only when the operator says so."})
    assert r.status_code == 200, r.text
    assert r.json()["kept"]["current"]["how"] == "interpreted"

    rules = client.get("/api/rules", params={"project": "ALPHA", "status": "active"}).json()["rules"]
    assert [x["id"] for x in rules if x["source"] == "captured"] == [rid]
    detail = client.get(f"/api/rules/{rid}").json()
    assert detail["l2"] == "Deploy only when the operator says so."
    assert detail["kept"]["message"] == "Never deploy on your own."

    edited = client.post(f"/api/rules/{rid}/interpretation", json={
        "actor": "operator", "text": "Never deploy."}).json()
    assert [v["how"] for v in edited["kept"]["versions"]] == ["interpreted", "edited"]
    assert client.post(f"/api/rules/{rid}/interpretation",
                       json={"agent_id": "cc-abc12345", "text": ""}).status_code == 422
    assert client.post("/api/rules/rl_00000000/interpretation",
                       json={"text": "x"}).status_code == 404


def test_tags_group_visions_and_filter_by_whole_tag(client):
    root = Path(client.app.state.store.data_root)
    make_chat(root, "ALPHA", AGENT, [
        ("2026-09-01T10:00:00", "#vision Keep the board calm.", "ok"),
        ("2026-09-01T10:05:00", "#vision Split the API by reader.", "ok"),
    ])
    client.app.state.store.rebuild()
    a = keeplib.keep_id("vision", "ALPHA", AGENT, 1)
    b = keeplib.keep_id("vision", "ALPHA", AGENT, 2)
    client.get("/api/visions")

    r = client.post(f"/api/visions/{a}/update", json={"tags": "ui,product"})
    assert r.status_code == 200, r.text
    assert r.json()["metadata"]["tags"] == "ui,product"
    client.post(f"/api/visions/{b}/update", json={"tags": "backend"})

    def ids(tag: str) -> list[str]:
        return [v["id"] for v in client.get("/api/visions", params={"tag": tag}).json()["visions"]]

    assert ids("ui") == [a] and ids("product") == [a]
    assert ids("backend") == [b]
    assert ids("u") == [], "a tag matches a whole member, never part of one"


def test_a_rule_is_written_from_a_problem_by_the_operator_only(client):
    root = Path(client.app.state.store.data_root)
    make_chat(root, "ALPHA", AGENT, [
        ("2026-09-01T10:00:00", "#problem Tasks saved in the same minute vanish.", "found it"),
    ])
    client.app.state.store.rebuild()
    pid = keeplib.keep_id("problem", "ALPHA", AGENT, 1)
    client.get("/api/problems")

    assert client.post(f"/api/problems/{pid}/rule", json={
        "agent_id": "cc-abc12345", "text": "x"}).status_code == 422
    assert client.post(f"/api/problems/{pid}/rule", json={"actor": "operator", "text": " "}).status_code == 422

    r = client.post(f"/api/problems/{pid}/rule", json={
        "actor": "operator", "text": "Mint ids from the whole headline."})
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["metadata"]["related_incident"] == pid and rule["metadata"]["source"] == "problem"
    assert rule["kept"]["from"] == pid
    assert rule["kept"]["message"] == "Tasks saved in the same minute vanish."
    assert [v["how"] for v in rule["kept"]["versions"]] == ["edited"]

    rid = rule["metadata"]["id"]
    again = client.post(f"/api/problems/{pid}/rule", json={
        "actor": "operator", "text": "Mint ids from the whole headline."})
    assert again.json()["metadata"]["id"] == rid, "a second click is the same rule"
    assert len([r for r in client.get("/api/rules").json()["rules"] if r["related_incident"] == pid]) == 1
    assert client.post(f"/api/rules/{rid}/interpretation", json={
        "actor": "operator", "text": "Mint ids from the title too."}).status_code == 200
    assert client.get(f"/api/problems/{pid}").json()["metadata"]["status"] == "open", "the problem is not changed"


def test_a_posted_entry_has_no_interpretation(client):
    posted = client.post("/api/visions", json={
        "created_date": "2609-01", "created_time": "10:00", "project": "ALPHA",
        "agent_id": "cc-abc12345", "l1": "Stay local"}).json()
    vid = posted["metadata"]["id"]
    assert client.get(f"/api/visions/{vid}").json().get("kept") is None
    assert client.post(f"/api/visions/{vid}/interpretation",
                       json={"text": "x"}).status_code == 409
