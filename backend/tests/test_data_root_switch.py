"""Web-editable data root: validation, .env persistence, live hot-swap."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.routers import setup as setup_router
from backend.routers.terminal import resolve_terminal_cwd
from backend.server import create_app


@pytest.fixture()
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    old = tmp_path / "old-root"
    new = tmp_path / "new-root"
    old.mkdir()
    new.mkdir()
    (old / "goals.csv").write_text(
        "id,created_date,project,agent_id,goal_text,parent_goal_id,related,"
        "time_est,confidence_pct,success_comment,status,children_n,"
        "retro_outcome,md_ref,sprint_id\n"
        "g_old,2608-10,alpha,agent-a,Old-root goal,,,,80,,active,0,unknown,,\n",
        encoding="utf-8",
    )
    env = tmp_path / "dot-env"
    env.write_text('HOST=127.0.0.1\nSCAN_DATA_ROOT="/was/here"\n', encoding="utf-8")
    monkeypatch.setattr(setup_router, "ENV_PATH", env)
    return {"old": old, "new": new, "env": env}


def test_switch_persists_env_and_hot_swaps(roots: dict[str, Path]) -> None:
    app = create_app(data_root=roots["old"], watch=False)
    with TestClient(app) as client:
        assert "g_old" in [
            g["id"] for g in client.get("/api/goals").json()["goals"]
        ]

        r = client.post("/api/setup/data-root", json={"path": str(roots["new"])})
        assert r.status_code == 200
        body = r.json()
        assert body["data_root"] == str(roots["new"])
        assert body["restart_required"] is False

        # .env updated in place, other lines preserved.
        env_text = roots["env"].read_text(encoding="utf-8")
        assert f'SP_DATA_ROOT="{roots["new"]}"' in env_text
        # The line written under the product's former name is taken over,
        # not left beside the new one saying something else.
        assert "SCAN_DATA_ROOT" not in env_text
        assert "HOST=127.0.0.1" in env_text
        assert "/was/here" not in env_text

        # The running app now serves the new (empty) root — no restart.
        assert client.get("/api/goals").json()["total"] == 0
        assert client.get("/api/health").json()["data_root"] == str(roots["new"])

        # Old data was left untouched where it was.
        assert (roots["old"] / "goals.csv").exists()


def test_switch_appends_when_env_missing(roots: dict[str, Path]) -> None:
    roots["env"].unlink()
    app = create_app(data_root=roots["old"], watch=False)
    with TestClient(app) as client:
        r = client.post("/api/setup/data-root", json={"path": str(roots["new"])})
        assert r.status_code == 200
    assert f'SP_DATA_ROOT="{roots["new"]}"' in roots["env"].read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "path",
    [
        "",                       # required
        "relative/path",          # must be absolute
        "/definitely/not/there",  # must exist
        '/tmp/has"quote',         # unsafe for .env
    ],
)
def test_switch_rejects_bad_paths(roots: dict[str, Path], path: str) -> None:
    app = create_app(data_root=roots["old"], watch=False)
    with TestClient(app) as client:
        r = client.post("/api/setup/data-root", json={"path": path})
        assert r.status_code == 422
    # .env untouched on rejection.
    assert "/was/here" in roots["env"].read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Terminal cwd allowlist
# ---------------------------------------------------------------------------


@pytest.fixture()
def terminal_root(tmp_path: Path) -> dict[str, Path]:
    data_root = tmp_path / "data"
    project_dir = tmp_path / "code" / "my-app"
    outside = tmp_path / "elsewhere"
    for p in (data_root, project_dir, outside):
        p.mkdir(parents=True)
    (data_root / "integrations.csv").write_text(
        "project,path,created_date\n"
        f"my-app,{project_dir},2608-13\n",
        encoding="utf-8",
    )
    return {"data": data_root, "project": project_dir, "outside": outside}


def test_terminal_opens_in_registered_project(terminal_root: dict[str, Path]) -> None:
    got = resolve_terminal_cwd(terminal_root["data"], "my-app", "")
    assert got == terminal_root["project"]


def test_terminal_unknown_project_falls_back(terminal_root: dict[str, Path]) -> None:
    got = resolve_terminal_cwd(terminal_root["data"], "nope", "")
    assert got == terminal_root["data"]


def test_terminal_cwd_inside_project_allowed(terminal_root: dict[str, Path]) -> None:
    sub = terminal_root["project"] / "src"
    sub.mkdir()
    got = resolve_terminal_cwd(terminal_root["data"], "", str(sub))
    assert got == sub


def test_terminal_cwd_outside_allowlist_denied(terminal_root: dict[str, Path]) -> None:
    got = resolve_terminal_cwd(terminal_root["data"], "", str(terminal_root["outside"]))
    assert got == terminal_root["data"]


def test_terminal_traversal_denied(terminal_root: dict[str, Path]) -> None:
    got = resolve_terminal_cwd(terminal_root["data"], "", "../elsewhere")
    assert got == terminal_root["data"]


def test_switch_accepts_a_windows_path_with_backslashes(roots: dict[str, Path], tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """Every Windows path holds a backslash; .env keeps it as plain text and
    the launcher reads it back unchanged."""
    import importlib.util

    win = tmp_path / "C:\\Users\\n\\sp-data"     # one folder name on POSIX, a real path's shape
    win.mkdir()
    app = create_app(data_root=roots["old"], watch=False)
    with TestClient(app) as client:
        r = client.post("/api/setup/data-root", json={"path": str(win)})
        assert r.status_code == 200, r.text
    spec = importlib.util.spec_from_file_location("sp_launcher_win", Path(__file__).resolve().parents[2] / "sp.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setattr(launcher, "ENV_FILE", roots["env"])
    assert launcher.read_env()["SP_DATA_ROOT"] == str(win)
