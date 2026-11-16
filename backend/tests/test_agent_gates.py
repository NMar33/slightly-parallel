"""Every operator-only write refuses an agent, by route.

The gates in actors.py and tasklib.py are reached by the other tests; these
fifteen were not (an audit's gate recorder found them never hit), so a gate
that stopped working would have passed the suite. One request per gate: an
agent's write, and the one refusal an agent gets.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.actors import AGENT_REFUSED

AGENT = "cc-gate12345"

ROUTES = [
    # (route, body, the words of the refusal)
    ("/api/skills/import", {"path": "/x"}, "taking a skill in is the operator's"),
    ("/api/skills/sk_any/uninstall", {"project": "alpha"}, "removing a skill is the operator's"),
    ("/api/skills/sk_any/keep-disk", {"project": "alpha"}, "taking a skill from disk is the operator's"),
    # The marks routes read the writer from `actor` alone: `agent_id` there
    # is the chat whose message is starred (the page's own star names it).
    ("/api/marks/unmark", {"kind": "task", "target": "tk_x", "actor": AGENT}, "Unmarking something important is the operator's"),
    ("/api/monitor/events/1/seen", {}, "Marking a monitor event seen is the operator's"),
    ("/api/monitor/events/seen", {}, "Marking monitor events seen is the operator's"),
    ("/api/evidence-prompts", {"name": "n", "text": "t"}, "the evidence prompts is the operator's"),
    ("/api/evidence-prompts/ep_x/delete", {}, "the evidence prompts is the operator's"),
    ("/api/tasks/evidence/ev_x/delete", {}, "removing evidence is the operator's"),
    ("/api/skills", {"created_date": "2610-25", "created_time": "10:00", "project": "alpha", "l1": "x"},
     "skills come from #skill in a message or the Skills page"),
    ("/api/artifacts", {"created_date": "2610-25", "created_time": "10:00", "project": "alpha", "l1": "x"},
     "artifacts come from #artifact in a message or the Artifacts page"),
    ("/api/rules/rl_x/update", {"auto": "1"}, "a rule is the operator's own #rule message"),
]


@pytest.mark.parametrize("route,body,words", ROUTES, ids=[r[0] for r in ROUTES])
@pytest.mark.parametrize("who", ["agent_id", "actor"])
def test_an_agents_write_is_refused_at_the_gate(client: TestClient, route: str, body: dict, words: str, who: str) -> None:
    r = client.post(route, json={**body, who: AGENT})
    assert r.status_code == AGENT_REFUSED, (route, r.status_code, r.text)
    assert words in r.json()["detail"], (route, r.text)


def test_the_terminal_gates_refuse_an_agent(client: TestClient, monkeypatch) -> None:
    from backend.routers import terminal

    if not terminal.SUPPORTED:
        pytest.skip("the terminal needs macOS or Linux")
    assert client.post("/api/settings", json={"values": {"terminal.enabled": True}}).status_code == 200
    for route, what in (("/api/terminal/sessions/ts_x/type", "Typing into a terminal"),
                        ("/api/terminal/sessions/ts_x/rename", "Renaming a terminal"),
                        ("/api/terminal/sessions/ts_x/close", "Closing a terminal")):
        for who in ("agent_id", "actor"):
            r = client.post(route, json={"text": "x", "label": "x", who: AGENT})
            assert r.status_code == AGENT_REFUSED and f"{what} is the operator's" in r.json()["detail"], (route, who, r.text)
