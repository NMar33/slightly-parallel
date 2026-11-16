"""What real agents send to the MCP write tools, through the real translator
into the gated server: every answer is an entry stored with the meaning
sent, or a refusal that changes no file and does not contradict itself.

Agents send a list where one value is published (``"tags": ["ag_followup"]``,
twice in the paid runs: refused with ag_followup named as allowed), a number
as text, text as a number, null, an empty string, and fields the lens does
not have. The write fuzzer (test_write_fuzzer.py) walks the HTTP routes as
the operator, with junk values; this walks the agent's way in, with values
of the right meaning in the wrong shape.

The cases with a fixed answer are named in EXPECT; for the rest the rules
above hold: an accepted write never stores the Python text of a list, a
dict, None or a bool, and a refused one leaves the data root as it was.
"""

from __future__ import annotations

import itertools
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import mcp
from backend import server as _server
from backend.server import create_app
from tests.refusals import changed, contradicts, snapshot
from tests.test_every_get_answers import FIXTURES
from tests.test_mcp_tools_pass_the_gate import _GatedApi

AGENT = "cc-shape123"
PROJECT = "alpha-labs"
STAMPED = {"project", "agent_id", "created_date", "created_time"}
_ARCH_ALL = ["does", "owes", "runs", "stores", "talks", "built with", "faces", "holds"]

# The fixed answers: (lens, field, value) → stored text, or None for refused.
EXPECT: dict[tuple[str, str, str], str | None] = {
    ("task", "tags", repr(["ag_followup"])): "ag_followup",
    ("task", "tags", repr(["ag_bug", "ag_debt"])): "ag_bug,ag_debt",
    ("task", "tags", "'ag_bug, ag_debt'"): "ag_bug,ag_debt",
    ("task", "tags", repr([5])): None,
    ("task", "tags", "5"): None,
    ("task", "status", repr(["agent"])): None,
    ("task", "status", "'agent'"): "agent",
    ("problem", "status", repr(["open"])): None,
    ("decision", "weight", repr(["minor"])): None,
}


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {"project": PROJECT, "agent_id": AGENT})
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False)) as c:
        tr = mcp.Translator(_GatedApi(c), cwd=str(root))
        tr.ensure()
        yield tr, root


def _base(lens: dict, n: int) -> dict[str, Any]:
    head = lens["text_fields"][0]
    out: dict[str, Any] = {head: f"an entry an agent wrote, number {n}"}
    if lens["name"] == "task":
        out.update(tags="ag_bug", status="agent")
    if lens["name"] == "architecture":
        out["checked"] = list(_ARCH_ALL)
    return out


def _shapes(lens: dict, field: str, spec: dict) -> list[Any]:
    """Values of the right meaning in the shapes agents send."""
    enum = spec.get("enum") or []
    plain: Any = enum[0] if enum else ("3" if spec.get("type") == "integer" else "a value")
    if lens["name"] == "task" and field == "status":
        plain = "agent"
    if lens["name"] == "task" and field == "tags":
        return [["ag_followup"], ["ag_bug", "ag_debt"], "ag_bug, ag_debt", [5], 5, None, ""]
    out: list[Any] = [[plain], None, ""]
    out.append(5 if spec.get("type") != "integer" else "5")
    if spec.get("type") == "array":
        out.append("one line")   # a list field sent as text
    return out


def _stored(answer: Any) -> dict:
    meta = answer.get("metadata") if isinstance(answer, dict) else None
    return meta if isinstance(meta, dict) else {}


def _python_text(value: Any) -> bool:
    s = str(value or "")
    return s.startswith(("['", '["', "[1", "[5", "{'", '{"')) or s in ("None", "True", "False")


def test_agent_shaped_values_are_stored_as_meant_or_refused_without_a_change(world) -> None:
    tr, root = world
    counter = itertools.count(1)
    problems: list[str] = []
    tried = refused = 0
    lenses = [l for l in tr.lenses.values() if l.get("agent_write", True)]
    assert {l["name"] for l in lenses} >= {"task", "decision", "problem", "scan", "standup", "file"}
    for lens in sorted(lenses, key=lambda l: l["name"]):
        fields = {k: v for k, v in (lens.get("fields") or {}).items() if k not in STAMPED}
        # The base entry is accepted: else the shapes below say nothing.
        tr.call("write_entry", {"lens": lens["name"], "fields": _base(lens, next(counter))})
        cases: list[tuple[str, Any]] = [(f, v) for f, spec in sorted(fields.items()) for v in _shapes(lens, f, spec)]
        cases.append(("colour", "blue"))   # a field the lens does not have
        for field, value in cases:
            body = {**_base(lens, next(counter)), field: value}
            if field == lens["text_fields"][0] and value in (None, ""):
                body[field] = value
            before = snapshot(root, skip=("logs/",))
            tried += 1
            key = (lens["name"], field, repr(value))
            try:
                answer = tr.call("write_entry", {"lens": lens["name"], "fields": body})
            except mcp.ApiError as exc:
                refused += 1
                detail = str(exc)
                if detail.startswith("5"):
                    problems.append(f"{key}: server error {detail[:160]}")
                moved = changed(before, snapshot(root, skip=("logs/",)))
                if moved:
                    problems.append(f"{key}: refused ({detail[:100]}) and changed {moved[:4]}")
                if who := contradicts(detail, value):
                    problems.append(f"{key}: refused {who!r} and listed it as allowed: {detail[:200]}")
                if key in EXPECT and EXPECT[key] is not None:
                    problems.append(f"{key}: refused, expected {EXPECT[key]!r}: {detail[:160]}")
                if field == "colour" and "colour" not in detail:
                    problems.append(f"{key}: an unknown field refused without its name: {detail[:160]}")
                continue
            if field == "colour":
                problems.append(f"{key}: an unknown field was accepted")
            if key in EXPECT and EXPECT[key] is None:
                problems.append(f"{key}: accepted, expected a refusal")
            row = _stored(answer)
            if key in EXPECT and EXPECT[key] is not None and row.get(field) != EXPECT[key]:
                problems.append(f"{key}: stored {row.get(field)!r}, expected {EXPECT[key]!r}")
            for col, got in row.items():
                if col not in ("id",) and _python_text(got):
                    problems.append(f"{key}: stored Python text in {col}: {str(got)[:80]}")
    assert tried > 200 and refused > 10, (tried, refused)
    assert not problems, f"{len(problems)} of {tried}:\n" + "\n".join(problems[:60])
