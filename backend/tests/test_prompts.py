"""Agent prompt files from Settings: edit, keep the original, version, restore."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def env(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    repo = tmp_path / "repo"
    (repo / "templates").mkdir(parents=True)
    (repo / "SLIGHTLY-PARALLEL.md").write_text("# Contract v1\n\nPost a scan when asked.\n", encoding="utf-8")
    (repo / "templates" / "agents-block.md").write_text("## Slightly Parallel\n- Project code: `$project_code`\n", encoding="utf-8")
    app = create_app(data_root=data_root, watch=False, prompt_root=repo)
    with TestClient(app) as client:
        yield client, data_root, repo


def test_list_and_detail_before_any_edit(env) -> None:
    client, _root, repo = env
    files = client.get("/api/prompts").json()["files"]
    assert [f["key"] for f in files] == ["contract", "agents-block"]
    m = files[0]
    assert m["path"] == str(repo / "SLIGHTLY-PARALLEL.md") and m["exists"] and m["lines"] == 3
    assert m["has_original"] is False and m["is_original"] is True and m["versions_n"] == 0
    d = client.get("/api/prompts/contract").json()
    assert d["text"].startswith("# Contract v1") and d["versions"] == []
    assert client.get("/api/prompts/nope").status_code == 404


def test_save_keeps_the_original_and_a_version_then_restore_round_trips(env) -> None:
    client, root, repo = env
    v1 = (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")

    r = client.post("/api/prompts/contract", json={"text": "# Contract v2\n\nScans on /scan only.\n", "note": "scan rule"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action"] == "saved" and out["is_original"] is False and out["has_original"] is True
    assert (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8").startswith("# Contract v2")  # the live file
    assert (root / "prompts" / "contract" / "original.md").read_text(encoding="utf-8") == v1
    assert len(out["versions"]) == 1 and out["versions"][0]["note"] == "scan rule"
    vid = out["versions"][0]["id"]
    assert client.get(f"/api/prompts/contract/versions/{vid}").json()["text"] == v1
    assert client.get("/api/prompts/contract/versions/original").json()["text"] == v1

    # Saving the same text again is a no-op — no phantom version.
    same = client.post("/api/prompts/contract", json={"text": "# Contract v2\n\nScans on /scan only.\n"}).json()
    assert same["action"] == "unchanged" and len(same["versions"]) == 1

    r = client.post("/api/prompts/contract", json={"text": "# Contract v3\n", "note": "third"})
    assert len(r.json()["versions"]) == 2

    # Restore the original: the file is v1 again, and v3 is kept as a version.
    r = client.post("/api/prompts/contract/restore", json={"version": "original"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["action"] == "restored" and out["is_original"] is True
    assert (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8") == v1
    assert len(out["versions"]) == 3 and out["versions"][0]["note"].startswith("before restore")
    assert client.get(f"/api/prompts/contract/versions/{out['versions'][0]['id']}").json()["text"] == "# Contract v3\n"

    # Restore a specific version id.
    r = client.post("/api/prompts/contract/restore", json={"version": vid})
    assert (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8") == v1 and r.json()["action"] == "unchanged"
    assert client.post("/api/prompts/contract/restore", json={"version": "zzz"}).status_code == 404


def test_save_refuses_blank_non_string_and_oversized(env) -> None:
    client, _root, _repo = env
    assert client.post("/api/prompts/contract", json={"text": "   \n"}).status_code == 422
    assert client.post("/api/prompts/contract", json={"text": 5}).status_code == 422
    assert client.post("/api/prompts/contract", json={"text": "x" * (512 * 1024 + 1)}).status_code == 422


def test_edited_agents_block_template_is_what_setup_writes(env, tmp_path: Path) -> None:
    client, _root, _repo = env
    client.post("/api/prompts/agents-block", json={"text": "## Slightly Parallel\n- Code: `$project_code`\n- Hello from the template\n"})
    proj = tmp_path / "proj"
    proj.mkdir()
    r = client.post("/api/setup/integrate", json={
        "project_code": "my-app", "project_dir": str(proj),
        "write_agents": True, "write_claude_bridge": False, "write_claude_hooks": False,
    })
    assert r.status_code == 200, r.text


def test_the_old_key_merkhet_is_an_alias_and_an_old_folder_stays_in_use(env) -> None:
    # The contract's key was the working title until 2026-10-14: a caller
    # from before the rename gets the same record under the new key, and a
    # data root whose versions sit under prompts/merkhet/ keeps using them.
    client, root, repo = env
    v1 = (repo / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")
    (root / "prompts" / "merkhet").mkdir(parents=True)
    (root / "prompts" / "merkhet" / "original.md").write_text("# from before\n", encoding="utf-8")
    d = client.get("/api/prompts/merkhet").json()
    assert d["key"] == "contract" and d["text"] == v1 and d["has_original"] is True
    assert client.get("/api/prompts/merkhet/versions/original").json()["text"] == "# from before\n"
    r = client.post("/api/prompts/merkhet", json={"text": "# Contract v2\n", "note": "via the old key"})
    assert r.status_code == 200 and r.json()["key"] == "contract"
    assert not (root / "prompts" / "contract").exists()  # nothing moved, nothing split
    assert (root / "prompts" / "merkhet" / "history.json").exists()
    assert client.get("/api/prompts/contract").json()["versions"][0]["note"] == "via the old key"
    assert client.get("/api/prompts/merkhet.nope").status_code == 404
