"""The tour: scripts are kept, shots are served, and neither trusts input.

Capture itself is not exercised here — it needs a browser and a running
frontend. What is pinned is everything around it: the shapes the studio
saves and reloads, the manifest it opens on, and the two places a path or
an id from the browser could reach the filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _script(sid: str = "quick", **over) -> dict:
    return {
        "id": sid,
        "name": "Quick tour",
        "note": "the short one",
        "title": "Slightly Parallel",
        "subtitle": "a dashboard",
        "endline": "self-hosted",
        "theme": "midnight",
        "aspect": "16:9",
        "lead": 3,
        "tail": 3.5,
        "beats": [
            {"id": "board", "page": "/kanban", "chapter": "The board",
             "title": "The board", "text": "cards move left to right",
             "zoom": "full", "hold": 5, "on": True},
        ],
        **over,
    }


# ---------------------------------------------------------------- scripts ---


def test_a_saved_script_comes_back_whole(client: TestClient) -> None:
    assert client.get("/api/tour/scripts").json()["scripts"] == []

    r = client.post("/api/tour/scripts", json={"script": _script()})
    assert r.status_code == 200, r.text

    scripts = client.get("/api/tour/scripts").json()["scripts"]
    assert len(scripts) == 1
    assert scripts[0]["beats"][0]["text"] == "cards move left to right"
    assert scripts[0]["lead"] == 3


def test_saving_the_same_id_replaces_rather_than_piles_up(client: TestClient) -> None:
    client.post("/api/tour/scripts", json={"script": _script()})
    client.post("/api/tour/scripts", json={"script": _script(name="Renamed")})
    scripts = client.get("/api/tour/scripts").json()["scripts"]
    assert len(scripts) == 1
    assert scripts[0]["name"] == "Renamed"


def test_a_script_needs_a_slug_id_and_at_least_one_beat(client: TestClient) -> None:
    assert client.post("/api/tour/scripts", json={"script": _script("Not A Slug")}).status_code == 422
    assert client.post("/api/tour/scripts", json={"script": _script(beats=[])}).status_code == 422
    assert client.post("/api/tour/scripts", json={"script": "nope"}).status_code == 422


def test_only_the_beats_a_script_plays_count_against_the_limit(client: TestClient) -> None:
    # Every preset carries the whole library, the beats it leaves out off:
    # a library larger than one video must still save.
    from backend.routers.tour import MAX_BEATS

    beat = _script()["beats"][0]
    off = [{**beat, "id": f"off-{i}", "on": False} for i in range(MAX_BEATS + 10)]
    r = client.post("/api/tour/scripts", json={"script": _script(beats=[beat, *off])})
    assert r.status_code == 200, r.text
    on = [{**beat, "id": f"on-{i}"} for i in range(MAX_BEATS + 1)]
    assert client.post("/api/tour/scripts", json={"script": _script(beats=on)}).status_code == 422


def test_deleting_a_script_that_is_not_there_is_a_404(client: TestClient) -> None:
    client.post("/api/tour/scripts", json={"script": _script()})
    assert client.post("/api/tour/scripts/quick/delete").status_code == 200
    assert client.post("/api/tour/scripts/quick/delete").status_code == 404
    assert client.get("/api/tour/scripts").json()["scripts"] == []


# ------------------------------------------------------------------ shots ---


def test_shots_are_empty_before_anything_is_photographed(client: TestClient) -> None:
    body = client.get("/api/tour/shots").json()
    assert body["files"] == []
    assert body["shots"] == []
    assert body["at"] == ""


def test_the_manifest_carries_the_rectangles_the_film_zooms_to(
    client: TestClient, data_root: Path,
) -> None:
    shots = data_root / "tour_shots"
    shots.mkdir()
    (shots / "board-0.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (shots / "manifest.json").write_text(json.dumps({
        "ok": True, "at": "2026-09-06T09:00:00Z",
        "view": {"width": 1600, "height": 1000}, "scale": 2,
        "shots": [{"id": "board", "files": ["board-0.png"],
                   "rect": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}, "error": ""}],
    }))
    body = client.get("/api/tour/shots").json()
    assert body["files"] == ["board-0.png"]
    assert body["at"] == "2026-09-06T09:00:00Z"
    assert body["view"] == {"width": 1600, "height": 1000}
    assert body["shots"][0]["rect"]["w"] == 0.3


def test_an_old_manifest_without_a_stamp_falls_back_to_the_file(
    client: TestClient, data_root: Path,
) -> None:
    shots = data_root / "tour_shots"
    shots.mkdir()
    (shots / "manifest.json").write_text(json.dumps({"shots": []}))
    assert client.get("/api/tour/shots").json()["at"] != ""


def test_a_shot_is_served_and_only_by_a_plain_name(
    client: TestClient, data_root: Path,
) -> None:
    shots = data_root / "tour_shots"
    shots.mkdir()
    (shots / "board-0.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    shot = client.get("/api/tour/shot/board-0.png")
    assert shot.status_code == 200
    # A re-shot beat keeps its name: the browser must ask before reusing it.
    assert shot.headers["cache-control"] == "no-cache"
    assert client.get("/api/tour/shot/missing-0.png").status_code == 404
    # Not a picture, and not a way out of the folder.
    assert client.get("/api/tour/shot/manifest.json").status_code == 422
    assert client.get("/api/tour/shot/..%2F..%2Ftasks.csv").status_code in (404, 422)


# ---------------------------------------------------------------- capture ---


def test_capture_refuses_an_empty_or_oversized_job(client: TestClient) -> None:
    assert client.post("/api/tour/capture", json={"beats": []}).status_code == 422
    too_many = [{"id": f"b{i}", "page": "/"} for i in range(61)]
    assert client.post("/api/tour/capture", json={"beats": too_many}).status_code == 422


def test_capture_photographs_its_own_world_never_the_data_root(client: TestClient, monkeypatch) -> None:
    """The capture plays the example into a folder of its own
    (tour_world.prepare) and never touches the example in the data root;
    "reseed" plays the month again."""
    from backend import example, tour_world
    asked: list[bool] = []
    monkeypatch.setattr(example, "replay", lambda app: pytest.fail("the data root's example was played again"))
    monkeypatch.setattr(tour_world, "prepare", lambda home, fresh=False: (asked.append(fresh) or (home / "work", "git is not installed")))
    r = client.post("/api/tour/capture", json={"beats": [{"id": "board", "page": "/kanban"}], "reseed": True})
    assert asked == [True]
    assert r.status_code == 503
    assert "could not be played: git is not installed" in r.json()["detail"]


def test_the_pictures_show_a_readers_paths_not_this_computers() -> None:
    """The mask the capture is given: the world's copies, the example's
    repository, this checkout and the home folder, longest first."""
    from backend.routers.tour import capture_mask
    home = Path("/home/ann")
    world = Path("/tmp/slightly-parallel-tour-world-8123/work")
    repo = home / "src" / "slightly-parallel"
    mask = capture_mask(world, repo, home)
    expected = {
        "/tmp/slightly-parallel-tour-world-8123/work/example/shopfront": "~/code/shopfront",
        "/tmp/slightly-parallel-tour-world-8123/clean/example/shopfront": "~/code/shopfront",
        "/tmp/slightly-parallel-tour-world-8123/work": "~/.slightly-parallel",
        "/tmp/slightly-parallel-tour-world-8123/clean": "~/.slightly-parallel",
        "/home/ann/src/slightly-parallel": "~/code/slightly-parallel",
        "/home/ann": "~",
        # The short form narrow cards print: "ran in example/shopfront".
        "example/shopfront": "code/shopfront",
    }
    # The full paths are the system's own (backslashes on Windows); the short form is not a path.
    assert {m["from"]: m["to"] for m in mask} == {(str(Path(k)) if k.startswith("/") else k): v for k, v in expected.items()}
    lengths = [len(m["from"]) for m in mask]
    assert lengths == sorted(lengths, reverse=True)
    # A home of "/" would rewrite every slash on the page.
    assert all(m["from"] != "/" for m in capture_mask(world, repo, Path("/")))


def test_the_capture_job_carries_the_mask(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    import contextlib
    import subprocess

    from backend import tour_world
    from backend.routers import tour
    monkeypatch.setattr(tour_world, "prepare", lambda home, fresh=False: (tmp_path / "work", ""))
    monkeypatch.setattr(tour_world, "server", lambda root: contextlib.nullcontext("http://127.0.0.1:1"))
    jobs: list[dict] = []

    def run(cmd, **kw):
        jobs.append(json.loads(kw["input"]))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"ok": True, "shots": []}), stderr="")
    monkeypatch.setattr(tour.subprocess, "run", run)
    r = client.post("/api/tour/capture", json={"beats": [{"id": "board", "page": "/kanban"}], "base": "http://127.0.0.1:5181"})
    assert r.status_code == 200, r.text
    mask = {m["from"]: m["to"] for m in jobs[0]["mask"]}
    assert mask[str(tmp_path / "work")] == "~/.slightly-parallel"
    assert mask[str(tour._repo_root())] == "~/code/slightly-parallel"


def test_the_world_is_played_once_a_day_and_each_capture_gets_a_fresh_copy(tmp_path: Path, monkeypatch) -> None:
    from backend import example, tour_world
    plays: list[Path] = []

    def play(root: Path) -> str:
        plays.append(root)
        root.mkdir(parents=True)
        (root / "tasks.csv").write_text("id,status\ntk_1,todo\n")
        return ""

    monkeypatch.setattr(example, "_play", play)
    work, error = tour_world.prepare(tmp_path)
    assert error == "" and len(plays) == 1
    (work / "tasks.csv").write_text("id,status\ntk_1,doing\n")   # a beat dragged the card
    work, _ = tour_world.prepare(tmp_path)
    assert len(plays) == 1                                          # the same day: played once
    assert "todo" in (work / "tasks.csv").read_text()               # the clean board again
    # The board's morning question is answered, so it covers no picture.
    assert json.loads((work / "ui_prefs.json").read_text())["sp-today-carry-seen"]
    tour_world.prepare(tmp_path, fresh=True)
    assert len(plays) == 2


def test_the_world_reports_what_the_builder_said(tmp_path: Path, monkeypatch) -> None:
    from backend import example, tour_world
    monkeypatch.setattr(example, "_play", lambda root: "node is not installed")
    assert tour_world.prepare(tmp_path)[1] == "node is not installed"


def test_replay_waits_for_a_build_that_is_running(client: TestClient) -> None:
    from backend import example
    app = client.app
    assert example._claim(app)
    try:
        assert example.replay(app) == "the example project is being played already"
    finally:
        example._state(app)["building"] = False
