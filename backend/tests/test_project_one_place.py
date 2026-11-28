"""`project` has one place: top-level, next to lens (tk_0b8a32d2, audit P23).

Fixture (tests/test_membership_tools.py): chat A from ALPHA joins BETA;
GAMMA is no project of A's. Through the real translator into the real gated
server, every shape of a project either writes where it says, or is refused
with the one right shape; nothing is guessed or silently overridden.
"""

from __future__ import annotations

import re

import pytest

from backend import mcp, mcp_args
from tests.test_membership_tools import DECISION, tree, world  # noqa: F401 — the fixture

pytestmark = pytest.mark.strict_membership

FIELDS = DECISION["fields"]


def _project(got: dict) -> str:
    return str(got["metadata"]["project"])


def test_a_fields_project_never_lands_somewhere_it_does_not_name(world) -> None:  # noqa: F811
    """The silent misroute: a project in `fields` was written over by the
    stamp (the home, or the top-level value), so the card landed in a project
    the call did not name. Now it is written where named, or refused."""
    tr, _c, _root = world
    for args in ({"lens": "decision", "fields": {**FIELDS, "project": "BETA"}},
                 {"lens": "decision", "project": "ALPHA", "fields": {**FIELDS, "project": "BETA"}}):
        try:
            got = tr.call("write_entry", args)
        except mcp.ApiError:
            continue
        assert _project(got) == "BETA", (args, _project(got))


def test_top_level_project_writes_there(world) -> None:  # noqa: F811
    tr, _c, _root = world
    got = tr.call("write_entry", {"lens": "decision", "project": "BETA", "fields": FIELDS})
    assert _project(got) == "BETA" and got["where"].endswith("→ BETA")


def test_no_project_anywhere_is_home_and_where_says_so(world) -> None:  # noqa: F811
    tr, _c, _root = world
    got = tr.call("write_entry", {"lens": "decision", "fields": FIELDS})
    assert _project(got) == "ALPHA" and got["where"].endswith("→ ALPHA")


def test_a_project_only_in_fields_is_refused_with_the_shape(world) -> None:  # noqa: F811
    tr, _c, root = world
    before = tree(root)
    with pytest.raises(mcp.ApiError) as err:
        tr.call("write_entry", {"lens": "task", "fields": {"title": "Check it", "tags": "ag_bug", "project": "BETA"}})
    assert str(err.value) == ('put project next to lens, not inside fields: '
                              '{"lens":"task","project":"BETA","fields":{…}}')
    assert tree(root) == before


def test_two_different_projects_are_refused_naming_both(world) -> None:  # noqa: F811
    tr, _c, root = world
    before = tree(root)
    with pytest.raises(mcp.ApiError) as err:
        tr.call("write_entry", {"lens": "decision", "project": "ALPHA",
                                "fields": {**FIELDS, "project": "BETA"}})
    text = str(err.value)
    assert "ALPHA" in text and "BETA" in text and '"project":"ALPHA"' in text, text
    assert tree(root) == before


def test_the_same_project_twice_is_accepted_once(world) -> None:  # noqa: F811
    tr, _c, _root = world
    got = tr.call("write_entry", {"lens": "decision", "project": "BETA",
                                  "fields": {**FIELDS, "project": "BETA"}})
    assert _project(got) == "BETA"
    posted = tr.api.calls[-1][2] or {}
    assert posted["project"] == "BETA"


def test_a_tool_that_takes_no_project_refuses_one(world) -> None:  # noqa: F811
    """standup_material read the home whatever project it was sent: a
    `project: BETA` was dropped without a word."""
    tr, _c, _root = world
    with pytest.raises(mcp.ApiError) as err:
        tr.call("standup_material", {"date": "2611-19", "project": "BETA"})
    assert str(err.value).startswith("standup_material takes no project")
    assert not [p for _m, p, _b in tr.api.calls if p.startswith("/api/standups")]


def test_an_argument_a_tool_does_not_take_is_refused_in_one_line(world) -> None:  # noqa: F811
    tr, _c, _root = world
    with pytest.raises(mcp.ApiError) as err:
        tr.call("write_entry", {"lens": "decision", "decision": "chose sqlite", "fields": FIELDS})
    text = str(err.value)
    assert "\n" not in text
    assert text == "write_entry takes no argument decision — it takes: fields, lens, project"


def test_the_project_tool_takes_project(world) -> None:  # noqa: F811
    """The `project` tool took the code as `code`: the one value under two names."""
    tr, _c, _root = world
    tr.call("project", {"project": "BETA"})
    assert tr.api.calls[-1][1] == "/api/project/BETA"
    with pytest.raises(mcp.ApiError, match=r'\{"project":"BETA"\}'):
        tr.call("project", {"code": "BETA"})


def test_every_project_tool_refuses_a_project_of_the_wrong_shape(world) -> None:  # noqa: F811
    tr, _c, _root = world
    for tool in sorted(mcp_args.PROJECT_TOOLS):
        with pytest.raises(mcp.ApiError, match="project is one project code"):
            given = {"lens": "decision", "fields": FIELDS} if tool == "write_entry" else {}
            tr.call(tool, {**given, "project": ["BETA"]})


class _Posts(mcp.Api):
    def __init__(self) -> None:
        super().__init__("http://testserver")
        self.posts: list[tuple[str, dict | None]] = []

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        self.posts.append((path, body))
        return {}


def _bare(monkeypatch) -> mcp.Translator:
    tr = mcp.Translator.__new__(mcp.Translator)
    tr.api, tr.schema, tr.lenses, tr.vocab, tr.cwd, tr.client, tr.thread = _Posts(), {}, {}, {}, "", "", ""
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {"agent_id": "cc-aaaa1111", "project": "ALPHA"})
    return tr


def test_core_attach_refuses_a_different_parsed_author_before_posting(monkeypatch) -> None:
    tr = _bare(monkeypatch)
    with pytest.raises(mcp.ApiError, match="core_attach needs a message of this chat"):
        tr.call("core_attach", {"id": "cr_a", "message": "cc-aaaa1111#other#5", "task_id": "tk_a"})
    assert tr.api.posts == []


def test_mcp_names_translate_to_the_existing_http_shapes(monkeypatch) -> None:
    tr = _bare(monkeypatch)
    message = "cc-aaaa1111#5"
    tr.call("task_move", {"id": "tk_a", "project": "BETA"})
    tr.call("carry_brief", {"message": message + "/reply", "text": "the brief"})
    tr.call("core_attach", {"id": "cr_a", "message": message, "task_id": "tk_a"})
    tr.call("publish_write", {"id": "pu_a", "links": [{"url": "https://example.org"}]})
    assert tr.api.posts == [
        ("/api/tasks/tk_a/move", {"agent_id": "cc-aaaa1111", "to": "BETA"}),
        ("/api/carries/brief", {"agent_id": "cc-aaaa1111", "target": message + "/reply", "text": "the brief"}),
        ("/api/cores/cr_a/links", {"agent_id": "cc-aaaa1111", "kind": "message", "target": message, "note": ""}),
        ("/api/cores/cr_a/links", {"agent_id": "cc-aaaa1111", "kind": "task", "target": "tk_a", "note": ""}),
        ("/api/publishing/cards/pu_a/write", {"agent_id": "cc-aaaa1111", "links": [{"url": "https://example.org"}]}),
    ]


@pytest.mark.parametrize(("tool", "args", "where"), [
    ("task_evidence", {"id": "tk_12345678", "items": [{"kind": "text", "title": "t", "body": "b", "agent_id": "cc-x"}]},
     "items[0]"),
    ("map_write", {"map": {"template": "tool", "rows": [], "agent_id": "cc-x"}}, "map"),
    ("map_write", {"map": {"template": "tool", "rows": [{"kind": "module", "name": "m", "session_id": "s"}]}},
     "map.rows[0]"),
    ("entrypoint_way", {"id": "ep_1", "way": {"name": "w", "kind": "page", "url": "http://x/", "actor": "cc-x"}}, "way"),
    ("note_write", {"text": "# N", "kind": "context", "images": [{"path": "/x.png", "created_by": "cc-x"}]},
     "images[0]"),
    ("usage_prices_write", {"models": {"m": {"input": 1, "agent_id": "cc-x"}}, "sources": ["https://e.org"]},
     "models.m"),
])
def test_identity_inside_an_object_a_tool_carries_is_refused_by_name(monkeypatch, tool, args, where) -> None:
    """It was dropped there without a word (tk_0b8a32d2): the evidence item,
    the map, the way in kept everything else and lost the identity."""
    tr = _bare(monkeypatch)
    with pytest.raises(mcp.ApiError, match=rf"is stamped by Slightly Parallel; leave it out \(inside {re.escape(where)}\)$"):
        tr.call(tool, args)
    assert tr.api.posts == []


def test_a_project_inside_an_object_is_refused_and_a_maps_from_is_a_part(monkeypatch) -> None:
    tr = _bare(monkeypatch)
    with pytest.raises(mcp.ApiError, match=r"^put project next to the other arguments, not inside map$"):
        tr.call("map_write", {"map": {"template": "tool", "rows": [], "project": "GAMMA"}})
    with pytest.raises(mcp.ApiError, match=r"^task_evidence takes no project, inside items\[0\] either$"):
        tr.call("task_evidence", {"id": "tk_12345678", "items": [{"kind": "text", "project": "GAMMA"}]})
    # A relation's `from` names a part of the program, not a writer.
    tr.call("map_write", {"map": {"template": "tool", "rows": [], "relations": [{"from": "a", "to": "b", "verb": "calls"}]}})
    assert tr.api.posts and tr.api.posts[-1][0] == "/api/map"


def test_an_argument_sent_as_null_is_no_argument(monkeypatch) -> None:
    """Some clients echo every optional key as null: that is not a value."""
    tr = _bare(monkeypatch)
    tr.call("task_report", {"id": "tk_12345678", "summary": "Done.", "not_an_argument": None, "agent_id": None})
    assert tr.api.posts[-1] == ("/api/tasks/tk_12345678/report", {"agent_id": "cc-aaaa1111", "summary": "Done."})
    with pytest.raises(mcp.ApiError, match="takes no argument not_an_argument"):
        tr.call("task_report", {"id": "tk_12345678", "summary": "Done.", "not_an_argument": 0})
