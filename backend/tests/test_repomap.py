"""The map of a program: rows of one kind, checked against the vocabulary,
the template and the folder, kept in versions."""

from __future__ import annotations


from fastapi.testclient import TestClient

from backend import repomap
from backend.csvio import append_row

MAP = {
    "template": "tool",
    "rows": [
        {"kind": "runtime", "name": "Python 3.12", "what": "the only language", "where": "pyproject.toml", "evidence": "computed"},
        {"kind": "entry", "name": "cli.py", "what": "the command a person runs", "where": "cli.py", "evidence": "opened cli.py"},
        {"kind": "surface", "name": "commands", "what": "rename and report", "where": "cli.py", "evidence": "opened cli.py"},
        {"kind": "module", "name": "core", "what": "renaming logic", "where": "core", "evidence": "opened core/rename.py"},
        {"kind": "data-in", "name": "photos", "what": "a folder of images", "where": "cli.py", "evidence": "opened cli.py"},
        {"kind": "data-out", "name": "renamed files", "what": "the same folder, renamed", "where": "cli.py", "evidence": "opened cli.py"},
        {"kind": "config", "name": "none", "what": "no configuration", "where": "cli.py", "evidence": "searched for env reads and config files"},
        {"kind": "build", "name": "none", "what": "run from the checkout", "where": "pyproject.toml", "evidence": "searched pyproject"},
        {"kind": "test", "name": "pytest", "what": "unit tests", "where": "tests", "evidence": "ran pytest, 3 passed"},
        {"kind": "external", "name": "none", "what": "nothing outside", "where": "pyproject.toml", "evidence": "searched imports"},
    ],
    "relations": [{"from": "cli.py", "verb": "reads", "to": "photos"}, {"from": "cli.py", "verb": "writes", "to": "renamed files"}],
    "notes": {"shape": "A small tool.", "main_path": "cli.py reads photos and writes renamed files."},
}


def _project(client: TestClient, tmp_path):
    store = client.app.state.store
    repo = tmp_path / "photos"
    (repo / "core").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "cli.py").write_text("import os\nPORT = os.environ.get('PHOTOS_PORT')\n", encoding="utf-8")
    (repo / "core" / "rename.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text('[project]\nname = "photos"\nrequires-python = ">=3.12"\ndependencies = [\n "pillow",\n]\n', encoding="utf-8")
    append_row(store.data_root / "integrations.csv", ("project", "path"), {"project": "ALPHA", "path": str(repo)})
    repomap._cache.clear()
    return store, repo


def test_the_detectors_read_the_repository_with_no_model(client: TestClient, tmp_path) -> None:
    store, repo = _project(client, tmp_path)
    f = repomap.detect(repo)
    assert f["languages"][0][0] == "Python" and f["env_variables_read_by_code"] == ["PHOTOS_PORT"]
    assert [m["file"].endswith("pyproject.toml") for m in f["manifests"]] == [True]
    assert f["manifests"][0]["declares"]["dependencies"] == ["pillow"] and f["test_folders"] == ["tests"]


def test_a_map_is_checked_against_the_vocabulary_the_template_and_the_folder(client: TestClient, tmp_path) -> None:
    store, repo = _project(client, tmp_path)
    post = lambda m, note="": client.post("/api/map", json={"project": "ALPHA", "agent_id": "cc-m", "map": m, "note": note})
    first = post(MAP, "first")
    assert first.status_code == 201, first.text
    out = first.json()
    assert out["n"] == 1 and out["warnings"] == [] and out["by_kind"]["module"] == 1
    assert (store.data_root / "projects" / "ALPHA" / "map" / "v001.json").is_file()
    again = post(MAP)
    assert again.status_code == 200 and again.json()["existing"] is True

    # Warnings name what to fix: a template kind not answered, a path not found, a relation naming no row.
    thin = {**MAP, "rows": MAP["rows"][:3] + [{"kind": "store", "name": "cache", "what": "a cache", "where": "nowhere.db", "evidence": "opened"}],
            "relations": [{"from": "cli.py", "verb": "reads", "to": "ghost"}]}
    w = post(thin, "thin").json()["warnings"]
    assert any("`module` row" in x for x in w) and any("nowhere.db" in x for x in w) and any("“ghost”" in x for x in w)

    # Shape faults are refused, with the vocabulary in the answer.
    bad = {**MAP, "rows": [{"kind": "widget", "name": "x", "what": "y", "where": "cli.py", "evidence": "opened"}]}
    r = post(bad)
    assert r.status_code == 422 and "not one of" in r.json()["detail"]
    assert post({**MAP, "template": "sculpture"}).status_code == 422
    assert post({"rows": "no"}).status_code == 422

    got = client.get("/api/map?project=ALPHA").json()
    assert got["map"]["n"] == 2 and len(got["map"]["changes"]["removed"]) > 0 and got["versions"][0]["note"] == "first"
    assert got["facts"]["languages"][0][0] == "Python" and "tool" in got["templates"]
    assert client.get("/api/map?project=ALPHA&version=1").json()["map"]["n"] == 1
    mat = client.get("/api/map/material?project=ALPHA").json()
    assert mat["current_map"]["n"] == 2 and "Step 1" in mat["instructions"] and mat["model"] in ("haiku", "sonnet", "opus")

    # The standup does not get the map; the day's numbers only show that a version was written.
    sm = client.get("/api/standups/material?project=ALPHA&date=2609-21").json()
    assert "map" not in sm
    from datetime import datetime

    from backend import daynumbers
    today = datetime.now().strftime("%y%m-%d")
    assert daynumbers.day(store, "ALPHA", today)["map_versions"] == [1, 2]
