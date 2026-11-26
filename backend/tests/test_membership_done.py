"""#done reads the chat's member projects (tk_d1d25a4d step 3, note
nt_258a7ed7 §3 «#done»).

Chat A from ALPHA joined BETA; GAMMA is no project of A's. An id next to
#done closes a task in any project (the operator's answer 2, dc_f6ec18c8);
the «last task named» fallback and the other ids count a task as local when
its project or one of its projects is a member project; a task outside them
is a doubt, «not a project of this agent».
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app
from tests.conftest import make_chat

pytestmark = pytest.mark.strict_membership

A = "cc-aaaa1111"
GAMMA_TASK = "tk_gamma_one"
SHARED = "tk_gamma_two"      # GAMMA's, shown on BETA too


@pytest.fixture()
def world(data_root: Path):
    (data_root / "projects" / "GAMMA").mkdir(parents=True)
    with (data_root / "tasks.csv").open("a", encoding="utf-8") as fh:
        fh.write(f"{GAMMA_TASK},2611-20,10:00,GAMMA,operator,Gamma task,todo,med,,,,,10,,,,,GAMMA,,,,,,,,,,,\n")
        fh.write(f'{SHARED},2611-20,10:00,GAMMA,operator,Shared task,todo,med,,,,,10,,,,,"GAMMA,BETA",,,,,,,,,,,\n')
    (data_root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    make_chat(data_root, "ALPHA", A, [("2026-11-20T10:00:00", "start", "ok")])
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert c.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "BETA"}).status_code == 200
        yield c, data_root


def _at(minutes: int) -> str:
    return (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def _done(c: TestClient, root: Path, turns: list[str]) -> dict:
    make_chat(root, "ALPHA", A, [("2026-11-20T10:00:00", "start", "ok")]
              + [(_at(30 - 5 * i), text, "ok") for i, text in enumerate(turns)])
    c.app.state.store.rebuild()
    return c.get("/api/done-tags", params={"agent_id": A}).json()


def _results(got: dict) -> dict[str, str]:
    return {t["id"]: t["result"] for t in got["tasks"]}


def _doubts(got: dict) -> dict[str, str]:
    return {d["id"]: d["reason"] for d in got.get("doubt") or []}


def test_an_id_next_to_done_closes_in_any_project(world) -> None:
    c, root = world
    got = _done(c, root, [f"#done {GAMMA_TASK}"])
    assert _results(got) == {GAMMA_TASK: "moved"}


def test_the_last_task_named_counts_in_a_member_project(world) -> None:
    c, root = world
    got = _done(c, root, ["work on tk_beta_x now", "#done"])
    assert _results(got) == {"tk_beta_x": "moved"}


def test_a_task_shown_on_a_member_project_counts_by_its_projects(world) -> None:
    c, root = world
    got = _done(c, root, [f"work on {SHARED} now", "#done"])
    assert _results(got) == {SHARED: "moved"}


def test_a_task_outside_the_members_is_a_doubt(world) -> None:
    c, root = world
    got = _done(c, root, ["work on tk_alpha_auth", f"and look at {GAMMA_TASK}", "#done"])
    assert _results(got) == {"tk_alpha_auth": "moved"}
    assert _doubts(got) == {GAMMA_TASK: "other_project"}
    assert got["confirmation"].startswith("#done ") and GAMMA_TASK in got["confirmation"]


def test_the_hook_words_the_doubt() -> None:
    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture.py"
    spec = importlib.util.spec_from_file_location("sp_capture_done", hooks)
    assert spec and spec.loader
    cap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cap)
    text = cap._done_outcome_notice({"tasks": [], "doubt": [{"id": GAMMA_TASK, "reason": "other_project"}],
                                     "confirmation": f"#done {GAMMA_TASK}"})
    assert f"{GAMMA_TASK} (not a project of this agent)" in text
