"""Entry writes name every reason at once (tk_90c1ba5f): the MCP
translator's own checks, a lens create and a lens update. One reason reads
as before; a missing row is the only reason."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import mcp as translator

AG = "cc-c6c6c6c6"


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


def _translator(client: TestClient) -> translator.Translator:
    schema = client.get("/api/schema").json()
    tr = translator.Translator.__new__(translator.Translator)
    tr.schema = schema
    tr.lenses = {lens["name"]: lens for lens in schema["lenses"]}
    tr.vocab = schema.get("vocabularies", {})
    tr._refresh = lambda lens: False                     # type: ignore[method-assign]
    tr._stamp = lambda args: {"agent_id": AG, "project": "ALPHA"}  # type: ignore[method-assign]
    return tr


def decision(**more) -> dict:
    return {"created_date": "2611-26", "created_time": "10:00", "project": "ALPHA", "agent_id": "operator",
            "decision": "chose sqlite", "why": "small", **more}


# -- the MCP translator -------------------------------------------------------

def test_write_entry_names_an_unknown_field_and_a_bad_value_together(client: TestClient) -> None:
    tr = _translator(client)
    with pytest.raises(translator.ApiError) as exc:
        tr.call("write_entry", {"lens": "decision", "fields": {"decision": "x", "colour": "red",
                                                               "weight": "huge"}})
    text = str(exc.value)
    assert text.startswith("2 reasons, fix them all before sending again:\n1. decision has no field colour")
    assert "\n2. decision.weight 'huge' is not a known value" in text


def test_two_bad_values_are_both_named_by_the_translator(client: TestClient) -> None:
    tr = _translator(client)
    with pytest.raises(translator.ApiError) as exc:
        tr._check_vocab("task", {"status": "bogus", "resurface_to": ["x"]})
    lines = str(exc.value).split("\n")
    assert len(lines) == 3 and "task.status 'bogus'" in lines[1] and "task.resurface_to is one text value" in lines[2]


def test_one_bad_value_reads_as_before(client: TestClient) -> None:
    tr = _translator(client)
    with pytest.raises(translator.ApiError) as exc:
        tr._check_vocab("task", {"status": "bogus"})
    assert str(exc.value).startswith("task.status 'bogus' is not a known value — use one of: ")
    assert "\n" not in str(exc.value)


# -- a lens create -----------------------------------------------------------

def test_two_list_columns_and_a_bad_value_are_all_named(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post("/api/decisions", json=decision(source=["chat"], related_goal_id={"a": 1}, weight="huge"))
    assert r.status_code == 422
    got = r.json()["detail"].split("\n")
    assert got[:2] == ["related_goal_id is text, not a list or an object", "source is text, not a list or an object"] \
        or got[:2] == ["source is text, not a list or an object", "related_goal_id is text, not a list or an object"]
    assert len(got) == 3 and got[2].startswith("decision.weight huge is not a known value")
    assert tree(data_root) == before


def test_a_create_with_one_bad_value_reads_as_before(client: TestClient) -> None:
    r = client.post("/api/decisions", json=decision(weight="huge"))
    assert (r.status_code, r.json()["detail"]) == (
        422, "decision.weight huge is not a known value — use one of: major, minor, normal")


# -- a lens update -----------------------------------------------------------

def test_an_update_of_a_missing_row_is_the_404_whatever_else(client: TestClient, data_root: Path) -> None:
    before = tree(data_root)
    r = client.post("/api/decisions/dc_nothere00/update", json={"weight": "huge"})
    assert r.status_code == 404
    assert tree(data_root) == before


def test_an_update_names_every_reason(client: TestClient, data_root: Path) -> None:
    r = client.post("/api/visions", json={"created_date": "2611-26", "created_time": "10:00", "project": "ALPHA",
                                         "agent_id": "operator", "vision": "a calmer board"})
    if r.status_code not in (200, 201):
        pytest.skip(f"no vision lens create here: {r.text}")
    vid = r.json()["metadata"]["id"]
    before = tree(data_root)
    r = client.post(f"/api/visions/{vid}/update", json={"agent_id": AG, "archived_at": "yesterday"})
    assert r.status_code == 422
    assert r.json()["detail"].split("\n") == ["archiving a vision is the operator's",
                                             "archived_at must be a valid YYMM-DD date"]
    assert tree(data_root) == before
