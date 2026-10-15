"""The contract as parts — composed into SLIGHTLY-PARALLEL.md, edited one block at a time.

1. Parts compose in filename order; headings go before bodies; the
   commands table is generated from the parts' rows.
2. With a parts folder, SLIGHTLY-PARALLEL.md is read-only through the API; a part
   save (body only) or switch recomposes the file, with versions kept.
3. The committed SLIGHTLY-PARALLEL.md equals the composition of the committed parts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.contract_parts import compose, load_parts, parse_part, render_part
from backend.server import create_app

_REPO = Path(__file__).resolve().parents[2]

PREAMBLE = "---\nkey: preamble\ntitle: Preamble\nenabled: true\n---\n\n# Contract\n\nRead me.\n"
CAPTURE = (
    "---\nkey: capture\nsection: 1\nheading: ## 1. Capture\ntitle: Capture\nenabled: true\n"
    "command: /scan | Post a scan\n---\n\nYour chat is captured.\n"
)
COMMANDS = (
    "---\nkey: commands\nsection: 2\nheading: ## 2. Commands\ntitle: Commands\nenabled: true\n---\n\n"
    "When the user types one of these:\n\n<!-- commands -->\n\nThat is all.\n"
)
TASK = (
    "---\nkey: task\nsection: 4\ntitle: Agent task\nenabled: true\n"
    "command: /task <hint> | Write the task\ncommand: /drop | Drop it\n---\n\nOnly on /task.\n"
)


def _write_parts(repo: Path) -> None:
    d = repo / "prompts" / "contract"
    d.mkdir(parents=True)
    (d / "00-preamble.md").write_text(PREAMBLE, encoding="utf-8")
    (d / "10-capture.md").write_text(CAPTURE, encoding="utf-8")
    (d / "20-commands.md").write_text(COMMANDS, encoding="utf-8")
    (d / "40-task.md").write_text(TASK, encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. composition
# ---------------------------------------------------------------------------


def test_parse_and_render_round_trip() -> None:
    p = parse_part(TASK, "40-task.md")
    assert (p.key, p.section, p.title, p.enabled) == ("task", "4", "Agent task", True)
    assert p.commands == [("/task <hint>", "Write the task"), ("/drop", "Drop it")]
    assert p.body == "Only on /task.\n" and p.order == 40
    assert render_part(p) == TASK
    bare = parse_part("no frontmatter at all\n", "99-bare.md")
    assert bare.key == "bare" and bare.body == "no frontmatter at all\n"


def test_compose_orders_headings_and_generates_the_table(tmp_path: Path) -> None:
    _write_parts(tmp_path)
    parts = load_parts(tmp_path)
    assert [p.key for p in parts] == ["preamble", "capture", "commands", "task"]
    text = compose(parts)
    assert text == (
        "# Contract\n\nRead me.\n\n"
        "## 1. Capture\n\nYour chat is captured.\n\n"
        "## 2. Commands\n\nWhen the user types one of these:\n\n"
        "| Command | What you do |\n|---|---|\n"
        "| `/scan` | Post a scan |\n| `/task <hint>` | Write the task |\n| `/drop` | Drop it |\n\n"
        "That is all.\n\n"
        "Only on /task.\n"
    )
    parts[3].enabled = False
    off = compose(parts)
    assert "Only on /task." not in off and "/task <hint>" not in off and "/scan" in off


# ---------------------------------------------------------------------------
# 2. the API
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    repo = tmp_path / "repo"
    (repo / "templates").mkdir(parents=True)
    (repo / "templates" / "agents-block.md").write_text("## Slightly Parallel\n", encoding="utf-8")
    _write_parts(repo)
    (repo / "SLIGHTLY-PARALLEL.md").write_text(compose(load_parts(repo)), encoding="utf-8")
    app = create_app(data_root=data_root, watch=False, prompt_root=repo)
    with TestClient(app) as client:
        yield client, data_root, repo


def test_detail_carries_the_parts_and_the_file_is_read_only(env) -> None:
    client, _root, repo = env
    files = client.get("/api/prompts").json()["files"]
    assert files[0]["composed"] is True and files[0]["parts_n"] == 4
    d = client.get("/api/prompts/contract").json()
    assert d["text"] == (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")
    keys = [p["key"] for p in d["parts"]]
    assert keys == ["contract.preamble", "contract.capture", "contract.commands", "contract.task"]
    task = d["parts"][3]
    assert task["text"] == "Only on /task.\n" and task["enabled"] is True
    assert task["commands"] == [{"cmd": "/task <hint>", "what": "Write the task"}, {"cmd": "/drop", "what": "Drop it"}]
    assert task["is_original"] is True and task["original"] is None
    r = client.post("/api/prompts/contract", json={"text": "# whole\n"})
    assert r.status_code == 422 and "part" in r.json()["detail"]
    assert client.post("/api/prompts/contract/restore", json={"version": "original"}).status_code == 422
    assert client.get("/api/prompts/contract.nope").status_code == 404


def test_saving_a_part_recomposes_and_keeps_versions(env) -> None:
    client, root, repo = env
    r = client.post("/api/prompts/contract.task", json={"text": "Only on /task. Never alone.\n", "note": "tighter"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action"] == "saved" and out["text"] == "Only on /task. Never alone.\n"
    assert out["has_original"] and not out["is_original"]
    # the live contract changed; the part file kept its frontmatter
    live = (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")
    assert live.endswith("Only on /task. Never alone.\n") and "| `/task <hint>` |" in live
    on_disk = (repo / "prompts" / "contract" / "40-task.md").read_text(encoding="utf-8")
    assert on_disk.startswith("---\nkey: task\nsection: 4\n") and on_disk.endswith("Never alone.\n")
    # versions and the original speak the body, not the frontmatter
    vid = out["versions"][0]["id"]
    assert client.get(f"/api/prompts/contract.task/versions/{vid}").json()["text"] == "Only on /task.\n"
    assert client.get("/api/prompts/contract.task/versions/original").json()["text"] == "Only on /task.\n"
    assert (root / "prompts" / "contract.task" / "original.md").read_text(encoding="utf-8") == TASK
    # restore puts the body back and recomposes
    r = client.post("/api/prompts/contract.task/restore", json={"version": "original"})
    assert r.status_code == 200 and r.json()["is_original"] is True
    assert (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8").endswith("Only on /task.\n")
    # blank is refused
    assert client.post("/api/prompts/contract.task", json={"text": " \n"}).status_code == 422


def test_switching_a_part_off_drops_its_block_and_its_rows(env) -> None:
    client, _root, repo = env
    r = client.post("/api/prompts/contract.task", json={"enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False and r.json()["action"] == "saved"
    live = (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")
    assert "Only on /task." not in live and "/task <hint>" not in live and "| `/scan` |" in live
    again = client.post("/api/prompts/contract.task", json={"enabled": False}).json()
    assert again["action"] == "unchanged"
    back = client.post("/api/prompts/contract.task", json={"enabled": True}).json()
    assert back["enabled"] is True and "Only on /task." in (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")
    assert client.post("/api/prompts/agents-block", json={"enabled": False}).status_code == 422
    assert client.post("/api/prompts/contract.task", json={}).status_code == 422


def test_a_plain_contract_file_without_parts_still_edits_whole(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    repo = tmp_path / "repo"
    (repo / "templates").mkdir(parents=True)
    (repo / "templates" / "agents-block.md").write_text("## Slightly Parallel\n", encoding="utf-8")
    (repo / "SLIGHTLY-PARALLEL.md").write_text("# plain\n", encoding="utf-8")
    app = create_app(data_root=data_root, watch=False, prompt_root=repo)
    with TestClient(app) as client:
        d = client.get("/api/prompts/contract").json()
        assert d["composed"] is False and "parts" not in d
        assert client.post("/api/prompts/contract", json={"text": "# plain v2\n"}).json()["action"] == "saved"


# ---------------------------------------------------------------------------
# 3. the repo
# ---------------------------------------------------------------------------


def test_the_committed_contract_is_the_composition_of_its_parts() -> None:
    parts = load_parts(_REPO)
    assert len(parts) >= 15
    assert (_REPO / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8") == compose(parts)
