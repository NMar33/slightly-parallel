"""Operator settings: schema-driven API + the logger script honoring them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _capture(data_root: Path, agent: str = "test-agent"):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sp_capture_settings_test", _HOOKS / "capture.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_settings_test"] = mod
    spec.loader.exec_module(mod)
    return mod.TurnCapture(data_root, "alpha", agent)


@pytest.fixture()
def env(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    app = create_app(data_root=data_root, watch=False)
    with TestClient(app) as client:
        yield client, data_root


def test_get_settings_returns_grouped_schema_with_defaults(env) -> None:
    client, _root = env
    body = client.get("/api/settings").json()
    groups = {g["name"]: g["settings"] for g in body["groups"]}
    assert "Agent signals" in groups and "Dashboard" in groups
    by_key = {s["key"]: s for g in body["groups"] for s in g["settings"]}
    spec = by_key["agent.contract_refresh_turns"]
    assert spec["value"] == spec["default"] == 25
    assert spec["minimum"] == 0 and spec["maximum"] == 500
    assert by_key["ui.poll_seconds"]["value"] == 5


def test_update_persists_and_round_trips(env) -> None:
    client, data_root = env
    r = client.post(
        "/api/settings",
        json={"values": {"agent.contract_refresh_turns": 40, "ui.poll_seconds": 10}},
    )
    assert r.status_code == 200
    assert r.json()["values"]["agent.contract_refresh_turns"] == 40

    stored = json.loads((data_root / "settings.json").read_text())
    assert stored["agent"]["contract_refresh_turns"] == 40
    assert stored["ui"]["poll_seconds"] == 10

    by_key = {
        s["key"]: s["value"]
        for g in client.get("/api/settings").json()["groups"]
        for s in g["settings"]
    }
    assert by_key["agent.contract_refresh_turns"] == 40
    # Untouched settings keep their defaults.
    assert by_key["agent.standup_enabled"] is True


def test_update_rejects_invalid_values_atomically(env) -> None:
    client, data_root = env
    for bad in (
        {"agent.contract_refresh_turns": -1},
        {"agent.contract_refresh_turns": "lots"},
        {"agent.standup_enabled": "yes"},
        {"unknown.key": 1},
        {"ui.poll_seconds": 1},  # below minimum
    ):
        r = client.post("/api/settings", json={"values": bad})
        assert r.status_code == 422, bad
    assert not (data_root / "settings.json").exists()


def test_unreadable_settings_file_degrades_to_defaults(env) -> None:
    client, data_root = env
    (data_root / "settings.json").write_text("{not json", encoding="utf-8")
    by_key = {
        s["key"]: s["value"]
        for g in client.get("/api/settings").json()["groups"]
        for s in g["settings"]
    }
    assert by_key["agent.contract_refresh_turns"] == 25


def test_script_contract_refresh_follows_settings(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "settings.json").write_text(
        json.dumps({"agent": {"contract_refresh_turns": 2}}), encoding="utf-8"
    )
    cap = _capture(data_root)
    results = []
    for _ in range(3):
        results.append(cap.open_turn("hello"))
        cap.complete_turn("done")
    assert [r["turn_number"] for r in results] == [1, 2, 3]
    assert [r["contract_refresh_due"] for r in results] == [False, True, False]


def test_script_disabled_triggers(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "settings.json").write_text(
        json.dumps(
            {
                "agent": {
                    "contract_refresh_turns": 0,
                    "decision_hint_enabled": False,
                }
            }
        ),
        encoding="utf-8",
    )
    signals = _capture(data_root).open_turn("we decided to use X")
    assert signals["decision_hint"] is None
    assert signals["contract_refresh_due"] is False


def test_script_defaults_without_settings_file(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    result = _capture(data_root).open_turn("hello")
    assert result["turn_number"] == 1
    assert result["contract_refresh_due"] is False
    assert "standup_due" in result


def test_choice_setting_validates_membership(env) -> None:
    client, _root = env
    ok = client.post(
        "/api/settings",
        json={"values": {"ui.default_project_tab": "terminals"}},
    )
    assert ok.status_code == 200
    bad = client.post(
        "/api/settings",
        json={"values": {"ui.default_project_tab": "nonsense"}},
    )
    assert bad.status_code == 422


def test_settings_payload_includes_environment(env) -> None:
    client, _root = env
    body = client.get("/api/settings").json()
    labels = {e["label"] for e in body["environment"]}
    assert {"Data root", "Bind address", "Terminal"} <= labels


def test_snapshot_capabilities_and_no_daily_activity(env) -> None:
    client, _root = env
    snap = client.get("/api/snapshot").json()
    # The Overview no longer draws an activity heatmap; the server no longer counts one.
    assert "daily_activity" not in snap
    # Terminal env vars are unset in tests → capability off.
    assert snap["capabilities"] == {"terminal_enabled": False}


def test_a_retired_setting_in_settings_json_still_loads(env) -> None:
    """overview.daily_activity_days was removed; a file that still holds it loads,
    the other values survive, and the next save drops the retired key."""
    client, data_root = env
    (data_root / "settings.json").write_text(
        json.dumps({"overview": {"daily_activity_days": 14, "recent_activity_limit": 9}}),
        encoding="utf-8",
    )
    body = client.get("/api/settings").json()
    by_key = {s["key"]: s["value"] for g in body["groups"] for s in g["settings"]}
    assert "overview.daily_activity_days" not in by_key
    assert by_key["overview.recent_activity_limit"] == 9
    assert client.get("/api/snapshot").status_code == 200
    r = client.post("/api/settings", json={"values": {"overview.open_tasks_limit": 5}})
    assert r.status_code == 200
    stored = json.loads((data_root / "settings.json").read_text(encoding="utf-8"))
    assert "daily_activity_days" not in stored["overview"]
    assert stored["overview"]["recent_activity_limit"] == 9
