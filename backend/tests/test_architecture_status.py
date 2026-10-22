"""#architecture does only what is out of date: the server says which."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend import repomap
from backend.server import create_app


def test_a_new_project_owes_the_page_and_nothing_it_cannot_do(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        s = c.get("/api/architecture/status?project=alpha").json()
    assert s["form"]["needed"] is False and "no scan" in s["form"]["why"]
    assert s["page"]["needed"] is True
    assert s["map"]["needed"] is False and "no folder" in s["map"]["why"]


def test_the_shape_ignores_counts_and_git_and_sees_a_new_dependency() -> None:
    f = {"folder": "/x", "files": 10, "languages": [("py", 9)], "top_level_folders": [("backend", 9)],
         "manifests": [{"file": "/x/pyproject.toml", "declares": {"name": "x", "dependencies": ["a"]}}],
         "git": {"commits": "5"}}
    same = {**f, "files": 99, "languages": [("py", 90)], "git": {"commits": "6"}}
    grown = {**f, "manifests": [{"file": "/x/pyproject.toml", "declares": {"name": "x", "dependencies": ["a", "b"]}}]}
    assert repomap.shape_print(f) == repomap.shape_print(same)
    assert repomap.shape_print(f) != repomap.shape_print(grown)
    assert repomap.shape_print({}) == ""
