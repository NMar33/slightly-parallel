"""Every MCP tool, called through the real translator against the real gated
server, reaches its router: the gate refuses none of them. The gate's path
list (server._MCP_WRITE_PATHS) is kept by hand beside the translator; the
#undo tools shipped refused because the list missed them (tk_d032ea2e).
Here a new tool that posts somewhere the list does not name fails CI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import mcp
from backend import server as _server
from backend.server import MCP_NEEDS_AGENT, MCP_PATH_REFUSAL, MCP_REFUSAL, _WRITE_TOOLS, create_app

AGENT = "cc-alpha123"
GATE_REFUSALS = (MCP_PATH_REFUSAL, MCP_REFUSAL, MCP_NEEDS_AGENT)

# Arguments that get each tool as far as its request; the router may still
# refuse them (no such task, no request in the chat): that is not the gate.
ARGS: dict[str, dict[str, Any]] = {
    "write_entry": {"lens": "decision", "fields": {"decision": "chose sqlite", "why": "small"}},
    "update_entry": {"lens": "decision", "id": "dc_none", "changes": {"why": "x"}},
    "interpret": {"lens": "vision", "id": "vs_none", "text": "x"},
    "undo_propose": {"ids": ["vs_none"]},
    "standup_postpone": {"date": "2609-17", "hours": 4},
    "standup_material": {"date": "2609-17", "claim": True},
    "map_write": {"map": {"template": "tool", "rows": []}, "note": "x"},
    "architecture_page": {"text": "x", "note": "x"},
    "task_update": {"id": "tk_none", "title": "x"},
}


class _GatedApi(mcp.Api):
    """The translator's client, sending its requests into the test app."""

    def __init__(self, client: TestClient) -> None:
        super().__init__("http://testserver")
        self.client = client
        self.calls: list[tuple[str, str, int, str]] = []

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        r = self.client.request(method, path, json=body,
                                headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        try:
            detail = str(r.json().get("detail", "")) if r.status_code >= 400 else ""
        except (ValueError, AttributeError):
            detail = r.text
        self.calls.append((method, path.split("?")[0], r.status_code, detail))
        if r.status_code >= 400:
            raise mcp.ApiError(f"{r.status_code}: {detail}")
        return r.json()


@pytest.fixture()
def translator(data_root: Path, monkeypatch):
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    monkeypatch.setattr(mcp.Translator, "identity",
                        lambda self: {"project": "alpha", "agent_id": AGENT})
    with TestClient(create_app(data_root=data_root, watch=False, run_monitor=False)) as c:
        yield mcp.Translator(_GatedApi(c), cwd=str(data_root))


def _run(tr: mcp.Translator, tool: str) -> list[tuple[str, str, int, str]]:
    api = tr.api
    assert isinstance(api, _GatedApi)
    before = len(api.calls)
    try:
        tr.call(tool, {"id": "x_none", **ARGS.get(tool, {})})
    except mcp.ApiError:
        pass  # refused by its router, or by the translator before a request
    return api.calls[before:]


@pytest.mark.parametrize("tool", sorted(mcp.TOOLS))
def test_the_gate_lets_every_tool_through(translator, tool) -> None:
    calls = _run(translator, tool)
    assert calls, f"{tool} made no request: give it arguments in ARGS"
    for method, path, status, detail in calls:
        assert not (status == 403 and any(r in detail for r in GATE_REFUSALS)), \
            f"the gate refused {tool}: {method} {path} → {detail}"


def test_the_refusal_names_every_tool_that_writes(translator) -> None:
    writes = {tool for tool in mcp.TOOLS
              if any(m == "POST" for m, *_ in _run(translator, tool))}
    # standup_material posts only to claim the day for the helper; it reads.
    assert writes - {"standup_material"} == set(_WRITE_TOOLS)
