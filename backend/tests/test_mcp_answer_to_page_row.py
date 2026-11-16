"""From the MCP answer to the page's row: an entry an agent writes through
the translator is in the list the page reads next, under the id the answer
gave, also when the page asks with the tag of what it had (a 304 there would
show the old list). An OpenCode run on macOS saved a scan that the Scans page
did not show within 10 s (round 4, unexplained); this is the path it took."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import mcp
from backend import server as _server
from backend.server import create_app
from tests.test_every_get_answers import FIXTURES
from tests.test_mcp_tools_pass_the_gate import _GatedApi

PROJECT = "alpha-labs"

# lens → (fields, the list the page reads, the key of its rows)
CASES = {
    "scan": ({"summary": "the scan an agent wrote"}, "/api/scans?project=alpha-labs", "scans"),
    "decision": ({"decision": "chose sqlite", "why": "small"}, "/api/decisions?project=alpha-labs", "decisions"),
    "problem": ({"problem": "the login times out"}, "/api/problems?project=alpha-labs", "problems"),
    "task": ({"title": "a task an agent wrote", "tags": ["ag_bug"], "status": "agent"},
             "/api/tasks?project=alpha-labs", "tasks"),
}


@pytest.mark.parametrize("watch", [False, True])
@pytest.mark.parametrize("lens", sorted(CASES))
def test_the_written_entry_is_the_next_row_the_page_reads(tmp_path: Path, monkeypatch, lens: str, watch: bool) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    monkeypatch.setattr(mcp.Translator, "identity", lambda self: {"project": PROJECT, "agent_id": "cc-trace123"})
    fields, page, key = CASES[lens]
    with TestClient(create_app(data_root=root, watch=watch, run_monitor=False)) as c:
        tr = mcp.Translator(_GatedApi(c), cwd=str(root))
        before = c.get(page)
        assert before.status_code == 200
        etag = before.headers.get("etag")
        answer = tr.call("write_entry", {"lens": lens, "fields": fields})
        eid = answer["metadata"]["id"]
        after = c.get(page, headers={"If-None-Match": etag} if etag else {})
        assert after.status_code == 200, f"{lens}: the page's next read was {after.status_code} after {eid}"
        rows = after.json()[key] if isinstance(after.json(), dict) else after.json()
        assert eid in [r.get("id") for r in rows], f"{lens}: {eid} not in {page}"
