"""The Usage page's analysis: what the numbers above it mean for the plan limits.

Four parts, each counted from what usagelib already reads:

- **window_now** — the Claude Code 5-hour window: used, the pace over the
  last hour of readings, and when it runs out at that pace (or that it lasts
  until the reset).
- **units** — how much of the 5-hour window one dollar at API prices takes,
  per model, measured: in each past window, the rise of the used percentage
  between two readings set against the dollars spent between them. Only
  readings that go up count (an idle session's status line sends an older one
  again), a window is cut where it reached 99% (the cap hides the rest), and
  a model gets a number only from windows where it made 85% of the dollars.
  It is an observed ratio, not the plan's rate: use outside these chats (the
  claude.ai site, another computer) raises it.
- **resumes** — coming back to a chat after more than an hour: the context
  written to the cache again, what it cost and, with the units, how much of
  the window.
- **context** — the main agent's replies by the size of the context they read,
  with what they cost.

The units are measured over the last 30 days whatever range the page shows,
and over every project: the limits are the account's.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import usagelib

UNIT_DAYS = 30
PURE_SHARE = 0.85      # a window counts for a model when it made this share of the dollars
MIN_RISE = 3.0         # percentage points: below this the reading's rounding dominates
MIN_DOLLARS = 1.0
CAP = 99.0
PACE_SPAN_S = 3600     # the pace is read over the last hour of readings …
PACE_MIN_S = 600       # … and at least ten minutes of them
TOP_CHATS = 5


def _usd(micro: float) -> float:
    return round(micro / 1_000_000, 2)


def _series(data_root: Path) -> list[dict[str, Any]]:
    """Claude Code's readings of its newest account, oldest first."""
    rows, _bad = usagelib.limit_history(data_root)
    lines = [r for r in rows.get("claude-code") or [] if isinstance(r.get("five_hour"), dict)]
    if not lines:
        return []
    account = max(lines, key=lambda r: r["at"]).get("account", "")
    return sorted((r for r in lines if r.get("account", "") == account), key=lambda r: r["at"])


def _windows(series: list[dict[str, Any]]) -> dict[str, list[tuple[datetime, float]]]:
    """Each 5-hour window's readings that go up, up to the cap: {resets_at: [(at, used)]}."""
    out: dict[str, list[tuple[datetime, float]]] = {}
    for r in series:
        w = r["five_hour"]
        used, resets, at = w.get("used"), w.get("resets_at") or "", usagelib._moment(r["at"])
        if used is None or not resets or at is None:
            continue
        got = out.setdefault(resets, [])
        if got and (used < got[-1][1] or got[-1][1] >= CAP):
            continue
        if not got or used > got[-1][1]:
            got.append((at, float(used)))
    return out


def _slots(store: Any) -> dict[tuple[str, str], int]:
    """Every chat's ten-minute slots of dollars by model, summed."""
    out: dict[tuple[str, str], int] = {}
    for a in store.agents():
        folder = usagelib.chat_folder(a)
        if folder is None:
            continue
        for key, micro in (usagelib.chat_usage(folder / usagelib.USAGE_FILE).get("slots") or {}).items():
            out[key] = out.get(key, 0) + micro
    return out


SLOT_S = 600


def _slot(d: datetime) -> str:
    """The ten-minute slot ``d`` falls in, as usagelib keys it (``…T10:20``)."""
    return d.isoformat()[:15] + "0"


def _between(slots: dict[tuple[str, str], int], a: datetime, b: datetime) -> dict[str, int]:
    """Dollars by model in the slots from ``a``'s to ``b``'s, ``b``'s left
    out: both ends floored to the slot, so a stretch is counted in whole
    slots and a slot is never counted in two stretches that meet."""
    lo, hi = _slot(a), _slot(b)
    out: dict[str, int] = {}
    for (slot, model), micro in slots.items():
        if lo <= slot < hi:
            out[model] = out.get(model, 0) + micro
    return out


def units(series: list[dict[str, Any]], slots: dict[tuple[str, str], int], ref: datetime) -> dict[str, Any]:
    """Percent of the 5-hour window per dollar, per model: ``{models: [{model,
    pct_per_usd, low, high, windows, window_usd}], windows, mixed}``."""
    since = ref - timedelta(days=UNIT_DAYS)
    per_model: dict[str, list[float]] = {}
    every: list[float] = []
    counted = mixed = 0
    for _resets, points in _windows(series).items():
        if len(points) < 2 or points[0][0] < since:
            continue
        (a, ua), (b, ub) = points[0], points[-1]
        spent = _between(slots, a, b)
        total = sum(spent.values())
        if ub - ua < MIN_RISE or total < MIN_DOLLARS * 1_000_000:
            continue
        model, micro = max(spent.items(), key=lambda kv: kv[1])
        counted += 1
        every.append((ub - ua) / (total / 1_000_000))
        if micro / total < PURE_SHARE:
            mixed += 1
            continue
        per_model.setdefault(model, []).append((ub - ua) / (total / 1_000_000))
    models = []
    for model, ratios in sorted(per_model.items()):
        mid = statistics.median(ratios)
        models.append({"model": model, "pct_per_usd": round(mid, 3), "low": round(min(ratios), 3),
                       "high": round(max(ratios), 3), "windows": len(ratios),
                       "window_usd": round(100 / mid) if mid > 0 else None})
    models.sort(key=lambda m: -m["pct_per_usd"])
    # A model with no window of its own is counted at the rate of all windows.
    fallback = round(statistics.median(every), 3) if every else None
    return {"models": models, "windows": counted, "mixed": mixed, "days": UNIT_DAYS, "fallback": fallback}


HISTORY_DAYS = 14


def history(series: list[dict[str, Any]], slots: dict[tuple[str, str], int], ref: datetime) -> list[dict[str, Any]]:
    """The past 5-hour windows, oldest first: ``[{start, resets_at, peak,
    capped, usd, model, model_share}]`` — how high each went, whether it hit
    the cap, what was spent in it and on which model mostly."""
    since = ref - timedelta(days=HISTORY_DAYS)
    out = []
    for resets, points in _windows(series).items():
        end = usagelib._moment(resets)
        if end is None or end < since or not points:
            continue
        start = end - timedelta(hours=5)
        # Up to the reset, or up to now with the slot under way.
        spent = _between(slots, start, min(end, ref + timedelta(seconds=SLOT_S)))
        total = sum(spent.values())
        model, micro = max(spent.items(), key=lambda kv: kv[1]) if spent else ("", 0)
        peak = points[-1][1]
        out.append({"start": usagelib._iso(start), "resets_at": resets, "peak": peak, "capped": peak >= CAP,
                    "usd": _usd(total), "model": model, "model_share": round(micro / total, 2) if total else 0})
    return sorted(out, key=lambda w: w["start"])


def _rate(unit: dict[str, float], fallback: float | None):
    """Percent of the 5-hour window per dollar of ``model`` used in ``tool``;
    None when it is not Claude Code's (other tools have limits of their own,
    an OpenCode chat on a Claude model included) or nothing was measured."""
    def at(model: str, tool: str) -> float | None:
        if tool != "claude-code" or not model.startswith("claude-"):
            return None
        return unit.get(model, fallback)
    return at


def _band_pct(band: list[Any], rate: Any) -> float:
    """A context band's replies as percent of the window, each model at its
    own rate (the bands hold Claude Code's replies only)."""
    by_model = band[2] if len(band) > 2 else {}
    return sum((c / 1_000_000 * (rate(m, "claude-code") or 0) for m, c in by_model.items()), 0.0)


def mix(tools: list[dict[str, Any]], totals: dict[str, Any], resumes: dict[str, Any],
        bands: dict[int, list[int]], rate: Any) -> dict[str, Any]:
    """Where the range's use of the window went, by working pattern, in percent
    of one 5-hour window (100 = one full window). The parts do not overlap:
    helpers; the main agent's context written again after a break of over an
    hour; other rebuilds; the main agent's own replies by context size."""
    total = helpers = main_rebuilt = 0.0
    for tl in tools:
        for m in tl.get("models") or []:
            u = rate(m["model"], tl.get("tool") or "")
            if u is None:
                continue
            cost = m.get("cost") or {}
            total += (m.get("cost_usd") or 0) * u
            helpers += (cost.get("helpers") or 0) * u
            main_rebuilt += (cost.get("rebuilt") or 0) * u
    resumed = sum(c / 1_000_000 * (rate(m, "claude-code") or 0) for m, c in resumes["by_model"].items())
    band_w = [_band_pct(bands.get(i, [0, 0, {}]), rate) for i in range(len(usagelib.CONTEXT_BANDS) + 1)]
    parts = [
        {"key": "helpers", "pct": round(helpers, 1)},
        {"key": "resumes", "pct": round(resumed, 1)},
        {"key": "rebuilds", "pct": round(max(0.0, main_rebuilt - resumed), 1)},
        {"key": "over_500k", "pct": round(band_w[3], 1)},
        {"key": "200k_500k", "pct": round(band_w[2], 1)},
        {"key": "under_200k", "pct": round(band_w[0] + band_w[1], 1)},
    ]
    known = sum(p["pct"] for p in parts)
    if total - known > 0.5:
        parts.append({"key": "other", "pct": round(total - known, 1)})
    return {"total_pct": round(total, 1), "windows": round(total / 100, 1), "parts": parts,
            "helpers_n": int(((totals.get("helpers") or {}).get("n")) or 0)}


def prices(tools: list[dict[str, Any]], resumes: dict[str, Any], window_pct: float | None,
           bands: dict[int, list[int]], mixed: dict[str, Any], rate: Any) -> list[dict[str, Any]]:
    """What one occurrence of each pattern takes of the 5-hour window: ``[{key,
    each_pct, times, total_pct}]``, the dearest first."""
    out = []
    if resumes["events"] and window_pct is not None:
        out.append({"key": "resume", "each_pct": round(window_pct / resumes["events"], 2),
                    "times": resumes["events"], "total_pct": window_pct})
    helpers = next((p["pct"] for p in mixed["parts"] if p["key"] == "helpers"), 0)
    if mixed["helpers_n"] and helpers:
        out.append({"key": "helper", "each_pct": round(helpers / mixed["helpers_n"], 2),
                    "times": mixed["helpers_n"], "total_pct": helpers})
    for tl in tools:
        for m in tl.get("models") or []:
            u = rate(m["model"], tl.get("tool") or "")
            if u is None or not m.get("turns"):
                continue
            cost = m.get("cost") or {}
            mc = sum(cost.get(k) or 0 for k in ("new", "rebuilt", "warm", "output"))
            if mc and m["turns"] >= 3:
                out.append({"key": "message", "model": m["model"], "each_pct": round(mc * u / m["turns"], 2),
                            "times": m["turns"], "total_pct": round(mc * u, 1)})
    for i, key in ((3, "reply_over_500k"), (2, "reply_200k_500k"), (1, "reply_100k_200k"), (0, "reply_under_100k")):
        band: list[Any] = bands.get(i) or [0, 0, {}]
        n, pct = int(band[0]), _band_pct(band, rate)
        if n:
            out.append({"key": key, "each_pct": round(pct / n, 3), "times": n, "total_pct": round(pct, 1)})
    return sorted(out, key=lambda x: -x["each_pct"])


def chats_by_window(chats: list[dict[str, Any]], costs: dict[str, dict[tuple[str, str], int]], rate: Any,
                    top: int = 8) -> list[dict[str, Any]]:
    """The chats that took the most of the window, with what made them dear.
    A chat's dollars (helpers included) are priced model by model, Claude
    Code's only: ``costs`` is ``{agent_id: {(tool, model): micro}}``."""
    out = []
    for c in chats:
        total = 0.0
        for (tool, model), micro in (costs.get(c["agent_id"]) or {}).items():
            u = rate(model, tool)
            if u is not None:
                total += micro / 1_000_000 * u
        cost = c.get("cost") or {}
        if total <= 0:
            continue
        out.append({"agent_id": c["agent_id"], "title": c.get("title") or c["agent_id"], "model": c.get("model") or "",
                    "pct": round(total, 1), "helpers_share": round((cost.get("helpers") or 0) / c["cost_usd"], 2) if c.get("cost_usd") else 0,
                    "rebuilt_share": round((cost.get("rebuilt") or 0) / c["cost_usd"], 2) if c.get("cost_usd") else 0,
                    "rebuilds": c.get("rebuilds") or 0, "turns": c.get("turns") or 0})
    return sorted(out, key=lambda x: -x["pct"])[:top]


def window_now(series: list[dict[str, Any]], slots: dict[tuple[str, str], int], ref: datetime) -> dict[str, Any] | None:
    """The 5-hour window open now: ``{used, resets_at, read_at, pace_per_hour,
    runs_out_at, lasts, spent_usd}``; None without a reading of an open window.

    The pace is the rise over the hour before now, every reading counted (one
    that did not change too): while the operator is idle the pace falls to 0,
    and the window lasts, instead of keeping the last busy hour's pace."""
    if not series:
        return None
    resets = series[-1]["five_hour"].get("resets_at") or ""
    end = usagelib._moment(resets)
    if end is None or end <= ref:
        return None
    points: list[tuple[datetime, float]] = []
    for r in series:
        w, at = r["five_hour"], usagelib._moment(r["at"])
        if (w.get("resets_at") or "") != resets or w.get("used") is None or at is None or at > ref:
            continue
        # Within one window the percentage never goes down (an idle session sends an older one again).
        points.append((at, max(float(w["used"]), points[-1][1] if points else 0.0)))
    if not points:
        return None
    last_at, used = points[-1]
    pace = None
    start = ref - timedelta(seconds=PACE_SPAN_S)
    before = [p for p in points if p[0] <= start]
    base_at, base_used = (start, before[-1][1]) if before else points[0]
    if (ref - base_at).total_seconds() >= PACE_MIN_S:
        pace = round((used - base_used) / ((ref - base_at).total_seconds() / 3600), 1)
    runs_out = None
    if pace and pace > 0:
        at = ref + timedelta(hours=(100 - used) / pace)
        runs_out = usagelib._iso(at) if at < end else None
    spent = sum(_between(slots, end - timedelta(hours=5), ref + timedelta(seconds=SLOT_S)).values())
    return {"used": used, "resets_at": resets, "read_at": usagelib._iso(last_at),
            "pace_per_hour": pace, "runs_out_at": runs_out,
            "lasts": pace is not None and runs_out is None, "spent_usd": _usd(spent)}


def _pct(by_model: dict[str, int], rate: Any) -> float | None:
    """Claude Code's dollars by model as percent of the 5-hour window; None
    when a model with dollars has no measured rate (unknown, never 0)."""
    total = 0.0
    for model, micro in by_model.items():
        if not micro:
            continue
        u = rate(model, "claude-code")
        if u is None:
            return None
        total += micro / 1_000_000 * u
    return round(total, 1)


def build(store: Any, ref: datetime, bands: dict[int, list[Any]], resumes: dict[str, Any],
          resume_chats: dict[str, list[int]], agent_rows: dict[str, dict[str, Any]],
          tools: list[dict[str, Any]] | None = None, totals: dict[str, Any] | None = None,
          chats: list[dict[str, Any]] | None = None,
          chat_costs: dict[str, dict[tuple[str, str], int]] | None = None) -> dict[str, Any]:
    root = Path(store.data_root)
    series = _series(root)
    slots = _slots(store)
    u = units(series, slots, ref)
    unit = {m["model"]: m["pct_per_usd"] for m in u["models"]}
    tops = sorted(resume_chats.items(), key=lambda kv: -kv[1][1])[:TOP_CHATS]
    events = resumes["events"]
    names = [*(f"up to {t // 1000}k" for t in usagelib.CONTEXT_BANDS), f"over {usagelib.CONTEXT_BANDS[-1] // 1000}k"]
    replies = sum(b[0] for b in bands.values())
    rate = _rate(unit, u["fallback"])
    resumed_pct = _pct(resumes["by_model"], rate)
    mixed = mix(tools or [], totals or {}, resumes, bands, rate)
    return {
        "mix": mixed,
        "prices": prices(tools or [], resumes, resumed_pct, bands, mixed, rate),
        "history": history(series, slots, ref),
        "chats": chats_by_window(chats or [], chat_costs or {}, rate),
        "window_now": window_now(series, slots, ref),
        "units": u,
        "resumes": {
            "events": events, "cost_usd": _usd(resumes["cost"]),
            "avg_context": round(resumes["context"] / events) if events else 0,
            "avg_usd": _usd(resumes["cost"] / events) if events else 0,
            "window_pct": resumed_pct,
            "after_s": usagelib.RESUME_GAP_S,
            "chats": [{"agent_id": aid, "title": usagelib._title(agent_rows.get(aid, {})) or aid,
                       "events": n, "cost_usd": _usd(c)} for aid, (n, c) in tops],
        },
        "context": {
            "replies": replies,
            "bands": [{"band": names[i], "replies": bands.get(i, [0, 0])[0],
                       "share": round(bands.get(i, [0, 0])[0] / replies, 4) if replies else 0,
                       "cost_usd": _usd(bands.get(i, [0, 0])[1]),
                       "usd_per_reply": _usd(bands[i][1] / bands[i][0]) if bands.get(i, [0, 0])[0] else 0}
                      for i in range(len(names))],
        },
    }
