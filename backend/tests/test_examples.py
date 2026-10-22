"""Examples: a new data root starts with mock visions, rules, problems and a skill — never written anywhere."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.server import create_app

OWN = "# Proj\n\nOwn notes.\n"


def _examples(c: TestClient, base: str) -> list[dict]:
    return [r for r in c.get(f"/api/{base}").json()[base] if r.get("source") == "demo"]


def test_a_new_data_root_starts_with_examples_once(data_root: Path, monkeypatch):
    monkeypatch.setenv("SP_EXAMPLES", "1")
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert [len(_examples(c, b)) for b in ("visions", "rules", "problems", "skills")] == [2, 3, 2, 1]
        vision = c.get("/api/visions/vs_e0000001").json()
        assert vision["kept"]["message"].startswith("when I start a new project")
        assert [v["how"] for v in vision["kept"]["versions"]] == ["interpreted", "edited"]
        assert vision["kept"]["turn"]["user"].endswith("#vision")
        assert [t["n"] for t in vision["kept"]["before"]] == [1, 2] and len(vision["kept"]["after"]) == 1
        assert c.get("/api/visions/vs_e0000002").json()["kept"]["turn"] is None
        problem = c.get("/api/problems/pb_e0000002").json()["metadata"]
        assert problem["status"] == "open" and "example" in problem["tags"]
        rule = c.get("/api/rules/rl_e0000003").json()
        assert rule["metadata"]["related_incident"] == "pb_e0000001" and rule["kept"]["from"] == "pb_e0000001"

        removed = c.post("/api/examples/remove").json()["removed"]
        assert len(removed) == 8
        assert [len(_examples(c, b)) for b in ("visions", "rules", "problems", "skills")] == [0, 0, 0, 0]

    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert _examples(c, "rules") == [], "removed examples do not come back"
        state = c.get("/api/examples/state").json()
        assert state["present"] == [] and len(state["removed"]) == 8 and len(state["all"]) == 8
        added = c.post("/api/examples/restore").json()["added"]
        assert sorted(added) == sorted(removed), "restore puts every removed example back"
        assert [len(_examples(c, b)) for b in ("visions", "rules", "problems", "skills")] == [2, 3, 2, 1]
        state = c.get("/api/examples/state").json()
        assert len(state["present"]) == 8 and state["removed"] == []
        assert c.post("/api/examples/restore").json()["added"] == [], "a second restore writes nothing"


def test_examples_are_never_written_into_agents_md(data_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SP_EXAMPLES", "1")
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "AGENTS.md").write_text(OWN, encoding="utf-8")
    (data_root / "integrations.csv").write_text(f"project,path,created_date\nALPHA,{folder},2609-01\n", encoding="utf-8")
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert c.get("/api/rules/rl_e0000001").json()["metadata"]["auto"] == "yes"
        assert c.get("/api/integrations/all-rules").json()["items"] == []

        c.post("/api/rules/rl_e0000002/update", json={"auto": "yes", "actor": "operator"})
        assert c.get("/api/integrations/all-rules").json()["items"] == []
        assert (folder / "AGENTS.md").read_text(encoding="utf-8") == OWN

        s = c.post("/api/sets", json={"name": "Demo", "kind": "vision", "items": ["vs_e0000001", "vs_e0000002"]}).json()
        preview = c.post(f"/api/sets/{s['id']}/integrate", json={"project": "ALPHA", "dry_run": True}).json()
        assert "#vision" not in preview["content"] and "This set is empty." in preview["content"]


def test_a_later_example_arrives_and_removed_ones_stay_gone(data_root: Path, monkeypatch):
    """A version that adds an example reaches data roots that already have the others."""
    monkeypatch.setenv("SP_EXAMPLES", "1")
    from backend import examples

    later = {
        "kind": "rule", "id": "rl_e0009999", "date": "2609-05", "time": "10:00",
        "l1": "Say what you did not check",
        "message": "you said it was done but you never ran the migration #rule",
        "versions": [("interpreted", "", "When reporting work, say what you did not check.")],
        "fields": {"tags": "example", "status": "active"},
    }
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert len(_examples(c, "rules")) == 3
        assert "rl_e0000001" in c.post("/api/examples/remove").json()["removed"]

    monkeypatch.setattr(examples, "EXAMPLES", [*examples.EXAMPLES, later])
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert {r["id"] for r in _examples(c, "rules")} == {"rl_e0009999"}
        assert _examples(c, "skills") == []
