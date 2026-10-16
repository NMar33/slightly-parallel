"""File-lens entries — the three layers that make them reproducible.

1. The API can store what the lens reads (``paths`` frontmatter), chains
   per project, and fills mechanics from git.
2. The scan response carries ``files_entry`` and a reminder until the
   entry exists.
3. The capture hook raises ``files_due`` once per uncovered scan.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.docs_md import build_detail
from backend.server import create_app
from tests.conftest import git_env

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


capture = _load("sp_capture_files", "capture.py")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    return r


@pytest.fixture()
def client(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _scan(client: TestClient, **over) -> dict:
    body = {
        "created_date": "2608-18", "created_time": "10:00", "project": "alpha",
        "agent_id": "cc-a", "l1": "auth shipped", "files_n": 2,
        "lines_add": 10, "lines_del": 2, "decisions_n": 0, "scope": "auth",
    }
    body.update(over)
    r = client.post("/api/scans", json=body)
    assert r.status_code in (200, 201), r.text      # 200 when the same scan is written again
    return r.json()


def _files(client: TestClient, scan_id: str, **over) -> dict:
    body = {
        "created_date": "2608-18", "created_time": "10:01", "project": "alpha",
        "agent_id": "cc-a", "l1": "2 files · +10/−2 · auth",
        "trigger_lens": "scan", "trigger_id": scan_id,
        "paths": [
            {"path": "app/auth.py", "importance": 5, "blast_radius": 9,
             "test_coverage": "covered", "why": "token path"},
            {"path": "app/main.py", "importance": 2, "why": "wiring"},
        ],
        "l2": "auth is the request gate now",
        "l3": ["app/auth.py — refresh()"],
    }
    body.update(over)
    r = client.post("/api/files", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# build_detail: frontmatter is real YAML now
# ---------------------------------------------------------------------------


def test_build_detail_emits_lists_and_quotes_scalars() -> None:
    doc = build_detail(
        {"l1": "note: colons and #hashes", "paths": [{"path": "a.py", "importance": 4}],
         "l2": "x"},
        "fl_test",
    )
    fm = yaml.safe_load(doc[3:doc.index("\n---", 3)])
    assert fm["l1"] == "note: colons and #hashes"
    assert fm["paths"] == [{"path": "a.py", "importance": 4}]
    assert "## L2" in doc


# ---------------------------------------------------------------------------
# Layer 1 — the API stores paths, chains per project, feeds the heatmap
# ---------------------------------------------------------------------------


def test_file_entry_round_trips_paths_and_feeds_heatmap(client: TestClient) -> None:
    scan = _scan(client)
    out = _files(client, scan["metadata"]["id"])
    fid = out["metadata"]["id"]
    assert fid.startswith("fl_")
    assert out.get("warnings", []) == []

    detail = client.get(f"/api/files/{fid}").json()
    assert [p["path"] for p in detail["paths"]] == ["app/auth.py", "app/main.py"]
    assert detail["paths"][0]["importance"] == 5
    assert detail["paths"][1]["action"] == "modified"

    heat = client.get("/api/files/heatmap?project=alpha").json()
    assert {f["path"] for f in heat["files"]} == {"app/auth.py", "app/main.py"}
    assert heat["matrix"]["app/auth.py||2608-18"]["entry_ids"] == [fid]


def test_rewording_a_file_entry_keeps_its_paths(client: TestClient) -> None:
    """The paths live in the document's head, not in a column: an update of
    the text must carry them over."""
    scan = _scan(client)
    fid = _files(client, scan["metadata"]["id"])["metadata"]["id"]
    r = client.post(f"/api/files/{fid}/update", json={"l2": "auth is the gate, reworded"})
    assert r.status_code == 200, r.text
    detail = client.get(f"/api/files/{fid}").json()
    assert detail["l2"] == "auth is the gate, reworded"
    assert [p["path"] for p in detail["paths"]] == ["app/auth.py", "app/main.py"]
    assert detail["paths"][0]["importance"] == 5
    assert detail["l3"] == ["app/auth.py — refresh()"]


def test_file_entries_chain_per_project(client: TestClient) -> None:
    (client.app.state.store.data_root / "projects" / "beta").mkdir(parents=True, exist_ok=True)
    a1 = _files(client, "sn_a1")["metadata"]["id"]
    b1 = _files(client, "sn_b1", project="beta", created_time="10:02")["metadata"]["id"]
    a2 = _files(client, "sn_a2", created_time="10:03")
    b2 = _files(client, "sn_b2", project="beta", created_time="10:04")
    assert a2["metadata"]["prev_file_id"] == a1
    assert b2["metadata"]["prev_file_id"] == b1


def test_file_entry_warnings_name_the_missing_judgment(client: TestClient) -> None:
    bare = _files(client, "sn_x", paths=[{"path": "a.py"}, "b.py"])
    assert any("judgment" in w for w in bare["warnings"])
    none = _files(client, "", created_time="10:05", paths=[])
    joined = " ".join(none["warnings"])
    assert "paths list" in joined and "trigger_id" in joined


# ---------------------------------------------------------------------------
# Layer 1b — git fills the mechanics when the project path is a repo
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True,
        env=git_env(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"),
    ).stdout.strip()


def test_git_fills_lines_actions_and_l4(client: TestClient, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "app").mkdir()
    (repo / "app" / "main.py").write_text("a\nb\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")

    root = client.app.state.store.data_root
    with open(root / "integrations.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["project", "path", "created_date"])
        w.writerow(["alpha", str(repo), "2608-18"])

    # First entry pins the range start; nothing to fill yet.
    first = _files(client, "sn_0", paths=[{"path": "app/main.py", "importance": 3}],
                   commit_to=base)
    assert first["metadata"]["id"]

    # Work: modify one file, create another (uncommitted), then post.
    (repo / "app" / "main.py").write_text("a\nb\nc\nd\n")
    (repo / "app" / "auth.py").write_text("x\ny\nz\n")
    out = _files(client, "sn_1", created_time="10:09", paths=[
        {"path": "app/main.py", "importance": 2, "why": "wiring"},
        {"path": "app/auth.py", "importance": 5, "why": "gate"},
    ])
    detail = client.get(f"/api/files/{out['metadata']['id']}").json()
    by = {p["path"]: p for p in detail["paths"]}
    assert by["app/main.py"]["lines_add"] == 2 and by["app/main.py"]["lines_del"] == 0
    assert by["app/auth.py"] == {**by["app/auth.py"], "lines_add": 3, "action": "created"}
    assert detail["commit_from"] == base and detail["dirty"] is True
    assert "app/main.py" in detail["l4"]


def test_non_git_project_degrades_to_agent_numbers(client: TestClient, tmp_path: Path) -> None:
    root = client.app.state.store.data_root
    plain = tmp_path / "plain"
    plain.mkdir()
    with open(root / "integrations.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["project", "path", "created_date"])
        w.writerow(["alpha", str(plain), "2608-18"])
    out = _files(client, "sn_p", paths=[{"path": "a.py", "lines_add": 7, "importance": 1}])
    detail = client.get(f"/api/files/{out['metadata']['id']}").json()
    assert detail["paths"][0]["lines_add"] == 7
    assert detail["commit_to"] == ""


# ---------------------------------------------------------------------------
# Layer 2 — the scan response reminds until the file entry exists
# ---------------------------------------------------------------------------


def test_scan_response_links_or_reminds(client: TestClient) -> None:
    scan = _scan(client)
    sid = scan["metadata"]["id"]
    assert scan["files_entry"] is None
    assert any(sid in w and "lens file" in w for w in scan["warnings"])

    fid = _files(client, sid)["metadata"]["id"]
    again = client.get(f"/api/scans/{sid}").json()
    assert again["files_entry"] == fid
    # Idempotent re-post now sees the link and stops nagging about files
    # (the architecture answer is still owed — that is its own reminder).
    re = _scan(client)
    assert re["files_entry"] == fid
    assert not any("lens file" in w for w in re["warnings"])


# ---------------------------------------------------------------------------
# Layer 3 — the hook notices an uncovered scan, once
# ---------------------------------------------------------------------------


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def test_hook_files_due_once_per_scan(root: Path) -> None:
    today = capture._yymm_dd(datetime.now())
    _write_csv(root / "scans.csv", ["id", "created_date", "created_time", "project"],
               [["sn_old", "2501-01", "09:00", "alpha"],
                ["sn_new", today, "09:00", "alpha"]])
    cap = capture.TurnCapture(root, "alpha", "cc-h")

    s1 = cap.open_turn("what next?")
    assert s1["files_due"] == "sn_new"
    assert "sn_new" in capture.format_signals(s1)
    cap.complete_turn("posting it")

    s2 = cap.open_turn("and now?")
    assert s2["files_due"] is None  # notified already

    other = capture.TurnCapture(root, "alpha", "cc-other")
    assert other.open_turn("hi")["files_due"] == "sn_new"  # per agent


def test_hook_files_due_respects_coverage_recency_and_setting(root: Path) -> None:
    today = capture._yymm_dd(datetime.now())
    _write_csv(root / "scans.csv", ["id", "created_date", "created_time", "project"],
               [["sn_cov", today, "09:00", "alpha"]])
    _write_csv(root / "files.csv", ["id", "project", "trigger_id"],
               [["fl_1", "alpha", "sn_cov"]])
    assert capture.TurnCapture(root, "alpha", "cc-1").open_turn("x")["files_due"] is None

    _write_csv(root / "scans.csv", ["id", "created_date", "created_time", "project"],
               [["sn_stale", "2501-01", "09:00", "alpha"]])
    assert capture.TurnCapture(root, "alpha", "cc-2").open_turn("x")["files_due"] is None

    _write_csv(root / "scans.csv", ["id", "created_date", "created_time", "project"],
               [["sn_off", today, "09:00", "alpha"]])
    (root / "settings.json").write_text(
        json.dumps({"agent": {"files_due_enabled": False}}), encoding="utf-8"
    )
    assert capture.TurnCapture(root, "alpha", "cc-3").open_turn("x")["files_due"] is None


# ---------------------------------------------------------------------------
# Identity notice — the agent learns the id and clock its entries must carry
# ---------------------------------------------------------------------------


def test_hook_announces_identity_on_first_turn_and_refresh(root: Path) -> None:
    (root / "settings.json").write_text(
        json.dumps({"agent": {"contract_refresh_turns": 3}}), encoding="utf-8"
    )
    cap = capture.TurnCapture(root, "alpha", "cc-me")
    s1 = cap.open_turn("hello")
    assert s1["identity"]["agent_id"] == "cc-me"
    assert "your agent_id is cc-me" in capture.format_signals(s1)
    cap.complete_turn("hi")
    assert cap.open_turn("two")["identity"] is None
    cap.complete_turn("ok")
    assert cap.open_turn("three")["identity"] is not None  # refresh turn


# ---------------------------------------------------------------------------
# Heatmap columns — one per checkpoint, linked to scan and session
# ---------------------------------------------------------------------------


def test_heatmap_entries_link_scan_and_session(client: TestClient, root: Path) -> None:
    chat = root / "projects" / "alpha" / "chats" / "cc-a"
    chat.mkdir(parents=True)
    chat.joinpath("chat.md").write_text(
        "# Chat log — cc-a\n\n---\n"
        "\n## Turn 1 · 2026-08-18T09:50:00\n**User**: start\n**Agent**: ok\n"
        "\n## Turn 2 · 2026-08-18T09:58:00\n**User**: ship it\n**Agent**: shipped\n",
        encoding="utf-8",
    )
    chat.joinpath("meta.json").write_text(json.dumps({"agent_id": "cc-a"}), encoding="utf-8")
    client.app.state.store.rebuild()

    scan = _scan(client)
    sid = scan["metadata"]["id"]
    e1 = _files(client, sid)["metadata"]["id"]
    e2 = _files(client, sid, created_time="10:30",
                paths=[{"path": "app/auth.py", "importance": 1, "why": "again"}])["metadata"]["id"]

    heat = client.get("/api/files/heatmap?project=alpha").json()
    assert [e["id"] for e in heat["entries"]] == [e1, e2]
    first = heat["entries"][0]
    assert first["scan_id"] == sid and first["paths_n"] == 2
    session = client.get("/api/sessions?project=alpha&agent_id=cc-a").json()["sessions"][0]
    assert first["session_id"] == session["id"]
    # The row names the agent and says where it ran, so /sessions can offer
    # the resume without a second request.
    assert session["agent"]["agent_id"] == "cc-a"
    assert set(session["agent"]) >= {"agent_name", "chat_title", "tool", "cwd", "session_ref"}
    # Per-checkpoint cells keep each touch apart; the date matrix sums them.
    assert heat["cells"][f"app/auth.py||{e1}"]["count"] == 1
    assert heat["matrix"]["app/auth.py||2608-18"]["count"] == 2


def _register(client: TestClient, path: Path) -> None:
    root = client.app.state.store.data_root
    with open(root / "integrations.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["project", "path", "created_date"])
        w.writerow(["alpha", str(path), "2608-19"])


def test_first_entry_in_fresh_repo_fills_from_empty_tree(client: TestClient, tmp_path: Path) -> None:
    repo = tmp_path / "fresh"
    repo.mkdir()
    _git(repo, "init", "-q")                       # no commits at all
    (repo / "main.py").write_text("a\nb\nc\n")
    _register(client, repo)
    out = _files(client, "sn_f", paths=[{"path": "main.py", "importance": 3, "why": "entry"}])
    d = client.get(f"/api/files/{out['metadata']['id']}").json()
    assert d["git_status"] == "filled" and d["range_basis"] == "empty-tree"
    assert d["paths"][0]["lines_add"] == 3 and d["paths"][0]["action"] == "created"


def test_first_entry_in_existing_repo_diffs_since_head(client: TestClient, tmp_path: Path) -> None:
    repo = tmp_path / "old"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "main.py").write_text("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    (repo / "main.py").write_text("a\nb\nc\n")      # two uncommitted lines
    _register(client, repo)
    out = _files(client, "sn_h", paths=[{"path": "main.py", "importance": 3, "why": "x"}])
    d = client.get(f"/api/files/{out['metadata']['id']}").json()
    assert d["range_basis"] == "head" and d["paths"][0]["lines_add"] == 2


def test_git_status_names_the_reason_when_unfilled(client: TestClient, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    _register(client, plain)
    d1 = client.get(f"/api/files/{_files(client, 'sn_p1')['metadata']['id']}").json()
    assert d1["git_status"] == "not-a-repo"
    (client.app.state.store.data_root / "integrations.csv").unlink()
    d2 = client.get(f"/api/files/{_files(client, 'sn_p2', created_time='10:20')['metadata']['id']}").json()
    assert d2["git_status"] == "no-path"


def test_heatmap_over_every_project_keeps_the_same_path_apart_per_project(client: TestClient) -> None:
    """Without a project filter a README.md in alpha and one in beta are two
    files: the cells and the matrix hang on project::path, and each file row
    names its project. With a filter, the keys are the plain path as before."""
    (client.app.state.store.data_root / "projects" / "beta").mkdir(parents=True, exist_ok=True)
    a = _files(client, "sn_ha", project="alpha", created_time="10:01", paths=[{"path": "README.md", "action": "modified", "lines_add": 3, "lines_del": 1}])
    b = _files(client, "sn_hb", project="beta", created_time="10:02", paths=[{"path": "README.md", "action": "modified", "lines_add": 7, "lines_del": 0}])
    aid, bid = a["metadata"]["id"], b["metadata"]["id"]
    heat = client.get("/api/files/heatmap").json()
    readmes = [f for f in heat["files"] if f["path"] == "README.md"]
    assert {(f["project"], f["key"]) for f in readmes} == {("alpha", "alpha::README.md"), ("beta", "beta::README.md")}
    assert heat["cells"][f"alpha::README.md||{aid}"]["lines_add"] == 3
    assert heat["cells"][f"beta::README.md||{bid}"]["lines_add"] == 7
    assert heat["matrix"]["beta::README.md||2608-18"]["count"] == 1
    scoped = client.get("/api/files/heatmap?project=beta").json()
    assert [f["key"] for f in scoped["files"] if f["path"] == "README.md"] == ["README.md"]
    assert f"README.md||{bid}" in scoped["cells"]

