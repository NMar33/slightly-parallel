"""The Usage page's analysis (usageanalysis.py): the window's pace, what a
dollar takes of the window, resumes after a long break, replies by context."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend import usageanalysis, usagelib


def _reading(at: datetime, used: float, resets: datetime, account: str = "aaaaaaaaaaaa") -> dict[str, Any]:
    return {"at": at.isoformat(), "account": account, "five_hour": {"used": used, "resets_at": resets.isoformat()}}


def _slots(start: datetime, minutes: int, model: str, usd_per_slot: float) -> dict[tuple[str, str], int]:
    out = {}
    for i in range(0, minutes, 10):
        at = (start + timedelta(minutes=i)).isoformat()
        out[(at[:15] + "0", model)] = int(usd_per_slot * 1_000_000)
    return out


def test_a_dollar_of_each_model_is_measured_from_windows_it_made() -> None:
    ref = datetime(2026, 11, 10, 12, 0)
    w1 = datetime(2026, 11, 9, 10, 0)
    w2 = datetime(2026, 11, 9, 16, 0)
    series = [_reading(w1, 10, w1 + timedelta(hours=5)), _reading(w1 + timedelta(minutes=60), 4, w1 + timedelta(hours=5)),
              _reading(w1 + timedelta(minutes=120), 40, w1 + timedelta(hours=5)),
              _reading(w2, 0, w2 + timedelta(hours=5)), _reading(w2 + timedelta(minutes=120), 30, w2 + timedelta(hours=5))]
    slots = {**_slots(w1, 120, "claude-opus-5-5", 5.0), **_slots(w2, 120, "claude-fable-5-1", 2.0)}
    got = {m["model"]: m for m in usageanalysis.units(series, slots, ref)["models"]}
    # Opus: 10% to 40% (the 4% is an older reading sent again) over 12 slots of $5.
    assert got["claude-opus-5-5"]["pct_per_usd"] == 0.5
    assert got["claude-fable-5-1"]["windows"] == 1 and got["claude-fable-5-1"]["window_usd"] == 80


def test_a_window_cut_at_the_cap_and_a_mixed_one_give_no_model_its_number() -> None:
    ref = datetime(2026, 11, 10, 12, 0)
    w = datetime(2026, 11, 9, 10, 0)
    series = [_reading(w, 50, w + timedelta(hours=5)), _reading(w + timedelta(minutes=60), 99, w + timedelta(hours=5)),
              _reading(w + timedelta(minutes=120), 100, w + timedelta(hours=5))]
    slots = {**_slots(w, 120, "claude-opus-5-5", 1.0), **_slots(w, 120, "claude-fable-5-1", 1.0)}
    u = usageanalysis.units(series, slots, ref)
    assert u["models"] == [] and u["mixed"] == 1


def test_the_pace_says_when_the_window_runs_out() -> None:
    now = datetime(2026, 11, 10, 12, 0)
    resets = datetime(2026, 11, 10, 15, 0)
    series = [_reading(now - timedelta(minutes=60), 40, resets), _reading(now - timedelta(minutes=30), 55, resets),
              _reading(now, 70, resets)]
    w = usageanalysis.window_now(series, {}, now)
    assert w is not None and w["pace_per_hour"] == 30.0 and w["runs_out_at"] == "2026-11-10T13:00:00" and not w["lasts"]
    slow = [_reading(now - timedelta(minutes=60), 10, resets), _reading(now, 12, resets)]
    w = usageanalysis.window_now(slow, {}, now)
    assert w is not None and w["lasts"] and w["runs_out_at"] is None
    assert usageanalysis.window_now(slow, {}, resets + timedelta(minutes=1)) is None


def _rec(i: int, at: datetime, **kw: Any) -> dict[str, Any]:
    return {"turn": i, "at": at.isoformat(), "id": f"m{i}", "tool": "claude-code", "model": "claude-opus-5-5",
            "new": 0, "cache_write": 0, "cache": 0, "output": 0, "thinking": 0, "ttl": "1h", "helper": "", **kw}


def test_a_resume_after_an_hour_and_the_replies_by_context(tmp_path: Path) -> None:
    t0 = datetime(2026, 11, 9, 10, 0)
    f = tmp_path / "usage.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in [
        _rec(1, t0, new=300_000, cache_write=300_000),
        _rec(2, t0 + timedelta(minutes=30), cache=300_000, new=10_000, cache_write=10_000),
        _rec(3, t0 + timedelta(hours=2), new=310_000, cache_write=310_000),       # back after 90 minutes
        _rec(4, t0 + timedelta(hours=2, minutes=1), cache=310_000, new=600_000, cache_write=600_000),
    ]) + "\n")
    usagelib.use_prices(tmp_path)
    buckets = usagelib.chat_usage(f)["buckets"].values()
    assert sum(b["resumes"]["events"] for b in buckets) == 1
    assert sum(b["resumes"]["context"] for b in buckets) == 310_000
    assert sum(b["resumes"]["cost"] for b in buckets) == 310_000 * 8            # the 1-hour write price, $8
    bands: dict[int, int] = {}
    for b in buckets:
        for k, v in b["ctx"].items():
            bands[k] = bands.get(k, 0) + v[0]
    assert bands == {2: 3, 3: 1}                                                 # 300k, 310k, 310k; then 910k


def test_the_mix_adds_up_and_other_tools_stay_out_of_claude_codes_window() -> None:
    rate = usageanalysis._rate({"claude-opus-5-5": 0.5}, 0.7)
    assert rate("claude-opus-5-5", "claude-code") == 0.5 and rate("claude-fable-5-1", "claude-code") == 0.7
    assert rate("gpt-6.1-sol", "codex") is None and rate("claude-opus-5-5", "opencode") is None
    tools = [{"tool": "claude-code", "models": [
        {"model": "claude-opus-5-5", "cost_usd": 100.0, "turns": 10,
         "cost": {"new": 10.0, "rebuilt": 20.0, "warm": 30.0, "output": 10.0, "helpers": 30.0}}]},
        {"tool": "codex", "models": [{"model": "gpt-6.1-sol", "cost_usd": 50.0, "turns": 5,
                                      "cost": {"new": 50.0, "rebuilt": 0, "warm": 0, "output": 0, "helpers": 0}}]}]
    resumes = {"events": 2, "cost": 10_000_000, "context": 0, "by_model": {"claude-opus-5-5": 10_000_000}}
    bands = {3: [5, 50_000_000, {"claude-opus-5-5": 50_000_000}], 0: [10, 0, {}]}
    got = usageanalysis.mix(tools, {"helpers": {"n": 3}}, resumes, bands, rate)
    parts = {p["key"]: p["pct"] for p in got["parts"]}
    assert got["total_pct"] == 50.0 and got["windows"] == 0.5             # Codex's $50 is not in it
    assert parts["helpers"] == 15.0 and parts["resumes"] == 5.0 and parts["rebuilds"] == 5.0
    assert round(sum(parts.values()), 1) == got["total_pct"]
    priced = usageanalysis.prices(tools, resumes, 5.0, bands, got, rate)
    each = {(p["key"], p.get("model")): p["each_pct"] for p in priced}
    # A helper 15/3, a reply over 500k 25/5, a message 35/10, a resume 5/2: the dearest first; no Codex.
    assert each == {("helper", None): 5.0, ("reply_over_500k", None): 5.0, ("message", "claude-opus-5-5"): 3.5,
                    ("resume", None): 2.5, ("reply_under_100k", None): 0.0}
    assert [p["each_pct"] for p in priced] == sorted(each.values(), reverse=True)


def test_only_claude_codes_replies_count_in_the_bands_and_the_resumes(tmp_path: Path) -> None:
    t0 = datetime(2026, 11, 9, 10, 0)
    f = tmp_path / "usage.jsonl"
    rows = []
    for tool, model in (("codex", "gpt-6.1-sol"), ("opencode", "claude-opus-5-5")):
        rows += [_rec(1, t0, tool=tool, model=model, id=f"{tool}1", new=300_000, cache_write=300_000),
                 _rec(2, t0 + timedelta(hours=2), tool=tool, model=model, id=f"{tool}2",
                      new=310_000, cache_write=310_000)]
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    usagelib.use_prices(tmp_path)
    buckets = list(usagelib.chat_usage(f)["buckets"].values())
    assert buckets and all(b["ctx"] == {} and b["resumes"]["events"] == 0 for b in buckets)


def test_an_opencode_chat_on_a_claude_model_stays_out_of_the_window() -> None:
    rate = usageanalysis._rate({"claude-opus-5-5": 0.5}, 0.7)
    tools = [{"tool": "opencode", "models": [
        {"model": "claude-opus-5-5", "cost_usd": 40.0, "turns": 4,
         "cost": {"new": 40.0, "rebuilt": 0, "warm": 0, "output": 0, "helpers": 0}}]}]
    resumes = {"events": 0, "cost": 0, "context": 0, "by_model": {}}
    got = usageanalysis.mix(tools, {}, resumes, {}, rate)
    assert got["total_pct"] == 0.0
    assert usageanalysis.prices(tools, resumes, None, {}, got, rate) == []


def test_slot_edges_count_each_slot_once() -> None:
    m = "claude-opus-5-5"
    slots = {("2026-11-09T10:00", m): 1, ("2026-11-09T10:10", m): 10, ("2026-11-09T10:20", m): 100}
    at = datetime(2026, 11, 9, 10, 7)
    # From inside the first slot to the start of the third: the first two whole.
    assert usageanalysis._between(slots, at, datetime(2026, 11, 9, 10, 20)) == {m: 11}
    # Two stretches that meet count the slot between them once.
    left = usageanalysis._between(slots, at, datetime(2026, 11, 9, 10, 14))
    right = usageanalysis._between(slots, datetime(2026, 11, 9, 10, 14), datetime(2026, 11, 9, 10, 30))
    assert left == {m: 1} and right == {m: 110}


def test_the_history_of_windows() -> None:
    ref = datetime(2026, 11, 10, 12, 0)
    w1 = datetime(2026, 11, 9, 10, 0)
    end1 = w1 + timedelta(hours=5)
    w2 = datetime(2026, 11, 10, 9, 0)
    end2 = w2 + timedelta(hours=5)
    series = [_reading(w1 + timedelta(minutes=10), 20, end1), _reading(w1 + timedelta(hours=2), 99.5, end1),
              _reading(w2 + timedelta(minutes=30), 10, end2), _reading(w2 + timedelta(hours=2), 30, end2)]
    slots = {**_slots(w1, 60, "claude-fable-5-1", 3.0), **_slots(w1, 60, "claude-opus-5-5", 1.0),
             **_slots(w2, 180, "claude-opus-5-5", 1.0),
             **_slots(datetime(2026, 11, 8, 10, 0), 60, "claude-opus-5-5", 9.0)}   # before both windows
    got = usageanalysis.history(series, slots, ref)
    assert [w["resets_at"] for w in got] == [end1.isoformat(), end2.isoformat()]
    first, now = got
    assert first["start"] == "2026-11-09T10:00:00" and first["peak"] == 99.5 and first["capped"] is True
    assert first["usd"] == 24.0 and first["model"] == "claude-fable-5-1" and first["model_share"] == 0.75
    # The open window: what was spent up to now, the slot under way included.
    assert now["capped"] is False and now["usd"] == 18.0 and now["model"] == "claude-opus-5-5"


def test_a_chat_is_priced_model_by_model() -> None:
    rate = usageanalysis._rate({"claude-opus-5-5": 0.5, "claude-fable-5-1": 2.0}, None)
    chats = [{"agent_id": "cc-a", "title": "A", "model": "claude-fable-5-1", "cost_usd": 75.0,
              "cost": {"helpers": 10.0, "rebuilt": 5.0}, "turns": 3},
             {"agent_id": "cx-b", "title": "B", "model": "gpt-6.1-sol", "cost_usd": 90.0, "cost": {}, "turns": 2}]
    costs = {"cc-a": {("claude-code", "claude-opus-5-5"): 10_000_000, ("claude-code", "claude-fable-5-1"): 10_000_000,
                      ("opencode", "claude-opus-5-5"): 5_000_000, ("codex", "gpt-6.1-sol"): 50_000_000},
             "cx-b": {("codex", "gpt-6.1-sol"): 90_000_000}}
    got = usageanalysis.chats_by_window(chats, costs, rate)
    # $10 of Opus at 0.5 and $10 of Fable at 2.0; OpenCode's and Codex's dollars are not in it.
    assert [(c["agent_id"], c["pct"]) for c in got] == [("cc-a", 25.0)]


def test_with_no_measured_rate_a_resume_is_unknown_not_zero() -> None:
    rate = usageanalysis._rate({}, None)
    assert usageanalysis._pct({"claude-opus-5-5": 4_000_000}, rate) is None
    assert usageanalysis._pct({"claude-opus-5-5": 4_000_000}, usageanalysis._rate({}, 0.5)) == 2.0
    assert usageanalysis._pct({}, rate) == 0.0


def test_units_from_a_real_parse_of_a_usage_file(tmp_path: Path) -> None:
    """The slots units() reads come from chat_usage: Claude Code's dollars only,
    each message in the ten-minute slot of its own time."""
    t0 = datetime(2026, 11, 9, 10, 0)
    f = tmp_path / "usage.jsonl"
    recs = []
    for i in range(12):        # one message every ten minutes for two hours, $4 each (1M new at $4/M)
        recs.append(_rec(i + 1, t0 + timedelta(minutes=10 * i, seconds=30), id=f"c{i}", new=1_000_000, ttl=""))
    recs.append(_rec(20, t0 + timedelta(minutes=30), id="x1", tool="codex", model="gpt-6.1-sol", new=5_000_000))
    f.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    usagelib.use_prices(tmp_path)
    slots = usagelib.chat_usage(f)["slots"]
    assert {m for _s, m in slots} == {"claude-opus-5-5"} and sum(slots.values()) == 48_000_000
    end = t0 + timedelta(hours=5)
    series = [_reading(t0, 10, end), _reading(t0 + timedelta(hours=2), 34, end)]
    u = usageanalysis.units(series, slots, datetime(2026, 11, 10, 12, 0))
    # 24 points over $48: half a point per dollar.
    assert [(m["model"], m["pct_per_usd"]) for m in u["models"]] == [("claude-opus-5-5", 0.5)] and u["fallback"] == 0.5


def test_the_pace_falls_while_the_operator_is_idle() -> None:
    """Readings that did not change count: an hour after the last rise the
    pace is 0 and the window lasts, not the last busy hour's 'runs out'."""
    busy = datetime(2026, 11, 10, 11, 0)
    resets = datetime(2026, 11, 10, 15, 0)
    series = [_reading(busy - timedelta(minutes=60), 40, resets), _reading(busy - timedelta(minutes=30), 55, resets),
              _reading(busy, 70, resets), _reading(busy + timedelta(minutes=40), 70, resets)]
    w = usageanalysis.window_now(series, {}, busy + timedelta(minutes=30))
    assert w is not None and w["pace_per_hour"] == 15.0 and w["runs_out_at"] == "2026-11-10T13:30:00"
    w = usageanalysis.window_now(series, {}, busy + timedelta(minutes=90))
    assert w is not None and w["pace_per_hour"] == 0.0 and w["lasts"] and w["runs_out_at"] is None
    assert w["read_at"] == "2026-11-10T11:40:00"
    # No reading at all for 90 minutes: the same.
    w = usageanalysis.window_now(series[:3], {}, busy + timedelta(minutes=90))
    assert w is not None and w["pace_per_hour"] == 0.0 and w["lasts"]
