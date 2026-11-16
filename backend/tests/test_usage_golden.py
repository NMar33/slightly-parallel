"""Usage against a golden data root: testdata/usage/root (synthetic), read
under a fixed clock (SP_NOW), equal to the committed snapshots in
testdata/usage/expected. The frontend's tests read the same snapshots and
strings.json, so the page shows what the server means.

The root holds two projects; a Claude Code chat across midnight with two
helpers, an id written three times (10/40/50), a corrupt line, a line
without a time, a #done stretch, a #now card, a task reopened; a chat of
the days before (the usual day, a cache-only day, a day over 90 days back);
an active chat with nothing recorded; a Codex chat with its limits in its
records; limits.jsonl with a 62.5 window, an expired one and a bad line.

To write the snapshots again after a deliberate change:
``SP_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_usage_golden.py``
— then read the diff before keeping it.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import usagelib
from backend.server import create_app

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "testdata" / "usage"
EXPECTED = GOLDEN / "expected"
NOW = "2026-11-01T14:48:00"
URL = "http://127.0.0.1:8123"
UPDATE = os.environ.get("SP_UPDATE_GOLDEN") == "1"


def _plain(x: Any) -> Any:
    """As the wire carries it, without the reading's age (it follows the clock)."""
    got = json.loads(json.dumps(x, ensure_ascii=False))

    def drop(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: drop(w) for k, w in v.items() if k != "age_min"}
        if isinstance(v, list):
            return [drop(w) for w in v]
        return v
    return drop(got)


def _check(name: str, got: Any) -> None:
    path = EXPECTED / name
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(got, str):
            path.write_text(got + "\n", encoding="utf-8")
        else:
            path.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    if isinstance(got, str):
        assert got + "\n" == path.read_text(encoding="utf-8"), name
    else:
        assert _plain(got) == _plain(json.loads(path.read_text(encoding="utf-8"))), name


@pytest.fixture()
def golden(tmp_path: Path, monkeypatch) -> Iterator[tuple[TestClient, Path]]:
    root = tmp_path / "root"
    shutil.copytree(GOLDEN / "root", root)
    monkeypatch.setenv("SP_NOW", NOW)
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c, root


def _summaries(store: Any) -> dict[str, Any]:
    return {rng: usagelib.summary(store, None, rng) for rng in ("today", "7d", "30d")}


def _block(root: Path) -> str:
    return usagelib.usage_block(root, "GOLD", "cc-golden", URL)


def _strings(today: dict[str, Any], root: Path) -> dict[str, Any]:
    """The display strings the page and the chat viewer must show for the
    golden root, each made by the one rule (usagelib)."""
    fmt = usagelib.format_tokens
    tot, usual = today["totals"], today["usual"]
    limits: dict[str, Any] = {}

    def reading(got: dict[str, Any]) -> dict[str, Any]:
        row: dict[str, Any] = {"read_at_text": got["read_at_text"], "stale": got["stale"]}
        for w in usagelib.WINDOWS:
            v = got.get(w)
            row[w] = None if v is None else {
                "pct": usagelib.pct_text(None if v["used"] is None else v["used"] / 100),
                "in": v["in"], "resets_text": v["resets_text"], "expired_text": v["expired_text"]}
        return row

    for tool, got in today["limits"].items():
        row = reading(got)
        # Several accounts: the page names each after the tool and its key, newest first.
        if got["accounts_n"] > 1:
            row["series"] = [{
                "name": f"{usagelib.TOOL_LABELS[tool]} · account {(one['account'] or usagelib.DASH)[:8]}",
                "testid": f"limits-{tool}-{one['account'] or 'none'}", **reading(one)} for one in got["series"]]
        limits[tool] = row
    lines = {}
    for project, agent in (("GOLD", "cc-golden"), ("SIDE", "cx-golden"), ("GOLD", "cc-older")):
        lines[agent] = {str(n): t["line"] for n, t in usagelib.chat_turns(root, project, agent).items()}
    shows_ratio = usual["days_used"] >= usagelib.USUAL_MIN_DAYS
    return {
        "now": NOW,
        "today": {
            "tiles": {
                "new_output": fmt(tot["new_output"]), "cache": fmt(tot["cache"]),
                "share": usagelib.pct_text(tot["share"]), "turns": str(tot["turns"]),
                "chats": f"{tot['chats']} chats", "helpers": fmt(tot["helpers"]["new_output"]),
            },
            "usual": {
                "shows_ratio": shows_ratio,
                "new_output_ratio": usagelib.ratio_text(tot["new_output"], usual["new_output"]) if shows_ratio else "",
                "cache_ratio": usagelib.ratio_text(tot["cache"], usual["cache"]) if shows_ratio else "",
                "share": usagelib.pct_text(usual["share"]),
            },
            "limits": limits,
            "chats": [{"agent_id": c["agent_id"], "new_output": fmt(c["new_output"]), "cache": fmt(c["cache"]),
                       "share": usagelib.pct_text(c["share"]), "helpers": fmt(c["helpers"]["new_output"])}
                      for c in today["chats"]],
            "tasks": [{"id": t["id"], "new_output": fmt(t["new_output"]), "helpers": fmt(t["helpers"]["new_output"]),
                       "status": t["status"]} for t in today["tasks"]],
            "coverage": today["coverage"]["unreadable"],
        },
        "lines": lines,
    }


def test_the_golden_root_reads_as_the_snapshots(golden: tuple[TestClient, Path]) -> None:
    client, root = golden
    store = client.app.state.store  # type: ignore[attr-defined]
    got = _summaries(store)
    for rng, s in got.items():
        _check(f"summary.{rng}.json", s)
    _check("block.txt", _block(root))
    _check("strings.json", _strings(got["today"], root))
    _check("limits.json", {"limits": usagelib.limits(root)})


def test_the_routes_answer_the_snapshots(golden: tuple[TestClient, Path]) -> None:
    client, _root = golden
    for rng in ("today", "30d"):
        r = client.get(f"/api/usage?project=all&range={rng}")
        assert r.status_code == 200
        if not UPDATE:
            assert _plain(r.json()) == _plain(json.loads((EXPECTED / f"summary.{rng}.json").read_text("utf-8")))
    r = client.get("/api/usage/limits")
    if not UPDATE:
        # codex_poll says what this machine has (the codex binary, its home): not a snapshot's.
        assert _plain({"limits": r.json()["limits"]}) == _plain(json.loads((EXPECTED / "limits.json").read_text("utf-8")))
    block = client.get("/api/usage/chat/cc-golden?block=true").json()["block"]
    assert block == _block(_root)


def test_touching_every_file_changes_nothing(golden: tuple[TestClient, Path]) -> None:
    client, root = golden
    store = client.app.state.store  # type: ignore[attr-defined]
    before = _plain(_summaries(store)), _block(root)
    stamp = 1_900_000_000
    for p in root.rglob("*"):
        if p.is_file():
            os.utime(p, (stamp, stamp))
    store.rebuild()
    assert (_plain(_summaries(store)), _block(root)) == before


def test_the_sums_agree(golden: tuple[TestClient, Path]) -> None:
    client, _root = golden
    store = client.app.state.store  # type: ignore[attr-defined]
    for rng, s in _summaries(store).items():
        tot = s["totals"]
        assert s["chats_total"] == len(s["chats"]), rng
        assert sum(c["new_output"] for c in s["chats"]) == tot["new_output"], rng
        assert sum(c["helpers"]["new_output"] for c in s["chats"]) == tot["helpers"]["new_output"], rng
        assert sum(c["cache"] for c in s["chats"]) == tot["cache"], rng
        assert sum(t["new_output"] for t in s["by_tool"]) == tot["new_output"], rng
        for t in s["by_tool"]:
            assert sum(m["new_output"] for m in t["models"]) == t["new_output"], rng
            assert sum(m["helpers"]["new_output"] for m in t["models"]) == t["helpers"]["new_output"], rng
        # A turn counts in one task at most: the tasks never pass the chats.
        assert sum(t["new_output"] for t in s["tasks"]) <= tot["new_output"], rng
        assert sum(t["helpers"]["new_output"] for t in s["tasks"]) <= tot["helpers"]["new_output"], rng


def test_a_turn_across_midnight_counts_on_each_day(golden: tuple[TestClient, Path]) -> None:
    client, root = golden
    store = client.app.state.store  # type: ignore[attr-defined]
    turn = usagelib.chat_turns(root, "GOLD", "cc-golden")[1]
    assert (turn["new"], turn["output"]) == (14_000, 2_000)
    today = usagelib.summary(store, "GOLD", "today")
    week = usagelib.summary(store, "GOLD", "7d")
    cc_today = next(c for c in today["chats"] if c["agent_id"] == "cc-golden")
    cc_week = next(c for c in week["chats"] if c["agent_id"] == "cc-golden")
    # Before midnight: 12 000 new + 900 output, on 31 October only.
    assert cc_week["new_output"] - cc_today["new_output"] == 12_900


def test_the_golden_chat_reads_as_designed(golden: tuple[TestClient, Path]) -> None:
    _client, root = golden
    turns = usagelib.chat_turns(root, "GOLD", "cc-golden")
    # The id written three times: the last output (50) wins.
    assert turns[5]["output"] == 50 + 1_800 and turns[5]["helpers"] == {"n": 2, "new_output": 33_300, "cache": 8_000}
    assert turns[2]["rebuild"] == {"cause": "cache expired: 8 h 58 min since the last turn", "kind": "expired"}
    # Ten minutes after an hour's cache: not expired; the compaction is the cause.
    assert turns[7]["rebuild"] == {"cause": "context compacted", "kind": "compacted"}
    # A line without a time is counted in its turn.
    assert turns[7]["new"] == 18_000 + 700 + 50
    lim = usagelib.limits(root)
    assert lim["claude-code"]["five_hour"]["used"] == 62.5
    assert usagelib.pct_text(lim["claude-code"]["five_hour"]["used"] / 100) == "62%"
    assert lim["codex"]["five_hour"]["expired"] is True and lim["codex"]["stale"] is True


def test_every_row_of_the_page_can_be_shown_in_dollars(golden: tuple[TestClient, Path]) -> None:
    """The dollars view reads ``cost`` on the totals and on each row."""
    client, _root = golden
    got = client.get("/api/usage?range=30d").json()
    rows = [got["totals"], *got["by_tool"], *[m for t in got["by_tool"] for m in t["models"]], *got["chats"], *got["tasks"]]
    for row in rows:
        assert set(row["cost"]) == {"new", "rebuilt", "warm", "output", "helpers"} and "cost_usd" in row
