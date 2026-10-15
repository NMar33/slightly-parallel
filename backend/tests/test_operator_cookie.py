"""A write as the operator needs the operator's cookie (server.OperatorCookie).

Before, any program on the computer could post as the operator by naming no
agent. The cookie is handed to a page of Slightly Parallel's own; a plain
HTTP client gets none and its operator write is refused.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from fastapi.testclient import TestClient

from backend.server import OPERATOR_TOKEN_FILE, create_app, operator_cookie


def _bare(app) -> TestClient:
    c = TestClient(app)
    c.cookies.clear()
    return c


def test_a_plain_request_cannot_write_as_the_operator(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False, run_monitor=False)
    with _bare(app) as c:
        r = c.post("/api/prefs", json={"values": {"sp-lang": "ru"}})
        assert r.status_code == 403
        assert "own pages" in r.json()["detail"]
        # Naming the operator outright changes nothing.
        r = c.post("/api/prefs", json={"values": {"x": "1"}, "actor": "operator"})
        assert r.status_code == 403
        # An upload is the operator's too.
        r = c.post("/api/prefs", content=b"a=1", headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 403


def test_a_page_of_its_own_gets_the_cookie_and_writes(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False, run_monitor=False)
    with _bare(app) as c:
        r = c.get("/api/health", headers={"Sec-Fetch-Site": "same-origin"})
        jar = r.headers.get("set-cookie", "")
        name, value = operator_cookie(app)
        assert jar.startswith(f"{name}={value}")
        assert "HttpOnly" in jar and "SameSite=Strict" in jar
        r = c.post("/api/prefs", json={"values": {"x": "1"}})
        assert r.status_code == 200, r.text


def test_no_cookie_for_a_plain_client_or_another_site(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False, run_monitor=False)
    with _bare(app) as c:
        assert "set-cookie" not in c.get("/api/health").headers
        assert "set-cookie" not in c.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"}).headers


def test_a_wrong_cookie_is_refused(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False, run_monitor=False)
    with _bare(app) as c:
        name, _ = operator_cookie(app)
        c.cookies.set(name, "not-the-token")
        assert c.post("/api/prefs", json={"values": {"x": "1"}}).status_code == 403


def test_agent_writes_through_mcp_need_no_cookie(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False, run_monitor=False)
    with _bare(app) as c:
        r = c.post("/api/tasks/tk_none/report", json={"agent_id": "cc-alpha", "summary": "x"},
                   headers={"x-sp-via": "mcp"})
        assert r.status_code != 403


def test_the_mcp_mark_without_an_agent_is_not_the_operator(data_root: Path) -> None:
    """Anyone can send the header; with no agent named it was an operator
    write that skipped the cookie."""
    app = create_app(data_root=data_root, watch=False, run_monitor=False)
    with _bare(app) as c:
        for body in ({"values": {"x": "1"}}, {"values": {"x": "1"}, "actor": "operator"}):
            r = c.post("/api/prefs", json=body, headers={"x-sp-via": "mcp"})
            assert r.status_code == 403
            assert "names the agent" in r.json()["detail"]


def test_putting_off_the_standup_still_needs_no_agent(data_root: Path) -> None:
    # The MCP tool standup_postpone sends project and date only; chats
    # running an older MCP server keep working.
    app = create_app(data_root=data_root, watch=False, run_monitor=False)
    with _bare(app) as c:
        r = c.post("/api/standups/postpone", json={"project": "ALPHA", "date": "2608-01", "hours": 4},
                   headers={"x-sp-via": "mcp"})
        assert r.status_code != 403, r.text


def test_the_token_is_kept_for_the_owner_only_and_across_restarts(data_root: Path) -> None:
    first = create_app(data_root=data_root, watch=False, run_monitor=False)
    path = data_root / OPERATOR_TOKEN_FILE
    if os.name != "nt":  # Windows has no owner-only mode bits to check
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    again = create_app(data_root=data_root, watch=False, run_monitor=False)
    assert operator_cookie(first) == operator_cookie(again)
