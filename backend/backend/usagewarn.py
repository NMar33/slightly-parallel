"""Usage warnings in the chat: a line under a Claude Code reply when the chat
costs a lot of the 5-hour limit.

Four kinds, at most one per reply, the first that applies:

- ``compact`` — the context passed the model's context window less 70k
  tokens: Claude Code is about to compact the chat on its own and keep only
  a summary (once per chat). The window is the one the status line reports;
  without it, 1M for a chat whose context already passed 200k, else 200k.
- ``context`` — the chat's context crossed 300k, then 500k, then 800k
  tokens (each once per chat).
- ``rebuild`` — the turn's first message wrote the whole chat to the cache
  again after a break of more than an hour (the cache had expired).
- ``window`` — the chat used more than 25% of the current 5-hour window
  (once per window).

The percent of the limit is the turn's dollars at API prices (usagelib's
cost fields) times the percent-of-limit per dollar of its model: the units
the Usage page's analysis measures (usageanalysis.units). The server writes
them to ``<data root>/.usage/units.json`` each time it builds the analysis
(``write_units``); the hook reads that file. A model without a unit takes
the file's fallback; without the file there is no percent. Only models whose
id starts with ``claude-`` count.

Standard library only, no relative imports: the capture hook loads this file
by path and hands it the usagelib it loaded (``due``).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

UNITS_FILE = "units.json"
USAGE_DIR = ".usage"
CONTEXT_STEPS = (300_000, 500_000, 800_000)
BREAK_S = 3600
WINDOW_SHARE = 25.0          # percent of the 5-hour window
WINDOW_S = 5 * 3600
KINDS = ("compact", "context", "rebuild", "window")
#: Claude Code compacts a chat on its own a little before the window is full.
COMPACT_HEADROOM = 70_000
BIG_WINDOW = 1_000_000
SMALL_WINDOW = 200_000
OFF_HINT = ("To turn these warnings off in this chat, type #usage-warnings-off. "
            "You can also turn them off in Settings.")
_COSTS = ("cost_new", "cost_rebuilt", "cost_warm", "cost_output")


def _shared() -> Any:
    """hookshared: imported in the server, loaded beside this file in the hook."""
    try:
        from . import hookshared
        return hookshared
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("sp_hookshared_w", Path(__file__).with_name("hookshared.py"))
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


# -- the units (written by the server, read by the hook) ---------------------

def units_path(data_root: Path) -> Path:
    return Path(data_root) / USAGE_DIR / UNITS_FILE


def _rate_of(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v <= 0 or v == float("inf"):
        return None
    return float(v)


def write_units(data_root: Path, units: Any) -> bool:
    """Keep the analysis' units (``{models: [{model, pct_per_usd}], fallback,
    days}``) as ``{at, days, models: {model: pct_per_usd}, fallback}``, the
    ``claude-`` models only. Written only when they changed; never raises.
    Answers whether the file was written."""
    if not isinstance(units, dict):
        return False
    models: dict[str, float] = {}
    for m in units.get("models") or []:
        if not isinstance(m, dict):
            continue
        name, rate = str(m.get("model") or ""), _rate_of(m.get("pct_per_usd"))
        if name.startswith("claude-") and rate is not None:
            models[name] = rate
    body = {"days": units.get("days"), "models": models, "fallback": _rate_of(units.get("fallback"))}
    path = units_path(data_root)
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(old, dict) and {k: old.get(k) for k in body} == body:
            return False
    except (OSError, ValueError):
        pass
    tmp = ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), **body}, fh, indent=2)
            fh.write("\n")
        # Patient on Windows, where a reader holding the file open refuses the swap a moment.
        _shared().replace_file(tmp, path)
        return True
    except OSError:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False


def read_units(data_root: Path) -> dict[str, Any] | None:
    """The units file; None when there is none or it cannot be read."""
    try:
        got = json.loads(units_path(data_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(got, dict):
        return None
    models = got.get("models") if isinstance(got.get("models"), dict) else {}
    return {"models": {str(k): r for k, v in models.items() if (r := _rate_of(v)) is not None},
            "fallback": _rate_of(got.get("fallback"))}


def rate(units: dict[str, Any] | None, model: str) -> float | None:
    """Percent of the 5-hour window per dollar of ``model``; None without a
    units file, for a model that is not Claude's, or with no unit and no
    fallback."""
    if units is None or not str(model or "").startswith("claude-"):
        return None
    return units["models"].get(model) or units.get("fallback")


def percent(by_model: dict[str, float], units: dict[str, Any] | None) -> float | None:
    """Dollars by model as percent of the 5-hour window; None when a model
    with dollars has no rate."""
    total = 0.0
    for model, usd in by_model.items():
        if not usd:
            continue
        r = rate(units, model)
        if r is None:
            return None
        total += usd * r
    return total


# -- words ---------------------------------------------------------------------

def pct_words(pct: float, lib: Any) -> str:
    """``12%`` by usagelib's rule (the nearest whole, a tie down); under 1%
    in tenths (``0.4%``), never ``0%``."""
    if pct >= 1:
        return str(lib.pct_text(pct / 100))
    return f"{max(0.1, int(pct * 10) / 10):.1f}%"


def _unit(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def gap_words(seconds: float) -> str:
    """``2 hours`` · ``1 hour 20 minutes`` · ``1 day 3 hours``: floored."""
    mins = max(0, int(seconds // 60))
    days, rest = divmod(mins, 24 * 60)
    hours, minutes = divmod(rest, 60)
    if days:
        return _unit(days, "day") + (f" {_unit(hours, 'hour')}" if hours else "")
    if hours:
        return _unit(hours, "hour") + (f" {_unit(minutes, 'minute')}" if minutes else "")
    return _unit(minutes, "minute")


# -- what applies to a turn ----------------------------------------------------

def _usd(tu: dict[str, Any], rebuilt: bool = True) -> float:
    """The turn's dollars; without the context written again, what a reply
    costs at this size of the chat."""
    return sum(float(tu.get(k) or 0) for k in _COSTS if rebuilt or k != "cost_rebuilt") / 1_000_000


def _break_s(cu: dict[str, Any], turn: int, lib: Any) -> float | None:
    """Seconds from the main agent's last message before the turn to the
    turn's first one."""
    turns = cu.get("turns") or {}
    cur = turns.get(turn)
    earlier = [n for n, t in turns.items() if n < turn and t.get("last")]
    if not cur or not cur.get("first") or not earlier:
        return None
    a = lib._moment(turns[max(earlier)]["last"].get("at"))
    b = lib._moment(cur["first"].get("at"))
    return (b - a).total_seconds() if a is not None and b is not None else None


def context_window(lib: Any, data_root: Path, folder: Path, turns: dict[int, dict[str, Any]]) -> int:
    """The chat's context window in tokens: the size the status line reported
    for its session; without one, 1M when the chat's context already passed
    200k (only a 1M window holds that), else 200k."""
    meta = lib.chat_meta(Path(folder))
    state = lib.session_state(data_root, "claude-code", str(meta.get("session_ref") or ""))
    ctx = state.get("context") if isinstance(state.get("context"), dict) else {}
    size = ctx.get("size")
    if not isinstance(size, bool) and isinstance(size, (int, float)) and size == size and size > COMPACT_HEADROOM:
        return int(size)
    peak = max((int(t.get("context_tokens") or 0) for t in turns.values()), default=0)
    return BIG_WINDOW if peak > SMALL_WINDOW else SMALL_WINDOW


def _window(lib: Any, data_root: Path, cu: dict[str, Any], units: dict[str, Any] | None,
            ref: datetime) -> tuple[str, float] | None:
    """(the open 5-hour window's reset, percent of it this chat used)."""
    got = (lib.limits(data_root, ref) or {}).get("claude-code") or {}
    five = got.get("five_hour") or {}
    resets = lib._moment(five.get("resets_at"))
    if resets is None or five.get("expired") or resets <= ref:
        return None
    start = resets - timedelta(seconds=int(five.get("span_s") or WINDOW_S))
    floor = start.strftime("%Y-%m-%dT%H:%M")[:15] + "0"
    by_model: dict[str, float] = {}
    for (slot, model), micro in (cu.get("slots") or {}).items():
        if slot >= floor:
            by_model[model] = by_model.get(model, 0.0) + micro / 1_000_000
    pct = percent(by_model, units)
    return (lib._iso(resets), pct) if pct is not None else None


def due(lib: Any, data_root: Path, folder: Path, turn: int, state: dict[str, Any],
        ref: datetime | None = None) -> tuple[str, str] | None:
    """(kind, text) of the warning for this turn, or None. ``lib``: usagelib.
    ``state`` is the chat's memory (meta.json ``usage_warned``): what was
    shown is written into it, so nothing repeats; the caller saves it."""
    # The prices the server counts with (an update in .usage/api-prices.jsonl),
    # not the built-in ones: the same dollars as units.json's.
    lib.use_prices(data_root)
    turns = lib.turns_in(folder, data_root)
    tu = turns.get(turn) if isinstance(turns, dict) else None
    if not tu or str(tu.get("tool") or "claude-code") != "claude-code":
        return None
    units = read_units(data_root)
    model = str(tu.get("model") or "")
    r = rate(units, model)
    pct = _usd(tu) * r if r is not None else None
    each = _usd(tu, rebuilt=False) * r if r is not None else None
    at: datetime = ref if ref is not None else lib.now()
    text = ""
    kind = ""

    ctx = int(tu.get("context_tokens") or 0)
    shown = [int(x) for x in state.get("context") or [] if isinstance(x, int)]
    crossed = [s for s in CONTEXT_STEPS if ctx >= s and s not in shown]
    if not state.get("compact"):
        limit = context_window(lib, data_root, folder, turns) - COMPACT_HEADROOM
        if ctx >= limit:
            state["compact"] = True
            if crossed:          # the size is told here; its steps are not told again
                state["context"] = sorted({*shown, *crossed})
                crossed = []
            kind = "compact"
            text = (f"This chat has {lib.format_tokens(ctx)} tokens. Claude Code will compact it at about "
                    f"{lib.format_tokens(limit)} tokens and keep only a summary.")
    if crossed and not kind:
        state["context"] = sorted({*shown, *crossed})
        kind = "context"
        text = f"This chat has {lib.format_tokens(ctx)} tokens."
        if each is not None:
            text += f" Each reply now uses about {pct_words(each, lib)} of the 5-hour limit."

    if not kind:
        rb = tu.get("rebuild") or {}
        if rb.get("kind") == "expired" and state.get("rebuild_turn") != turn:
            cu = lib.chat_usage(Path(folder) / lib.USAGE_FILE)
            gap = _break_s(cu, turn, lib)
            if gap is not None and gap > BREAK_S:
                state["rebuild_turn"] = turn
                kind = "rebuild"
                text = f"This reply read the whole chat again after a break of {gap_words(gap)}."
                if pct is not None:
                    text += f" It used about {pct_words(pct, lib)} of the 5-hour limit."

    if not kind and units is not None:
        cu = lib.chat_usage(Path(folder) / lib.USAGE_FILE)
        win = _window(lib, data_root, cu, units, at)
        if win is not None and win[1] > WINDOW_SHARE and state.get("window") != win[0]:
            state["window"] = win[0]
            kind = "window"
            text = f"This chat has used {pct_words(win[1], lib)} of the current 5-hour limit."

    if not kind:
        return None
    if not state.get("hint"):
        state["hint"] = True
        text += "\n" + OFF_HINT
    return kind, text
