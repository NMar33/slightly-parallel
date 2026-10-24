"""Test fixtures: build a self-contained agents-directory in a tmp path.

Mirrors the on-disk layout of a real data root so tests never touch live
data. Two projects: one with a full agent, one bare.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

# Before anything imports the backend: a test run never reads or writes the
# operator's data. Importing backend.server (or any create_app() a test makes
# without a data_root) would otherwise settle on ~/.slightly-parallel, or on
# whatever folder the shell exports. Every session gets a fresh folder of its
# own, removed when the session ends; the sandbox flag keeps skills out of
# the home folder and the system monitor off.
for _name in ("SCAN_DATA_ROOT", "DATA_ROOT"):
    os.environ.pop(_name, None)
os.environ["SP_SANDBOX"] = "1"
_SESSION_ROOT = tempfile.mkdtemp(prefix="sp-tests-")
os.environ["SP_DATA_ROOT"] = _SESSION_ROOT
atexit.register(shutil.rmtree, _SESSION_ROOT, True)

# Tests log to memory and stdout only; the real log file beside the
# server is not the place for their noise.
os.environ.setdefault("SP_LOG_FILE", "0")
# Nothing a test writes outlives it: skip waiting for the disk.
os.environ.setdefault("SP_FSYNC", "0")
# No test plays the example month by starting a server on an empty root;
# test_example.py turns it on where it is the subject.
os.environ.setdefault("SP_EXAMPLE", "0")

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app

# The server answers only to a name of this computer (server.OwnPagesOnly).
# Starlette's test client dials "testserver" unless told otherwise: every
# test client dials the loopback address instead, as a real page does.
_client_init = TestClient.__init__


def _loopback_client(self, app, base_url: str = "http://127.0.0.1:8123", *args, **kwargs):
    _client_init(self, app, base_url, *args, **kwargs)
    # A test client stands in for the operator's pages: it carries the
    # operator's cookie (server.OperatorCookie). test_operator_cookie.py
    # clears it to see the refusal.
    if getattr(getattr(app, "state", None), "operator_token", ""):
        from backend.server import operator_cookie
        self.cookies.set(*operator_cookie(app))


TestClient.__init__ = _loopback_client

# Its socket dials "testserver" by a constant of its own.
_client_socket = TestClient.websocket_connect


def _loopback_socket(self, url: str, *args, **kwargs):
    if url.startswith("/"):
        url = "ws://127.0.0.1:8123" + url
    return _client_socket(self, url, *args, **kwargs)


TestClient.websocket_connect = _loopback_socket


# ---------------------------------------------------------------------------
# Helpers shared by several test files (import from tests.conftest)
# ---------------------------------------------------------------------------


def make_chat(root: Path, project: str, agent: str, turns: list[tuple[str, str, str]]) -> None:
    """Write a chat.md the way the capture hook does; turns are (at, user, agent)."""
    d = root / "projects" / project / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "agent_name": agent, "project": project,
        "created_date": "2609-01", "last_active": "2026-09-01T10:00:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {agent}\n"]
    for i, (at, user, said) in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · {at}\n**User**: {user}\n**Agent**: {said}\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


def make_task(client: TestClient, title: str, status: str = "todo", **more: str) -> str:
    """An operator's task in project alpha, made over the API; its id."""
    r = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": title, "status": status, **more,
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _git_home() -> str:
    """One empty home for every git the run starts (it was one folder per
    call, never removed: thousands under /tmp), gone when the run ends."""
    import atexit
    import shutil
    import tempfile
    global _GIT_HOME
    if _GIT_HOME is None:
        _GIT_HOME = tempfile.mkdtemp(prefix="sp-git-home-")
        atexit.register(shutil.rmtree, _GIT_HOME, True)
    return _GIT_HOME


_GIT_HOME: str | None = None

# Every git the suite runs, through git_env or not (thirteen test files call
# `git commit` directly), sees no user or system config — a developer's
# commit.gpgsign asked for a key and failed nine tests — and has an identity.
os.environ.update({
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
})


def git_env(**overrides: str) -> dict[str, str]:
    """The environment for a git the tests run: the machine's own, with
    every GIT_* variable dropped (a run from inside a git hook would
    otherwise act on the outer repository), no user or system config
    (a developer's commit.gpgsign would ask for a key), and the
    overrides on top."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    home = _git_home()
    env.update({"HOME": home, "USERPROFILE": home, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    env.update(overrides)
    return env


def free_port() -> int:
    """A port nothing listens on right now, for a test that starts a server
    of its own (the helper lived in three files)."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def git_repo(repo: Path) -> Path:
    """A new git repository on branch main with a committer identity of its own."""
    import subprocess
    repo.mkdir(parents=True, exist_ok=True)
    env = git_env()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env)
    return repo


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    """Two projects: ALPHA (full), BETA (goals+decisions only, no agents)."""
    root = tmp_path / "00-agents"

    alpha = root / "projects" / "ALPHA"
    _write(
        alpha / "goals.csv",
        (
            "id,goal_text,parent_goal_id,related,time_est,confidence_pct,"
            "success_comment,created_date,agent_id,status,retro_date,retro_notes\n"
            "g_alpha_root,Ship Alpha MVP,,mvp,5 days,70,rough plan,2608-01,"
            "alpha-lead-2608-01,in_progress,,\n"
            "g_alpha_child,Wire alpha auth,g_alpha_root,auth,1 day,90,,"
            "2608-02,alpha-lead-2608-01,done,2608-03,hit — done in 4 hours\n"
            "g_alpha_cyr,рекогниция интеграций,g_alpha_root,integrations,2 days,60,,"
            "2608-04,alpha-lead-2608-01,in_progress,,\n"
        ),
    )
    _write(
        alpha / "decisions.csv",
        (
            "id,decision_text,rationale,date,agent_id,related_goal_id,source\n"
            "d_alpha_stack,Chose FastAPI over Flask,async story is cleaner,"
            "2608-02,alpha-lead-2608-01,g_alpha_root,explicit_slash\n"
            "d_alpha_db,DuckDB for materialised views,CSV-native no ETL,"
            "2608-03,alpha-lead-2608-01,g_alpha_root,auto_detected\n"
        ),
    )
    _write(
        alpha / "activity_log.csv",
        (
            "date,start_time,end_time,duration_min,goal_id,summary,agent_id\n"
            "2608-01,09:00,12:00,180,g_alpha_root,Kickoff and plan,"
            "alpha-lead-2608-01\n"
            "2608-02,10:00,11:00,60,g_alpha_child,Wire OAuth flow,"
            "alpha-lead-2608-01\n"
            "2608-04,14:00,16:00,120,g_alpha_cyr,Матолимп-style rec check,"
            "alpha-lead-2608-01\n"
        ),
    )
    _write(alpha / "log.md", "# ALPHA log\n\n- 2608-01 kickoff\n")

    meta = {
        "agent_id": "alpha-lead-2608-01",
        "agent_name": "alpha-lead",
        "project": "ALPHA",
        "parent_agent_id": None,
        "created_date": "2608-01",
        "last_active": "2608-04T16:00:00",
        "message_count": 42,
        "root_goal_id": "g_alpha_root",
        "goals_declared": ["g_alpha_root", "g_alpha_child", "g_alpha_cyr"],
        "decisions_made": ["d_alpha_stack", "d_alpha_db"],
        "files_touched": ["src/auth.py", "src/db.py", "README.md"],
        "tags": ["kickoff", "auth"],
        "l1_headline": "Alpha kickoff — chose FastAPI+DuckDB, OAuth wired",
    }
    _write(
        alpha / "chats" / "alpha-lead-2608-01" / "meta.json",
        json.dumps(meta, indent=2),
    )
    _write(
        alpha / "chats" / "alpha-lead-2608-01" / "chat.md",
        "# alpha-lead chat\n\n" + "line body\n" * 250,
    )

    # child agent with parent link — proves timeline connectors
    meta2 = dict(meta)
    meta2.update(
        {
            "agent_id": "alpha-followup-2608-05",
            "agent_name": "alpha-followup",
            "parent_agent_id": "alpha-lead-2608-01",
            "created_date": "2608-05",
            "last_active": "2608-05T18:00:00",
            "message_count": 8,
            "root_goal_id": "g_alpha_cyr",
            "goals_declared": ["g_alpha_cyr"],
            "decisions_made": [],
            "files_touched": ["src/db.py"],
            "tags": ["followup"],
            "l1_headline": "Followup on рекогниция integrations",
        }
    )
    _write(
        alpha / "chats" / "alpha-followup-2608-05" / "meta.json",
        json.dumps(meta2, indent=2),
    )

    # Tasks live in the root ledger, one row per task across projects.
    # ALPHA: one doing, one done (closed 2026-08-30 in the event log), one
    # archived; BETA: one todo. The endpoints count open = not done and not
    # archived, done_7d = closed in the last week and still done.
    _write(
        root / "tasks.csv",
        (
            "id,created_date,created_time,project,agent_id,title,status,priority,"
            "assignee,due_date,lane,tags,position,impact,effort,tokens,novelty,"
            "projects,sprint_id,archived_at,resurface_on,resurface_to,"
            "resurface_every_days,resurfaced_at,remember,today_on,stack_id,"
            "stack_head_at,md_ref\n"
            "tk_alpha_auth,2608-02,09:00,ALPHA,operator,Wire alpha auth,doing,high,"
            ",,,auth,10,,,,,ALPHA,,,,,,,,,,,\n"
            "tk_alpha_cyr,2608-03,09:00,ALPHA,operator,рекогниция интеграций,done,med,"
            ",,,,20,,,,,ALPHA,,,,,,,,,,,\n"
            "tk_alpha_old,2608-01,09:00,ALPHA,operator,Old archived chore,done,low,"
            ",,,,30,,,,,ALPHA,,2026-08-05T10:00:00,,,,,,,,,\n"
            "tk_beta_x,2608-03,10:00,BETA,operator,Beta lone task,todo,med,"
            ",,,,10,,,,,BETA,,,,,,,,,,,\n"
        ),
    )
    _write(
        root / "task_events.csv",
        (
            "event_id,task_id,timestamp,actor,field,old_value,new_value\n"
            "ev_1,tk_alpha_cyr,2026-08-30T12:00:00,operator,status,doing,done\n"
            "ev_2,tk_alpha_old,2026-08-04T12:00:00,operator,status,doing,done\n"
        ),
    )

    # BETA — CSVs only, no chats. Should degrade gracefully.
    beta = root / "projects" / "BETA"
    _write(
        beta / "goals.csv",
        (
            "id,goal_text,parent_goal_id,related,time_est,confidence_pct,"
            "success_comment,created_date,agent_id,status,retro_date,retro_notes\n"
            "g_beta_x,Beta lone goal,,x,1 day,50,,2608-03,beta-lone,new,,\n"
        ),
    )
    _write(
        beta / "decisions.csv",
        (
            "id,decision_text,rationale,date,agent_id,related_goal_id,source\n"
        ),
    )
    return root


@pytest.fixture()
def client(data_root: Path) -> TestClient:
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as c:
        # Agent writes come through the MCP translator, which marks them so;
        # the suite writes as agents everywhere, so it carries the mark.
        # test_mcp_only.py takes it off to prove the refusal.
        c.headers["X-SP-Via"] = "mcp"
        # Only on a write that names an agent, as the translator sends it: a
        # body with no agent is the operator's page, which never carries the
        # mark (server.MCP_NEEDS_AGENT refuses the mark without an agent).
        c.event_hooks["request"].append(_mark_only_agent_writes)
        yield c


def _mark_only_agent_writes(request) -> None:
    from backend.routers import deps
    if request.method == "GET" or "x-sp-via" not in request.headers:
        return
    try:
        body = json.loads(request.content or b"{}")
    except (ValueError, UnicodeDecodeError, Exception):  # noqa: BLE001 — a stream or a form keeps the mark
        return
    if not deps.is_agent(deps.identity_of(body)):
        del request.headers["x-sp-via"]


@pytest.fixture(autouse=True)
def _agents_may_write_over_http(monkeypatch):
    """The suite posts as agents over plain HTTP everywhere; in the product
    those writes come through the MCP translator. The gate is off here and
    switched on by name in test_cleanup.py, which proves the refusal."""
    from backend import server as _server
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: False)


@pytest.fixture(autouse=True)
def _never_touch_real_env(tmp_path, monkeypatch):
    """No test may write the repo's real .env — redirect it wholesale.

    The data-root endpoint persists SCAN_DATA_ROOT to setup.ENV_PATH; without
    this guard a test exercising it would poison the operator's live config
    (it happened once — this fixture is the tombstone).
    """
    from backend.routers import setup as setup_router

    monkeypatch.setattr(setup_router, "ENV_PATH", tmp_path / "dot-env-guard")
    # Fixture data roots start without the example entries; tests that want
    # them turn this back on.
    monkeypatch.setenv("SP_EXAMPLES", "0")


@pytest.fixture(autouse=True)
def _codex_config_in_tmp(tmp_path, monkeypatch):
    """Setup writes Codex's MCP server into ~/.codex/config.toml: in tests,
    never the real one."""
    from backend.routers import setup as setup_router
    monkeypatch.setattr(setup_router, "CODEX_CONFIG_PATH", tmp_path / "codex-home" / "config.toml")
    # Start at login and the shortcut: never the real login or desktop.
    monkeypatch.setattr(setup_router, "AUTOSTART_HOME", tmp_path / "home")
    monkeypatch.setattr(setup_router, "AUTOSTART_ROOT", tmp_path / "app")
