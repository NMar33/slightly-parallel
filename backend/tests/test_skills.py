"""Skills: #skill → a SKILL.md draft → versions and checks → copies Slightly Parallel installs and watches → usage."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from backend import keeplib, skilllib
from tests.conftest import make_chat

AGENT = "alpha-lead-2608-01"
_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"

GOOD = """---
name: cut-a-release
description: Cut a release of the app. Use when the operator asks to ship a version.
---

1. Run the tests: `pytest -q`.
2. Tag the commit: `git tag vX.Y.Z`.
3. Follow [the checklist](checklist.md).
"""


def _hook(module: str, filename: str):
    spec = importlib.util.spec_from_file_location(module, _HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module] = mod
    spec.loader.exec_module(mod)
    return mod


def _project(root: Path, tmp_path: Path) -> Path:
    folder = tmp_path / "proj"
    folder.mkdir()
    (root / "integrations.csv").write_text(f"project,path,created_date\nALPHA,{folder},2609-01\n", encoding="utf-8")
    return folder


def _new(client, **extra) -> str:
    r = client.post("/api/skills/new", json={"actor": "operator", "skill_md": GOOD,
                                             "files": {"checklist.md": "- tests pass\n"}, **extra})
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def test_the_hook_asks_for_a_draft_on_skill(tmp_path):
    capture = _hook("sp_capture_skills", "capture.py")
    cap = capture.TurnCapture(tmp_path / "data", "alpha", "cc-abc12345")
    signals = cap.open_turn("that worked, make it a skill #skill")
    sid = capture.keep_id("skill", "alpha", "cc-abc12345", 1)
    assert signals["kept"] == [{"kind": "skill", "id": sid, "route": "skills"}]
    assert f'MCP tool skill_draft {{id: "{sid}", skill_md, files}}' in capture.format_signals(signals)


def test_checks_say_what_stops_a_skill_from_working():
    assert skilllib.checks(GOOD, {"checklist.md": "- tests"}) == []
    texts = lambda md, files: [(c["level"], c["text"]) for c in skilllib.checks(md, files)]
    assert any(level == "error" and "--- block" in text for level, text in texts("just steps", {}))
    assert ("error", "The linked file is missing: checklist.md") in texts(GOOD, {})
    # A scheme is not a file path: a URL, a mailto:, or Slightly Parallel's image:1 in evidence.
    linked = GOOD.replace("[the checklist](checklist.md)", "[the notes](https://x.test/n) and ![shot](image:1)")
    assert [c for c in skilllib.checks(linked, {}) if c["level"] == "error"] == []
    vague = GOOD.replace(" Use when the operator asks to ship a version.", "")
    assert any(level == "warning" and "when to use" in text for level, text in texts(vague, {"checklist.md": "x"}))
    secret = GOOD + "\nexport KEY=sk-abcdefghijklmnopqrstuvwxyz123456\n"
    assert any("secret" in text for _, text in texts(secret, {"checklist.md": "x"}))
    assert any("lowercase" in text for _, text in texts(GOOD.replace("cut-a-release", "Cut_Release"), {"checklist.md": "x"}))


def test_a_kept_skill_gets_a_draft_and_versions_and_names_stay_unique(client):
    root = Path(client.app.state.store.data_root)
    make_chat(root, "ALPHA", AGENT, [("2026-09-01T10:00:00", "the release went fine, make it a skill #skill", "ok")])
    client.app.state.store.rebuild()
    kid = keeplib.keep_id("skill", "ALPHA", AGENT, 1)

    assert client.post(f"/api/skills/{kid}/draft", json={"agent_id": "cc-x", "skill_md": "no block"}).status_code == 422
    assert client.post(f"/api/skills/{kid}/draft", json={
        "agent_id": "cc-x", "skill_md": GOOD, "files": {"../escape.sh": "x"}}).status_code == 422
    r = client.post(f"/api/skills/{kid}/draft", json={
        "agent_id": "cc-x", "skill_md": GOOD, "files": {"checklist.md": "- tests pass\n"}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["metadata"]["name"] == "cut-a-release" and d["metadata"]["status"] == "draft"
    assert d["skill"]["current"]["files"] == {"checklist.md": "- tests pass\n"} and d["skill"]["checks"] == []
    assert d["kept"]["message"] == "the release went fine, make it a skill"

    # No files in the body keeps the ones the skill has: a rewrite of
    # SKILL.md must never drop the scripts beside it.
    edited = client.post(f"/api/skills/{kid}/draft", json={
        "actor": "operator", "skill_md": GOOD.replace("Tag the commit", "Tag the release commit"),
        "note": "clearer"}).json()
    assert [v["how"] for v in edited["kept"]["versions"]] == ["interpreted", "edited"]
    assert edited["skill"]["current"]["files"] == {"checklist.md": "- tests pass\n"}
    # An empty object is how they are removed.
    bare = client.post(f"/api/skills/{kid}/draft", json={
        "actor": "operator", "skill_md": GOOD.replace("Follow [the checklist](checklist.md).", "Say what you skipped."),
        "files": {}, "note": "no files"}).json()
    assert bare["skill"]["current"]["files"] == {} and bare["skill"]["checks"] == []
    assert client.get(f"/api/skills/{kid}/versions/1").json()["skill_md"].count("Tag the commit") == 1

    clash = client.post("/api/skills/new", json={"actor": "operator", "skill_md": GOOD, "files": {"checklist.md": "x"}})
    assert clash.status_code == 422 and "already named" in clash.text
    assert client.post("/api/skills/new", json={"agent_id": "cc-x", "skill_md": GOOD}).status_code == 422


def test_installed_copies_are_written_watched_and_taken_back(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    kid = _new(client)
    dests = [folder / ".claude" / "skills" / "cut-a-release", folder / ".agents" / "skills" / "cut-a-release"]

    assert client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA", "agent_id": "cc-x"}).status_code == 422
    assert client.post(f"/api/skills/{kid}/install", json={"project": "NOPE", "actor": "operator"}).status_code == 404
    dry = client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA", "dry_run": True}).json()
    assert dry["action"] == "created" and not dests[0].exists()

    assert client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"}).json()["action"] == "created"
    for dest in dests:
        assert (dest / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: cut-a-release")
        assert (dest / "checklist.md").exists() and (dest / ".sp-skill.json").exists()

    def status() -> list[str]:
        return [i["status"] for i in client.get(f"/api/skills/{kid}").json()["skill"]["installs"]]

    assert status() == ["fresh"]
    client.post(f"/api/skills/{kid}/draft", json={"actor": "operator", "skill_md": GOOD.replace("pytest -q", "pytest -x"),
                                                   "files": {"checklist.md": "- tests pass\n"}})
    assert status() == ["stale"]
    assert client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"}).json()["action"] == "updated"
    assert status() == ["fresh"]

    (dests[0] / "SKILL.md").write_text(GOOD.replace("pytest -q", "pytest -x") + "4. Announce it.\n", encoding="utf-8")
    (dests[0] / "checklist.md").write_text("- tests pass\n- the tag is pushed\n", encoding="utf-8")
    assert status() == ["changed"]
    changed = client.get(f"/api/skills/{kid}").json()["skill"]["installs"][0]
    assert changed["differs"] == ["SKILL.md", "checklist.md"]
    copy = client.get(f"/api/skills/{kid}/copy", params={"project": "ALPHA"}).json()
    assert "Announce it" in copy["skill_md"] and copy["files"]["checklist.md"].endswith("tag is pushed\n")
    assert client.get(f"/api/skills/{kid}/copy", params={"project": "NOPE"}).status_code == 404
    (dests[0] / "checklist.md").write_text("- tests pass\n", encoding="utf-8")
    kept = client.post(f"/api/skills/{kid}/keep-disk", json={"project": "ALPHA"}).json()
    assert kept["kept"]["versions"][-1]["note"] == "Taken from ALPHA" and "Announce it" in kept["skill"]["current"]["skill_md"]
    assert status() == ["fresh"] and "Announce it" in (dests[1] / "SKILL.md").read_text(encoding="utf-8")

    removed = client.post(f"/api/skills/{kid}/uninstall", json={"project": "ALPHA"}).json()["removed"]
    assert len(removed) == 2 and not any(d.exists() for d in dests) and status() == []


def test_install_state_is_never_served_from_the_cache(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    kid = _new(client)

    def etag() -> str:
        return client.get(f"/api/skills/{kid}").headers["etag"]

    first = etag()
    assert client.get(f"/api/skills/{kid}", headers={"If-None-Match": first}).status_code == 304

    client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"})
    after_install = etag()
    assert after_install != first

    # A hand edit inside the project folder: the data root never sees it.
    dest = folder / ".claude" / "skills" / "cut-a-release" / "SKILL.md"
    dest.write_text(dest.read_text(encoding="utf-8") + "\n4. Tell the team.\n", encoding="utf-8")
    after_edit = etag()
    assert after_edit != after_install
    assert client.get(f"/api/skills/{kid}", headers={"If-None-Match": after_install}).status_code == 200

    assert client.post(f"/api/skills/{kid}/uninstall", json={"project": "ALPHA", "force": True}).status_code == 200
    assert etag() != after_edit


def test_an_edited_copy_is_never_overwritten_or_removed_by_accident(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    kid = _new(client)
    client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"})
    dest = folder / ".claude" / "skills" / "cut-a-release"
    (dest / "SKILL.md").write_text(GOOD + "4. Tell the team.\n", encoding="utf-8")

    dry = client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA", "dry_run": True}).json()
    assert dry["action"] == "changed" and dry["edited"] == [str(dest)]
    r = client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"})
    assert r.status_code == 422 and "edited after Slightly Parallel wrote it" in r.text
    assert "Tell the team" in (dest / "SKILL.md").read_text(encoding="utf-8"), "the edit is still there"
    r = client.post(f"/api/skills/{kid}/uninstall", json={"project": "ALPHA"})
    assert r.status_code == 422 and dest.exists()

    forced = client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA", "force": True}).json()
    assert forced["action"] == "overwritten"
    assert "Tell the team" not in (dest / "SKILL.md").read_text(encoding="utf-8")
    assert client.post(f"/api/skills/{kid}/uninstall", json={"project": "ALPHA"}).json()["removed"] == [
        str(dest), str(folder / ".agents" / "skills" / "cut-a-release"),
    ]
    assert client.post(f"/api/skills/{kid}/uninstall", json={"project": "ALPHA"}).json() == {"removed": []}


def test_a_binary_file_in_a_copy_is_named_and_never_round_tripped(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    kid = _new(client)
    client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"})
    dest = folder / ".claude" / "skills" / "cut-a-release"
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe"
    (dest / "shot.png").write_bytes(png)

    install = client.get(f"/api/skills/{kid}").json()["skill"]["installs"][0]
    assert install["status"] == "changed" and install["differs"] == ["shot.png"]
    copy = client.get(f"/api/skills/{kid}/copy", params={"project": "ALPHA"}).json()
    assert copy["skipped"] == ["shot.png"] and "shot.png" not in copy["files"]
    r = client.post(f"/api/skills/{kid}/keep-disk", json={"project": "ALPHA"})
    assert r.status_code == 422 and "shot.png" in r.text and "not a text file" in r.text
    assert (dest / "shot.png").read_bytes() == png
    assert client.get(f"/api/skills/{kid}").json()["skill"]["current"]["n"] == 1, "no version was made of it"


def test_keep_disk_takes_the_copy_that_was_edited(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    kid = _new(client)
    client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"})
    claude = folder / ".claude" / "skills" / "cut-a-release"
    agents = folder / ".agents" / "skills" / "cut-a-release"
    (agents / "SKILL.md").write_text(GOOD + "4. Codex says so.\n", encoding="utf-8")
    kept = client.post(f"/api/skills/{kid}/keep-disk", json={"project": "ALPHA"}).json()
    assert "Codex says so" in kept["skill"]["current"]["skill_md"]
    assert "Codex says so" in (claude / "SKILL.md").read_text(encoding="utf-8"), "both copies now hold it"

    (claude / "SKILL.md").write_text(GOOD + "5. Claude.\n", encoding="utf-8")
    (agents / "SKILL.md").write_text(GOOD + "5. Codex.\n", encoding="utf-8")
    r = client.post(f"/api/skills/{kid}/keep-disk", json={"project": "ALPHA"})
    assert r.status_code == 422 and "both copies were edited" in r.text
    kept = client.post(f"/api/skills/{kid}/keep-disk", json={"project": "ALPHA", "path": str(agents)}).json()
    assert "5. Codex." in kept["skill"]["current"]["skill_md"]


def test_file_paths_that_would_break_the_folder_are_refused_before_anything_is_written(client):
    def new(files):
        return client.post("/api/skills/new", json={"actor": "operator", "skill_md": GOOD, "files": files})

    assert new({".": "x"}).status_code == 422
    assert new({"a/../b.md": "x"}).status_code == 422
    r = new({"a": "x", "a/b.md": "y"})
    assert r.status_code == 422 and "both a file and a folder" in r.text
    mine = [s for s in client.get("/api/skills").json()["skills"] if s.get("source") != "builtin"]
    assert mine == [], "a refused skill leaves no row behind"
    assert new({"big.md": "x" * 200_001}).status_code == 422

    kid = _new(client)
    for _ in range(2):
        client.post(f"/api/skills/{kid}/draft", json={"actor": "operator", "skill_md": GOOD,
                                                       "files": {"checklist.md": "- tests\r\n- tag\r\n"}})
    assert client.get(f"/api/skills/{kid}").json()["skill"]["current"]["n"] == 2, "CRLF twice is one version"


def test_usage_is_never_served_from_the_cache_after_a_backfill(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    make_chat(root, "ALPHA", AGENT, [("2026-09-01T10:00:00", "ship it #skill", "done")])
    kid = _new(client)
    first = client.get(f"/api/skills/{kid}")
    assert client.get(f"/api/skills/{kid}", headers={"If-None-Match": first.headers["etag"]}).status_code == 304
    uses = root / "projects" / "ALPHA" / "chats" / AGENT / "skills.jsonl"
    uses.write_text(json.dumps({"turn": 1, "at": "2026-09-01T10:00:05", "skill": "cut-a-release", "how": "auto"}) + "\n",
                    encoding="utf-8")
    client.app.state.store.rebuild()  # what the watcher does when the hook appends a use
    r = client.get(f"/api/skills/{kid}", headers={"If-None-Match": first.headers["etag"]})
    assert r.status_code == 200 and r.json()["skill"]["usage"]["uses"] == 1


def test_a_name_stays_unique_while_an_archived_skill_holds_it(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    _project(root, tmp_path)
    a = _new(client)
    client.post(f"/api/skills/{a}/install", json={"project": "ALPHA"})
    client.post(f"/api/skills/{a}/update", json={"actor": "operator", "status": "archived"})
    r = client.post("/api/skills/new", json={"actor": "operator", "skill_md": GOOD})
    assert r.status_code == 422 and "archived skill is already named cut-a-release" in r.text
    b = _new(client, skill_md=GOOD.replace("name: cut-a-release", "name: cut-a-release-2"))
    theirs = client.post(f"/api/skills/{b}/install", json={"project": "ALPHA", "dry_run": True}).json()
    assert theirs["action"] == "created"


def test_the_hook_records_a_use_once_however_often_stop_is_retried(tmp_path):
    cap = _hook("sp_capture_dedupe", "capture.py")
    tc = cap.TurnCapture(tmp_path / "data", "alpha", "cc-abc12345")
    uses = [{"skill": "cut-a-release", "at": "2026-09-01T10:00:05", "how": "auto"}]
    tc.record_skills(uses)
    tc.record_skills(uses)
    tc.record_skills([{"skill": "cut-a-release", "at": "2026-09-01T10:00:09", "how": "typed"}])
    lines = (tc.folder / "skills.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_the_two_builtin_command_lists_are_one():
    from backend import hookshared

    cc = _hook("sp_cc_builtins", "claude-code-capture.py")
    # One list, in hookshared.py: the hook loads that file by path, the
    # backfill here imports it.
    assert cc._BUILTINS == hookshared.BUILTIN_COMMANDS and "branch" in cc._BUILTINS
    assert skilllib.uses_in_record is hookshared.skill_uses


def test_the_example_skill_is_shown_but_never_installed(client, tmp_path):
    from backend import examples

    root = Path(client.app.state.store.data_root)
    _project(root, tmp_path)
    assert "sk_e0000001" in examples.seed(client.app.state.store)

    d = client.get("/api/skills/sk_e0000001").json()
    assert d["metadata"]["source"] == "demo" and d["metadata"]["name"] == "before-you-say-done"
    assert d["skill"]["current"]["skill_md"].startswith("---") and d["skill"]["checks"] == []
    # It reads like a kept skill: the operator's message and the turns around it.
    assert "make it a skill" in d["kept"]["message"] and len(d["kept"]["before"]) == 2

    r = client.post("/api/skills/sk_e0000001/install", json={"project": "ALPHA"})
    assert r.status_code == 422 and "example" in r.text
    assert not (tmp_path / "proj" / ".claude").exists()

    assert "sk_e0000001" in client.post("/api/examples/remove", json={}).json()["removed"]
    assert client.get("/api/skills/sk_e0000001").status_code == 404


def test_install_never_overwrites_a_folder_slightly_parallel_did_not_write(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    theirs = folder / ".claude" / "skills" / "cut-a-release"
    theirs.mkdir(parents=True)
    (theirs / "SKILL.md").write_text("mine", encoding="utf-8")
    kid = _new(client)
    r = client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"})
    assert r.status_code == 422 and "did not write" in r.text
    assert (theirs / "SKILL.md").read_text(encoding="utf-8") == "mine"


def test_all_projects_installs_into_the_home_folders(client, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows reads this one
    kid = _new(client)
    dests = [home / ".claude" / "skills" / "cut-a-release", home / ".agents" / "skills" / "cut-a-release"]

    assert client.post(f"/api/skills/{kid}/install", json={"project": "all"}).json()["action"] == "created"
    assert all((d / "SKILL.md").is_file() for d in dests)
    installs = client.get(f"/api/skills/{kid}").json()["skill"]["installs"]
    assert [(i["project"], i["status"]) for i in installs] == [("all", "fresh")]

    client.post(f"/api/skills/{kid}/draft", json={"actor": "operator", "skill_md": GOOD.replace("pytest -q", "pytest -x"),
                                                   "files": {"checklist.md": "- tests pass\n"}})
    assert client.get(f"/api/skills/{kid}").json()["skill"]["installs"][0]["status"] == "stale"
    assert client.post(f"/api/skills/{kid}/install", json={"project": "all"}).json()["action"] == "updated"
    assert len(client.post(f"/api/skills/{kid}/uninstall", json={"project": "all"}).json()["removed"]) == 2
    assert not any(d.exists() for d in dests)


def test_skills_already_on_disk_are_found_and_taken_in(client, tmp_path, monkeypatch):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows reads this one
    hand = """---
name: hand-made
description: A skill written by hand. Use when the operator asks for the old checklist.
---

1. Do the thing.
"""
    for base in (home / ".claude/skills/hand-made", folder / ".agents/skills/hand-made"):
        base.mkdir(parents=True)
        (base / "SKILL.md").write_text(hand, encoding="utf-8")
        (base / "notes.md").write_text("the old checklist\n", encoding="utf-8")
    no_block = folder / ".claude/skills/older-one"
    no_block.mkdir(parents=True)
    (no_block / "SKILL.md").write_text("Steps we always follow.\n", encoding="utf-8")
    mine = _new(client)  # what Slightly Parallel writes is not "found"
    client.post(f"/api/skills/{mine}/install", json={"project": "ALPHA"})

    found = client.get("/api/skills/found").json()["found"]
    by_name = {f["name"]: f for f in found}
    assert "cut-a-release" not in by_name
    assert [w["project"] for w in by_name["hand-made"]["where"]] == ["all", "ALPHA"]
    assert by_name["hand-made"]["files_n"] == 1 and by_name["hand-made"]["clash"] is False

    assert client.post("/api/skills/import", json={"path": str(tmp_path / "elsewhere")}).status_code == 404
    taken = client.post("/api/skills/import", json={"path": str(home / ".claude/skills/hand-made")})
    assert taken.status_code == 201, taken.text
    d = taken.json()
    assert d["metadata"]["name"] == "hand-made" and d["metadata"]["source"] == "imported"
    assert d["skill"]["current"]["files"] == {"notes.md": "the old checklist\n"}
    assert (home / ".claude/skills/hand-made/SKILL.md").exists()  # the folder is left as it was
    assert {f["name"]: f["clash"] for f in client.get("/api/skills/found").json()["found"]}["hand-made"] is True

    # A folder with no --- block still comes in: the folder name becomes the name.
    older = client.post("/api/skills/import", json={"path": str(no_block)}).json()
    assert older["metadata"]["name"] == "older-one"
    assert "Steps we always follow." in older["skill"]["current"]["skill_md"]


def test_usage_counts_the_chat_and_past_claude_logs(client, tmp_path):
    root = Path(client.app.state.store.data_root)
    folder = _project(root, tmp_path)
    make_chat(root, "ALPHA", "cc-abc12345", [
        ("2026-09-01T10:00:00", "ship it", "done"),
        ("2026-09-01T10:05:00", "again", "done"),
    ])
    kid = _new(client)
    (root / "projects/ALPHA/chats/cc-abc12345/skills.jsonl").write_text(
        json.dumps({"turn": 1, "at": "2026-09-01T10:00:30", "skill": "cut-a-release", "how": "auto"}) + "\n",
        encoding="utf-8")
    logs = tmp_path / "claude" / "proj"
    logs.mkdir(parents=True)
    base = {"sessionId": "abc12345-0000", "cwd": str(folder)}
    records = [
        {**base, "type": "user", "timestamp": "2026-09-01T10:05:10",
         "message": {"role": "user", "content": "<command-name>/cut-a-release</command-name>"}},
        {**base, "type": "assistant", "timestamp": "2026-09-01T10:05:20",
         "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "artifact-design"}}]}},
        {**base, "type": "user", "timestamp": "2026-09-01T10:05:30",
         "message": {"role": "user", "content": "<command-name>/branch</command-name>"}},
        {**base, "type": "user", "timestamp": "2026-09-01T10:05:40",
         "message": {"role": "user", "content": "logs show <command-name>/quoted</command-name> for typed commands"}},
    ]
    (logs / "s.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    store = client.app.state.store
    assert skilllib.backfill(store, claude_root=tmp_path / "claude")["added"] == 2
    assert skilllib.backfill(store, claude_root=tmp_path / "claude")["added"] == 0

    u = client.get("/api/skills/usage").json()
    assert u["skills"]["cut-a-release"]["uses"] == 2 and u["skills"]["cut-a-release"]["typed"] == 1
    assert [x["name"] for x in u["unknown"]] == ["artifact-design"]
    detail = client.get(f"/api/skills/{kid}").json()["skill"]["usage"]
    assert detail["uses"] == 2 and all(s["session_id"] for s in detail["sessions"])
    assert sorted(s["turn"] for s in detail["sessions"]) == [1, 2]


def test_the_hook_records_the_skills_that_ran_in_the_turn(tmp_path):
    cc = _hook("sp_cc_capture_skills", "claude-code-capture.py")
    transcript = tmp_path / "t.jsonl"
    records = [
        {"type": "user", "timestamp": "2026-09-01T09:00:00", "message": {"role": "user", "content": "earlier"}},
        {"type": "assistant", "timestamp": "2026-09-01T09:00:05",
         "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "old-one"}}]}},
        {"type": "user", "timestamp": "2026-09-01T10:00:00", "message": {"role": "user", "content": "do it"}},
        {"type": "assistant", "timestamp": "2026-09-01T10:00:05",
         "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "cut-a-release"}}]}},
        {"type": "user", "timestamp": "2026-09-01T10:00:06",
         "message": {"content": [{"type": "tool_result", "content": "Launching skill"}]}},
    ]
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    uses = cc.skills_in_turn(str(transcript))
    assert [(u["skill"], u["how"]) for u in uses] == [("cut-a-release", "auto")]

    capture = sys.modules["capture"]
    cap = capture.TurnCapture(tmp_path / "data", "alpha", "cc-abc12345")
    cap.open_turn("do it")
    cap.record_skills(uses)
    line = json.loads((tmp_path / "data/projects/alpha/chats/cc-abc12345/skills.jsonl").read_text().splitlines()[0])
    assert line["turn"] == 1 and line["skill"] == "cut-a-release" and line["at"] == "2026-09-01T10:00:05"


def test_an_install_that_wrote_nothing_leaves_the_stamp_alone(client, tmp_path):
    """`written_at` is when Slightly Parallel last wrote the files. Stamping it on an
    install that changed nothing rewrote skill_installs.json on every server
    start and left the repository dirty for a time nobody touched."""
    import json

    root = Path(client.app.state.store.data_root)
    _project(root, tmp_path)
    kid = _new(client)
    ledger = root / "skill_installs.json"

    def row() -> dict:
        rows = json.loads(ledger.read_text(encoding="utf-8"))
        rows = rows.get("installs", rows) if isinstance(rows, dict) else rows
        return next(r for r in rows if r["skill_id"] == kid)

    assert client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"}).json()["action"] == "created"
    first = row()
    before = ledger.read_bytes()

    again = client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"}).json()
    assert again["action"] == "unchanged"
    assert row() == first and ledger.read_bytes() == before        # not one byte moved

    # A real write records the version it wrote. (The stamp has one-second
    # resolution, so within a test it can equal the first one.)
    client.post(f"/api/skills/{kid}/draft", json={"actor": "operator",
                                                  "skill_md": GOOD.replace("pytest -q", "pytest -vv")})
    assert client.post(f"/api/skills/{kid}/install", json={"project": "ALPHA"}).json()["action"] == "updated"
    assert row()["version"] > first["version"] and ledger.read_bytes() != before
