"""Artifacts: #artifact → the agent writes a folder under artifacts/ → one call makes the record → the page previews it by kind.
Plus the skill Slightly Parallel ships with, make-an-artifact, on every data root."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend import keeplib, skilllib

AGENT = "cc-abc12345"
_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _hook(module: str, filename: str):
    spec = importlib.util.spec_from_file_location(module, _HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module] = mod
    spec.loader.exec_module(mod)
    return mod


def _chat(root: Path, project: str, agent: str, turns: list[tuple[str, str, str]]) -> None:
    d = root / "projects" / project / "chats" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent, "agent_name": agent, "project": project,
        "created_date": "2609-18", "last_active": "2026-09-18T10:00:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {agent}\n"]
    for i, (at, user, said) in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · {at}\n**User**: {user}\n**Agent**: {said}\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


def _kept(client: TestClient, text: str = "#artifact keep the corrections as a dataset") -> str:
    root = Path(client.app.state.store.data_root)
    _chat(root, "ALPHA", AGENT, [("2026-09-18T10:00:00", text, "on it")])
    client.app.state.store.rebuild()
    keeplib.adopt(client.app.state.store)
    return keeplib.keep_id("artifact", "ALPHA", AGENT, 1)


def _folder(client: TestClient, name: str, files: dict[str, str | bytes]) -> Path:
    dest = Path(client.app.state.store.data_root) / "projects" / "ALPHA" / "artifacts" / name
    for rel, body in files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            p.write_bytes(body)
        else:
            p.write_text(body, encoding="utf-8")
    return dest


def _write(client: TestClient, kid: str, **over):
    return client.post(f"/api/artifacts/{kid}/write", json={
        "agent_id": AGENT, "name": "corrections", "kind": "dataset",
        "description": "Sentences that read badly, the options offered, the one chosen.", **over,
    })


# ---------------------------------------------------------------------------
# Kept from chat
# ---------------------------------------------------------------------------


def test_the_hook_keeps_artifact_and_names_the_folder(tmp_path):
    capture = _hook("sp_capture_artifacts", "capture.py")
    (tmp_path / "data").mkdir()
    cap = capture.TurnCapture(tmp_path / "data", "alpha", AGENT)
    signals = cap.open_turn("#artifact keep this as a dataset")
    aid = capture.keep_id("artifact", "alpha", AGENT, 1)
    assert signals["kept"] == [{"kind": "artifact", "id": aid, "route": "artifacts",
                                "folder": str(tmp_path / "data" / "projects" / "alpha" / "artifacts")}]
    notice = capture.format_signals(signals)
    assert f"{tmp_path / 'data' / 'projects' / 'alpha' / 'artifacts'}/<name>/" in notice
    assert f'artifact_write {{id: "{aid}", name, kind, description}}' in notice


def test_the_hook_and_the_server_mint_the_same_id(client: TestClient):
    aid = _kept(client)
    hook = _hook("sp_capture_artifacts2", "capture.py")
    assert hook.keep_id("artifact", "ALPHA", AGENT, 1) == aid
    row = client.get(f"/api/artifacts/{aid}").json()
    assert row["metadata"]["status"] == "draft" and row["metadata"]["source"] == "captured"
    assert "corrections as a dataset" in row["kept"]["message"]
    assert row["artifact"]["exists"] is False and row["artifact"]["preview"]["missing"] is True


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def test_write_refuses_what_it_cannot_record(client: TestClient):
    aid = _kept(client)
    r = _write(client, aid)
    assert r.status_code == 422 and "does not exist yet" in r.text
    assert str(Path("ALPHA/artifacts/corrections")) in r.json()["detail"]   # the system's own separators
    _folder(client, "corrections", {"ARTIFACT.md": "just a manifest"})
    r = _write(client, aid)
    assert r.status_code == 422 and "holds nothing beside ARTIFACT.md" in r.text
    _folder(client, "corrections", {"rows.jsonl": '{"before":"a","after":"b"}\n'})
    assert _write(client, aid, name="Bad Name").status_code == 422
    assert _write(client, aid, kind="movie").status_code == 422
    assert _write(client, aid, description=" ").status_code == 422
    assert _write(client, aid, name="../../etc").status_code == 422
    assert client.post("/api/artifacts/ar_nope/write", json={"agent_id": AGENT}).status_code == 404


def test_write_makes_the_record_and_keeps_the_manifest_body(client: TestClient):
    aid = _kept(client)
    dest = _folder(client, "corrections", {
        "ARTIFACT.md": "---\nname: corrections\nkind: dataset\ndescription: draft\n---\n\nOne row per correction.\n",
        "rows.jsonl": '{"before":"a","after":"b"}\n{"before":"c","after":"d"}\n',
    })
    r = _write(client, aid)
    assert r.status_code == 200, r.text
    d = r.json()
    m = d["metadata"]
    assert m["status"] == "active" and m["name"] == "corrections" and m["kind"] == "dataset"
    assert m["files_n"] == 2 and int(m["bytes"]) > 0 and m["path"] == str(dest)
    assert d["l2"].startswith("Sentences that read badly")
    manifest = (dest / "ARTIFACT.md").read_text(encoding="utf-8")
    assert f'id: "{aid}"' in manifest and 'kind: "dataset"' in manifest and "One row per correction." in manifest
    assert d["artifact"]["manifest"]["body"] == "One row per correction."
    assert d["artifact"]["preview"]["tables"][0]["rows"] == 2
    listed = client.get("/api/artifacts", params={"project": "ALPHA"}).json()["artifacts"]
    assert [a["id"] for a in listed] == [aid]
    # Again after an edit: the update.
    (dest / "rows.jsonl").write_text('{"before":"a","after":"b"}\n', encoding="utf-8")
    r = _write(client, aid, description="Now one row.")
    assert r.status_code == 200 and r.json()["artifact"]["preview"]["tables"][0]["rows"] == 1
    assert r.json()["metadata"]["description"] == "Now one row."


def test_a_name_is_unique_within_a_project(client: TestClient):
    a = _kept(client)
    _folder(client, "corrections", {"rows.csv": "before,after\na,b\n"})
    assert _write(client, a).status_code == 200
    b = client.post("/api/artifacts/new", json={"project": "ALPHA", "name": "corrections", "kind": "dataset",
                                                "description": "another"})
    assert b.status_code == 422 and "already named corrections" in b.text


def test_the_operator_registers_a_folder_by_hand(client: TestClient):
    _folder(client, "notes", {"notes.md": "# Notes\n\nA page of notes.\n"})
    r = client.post("/api/artifacts/new", json={"project": "ALPHA", "name": "notes", "kind": "document",
                                                "description": "Notes from the review."})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["metadata"]["source"] == "written" and d["metadata"]["status"] == "active"
    assert d["artifact"]["preview"]["document"]["file"] == "notes.md"
    assert client.post("/api/artifacts/new", json={"project": "ALPHA", "name": "nope", "kind": "document",
                                                   "description": "x", "agent_id": AGENT}).status_code == 422
    assert client.post("/api/artifacts/new", json={"project": "ALPHA", "name": "missing", "kind": "document",
                                                   "description": "x"}).status_code == 422
    assert [a["name"] for a in client.get("/api/artifacts").json()["artifacts"]] == ["notes"]


# ---------------------------------------------------------------------------
# Previews by kind
# ---------------------------------------------------------------------------


def test_previews_follow_the_kind(client: TestClient):
    # dataset: csv + jsonl, one of them broken
    aid = _kept(client)
    _folder(client, "corrections", {
        "a.csv": "before,after\nx,y\n" + "\n".join("p,q" for _ in range(9)) + "\n",
        "b.jsonl": '{"k": 1}\n{"k": 2}\nnot json\n',
    })
    p = _write(client, aid).json()["artifact"]["preview"]
    a, b = p["tables"]
    assert a == {"file": "a.csv", "fields": ["before", "after"], "rows": 10,
                 "sample": [{"before": "x", "after": "y"}] + [{"before": "p", "after": "q"}] * 4}
    assert b["fields"] == ["k"] and b["rows"] == 2 and "line 3" in b["error"]

    # document: the largest markdown
    _folder(client, "report", {"short.md": "# a\n", "long.md": "# Long\n\n" + "words " * 50})
    d = client.post("/api/artifacts/new", json={"project": "ALPHA", "name": "report", "kind": "document",
                                                "description": "x"}).json()["artifact"]["preview"]
    assert d["document"]["file"] == "long.md" and d["document"]["text"].startswith("# Long")

    # page: index.html is the entry
    _folder(client, "site", {"index.html": "<h1>hi</h1>", "about.html": "<p>x</p>"})
    pg = client.post("/api/artifacts/new", json={"project": "ALPHA", "name": "site", "kind": "page",
                                                 "description": "x"}).json()["artifact"]["preview"]
    assert pg["entry"] == "index.html" and pg["pages"] == ["about.html", "index.html"]

    # app: the tree without dependencies, and the run line
    _folder(client, "tool", {
        "ARTIFACT.md": "---\nname: tool\nkind: app\ndescription: x\nrun: python main.py\n---\n",
        "main.py": "print(1)\n", "src/lib.py": "x = 1\n", "node_modules/left-pad/index.js": "junk",
        "dist/bundle.js": "junk", ".env": "SECRET=1",
    })
    app = client.post("/api/artifacts/new", json={"project": "ALPHA", "name": "tool", "kind": "app",
                                                  "description": "A tool."}).json()
    paths = [e["path"] for e in app["artifact"]["preview"]["tree"]]
    assert "main.py" in paths and "src/lib.py" in paths
    assert not any(x.startswith(("node_modules", "dist", ".env")) for x in paths)
    assert app["artifact"]["preview"]["run"] == "python main.py"
    assert [f["path"] for f in app["artifact"]["files"]] == ["ARTIFACT.md", "main.py", "src/lib.py"]


def test_files_are_served_from_the_folder_only(client: TestClient, data_root: Path):
    _folder(client, "site", {"index.html": "<h1>hi</h1>", "data.bin": b"\x00\x01"})
    (data_root / "secret.txt").write_text("no", encoding="utf-8")
    aid = client.post("/api/artifacts/new", json={"project": "ALPHA", "name": "site", "kind": "page",
                                                  "description": "x"}).json()["metadata"]["id"]
    r = client.get(f"/api/artifacts/{aid}/files/index.html")
    assert r.status_code == 200 and r.text == "<h1>hi</h1>"
    assert "sandbox" in r.headers["content-security-policy"] and r.headers["content-type"].startswith("text/html")
    assert client.get(f"/api/artifacts/{aid}/files/data.bin").headers["content-type"] == "application/octet-stream"
    assert client.get(f"/api/artifacts/{aid}/files/../../secret.txt").status_code == 404
    assert client.get(f"/api/artifacts/{aid}/files/%2e%2e/%2e%2e/secret.txt").status_code == 404
    assert client.get(f"/api/artifacts/{aid}/files/nope.txt").status_code == 404
    tree = client.get(f"/api/artifacts/{aid}/tree").json()["tree"]
    assert [e["path"] for e in tree] == ["ARTIFACT.md", "data.bin", "index.html"]


def test_a_hand_edit_in_the_folder_is_never_served_from_the_cache(client: TestClient):
    aid = _kept(client)
    dest = _folder(client, "corrections", {"rows.csv": "a,b\n1,2\n"})
    _write(client, aid)
    first = client.get(f"/api/artifacts/{aid}")
    assert client.get(f"/api/artifacts/{aid}", headers={"If-None-Match": first.headers["etag"]}).status_code == 304
    (dest / "rows.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    r = client.get(f"/api/artifacts/{aid}", headers={"If-None-Match": first.headers["etag"]})
    assert r.status_code == 200 and r.json()["artifact"]["preview"]["tables"][0]["rows"] == 2


# ---------------------------------------------------------------------------
# The MCP tool
# ---------------------------------------------------------------------------


def test_the_mcp_tool_forwards_the_record(client: TestClient, monkeypatch):
    from backend import mcp as mcp_mod

    aid = _kept(client)
    _folder(client, "corrections", {"rows.csv": "a,b\n1,2\n"})
    calls: list[tuple[str, dict]] = []

    class FakeApi:
        def get(self, path):
            if path.startswith("/api/schema"):
                return client.get("/api/schema").json()
            return {"agent_id": AGENT, "project": "ALPHA"}

        def post(self, path, body):
            calls.append((path, body))
            return client.post(path, json=body).json()

    tr = mcp_mod.Translator(FakeApi(), "/tmp")
    assert "artifact_write" in {t["name"] for t in tr.tool_defs()}
    out = tr.call("artifact_write", {"id": aid, "name": "corrections", "kind": "dataset", "description": "Rows."})
    assert calls[0][0] == f"/api/artifacts/{aid}/write" and calls[0][1]["agent_id"] == AGENT
    assert out["metadata"]["status"] == "active"


# ---------------------------------------------------------------------------
# The skill Slightly Parallel ships with
# ---------------------------------------------------------------------------


def test_make_an_artifact_is_on_every_data_root(client: TestClient, tmp_path: Path):
    rows = client.get("/api/skills").json()["skills"]
    mine = [r for r in rows if r["name"] == "make-an-artifact"]
    assert len(mine) == 1
    sk = mine[0]
    assert sk["source"] == "builtin" and sk["status"] == "active" and sk["id"] == skilllib.builtin_id("make-an-artifact")
    d = client.get(f"/api/skills/{sk['id']}").json()
    assert d["skill"]["current"]["n"] == 1 and "artifact_write" in d["skill"]["current"]["skill_md"]
    assert d["skill"]["checks"] == []
    # It survives the examples going, and installs like any skill.
    client.post("/api/examples/remove")
    assert client.get(f"/api/skills/{sk['id']}").status_code == 200
    root = Path(client.app.state.store.data_root)
    folder = tmp_path / "proj"
    folder.mkdir()
    (root / "integrations.csv").write_text(f"project,path,created_date\nALPHA,{folder},2609-01\n", encoding="utf-8")
    r = client.post(f"/api/skills/{sk['id']}/install", json={"project": "ALPHA"})
    assert r.status_code == 200, r.text
    assert (folder / ".claude" / "skills" / "make-an-artifact" / "SKILL.md").exists()
    # A second start writes nothing new; a changed template is the next version.
    assert skilllib.seed_builtin_skills(client.app.state.store) == []
    tpl = tmp_path / "templates" / "make-an-artifact"
    tpl.mkdir(parents=True)
    (tpl / "SKILL.md").write_text(
        '---\nname: make-an-artifact\ndescription: "Make an artifact. Use when the operator types #artifact."\n---\n\n1. New step.\n',
        encoding="utf-8",
    )
    assert skilllib.seed_builtin_skills(client.app.state.store, tmp_path / "templates") == [sk["id"]]
    assert client.get(f"/api/skills/{sk['id']}").json()["skill"]["current"]["n"] == 2
