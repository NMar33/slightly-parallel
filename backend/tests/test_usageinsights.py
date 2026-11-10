"""The feed of insights (usageinsights.py): one ordinary message a day, a
message for a window that ran out, pins, hiding, clearing."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from backend import usageinsights

A: dict[str, Any] = {
    "mix": {"total_pct": 400.0, "parts": [{"key": "over_500k", "pct": 160.0}, {"key": "helpers", "pct": 50.0}]},
    "prices": [
        {"key": "message", "model": "claude-fable-5-1", "each_pct": 4.0, "times": 42, "total_pct": 166.0},
        {"key": "message", "model": "claude-opus-5-5", "each_pct": 0.36, "times": 420, "total_pct": 150.0},
        {"key": "resume", "each_pct": 3.9, "times": 16, "total_pct": 63.0},
        {"key": "helper", "each_pct": 1.2, "times": 44, "total_pct": 50.0},
        {"key": "reply_over_500k", "each_pct": 0.2, "times": 820, "total_pct": 160.0},
        {"key": "reply_under_100k", "each_pct": 0.03, "times": 184, "total_pct": 6.0},
    ],
    "resumes": {"avg_context": 450_000},
    "chats": [{"agent_id": "cc-1", "title": "a chat", "pct": 169.0}],
    "history": [{"start": "2026-11-09T08:00:00", "resets_at": "2026-11-09T13:00:00", "capped": True, "model": "claude-fable-5-1"},
                {"start": "2026-11-01T08:00:00", "resets_at": "2026-11-01T13:00:00", "capped": True, "model": "claude-opus-5-5"}],
}


def test_a_day_brings_the_window_that_ran_out_and_one_ordinary_message() -> None:
    doc: dict[str, Any] = {"items": [], "day": ""}
    ref = datetime(2026, 11, 10, 9, 0)
    added = usageinsights.write_day(doc, A, ref)
    assert [(i["kind"], i["key"]) for i in added] == [("cap", "2026-11-09T13:00:00"), ("chat", "")]
    assert added[1]["params"]["share"] == 42                       # 169 of 400
    # The next days: the next kinds by weight, never one shown in the last seven days, the cap only once.
    kinds = [[i["kind"] for i in usageinsights.write_day(doc, A, ref + timedelta(days=d))] for d in (1, 2, 3, 4)]
    assert kinds == [["model"], ["context"], ["resume"], ["helpers"]]
    assert [i["kind"] for i in usageinsights.write_day(doc, A, ref + timedelta(days=5))] == ["cheap"]
    assert usageinsights.write_day(doc, A, ref + timedelta(days=6)) == []
    assert [i["kind"] for i in usageinsights.write_day(doc, A, ref + timedelta(days=8))] == ["chat"]


class _Store:
    def __init__(self, root):
        self.data_root = root


def test_pin_hide_and_clear_keep_the_pinned(tmp_path, monkeypatch) -> None:
    store = _Store(tmp_path)
    monkeypatch.setattr(usageinsights.usagelib, "summary", lambda *a, **k: {"analysis": A})
    first = usageinsights.feed(store, datetime(2026, 11, 10, 9, 0))["items"]
    assert [i["kind"] for i in first] == ["cap", "chat"]
    usageinsights.feed(store, datetime(2026, 11, 11, 9, 0))
    items = usageinsights.feed(store, datetime(2026, 11, 11, 10, 0))["items"]
    assert [i["kind"] for i in items] == ["model", "cap", "chat"]   # newest first
    usageinsights.change(store, items[2]["id"], pinned=True)
    got = usageinsights.feed(store, datetime(2026, 11, 11, 10, 0))
    assert [i["kind"] for i in got["items"]] == ["chat", "model", "cap"]   # pinned on top
    usageinsights.change(store, got["items"][1]["id"], hide=True)
    assert usageinsights.clear(store) == 1
    got = usageinsights.feed(store, datetime(2026, 11, 11, 10, 0))
    assert [i["kind"] for i in got["items"]] == ["chat"] and got["hidden"] == 2


def test_a_corrupt_feed_is_never_written_over(tmp_path, monkeypatch) -> None:
    import pytest
    store = _Store(tmp_path)
    monkeypatch.setattr(usageinsights.usagelib, "summary", lambda *a, **k: {"analysis": A})
    path = tmp_path / ".usage" / "insights.json"
    path.parent.mkdir(parents=True)
    broken = '{"items": [{"id": "in_1", "pinned": true'
    path.write_text(broken, encoding="utf-8")
    assert usageinsights.feed(store, datetime(2026, 11, 10, 9, 0)) == {"items": [], "hidden": 0}
    with pytest.raises(usageinsights.Unreadable):
        usageinsights.change(store, "in_1", pinned=False)
    with pytest.raises(usageinsights.Unreadable):
        usageinsights.clear(store)
    assert path.read_text(encoding="utf-8") == broken
    assert [p.name for p in path.parent.iterdir() if p.name != "insights.json.lock"] == ["insights.json"]


def test_a_hand_edited_item_without_kind_or_at_is_read(tmp_path, monkeypatch) -> None:
    import json
    store = _Store(tmp_path)
    monkeypatch.setattr(usageinsights.usagelib, "summary", lambda *a, **k: {"analysis": A})
    path = tmp_path / ".usage" / "insights.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"day": "", "items": [{"id": "in_x", "pinned": True}, "junk"]}), encoding="utf-8")
    got = usageinsights.feed(store, datetime(2026, 11, 10, 9, 0))
    assert got["items"][0]["id"] == "in_x" and {i.get("kind") for i in got["items"][1:]} == {"cap", "chat"}


def test_the_routes_answer_409_for_a_corrupt_feed(client) -> None:
    from pathlib import Path
    root = Path(client.app.state.store.data_root)
    (root / ".usage").mkdir(parents=True, exist_ok=True)
    (root / ".usage" / "insights.json").write_text("[", encoding="utf-8")
    r = client.post("/api/usage/insights/clear", json={})
    assert r.status_code == 409 and "cannot be read" in r.json()["detail"]
    assert client.get("/api/usage/insights").json() == {"items": [], "hidden": 0}
