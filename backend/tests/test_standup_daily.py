"""The project's daily standup: owed, claimed, postponed, written."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend import standuplib
from tests.conftest import git_repo

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _hook():
    spec = importlib.util.spec_from_file_location("sp_capture_standup", _HOOKS / "capture.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_standup"] = mod
    spec.loader.exec_module(mod)
    return mod


def _yesterday_chat(root: Path, agent: str = "cc-yest0001") -> str:
    then = datetime.now() - timedelta(days=1)
    d = root / "projects" / "ALPHA" / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({"agent_id": agent, "chat_title": "auth-work"}), encoding="utf-8")
    at = then.replace(hour=10, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%S")
    at2 = then.replace(hour=10, minute=20, second=0).strftime("%Y-%m-%dT%H:%M:%S")
    (d / "chat.md").write_text(
        f"# Chat log — {agent}\n\n---\n\n## Turn 1 · {at}\n**User**: make login work\n**Agent**: done\n"
        f"\n## Turn 2 · {at2}\n**User**: and logout\n**Agent**: done too\n", encoding="utf-8")
    return standuplib.yymm_dd(then)


def test_material_claim_postpone_and_written(client: TestClient) -> None:
    store = client.app.state.store
    day = _yesterday_chat(Path(store.data_root))
    store.rebuild()

    got = client.get(f"/api/standups/material?project=ALPHA&date={day}").json()
    assert got["messages_n"] == 2 and got["chats_n"] == 1 and got["standup_id"] == ""
    assert got["chats"][0]["chat"] == "auth-work" and got["chats"][0]["turns"][0]["user"] == "make login work"
    assert got["model"] == "opus" and got["ask_first"] is True
    assert "team lead" in got["instructions"] and "for_date" in got["next"]

    first = client.post("/api/standups/claim", json={"project": "ALPHA", "date": day, "agent_id": "cc-one"}).json()
    second = client.post("/api/standups/claim", json={"project": "ALPHA", "date": day, "agent_id": "cc-two"}).json()
    assert first["claimed"] is True and second == {"claimed": False, "claimed_by": "cc-one"}
    assert client.get(f"/api/standups/material?project=ALPHA&date={day}").json()["claimed_by"] == "cc-one"

    made = client.post("/api/standups", json={
        "created_date": standuplib.yymm_dd(datetime.now()), "project": "ALPHA", "agent_id": "cc-one",
        "summary": "Login and logout work.", "deviation": ["Nothing broke."],
        "movement": ["Login works.", "Logout works."], "for_date": day,
    })
    assert made.status_code in (200, 201), made.text
    assert made.json()["text"]["deviation"] == "- Nothing broke."     # a short list where the page shows text
    store.rebuild()
    assert standuplib.written(store, "ALPHA", day) == made.json()["metadata"]["id"]
    late = client.post("/api/standups/claim", json={"project": "ALPHA", "date": day, "agent_id": "cc-two"}).json()
    assert late["claimed"] is False and "written" in late["why"]

    assert client.get("/api/standups/material?project=NOPE").status_code == 404
    assert client.get("/api/standups/material?project=ALPHA&date=yesterday").status_code == 422
    assert "postponed_until" in client.post("/api/standups/postpone", json={"project": "ALPHA", "date": "2601-01"}).json()


def test_the_hook_says_when_yesterday_is_owed(tmp_path: Path) -> None:
    capture = _hook()
    root = tmp_path / "data"
    (root / "projects" / "ALPHA").mkdir(parents=True)
    assert capture._standup_owed(root, "ALPHA") is None            # no messages yesterday: nothing owed
    day = _yesterday_chat(root)

    owed = capture._standup_owed(root, "ALPHA")
    assert {k: v for k, v in owed.items() if k != "chars"} == {"date": day, "messages_n": 2, "chats_n": 1, "model": "opus", "map_model": "opus", "ask": True} and owed["chars"] > 0
    note = capture.format_signals({"standup_due": owed})
    assert f"no standup for {day}: 2 messages in 1 chat." in note and "Ask the user" in note and "daily-standup" in note

    # A new chat is told too, once: the standup is the project's.
    cap = capture.TurnCapture(root, "ALPHA", "cc-newtoday")
    assert cap.open_turn("good morning")["standup_due"]["date"] == day
    cap.complete_turn("hi")
    assert cap.open_turn("next")["standup_due"] is None

    # Postponed by the operator, claimed by another agent, or written: not owed.
    (root / "standup_state.json").write_text(json.dumps(
        {f"ALPHA|{day}": {"postponed_until": datetime.now().timestamp() + 3600}}), encoding="utf-8")
    assert capture._standup_owed(root, "ALPHA") is None
    (root / "standup_state.json").write_text(json.dumps(
        {f"ALPHA|{day}": {"claim": {"agent_id": "cc-x", "at": datetime.now().timestamp()}}}), encoding="utf-8")
    assert capture._standup_owed(root, "ALPHA") is None
    (root / "standup_state.json").unlink()
    (root / "standups.csv").write_text(f"id,project,created_date,for_date\nst_1,ALPHA,2601-01,{day}\n", encoding="utf-8")
    assert capture._standup_owed(root, "ALPHA") is None

    # An older standup names no day: written today, it covers yesterday.
    today = f"{datetime.now():%y%m-%d}"
    (root / "standups.csv").write_text(f"id,project,created_date\nst_old,ALPHA,{today}\n", encoding="utf-8")
    assert capture._standup_owed(root, "ALPHA") is None
    (root / "standups.csv").write_text(f"id,project,created_date\nst_old,ALPHA,{day}\n", encoding="utf-8")
    assert capture._standup_owed(root, "ALPHA") is not None      # written yesterday: it covers the day before

    # The operator's settings reach the notice.
    (root / "standups.csv").unlink()
    (root / "settings.json").write_text(json.dumps({"standup": {"model": "haiku", "ask": False}, "map": {"model": "sonnet"}}), encoding="utf-8")
    quiet = capture._standup_owed(root, "ALPHA")
    assert quiet["model"] == "haiku" and quiet["map_model"] == "sonnet" and quiet["ask"] is False
    assert "Write it now with a helper agent on haiku" in capture.format_signals({"standup_due": quiet})
    asked = capture.format_signals({"standup_due": {**quiet, "ask": True}})
    assert "1 write it with a helper agent on haiku (the Agent tool with model) and map the program with a helper agent on sonnet (the Agent tool with model) · 2 write only · 3 postpone; or another model: haiku, sonnet or opus" in asked


def test_the_built_in_skills_carry_the_contracts_writing_rules(client: TestClient) -> None:
    from backend import skilllib

    base = skilllib.BUILTIN_DIR
    md = skilllib._with_writing_rules((base / "log-a-decision" / "SKILL.md").read_text(encoding="utf-8"), base)
    assert skilllib.WRITING_RULES_MARK not in md and "Name the concrete thing" in md
    assert skilllib.checks(md, {}) == []
    assert skilllib.checks((base / "daily-standup" / "SKILL.md").read_text(encoding="utf-8"), {}) == []


def test_the_demo_data_holds_every_built_in_skill_as_it_is_now() -> None:
    """fixtures/ ships the built-in skills. A changed template is seeded into
    fixtures/ by any run with no data root set; commit those files with the
    template, or the demo shows an old skill and git status fills with noise."""
    import csv
    from pathlib import Path

    from backend import skilllib

    repo = Path(__file__).resolve().parents[2]
    rows = {r["name"]: r for r in csv.DictReader(open(repo / "fixtures" / "skills.csv", encoding="utf-8"))}
    for folder in sorted(p for p in skilllib.BUILTIN_DIR.iterdir() if (p / "SKILL.md").is_file()):
        assert folder.name in rows, f"fixtures/skills.csv lacks the built-in skill {folder.name}"
        kid = rows[folder.name]["id"]
        assert kid == skilllib.builtin_id(folder.name)
        kept = (repo / "fixtures" / "kept_versions" / f"{kid}.md").read_text(encoding="utf-8")
        now = skilllib._with_writing_rules((folder / "SKILL.md").read_text(encoding="utf-8"), skilllib.BUILTIN_DIR)
        first_step = next(ln for ln in now.splitlines() if ln.startswith("description:"))
        assert first_step.split(":", 1)[1].strip().strip('"')[:60] in kept, (
            f"fixtures hold an older {folder.name}: run the backend once with no data root, then commit fixtures/")


def test_a_days_numbers_are_counted_from_the_ledgers_and_git(client: TestClient, data_root) -> None:
    """Messages, tasks made and moved, decisions and the standup that covers
    the day come from the ledgers; commits from the project's repository.
    A drag on the board is not a change."""
    import subprocess

    from backend import daynumbers, gitwork, projectfacts
    from backend.csvio import append_row

    store = client.app.state.store
    root = Path(store.data_root)
    day = "2609-21"
    repo = git_repo(data_root.parent / "dayrepo")
    (repo / "a.py").write_text("1\n2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first", "--date", "2026-09-21T10:00:00"], cwd=repo, check=True,
                   env={**__import__("os").environ, "GIT_COMMITTER_DATE": "2026-09-21T10:00:00"})
    append_row(root / "integrations.csv", ("project", "path"), {"project": "ALPHA", "path": str(repo)})
    chat = root / "projects" / "ALPHA" / "chats" / "cc-day00001"
    chat.mkdir(parents=True, exist_ok=True)
    (chat / "meta.json").write_text(json.dumps({"agent_id": "cc-day00001"}), encoding="utf-8")
    (chat / "chat.md").write_text(
        "# Chat log\n\n---\n\n## Turn 1 · 2026-09-21T09:00:00\n**User**: hi\n**Agent**: hello\n\n---\n\n"
        "## Turn 2 · 2026-09-21T09:30:00\n**User**: go\n**Agent**: done\n", encoding="utf-8")
    tid = client.post("/api/tasks", json={"project": "ALPHA", "title": "Made today", "actor": "operator",
                                          "created_date": day}).json()["metadata"]["id"]
    client.post(f"/api/tasks/{tid}/update", json={"status": "done", "actor": "operator"})
    client.post(f"/api/tasks/{tid}/update", json={"position": 3, "actor": "operator"})
    client.post("/api/decisions", json={"created_date": day, "created_time": "10:00", "project": "ALPHA",
                                        "agent_id": "cc-x", "decision": "Yes.", "why": "Because."})
    client.post("/api/standups", json={"created_date": "2609-22", "created_time": "09:00", "project": "ALPHA",
                                       "agent_id": "cc-x", "summary": "A day.", "for_date": day})
    store.rebuild()
    gitwork.forget()
    projectfacts.forget()

    n = daynumbers.day(store, "ALPHA", day)
    today = datetime.now().strftime("%y%m-%d")
    assert n["messages_n"] == 2 and n["agents"] == ["cc-day00001"] and n["chats_n"] == 1
    assert n["tasks_created_n"] == 1 and n["decisions_n"] == 1 and n["standup_id"].startswith("st_")
    assert n["commits_n"] == 1 and n["files_n"] == 1 and n["lines_add"] == 2
    # The status change happened today, not on the 21st; the drag never counts.
    moved_today = daynumbers.day(store, "ALPHA", today)
    assert [c["field"] for t in moved_today["tasks"] for c in t["changes"]] == ["status"]
    assert moved_today["tasks_done_n"] == 1

    got = client.get("/api/standups/calendar?project=ALPHA&month=2026-09").json()
    assert got["days"][day]["commits_n"] == 1 and "tasks" not in got["days"][day]
    assert client.get("/api/standups/calendar?project=ALPHA&month=nope").status_code == 422
    mat = client.get(f"/api/standups/material?project=ALPHA&date={day}").json()
    assert mat["numbers"]["messages_n"] == 2 and isinstance(mat["tasks_changed"], list)
    assert "`numbers`" in mat["instructions"] and "`New:`" in mat["instructions"]


def test_material_gives_whole_answers_unless_the_operator_chose_clipped(client: TestClient) -> None:
    store = client.app.state.store
    then = datetime.now() - timedelta(days=1)
    d = Path(store.data_root) / "projects" / "ALPHA" / "chats" / "cc-long0001"
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({"agent_id": "cc-long0001"}), encoding="utf-8")
    middle = "THE MIDDLE OF THE WORK"
    answer = "start " + "x" * 2000 + middle + "y" * 2000 + " end"
    at = then.replace(hour=11, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%S")
    (d / "chat.md").write_text(f"# Chat log — cc-long0001\n\n---\n\n## Turn 1 · {at}\n**User**: go\n**Agent**: {answer}\n", encoding="utf-8")
    store.rebuild()
    day = standuplib.yymm_dd(then)

    whole = client.get(f"/api/standups/material?project=ALPHA&date={day}").json()
    turn = next(t for c in whole["chats"] if c["agent_id"] == "cc-long0001" for t in c["turns"])
    assert middle in turn["agent"] and whole["clipped"] is False
    assert whole["chars"]["full"] > whole["chars"]["clipped"]

    clipped = client.get(f"/api/standups/material?project=ALPHA&date={day}&clip=true").json()
    turn = next(t for c in clipped["chats"] if c["agent_id"] == "cc-long0001" for t in c["turns"])
    assert middle not in turn["agent"] and turn["agent"].startswith("start") and turn["agent"].endswith("end")


def test_a_standup_keeps_its_story_decisions_and_maybe_forgotten(client: TestClient) -> None:
    made = client.post("/api/standups", json={
        "created_date": "2610-08", "created_time": "09:00", "project": "ALPHA", "agent_id": "cc-story",
        "summary": "Scans cover each agent's own work.", "for_date": "2610-07",
        "story": "The day finished the rename.\n\nIn the evening the text was rewritten.",
        "movement": ["Changed: scans cover each agent's own work."],
        "decisions": ["A scan covers the asking agent's own work — two agents shared one window · operator, 00:00"],
        "forgotten": ["The Codex adapter was never run live."],
        "detail": "**Next:** the Russian pages.",
    })
    assert made.status_code in (200, 201), made.text
    sid = made.json()["metadata"]["id"]
    text = client.get(f"/api/standups/{sid}").json()["text"]
    assert text["story"].startswith("The day finished the rename.") and "\n\nIn the evening" in text["story"]
    assert text["decisions"] == ["A scan covers the asking agent's own work — two agents shared one window · operator, 00:00"]
    assert text["forgotten"] == ["The Codex adapter was never run live."]
    assert text["detail"] == "**Next:** the Russian pages."
    assert text["movement"] == ["Changed: scans cover each agent's own work."]


def test_the_day_record_lists_the_chats_and_the_tasks_they_named(client: TestClient) -> None:
    store = client.app.state.store
    day = _yesterday_chat(Path(store.data_root), "cc-dayrec01")
    made = client.post("/api/tasks", json={"project": "ALPHA", "title": "Make login work", "status": "todo"})
    tid = made.json().get("id") or made.json().get("task", {}).get("id") or made.json().get("metadata", {}).get("id")
    chat = Path(store.data_root) / "projects" / "ALPHA" / "chats" / "cc-dayrec01" / "chat.md"
    chat.write_text(chat.read_text(encoding="utf-8").replace("make login work", f"make login work ({tid})"), encoding="utf-8")
    store.rebuild()
    got = client.get(f"/api/standups/day?project=ALPHA&date={day}")
    assert got.status_code == 200, got.text
    rec = got.json()
    agent = next(a for a in rec["agents"] if a["agent_id"] == "cc-dayrec01")
    assert agent["turns_n"] == 2 and agent["chat"] == "auth-work" and tid in agent["tasks"]
    task = next(t for t in rec["tasks"] if t["id"] == tid)
    assert task["title"] == "Make login work" and task["agents"] == ["cc-dayrec01"]
    assert isinstance(rec["created"], list)


def test_a_standup_can_be_rewritten_and_a_part_changed_alone(client: TestClient) -> None:
    made = client.post("/api/standups", json={
        "created_date": "2610-08", "created_time": "09:30", "project": "ALPHA", "agent_id": "cc-rew",
        "summary": "Old summary.", "for_date": "2610-06",
        "story": "Old story.", "decisions": ["Keep A — reason · operator, 10:00"], "detail": "**Next:** x",
    }).json()
    sid = made["metadata"]["id"]
    r = client.post(f"/api/standups/{sid}/update", json={"summary": "New summary.", "story": "New story."})
    assert r.status_code == 200, r.text
    got = client.get(f"/api/standups/{sid}").json()
    assert got["metadata"]["l1"] == "New summary."
    assert got["text"]["story"] == "New story."
    assert got["text"]["decisions"] == ["Keep A — reason · operator, 10:00"]   # kept: not sent
    assert got["text"]["detail"] == "**Next:** x"
    lens = next(l for l in client.get("/api/schema").json()["lenses"] if l["name"] == "standup")
    assert lens["headline_mutable"] is True and "story" in lens["text_fields"]



def test_standup_by_hand_asks_which_model_first(tmp_path: Path) -> None:
    hook = _hook()
    (tmp_path / "settings.json").write_text(json.dumps({"standup": {"model": "haiku", "model_opencode": "bad name!"}}), encoding="utf-8")
    models = hook._helper_models(tmp_path)
    assert models["standup"] == {"claude": "haiku", "codex": "chat", "opencode": "chat"}
    assert models["map"]["claude"] == "opus"
    note = hook.format_signals({"commands": ["standup"], "helper_models": models})
    assert "#standup — ask the user now" in note and "helper agent on haiku" in note
    assert "Do not call standup_material" in note
