"""Usage: the tokens each chat used, and how much of each plan is used.

Read from three kinds of file the hooks write (the parsers of the tools' own
logs are in hookshared.py; this module reads only what they wrote):

- ``projects/<p>/chats/<agent>/usage.jsonl`` — one line per API message:
  ``{turn, at, id, tool, model, new, cache_write, cache, output, thinking,
  ttl, helper, limit?, compacted?}``. ``new`` is what the model read for the
  first time (cache writes included), ``output`` what it wrote (thinking
  inside it), ``cache`` what it read again from cache. One id is one
  message: the last line of an id wins.
- ``.usage/limits.jsonl`` — the plan limits, one line per reading. The
  limits are the account's: a line names its ``account`` (the tool's
  config folder, as a 12-hex key), and as data its ``model`` and
  ``session``; the readings of one (tool, account) are a series. Lines
  written before carry none of them and are one series of their tool.
- ``.usage/sessions/<tool>-<session>.json`` — an open chat's context and
  cache state, from Claude Code's status line.

The numbers of a turn: ``→ 1.9k ↑ 512 ↓ (108k)`` — new input up, output
down, cache in brackets. ``new_output`` is the MAIN agent's new + output
everywhere (totals, tools, models, chats, tasks, the line); helper agents
count into the turn that started them and are kept apart as ``helpers
{n, new_output, cache}``. Each message is counted on its own day.

One rule per number, shared with the hook and the page (the table
``testdata/usage/format-table.json`` holds the cases): tokens by
format_tokens; a percentage is the nearest whole number, a tie down
(``pct_text``); the ratio to the usual day in tenths, a tie down
(``ratio_text``); a duration floored (``span_text``).

Files are read once per change and kept as SUMS (per turn, per day, per
model), never as raw records; the limits history is read incrementally
(only the bytes appended since). Every clock read goes through ``now()``,
which honours ``SP_NOW`` (a local ISO moment; a test switch).

Standard library only at the top of the file, no relative imports outside
the functions that need the store: the capture hook loads this file by path
(``capture._backend_module("usagelib")``) for the #usage block and the line
after each reply.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import threading
import time
from bisect import bisect_right, insort
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

USAGE_FILE = "usage.jsonl"
USAGE_DIR = ".usage"
LIMITS_FILE = "limits.jsonl"
SESSIONS_DIR = "sessions"

TOOL_LABELS = {"claude-code": "Claude Code", "codex": "Codex", "opencode": "OpenCode", "cursor": "Cursor"}
#: The tools whose plan limits the #usage block lists (OpenCode reports none).
LIMIT_TOOLS = ("claude-code", "codex")
WINDOWS = ("five_hour", "seven_day")
WINDOW_WORDS = {"five_hour": "5-hour", "seven_day": "weekly"}
#: A window's length when the reading does not say (Codex gives window_minutes).
WINDOW_SPAN_S = {"five_hour": 5 * 3600, "seven_day": 7 * 24 * 3600}

RANGES = {"today": 1, "7d": 7, "30d": 30}
STALE_MIN = 15            # a limits reading older than this is drawn dimmed
USUAL_DAYS = 30           # the usual day: median of at most the 30 last active days …
USUAL_REACH = 90          # … within the last 90 calendar days, today left out
USUAL_MIN_DAYS = 3        # "× your usual day" needs this many active days
TOP_CHATS = 40
TOP_TASKS = 20
REBUILD_SHARE = 0.2       # a turn whose first read of the cache fell below 20% …
REBUILD_FLOOR = 20_000    # … of what the turn before left cached (cache + cache_write), over this
MISS_WINDOW_S = 120       # Claude Code's own miss cause counts within 2 min
LIMIT_AT_MAX_MIN = 30     # a turn takes the limits reading of at most 30 min before it
DASH = "—"
READ_COLUMN = 58          # where "(read HH:MM)" starts in the #usage block
SWEEP_S = 60              # how often the caches drop files that are gone

_SUMS = ("new", "output", "cache", "cache_write", "thinking", "rebuilt",
         "cost_new", "cost_rebuilt", "cost_warm", "cost_output", "unpriced")
_COSTS = ("cost_new", "cost_rebuilt", "cost_warm", "cost_output")

PRICES_FILE = "api-prices.jsonl"
PRICE_FIELDS = ("input", "write_5m", "write_1h", "read", "output")


def _price(i: float, w5: float | None, w1: float | None, r: float, o: float, **more: Any) -> dict[str, Any]:
    return {"input": i, "write_5m": w5, "write_1h": w1, "read": r, "output": o, **more}


#: API prices, dollars per million tokens, as they stood on API_PRICES_AS_OF.
#: What the Usage page's dollars are counted with; it is not what a plan
#: charges, and not its limits. #usage-price adds later ones
#: (.usage/api-prices.jsonl): a message is priced as of its own day. A model
#: with none counts in ``unpriced``. A write price of None: the tool's log
#: records no cache writes. ``over_tokens``: a longer prompt costs ``over``.
API_PRICES_AS_OF = "2026-11-05"
API_PRICES: dict[str, dict[str, Any]] = {
    "claude-fable-5-1": _price(10.0, 12.5, 20.0, 0.25, 50.0),
    "claude-fable-5": _price(10.0, 12.5, 20.0, 1.0, 50.0),
    "claude-opus-5-5": _price(4.0, 5.0, 8.0, 0.2, 20.0),
    "claude-opus-5": _price(5.0, 6.25, 10.0, 0.5, 25.0),
    "claude-sonnet-5-5": _price(2.0, 2.5, 4.0, 0.1, 10.0),
    "claude-sonnet-5": _price(2.0, 2.5, 4.0, 0.2, 10.0),
    "claude-haiku-5-5": _price(0.1, 0.125, 0.2, 0.01, 0.5, over_tokens=100_000,
                               over=_price(0.5, 0.625, 1.0, 0.05, 2.5)),
    "gpt-6.1-sol": _price(2.0, None, None, 0.1, 10.0),
}
API_PRICE_SOURCES = ("https://platform.claude.com/docs/en/about-claude/pricing",
                     "https://developers.openai.com/api/docs/pricing")


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------


def now() -> datetime:
    """The moment, naive local. ``SP_NOW`` (a local ISO moment such as
    ``2026-11-01T14:48:00``) fixes it, for tests and golden files."""
    fixed = os.environ.get("SP_NOW", "").strip()
    if fixed:
        got = _moment(fixed)
        if got is not None:
            return got
    return datetime.now()


_now = now  # for the functions whose ``now`` argument hides this one


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


def _finite(v: Any) -> float | None:
    """A number as a finite float; None for anything else (NaN, inf, text)."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def _int(v: Any) -> int:
    """A count as a whole number ≥ 0: ``"3"``, ``"3.0"``, ``3.7`` → 3;
    anything else (NaN, inf, text, a list) → 0. Never raises."""
    if isinstance(v, int) and not isinstance(v, bool):
        return max(0, v)
    if isinstance(v, str):
        s = v.strip()
        try:
            return max(0, int(s))
        except ValueError:
            pass
    f = _finite(v)
    return max(0, int(f)) if f is not None else 0


def _num(v: Any) -> float | None:
    return _finite(v)


def _band(n: int, step: int, top: int | None) -> int:
    """``n / step`` rounded half down; floored when rounding would reach
    ``top`` (the next band's display: 999 950 is 999k, not 1000k)."""
    q, r = divmod(n, step)
    if r * 2 > step:
        q += 1
    if top is not None and q >= top:
        q = n // step
    return q


def _tenths(q: int, unit: str) -> str:
    whole, tenth = divmod(q, 10)
    return f"{whole}{unit}" if tenth == 0 else f"{whole}.{tenth}{unit}"


def format_tokens(n: Any) -> str:
    """A token count as the pages and the terminal show it.

    0–999 ``512`` · 1 000–9 999 ``2.4k`` (``.0`` dropped: ``3k``) ·
    10 000–999 999 ``108k`` · 1M–9.99M ``4.1M`` · ≥ 10M ``41M``. Half rounds
    down, and a band never shows the next one's number (999 950 → ``999k``).
    None is ``—``; NaN and infinity count as 0."""
    if n is None:
        return DASH
    if isinstance(n, int) and not isinstance(n, bool):
        v = n
    else:
        f = _finite(n)
        if f is None:
            try:
                float(n)
            except (TypeError, ValueError):
                return DASH
            f = 0.0  # NaN, inf: 0, never a crash
        v = int(round(f))
    if v < 0:
        return "-" + format_tokens(-v)
    if v < 1_000:
        return str(v)
    if v < 10_000:
        return _tenths(_band(v, 100, 100), "k")
    if v < 1_000_000:
        return f"{_band(v, 1_000, 1_000)}k"
    if v < 10_000_000:
        return _tenths(_band(v, 100_000, 100), "M")
    return f"{_band(v, 1_000_000, None)}M"


def _pct(x: Any) -> int:
    """A share (0.625) as a whole percentage: the nearest, a tie down (62).
    Negative, NaN or not a number: 0."""
    f = _finite(x)
    if f is None or f <= 0:
        return 0
    v = round(f * 100, 6)          # float noise off: 0.699 * 100 is 69.9, not 69.899…
    whole = math.floor(v)
    return whole + 1 if v - whole > 0.5 else whole


def pct_text(x: Any) -> str:
    """``62%`` for 0.625; ``—`` when there is no share."""
    return DASH if _finite(x) is None else f"{_pct(x)}%"


def ratio_tenths(value: Any, usual: Any) -> int | None:
    """value ÷ usual in tenths, the nearest, a tie down; None without a usual."""
    v, u = _int(value), _int(usual)
    if u <= 0:
        return None
    return _band(v * 10, u, None)


def ratio_text(value: Any, usual: Any) -> str:
    """``1.6`` for 4.1M against a usual 2.6M; ``—`` without a usual."""
    q = ratio_tenths(value, usual)
    return DASH if q is None else f"{q // 10}.{q % 10}"


def share(cache: int, new: int) -> float | None:
    """cache ÷ (cache + new); None when both are 0."""
    whole = cache + new
    return round(cache / whole, 4) if whole > 0 else None


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def _moment(value: Any) -> datetime | None:
    """A stamp as naive local time: epoch seconds, naive ISO (local) or a
    zoned ISO (converted, not cut). None when it is no moment."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            f = float(value)
            return datetime.fromtimestamp(f) if math.isfinite(f) else None
        except (OverflowError, OSError, ValueError):
            return None
    try:
        d = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    try:
        return d.astimezone().replace(tzinfo=None) if d.tzinfo is not None else d
    except (OverflowError, OSError, ValueError):
        return None


def _iso(d: datetime | None) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%S") if d else ""


def yymm_dd(d: date) -> str:
    return f"{d.year % 100:02d}{d.month:02d}-{d.day:02d}"


def _day_of_iso(at: str) -> str:
    """``2026-11-01T14:02:11`` → ``2611-01``; '' when it is no day."""
    try:
        return yymm_dd(date.fromisoformat(at[:10]))
    except ValueError:
        return ""


def range_days(rng: str, today: date | None = None) -> list[str]:
    """The days of a range as YYMM-DD, oldest first."""
    today = today or now().date()
    n = RANGES.get(rng, 1)
    return [yymm_dd(today - timedelta(days=i)) for i in range(n - 1, -1, -1)]


def span_text(delta: timedelta) -> str:
    """``1 h 52 min`` · ``40 min`` · ``2 d 3 h``: floored, no padding."""
    mins = max(0, int(delta.total_seconds() // 60))
    if mins < 60:
        return f"{mins} min"
    if mins < 24 * 60:
        h, m = divmod(mins, 60)
        return f"{h} h {m} min" if m else f"{h} h"
    d, rest = divmod(mins, 24 * 60)
    h = rest // 60
    return f"{d} d {h} h" if h else f"{d} d"


def _clock(d: datetime, ref: datetime, weekday: bool = False) -> str:
    """``16:40`` on the same day as ``ref``; ``Thu 09:00`` on another day,
    or always with ``weekday``."""
    if weekday or d.date() != ref.date():
        return d.strftime("%a %H:%M")
    return d.strftime("%H:%M")


# ---------------------------------------------------------------------------
# Reading the files
# ---------------------------------------------------------------------------


class Unreadable(Exception):
    """A file that is there and cannot be read (permissions, a lock)."""


def _stat_sig(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise Unreadable(str(exc)) from exc
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _json_lines(data: bytes) -> tuple[list[dict[str, Any]], int]:
    """The JSON objects of jsonl bytes, and how many lines were not one."""
    out: list[dict[str, Any]] = []
    bad = 0
    for raw in data.split(b"\n"):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            bad += 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        else:
            bad += 1
    return out, bad


def _sums() -> dict[str, int]:
    return dict.fromkeys(_SUMS, 0)


def _add_sums(into: dict[str, int], r: dict[str, Any]) -> None:
    for k in _SUMS:
        into[k] += r[k]


def _record(r: dict[str, Any]) -> dict[str, Any] | None:
    """One usage line, every number made safe; None for a line to skip."""
    model = str(r.get("model") or "")
    if model == "<synthetic>":
        return None
    at = _moment(r.get("at"))
    limit = r.get("limit")
    lim: dict[str, float] = {}
    if isinstance(limit, dict):
        for w in WINDOWS:
            v = _finite(limit.get(w))
            if v is not None:
                lim[w] = v
    return {
        "turn": _int(r.get("turn")), "at": _iso(at), "id": str(r.get("id") or ""),
        "tool": str(r.get("tool") or ""), "model": model,
        **{k: _int(r.get(k)) for k in _SUMS},
        "ttl": str(r.get("ttl") or ""), "helper": str(r.get("helper") or ""),
        "effort": str(r.get("effort") or ""),
        "limit": lim, "compacted": r.get("compacted") is True,
    }


def _book_of(lines: list[dict[str, Any]], stamp: str) -> dict[str, Any]:
    """The prices over time: per model ``[(from, price)]``, oldest first;
    the built-in ones hold from the beginning."""
    models: dict[str, list[tuple[str, dict[str, Any]]]] = {m: [("", v)] for m, v in API_PRICES.items()}
    as_of, sources = API_PRICES_AS_OF, list(API_PRICE_SOURCES)
    for line in sorted(lines, key=lambda x: str(x.get("at") or "")):
        at = str(line.get("at") or "")
        got = line.get("models")
        if not at or not isinstance(got, dict):
            continue
        for model, price in got.items():
            if isinstance(price, dict) and _finite(price.get("input")) is not None:
                models.setdefault(str(model), []).append((at, price))
        as_of = at[:10]
        if isinstance(line.get("sources"), list) and line["sources"]:
            sources = [str(x) for x in line["sources"]]
    return {"stamp": stamp, "models": models, "as_of": as_of, "sources": sources}


_book: dict[str, Any] = _book_of([], "")


def use_prices(data_root: Path) -> dict[str, Any]:
    """The prices of this data root, for what is parsed next. A new book
    moves the stamp in chat_usage's key, so the files are counted again."""
    global _book
    path = Path(data_root) / USAGE_DIR / PRICES_FILE
    sig = _stat_sig(path)
    stamp = f"{path}:{sig}" if sig is not None else ""
    with _lock:
        if _book["stamp"] == stamp:
            return _book
    lines: list[dict[str, Any]] = []
    if sig is not None:
        try:
            lines = _json_lines(path.read_bytes())[0]
        except OSError:
            lines = []
    book = _book_of(lines, stamp)
    with _lock:
        _book = book
    return book


class PricesRefused(ValueError):
    """An update of the prices that says something it cannot mean."""


def _rate(value: Any, what: str) -> float:
    got = _finite(value)
    if got is None or got <= 0 or got > 1000:
        raise PricesRefused(f"{what}: a price is dollars per million tokens, above 0 and at most 1000; {value!r} sent")
    return got


def _clean_price(model: str, price: Any) -> dict[str, Any]:
    if not isinstance(price, dict):
        raise PricesRefused(f"{model}: a price is an object with {', '.join(PRICE_FIELDS)}")
    unknown = sorted(set(price) - {*PRICE_FIELDS, "over_tokens", "over"})
    if unknown:
        raise PricesRefused(f"{model}: unknown field {unknown[0]}; the fields are {', '.join((*PRICE_FIELDS, 'over_tokens', 'over'))}")
    out: dict[str, Any] = {}
    for k in ("input", "read", "output"):
        if price.get(k) is None:
            raise PricesRefused(f"{model}: {k} is required")
        out[k] = _rate(price[k], f"{model}.{k}")
    for k in ("write_5m", "write_1h"):
        out[k] = None if price.get(k) is None else _rate(price[k], f"{model}.{k}")
    if (price.get("over_tokens") is None) != (price.get("over") is None):
        raise PricesRefused(f"{model}: over_tokens and over go together")
    if price.get("over") is not None:
        if not isinstance(price["over"], dict):
            raise PricesRefused(f"{model}: over is an object with {', '.join(PRICE_FIELDS)}, "
                                "the prices above over_tokens")
        limit = _finite(price["over_tokens"])
        if limit is None or limit <= 0:
            raise PricesRefused(f"{model}: over_tokens is the prompt's length in tokens")
        out["over_tokens"] = int(limit)
        out["over"] = _clean_price(f"{model} over {int(limit)}", {k: v for k, v in price["over"].items()})
    return out


def write_prices(data_root: Path, body: dict[str, Any], by: str, at: datetime | None = None) -> dict[str, Any]:
    """One update of the prices: ``{models: {model: price}, sources: [url], note?}``.
    Appended, so the days before keep their prices. Answers what changed,
    and a warning for a price that moved more than five times."""
    models, sources = body.get("models"), body.get("sources")
    if not isinstance(models, dict) or not models:
        raise PricesRefused("models is required: {model: {input, write_5m, write_1h, read, output}}")
    if not isinstance(sources, list) or not any(str(x).startswith("https://") for x in sources):
        raise PricesRefused("sources is required: the https pages the prices were read from")
    clean = {str(m).strip(): _clean_price(str(m), p) for m, p in models.items() if str(m).strip()}
    book = use_prices(data_root)
    changed, new_models, same, warnings = [], [], [], []
    for model, price in sorted(clean.items()):
        known = book["models"].get(model)
        if not known:
            new_models.append(model)
            continue
        old = known[-1][1]
        diffs = [{"model": model, "field": k, "old": old.get(k), "new": price.get(k)}
                 for k in (*PRICE_FIELDS, "over_tokens", "over") if old.get(k) != price.get(k)]
        changed += diffs
        if not diffs:
            same.append(model)
        for d in diffs:
            if d["field"] in PRICE_FIELDS and d["old"] and d["new"] and not 0.2 <= d["new"] / d["old"] <= 5:
                warnings.append(f"{model}.{d['field']} moved from {d['old']} to {d['new']}: check it on the page")
    moment = (at or now()).replace(microsecond=0).isoformat()
    line = {"at": moment, "by": by, "sources": [str(x) for x in sources], "note": str(body.get("note") or "")[:400],
            "models": clean}
    path = Path(data_root) / USAGE_DIR / PRICES_FILE
    from . import hookshared
    path.parent.mkdir(parents=True, exist_ok=True)
    with hookshared.locked(path):
        hookshared._append_bytes(path, json.dumps(line, ensure_ascii=False) + "\n")
    use_prices(data_root)
    return {"at": moment, "changed": changed, "new_models": new_models, "unchanged": same, "warnings": warnings}


def price_material(data_root: Path, store: Any) -> dict[str, Any]:
    """What an update of the prices is written from: every model the chats
    used, the prices now, and the pages to read."""
    book = use_prices(data_root)
    used: dict[str, str] = {}
    for a in store.agents():
        folder = chat_folder(a)
        if folder is None:
            continue
        cu = chat_usage(folder / USAGE_FILE)
        for b in cu["buckets"].values():
            for (model, _helper) in b["models"]:
                if model:
                    used.setdefault(model, str(next(iter(cu["tools"]), "")))
    return {
        "models_used": [{"model": m, "tool": t, "has_price": m in book["models"]} for m, t in sorted(used.items())],
        "prices_now": {m: v[-1][1] for m, v in sorted(book["models"].items())},
        "as_of": book["as_of"],
        "pages": list(API_PRICE_SOURCES),
        "instructions": (
            "Read the pages with your web fetch tool, from the top; if your tool cannot read a page, say so and "
            "leave its models out. Use the provider's own pages only; "
            "for a model from another provider, find that provider's own pricing page and name it in sources. "
            "Give every model in models_used and every model in prices_now that the page lists: dollars per "
            "million tokens, standard tier: input, read (cache read or cached input), output, and write_5m and "
            "write_1h (cache writes; null when the provider has no such price for the model: a provider's other "
            "lifetimes are not these). A higher price for long prompts goes in over_tokens and over, with the same fields. "
            "Never guess, and never reuse a number from prices_now that the page does not show: leave that model out, "
            "and say so. Then call usage_prices_write {models, sources, note}. It keeps the days before at their old "
            "prices. Reply with what its answer says changed, its warnings, and the models you left out."),
    }


def price_of(model: str, at: str, book: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The model's price on a message's day (its first known, before that);
    None for a model with no price."""
    known = (book or _book)["models"].get(model)
    if not known:
        return None
    day = at[:10]
    got = known[0][1]
    for since, price in known:
        if since[:10] <= day:
            got = price
    return got


def _priced(r: dict[str, Any]) -> None:
    """A message's cost by kind (millionths of a dollar at API prices), or
    its tokens in ``unpriced``. A message with 1-hour writes is priced as all
    1-hour: the log names one lifetime per message."""
    price = price_of(r["model"], r["at"])
    if price is None:
        r["unpriced"] = r["new"] + r["cache"] + r["output"]
        return
    over = price.get("over")
    if isinstance(over, dict) and r["new"] + r["cache"] > (_finite(price.get("over_tokens")) or math.inf):
        price = over
    written = min(r["cache_write"], r["new"])
    base = float(price["input"])
    rate = price.get("write_1h" if r["ttl"] == "1h" else "write_5m")
    rate = base if rate is None else float(rate)
    rebuilt = min(r["rebuilt"], written)
    r["cost_new"] = round((r["new"] - written) * base + (written - rebuilt) * rate)
    r["cost_rebuilt"] = round(rebuilt * rate)
    r["cost_warm"] = round(r["cache"] * float(price.get("read") or 0))
    r["cost_output"] = round(r["output"] * float(price.get("output") or 0))


#: A break after which coming back to a chat is counted as a resume (the
#: 1-hour cache has gone by then).
RESUME_GAP_S = 3600
#: The context bands of the analysis: up to 100k, 200k, 500k, and above.
CONTEXT_BANDS = (100_000, 200_000, 500_000)


def _band_of(tokens: int) -> int:
    for i, top in enumerate(CONTEXT_BANDS):
        if tokens <= top:
            return i
    return len(CONTEXT_BANDS)


def _gap_s(a: Any, b: str) -> float | None:
    x, y = _moment(a), _moment(b)
    return (y - x).total_seconds() if x is not None and y is not None else None


def _rebuild_kind(last: dict[str, Any], r: dict[str, Any]) -> str:
    """Why old context was written again: the cache's lifetime passed since
    the message before, the model changed, or not known."""
    if last.get("model") and r["model"] and last["model"] != r["model"]:
        return "model"
    a, b = _moment(last.get("at")), _moment(r["at"])
    if a is not None and b is not None and (b - a).total_seconds() > _ttl_s(str(last.get("ttl") or "")):
        return "expired"
    return "other"


def _point(r: dict[str, Any]) -> dict[str, Any]:
    """What the turn keeps of a boundary message."""
    return {"at": r["at"], "model": r["model"], "new": r["new"], "cache": r["cache"],
            "cache_write": r["cache_write"]}


def _parse_usage(data: bytes) -> dict[str, Any]:
    """A chat's usage file, summed. Dedupe first (the last line of an id
    wins, at the first line's place), then sum; raw records are dropped.

    ``turns``: per turn the main agent's sums and boundary messages (first
    and last by time; file order on a tie), its models, last ttl, limit and
    the helpers apart. ``buckets``: per (turn, day, tool) the sums a page
    adds up, a message on its own day. ``no_time``: lines without a readable
    ``at`` (counted in their turn, on no day)."""
    raw, bad = _json_lines(data)
    by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    plain: list[tuple[int, dict[str, Any]]] = []
    for i, r in enumerate(raw):
        rec = _record(r)
        if rec is None:
            continue
        if rec["id"]:
            first = by_id.get(rec["id"])
            by_id[rec["id"]] = (first[0] if first else i, rec)
        else:
            plain.append((i, rec))
    del raw
    merged = sorted([*by_id.values(), *plain], key=lambda p: p[0])
    del by_id, plain
    # By time; a line without one keeps its place after the timed ones of its turn.
    merged.sort(key=lambda p: (p[1]["turn"], p[1]["at"] == "", p[1]["at"], p[0]))

    turns: dict[int, dict[str, Any]] = {}
    buckets: dict[tuple[int, str, str], dict[str, Any]] = {}
    tools: list[str] = []
    no_time = 0
    # What each agent of the chat (the main one, each helper) left cached.
    left: dict[str, dict[str, Any]] = {}
    slots: dict[tuple[str, str], int] = {}
    for _pos, r in merged:
        n = r["turn"]
        # Rebuilt: the part of what the message before left cached that this
        # one did not read from the cache, and wrote again. An estimate; the
        # first message after a compaction starts over and rebuilds nothing.
        last = left.get(r["helper"]) or {"held": 0}
        r["rebuilt"] = 0 if r["compacted"] else min(r["cache_write"], max(0, last["held"] - r["cache"]))
        kind = _rebuild_kind(last, r) if r["rebuilt"] else ""
        gap_s = _gap_s(last.get("at"), r["at"])
        left[r["helper"]] = {"held": r["cache"] + r["cache_write"], "at": r["at"], "model": r["model"],
                             "ttl": r["ttl"] or last.get("ttl") or ""}
        _priced(r)
        cost = sum(r[k] for k in _COSTS)
        if r["at"] and cost and r["tool"] == "claude-code":
            # Ten-minute slots of dollars by model: what the plan limits' readings are set against.
            slot = (r["at"][:15] + "0", r["model"])
            slots[slot] = slots.get(slot, 0) + cost
        t = turns.get(n)
        if t is None:
            t = turns[n] = {"main": _sums(), "messages": 0, "models": [], "model": "", "at": "",
                            "tool": "", "ttl": "", "last_ttl": "", "first": None, "last": None,
                            "compacted": False, "helper_ids": set(), "helpers": _sums(),
                            "limit": None, "limit_at": "", "helper_limit": None, "helper_limit_at": ""}
        if r["tool"] and r["tool"] not in tools:
            tools.append(r["tool"])
        if not r["at"]:
            no_time += 1
        elif r["at"] > t["at"]:
            t["at"] = r["at"]
        t["tool"] = t["tool"] or r["tool"]
        if r["helper"]:
            t["helper_ids"].add(r["helper"])
            _add_sums(t["helpers"], r)
            if r["limit"] and r["at"] >= t["helper_limit_at"]:
                t["helper_limit"], t["helper_limit_at"] = dict(r["limit"]), r["at"]
        else:
            _add_sums(t["main"], r)
            t["messages"] += 1
            if r["model"]:
                t["model"] = r["model"]
                if r["model"] not in t["models"]:
                    t["models"].append(r["model"])
            if r["ttl"] == "1h" or (r["ttl"] == "5m" and t["ttl"] != "1h"):
                t["ttl"] = r["ttl"]
            if r["ttl"]:
                t["last_ttl"] = r["ttl"]
            if r["compacted"]:
                t["compacted"] = True
            if r["at"]:
                if t["first"] is None or not t["first"]["at"]:
                    t["first"] = _point(r)
                t["last"] = _point(r)
            elif t["first"] is None:
                t["first"] = t["last"] = _point(r)
            if r["limit"] and r["at"] >= t["limit_at"]:
                t["limit"], t["limit_at"] = dict(r["limit"]), r["at"]

        day = _day_of_iso(r["at"]) if r["at"] else ""
        if not day:
            continue
        key = (n, day, r["tool"])
        b = buckets.get(key)
        if b is None:
            b = buckets[key] = {"main": _sums(), "helpers": _sums(), "helper_ids": set(),
                                "models": {}, "model": "", "model_at": "", "causes": {}, "ctx": {},
                                "resumes": {"events": 0, "cost": 0, "context": 0, "by_model": {}}}
        if not r["helper"] and r["tool"] == "claude-code":
            # Claude Code's main agent's replies by the size of the context
            # they read: the 5-hour window is Claude Code's, other tools'
            # replies have limits of their own.
            band = b["ctx"].setdefault(_band_of(r["new"] + r["cache"]), [0, 0, {}])
            band[0] += 1
            reply = cost - r["cost_rebuilt"]      # the reply itself; a rebuild is counted apart
            band[1] += reply
            band[2][r["model"]] = band[2].get(r["model"], 0) + reply
            if gap_s is not None and gap_s > RESUME_GAP_S and r["rebuilt"] >= REBUILD_FLOOR:
                # Back to the chat after a long break: the context written again.
                rs = b["resumes"]
                rs["events"] += 1
                rs["cost"] += r["cost_rebuilt"]
                rs["context"] += r["new"] + r["cache"]
                rs["by_model"][r["model"]] = rs["by_model"].get(r["model"], 0) + r["cost_rebuilt"]
        if kind and not r["helper"]:
            c = b["causes"].setdefault(kind, {"rebuilt": 0, "cost": 0, "events": 0})
            c["rebuilt"] += r["rebuilt"]
            c["cost"] += r["cost_rebuilt"]
            c["events"] += 1 if r["rebuilt"] >= REBUILD_FLOOR else 0
        _add_sums(b["helpers"] if r["helper"] else b["main"], r)
        m = b["models"].get((r["model"], bool(r["helper"])))
        if m is None:
            m = b["models"][(r["model"], bool(r["helper"]))] = {**_sums(), "helper_ids": set(), "efforts": {}}
        _add_sums(m, r)
        # The model's new input and output by the reasoning effort it ran
        # with ("" when the log does not say): the by-model table's split.
        m["efforts"][r["effort"]] = m["efforts"].get(r["effort"], 0) + r["new"] + r["output"]
        if r["helper"]:
            b["helper_ids"].add(r["helper"])
            m["helper_ids"].add(r["helper"])
        elif r["model"] and r["at"] >= b["model_at"]:
            b["model"], b["model_at"] = r["model"], r["at"]
    return {"turns": turns, "buckets": buckets, "tools": tools, "bad": bad, "no_time": no_time,
            "unreadable": False, "slots": slots}


_EMPTY_USAGE: dict[str, Any] = {"turns": {}, "buckets": {}, "tools": [], "bad": 0, "no_time": 0,
                                "unreadable": False, "sig": None, "slots": {}}

# path → (sig, parsed): a usage file is parsed again only when it moved.
_usage: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
_lock = threading.Lock()
_swept = [0.0]


def _sweep() -> None:
    """Drop what the caches hold for files that are gone (at most once a minute)."""
    t = time.monotonic()
    if t - _swept[0] < SWEEP_S:
        return
    _swept[0] = t
    with _lock:
        keys = list(_usage) + list(_derived)
    gone = {k for k in keys if not os.path.exists(k)}
    if gone:
        with _lock:
            for k in gone:
                _usage.pop(k, None)
                _derived.pop(k, None)


def chat_usage(path: Path) -> dict[str, Any]:
    """A chat's usage file, summed (see _parse_usage); the empty shape when
    there is none. A file that is there and cannot be read answers with
    ``unreadable: True`` and is not kept, so it is tried again."""
    path = Path(path)
    key = str(path)
    try:
        sig = _stat_sig(path)
        if sig is None:
            with _lock:
                _usage.pop(key, None)
            return _EMPTY_USAGE
        sig = (*sig, _book["stamp"])
        with _lock:
            hit = _usage.get(key)
        if hit is not None and hit[0] == sig:
            return hit[1]
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return _EMPTY_USAGE
        except OSError as exc:
            raise Unreadable(str(exc)) from exc
    except Unreadable:
        with _lock:
            _usage.pop(key, None)
        return {**_EMPTY_USAGE, "unreadable": True}
    parsed = _parse_usage(data)
    parsed["sig"] = sig
    with _lock:
        _usage[key] = (sig, parsed)
    _sweep()
    return parsed


def read_usage(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Kept for callers of the first version: the chat's turns as one
    record each (main agent), and the unreadable line count."""
    cu = chat_usage(path)
    out = [{"turn": n, "at": t["at"], "tool": t["tool"], "model": t["model"], **t["main"]}
           for n, t in sorted(cu["turns"].items())]
    return out, cu["bad"]


# ---------------------------------------------------------------------------
# The limits history, read incrementally
# ---------------------------------------------------------------------------


def _window_line(v: Any, name: str) -> dict[str, Any] | None:
    """A window of a limits line, made safe: ``used`` None when not given."""
    if not isinstance(v, dict):
        return None
    used = _finite(v.get("used"))
    resets = _iso(_moment(v.get("resets_at")))
    if used is None and not resets:
        return None
    minutes = _finite(v.get("window_minutes"))
    span = int(minutes * 60) if minutes is not None and minutes > 0 else WINDOW_SPAN_S[name]
    return {"used": used, "resets_at": resets, "span_s": span}


class _Limits:
    """One limits.jsonl: per tool the readings sorted by time (``keys`` the
    stamps, for bisect, built once and kept), and the same per series —
    (tool, account) — with, beside each reading, what the series holds up
    to it (``held``: each window's highest reading of its newest reset,
    ``_fold``), so a turn and the page look it up without a scan;
    ``models`` the models a series' lines named. Read again
    only from the byte where the last read stopped. A shorter file or
    another inode is read from the start; a line still being written waits
    for its newline."""

    def __init__(self) -> None:
        self.ino = -1
        self.offset = 0
        self.mtime = -1
        self.bad = 0
        self.keys: dict[str, list[str]] = {}
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.skeys: dict[tuple[str, str], list[str]] = {}
        self.srows: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.held: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.models: dict[tuple[str, str], set[str]] = {}
        self.version = 0
        self.tail = b""           # the last bytes read, to see a rewrite
        self.lock = threading.Lock()

    def _reset(self) -> None:
        if self.offset or self.rows:
            self.version += 1
        self.offset, self.bad, self.keys, self.rows, self.tail = 0, 0, {}, {}, b""
        self.skeys, self.srows, self.held, self.models = {}, {}, {}, {}

    def _same_start(self, path: Path) -> bool:
        """The bytes just before the offset are still the ones read: the
        file grew, it was not written again from the start."""
        if not self.tail:
            return True
        try:
            with path.open("rb") as fh:
                fh.seek(self.offset - len(self.tail))
                return fh.read(len(self.tail)) == self.tail
        except OSError:
            return False

    def update(self, path: Path) -> None:
        with self.lock:
            try:
                st = path.stat()
            except OSError:
                self._reset()
                self.ino, self.mtime = -1, -1
                return
            # A grown file is checked too: a clock with a coarse tick (Windows)
            # can show a rewrite with the same mtime.
            if st.st_ino != self.ino or st.st_size < self.offset or (
                    (st.st_mtime_ns != self.mtime or st.st_size != self.offset) and not self._same_start(path)):
                # Rotated or cut: from the start.
                self._reset()
                self.ino = st.st_ino
            elif st.st_size == self.offset and st.st_mtime_ns != self.mtime:
                # Rewritten to the same length (or touched): from the start.
                self._reset()
            if st.st_size == self.offset:
                self.mtime = st.st_mtime_ns
                return
            try:
                with path.open("rb") as fh:
                    fh.seek(self.offset)
                    data = fh.read(st.st_size - self.offset)
            except OSError:
                return
            end = data.rfind(b"\n")
            if end < 0:
                return  # half a line: wait for the rest
            chunk = data[: end + 1]
            self.offset += len(chunk)
            self.tail = (self.tail + chunk)[-64:]
            self.mtime = st.st_mtime_ns
            lines, bad = _json_lines(chunk)
            self.bad += bad
            for r in lines:
                at = _moment(r.get("at"))
                tool = str(r.get("tool") or "")
                if at is None or not tool:
                    self.bad += 1
                    continue
                line: dict[str, Any] = {"at": _iso(at), "tool": tool, "plan": str(r.get("plan") or ""),
                                        "source": str(r.get("source") or ""),
                                        "account": str(r.get("account") or ""), "model": str(r.get("model") or ""),
                                        "session": str(r.get("session") or ""),
                                        # A line from before readings named their account.
                                        "named": "account" in r}
                for w in WINDOWS:
                    got = _window_line(r.get(w), w)
                    if got is not None:
                        line[w] = got
                _place(self.keys.setdefault(tool, []), self.rows.setdefault(tool, []), line)
                sk = (tool, line["account"])
                if line["model"]:
                    self.models.setdefault(sk, set()).add(line["model"])
                keys, rows, held = self.skeys.setdefault(sk, []), self.srows.setdefault(sk, []), self.held.setdefault(sk, [])
                i = _place(keys, rows, line)
                # What the series holds from this reading on (all of it
                # again after one that came out of order).
                del held[i:]
                for j in range(i, len(rows)):
                    win = dict(held[j - 1]) if j else {}
                    _fold(win, rows[j])
                    held.append(win)
            self.version += 1


def _beats(new: tuple[str, float, str], old: tuple[str, float, str]) -> bool:
    """(resets_at, used, at) of a window: a later reset is a new window;
    within one window the percentage never goes down (an idle session's
    status line sends its last, older reading again), so the highest
    reading holds — the later of two equal ones."""
    return new > old


def _rank(line: dict[str, Any], w: str) -> tuple[str, float, str] | None:
    v = line.get(w)
    if not isinstance(v, dict):
        return None
    used = v.get("used")
    return (str(v.get("resets_at") or ""), -1.0 if used is None else float(used), line["at"])


def _fold(win: dict[str, tuple[tuple[str, float, str], dict[str, Any]]], line: dict[str, Any]) -> None:
    """Take one reading into a series' windows: {window: (rank, line)}."""
    for w in WINDOWS:
        rank = _rank(line, w)
        if rank is not None and (w not in win or _beats(rank, win[w][0])):
            win[w] = (rank, line)


def _place(keys: list[str], rows: list[dict[str, Any]], line: dict[str, Any]) -> int:
    """A reading into its time order (after equal stamps: file order); its index."""
    if not keys or line["at"] >= keys[-1]:
        keys.append(line["at"])
        rows.append(line)
        return len(rows) - 1
    # out of order: in its place
    i = bisect_right(keys, line["at"])
    insort(keys, line["at"])
    rows.insert(i, line)
    return i


_limits: dict[str, _Limits] = {}


def _limits_of(data_root: Path) -> _Limits:
    path = Path(data_root) / USAGE_DIR / LIMITS_FILE
    key = str(path)
    with _lock:
        reader = _limits.get(key)
        if reader is None:
            reader = _limits[key] = _Limits()
    reader.update(path)
    return reader


def limit_history(data_root: Path) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Every limits reading, per tool, oldest first; and the unreadable count."""
    r = _limits_of(data_root)
    return r.rows, r.bad


def _window(w: dict[str, Any] | None, name: str, ref: datetime) -> dict[str, Any] | None:
    if not isinstance(w, dict):
        return None
    resets = _moment(w.get("resets_at"))
    expired = resets is not None and resets <= ref
    return {
        "used": w.get("used"),
        "resets_at": _iso(resets),
        "in": span_text(resets - ref) if resets is not None and not expired else "",
        "expired": expired,
        "span_s": int(w.get("span_s") or WINDOW_SPAN_S[name]),
        "resets_text": _clock(resets, ref, name == "seven_day") if resets is not None else "",
        "expired_text": f"Reset at {resets.strftime('%H:%M')}. No reading since." if expired and resets else "",
    }


def _reading(last: dict[str, Any], ref: datetime) -> dict[str, Any]:
    """One reading as the page and the block show it."""
    read = _moment(last["at"]) or ref
    windows = {w: _window(last.get(w), w, ref) for w in WINDOWS}
    age = max(0, int((ref - read).total_seconds() // 60))
    return {
        **windows,
        "read_at": last["at"],
        "read_at_text": _clock(read, ref),
        "age_min": age,
        "stale": age > STALE_MIN,
        "expired": any(v is not None and v["expired"] for v in windows.values()),
        "plan": last.get("plan") or "",
        "source": last.get("source") or "",
    }


def _held(newest: dict[str, Any], win: dict[str, Any]) -> dict[str, Any]:
    """What a series holds at its reading ``newest`` (``win``, its held
    windows): each window's highest reading of its newest reset
    (``_beats``); read when the 5-hour value was read (the weekly one
    without it), with that reading's session and model; plan and source
    from ``newest``."""
    # Read when the 5-hour window's value was (the weekly one's without it).
    read = next((win[w][1] for w in WINDOWS if w in win), newest)
    out = {**newest, "at": read["at"], "session": read["session"], "model": read["model"]}
    for w in WINDOWS:
        out.pop(w, None)
        if w in win:
            out[w] = win[w][1][w]
    out["newest_at"] = newest["at"]
    return out


def _series(lines: list[dict[str, Any]], ref: datetime) -> list[dict[str, Any]]:
    """The series of one tool to show, newest first: a line that named no
    account (written before they were named) gives way to any newer named
    one; a series other than the newest whose every window passed its
    reset (an account not used this week) is left out."""
    lines = sorted(lines, key=lambda x: (x["at"], x.get("newest_at", "")), reverse=True)
    newest_named = max((x.get("newest_at", x["at"]) for x in lines if x["named"]), default="")
    out: list[dict[str, Any]] = []
    for line in lines:
        if not line["named"] and newest_named > line.get("newest_at", line["at"]):
            continue
        got = {"account": line["account"], "model": line["model"], **_reading(line, ref),
               "session": line["session"]}
        given = [got[w] for w in WINDOWS if got[w] is not None]
        if out and given and all(v["expired"] for v in given):
            continue
        out.append(got)
    return out


def limits(data_root: Path, at: datetime | None = None) -> dict[str, dict[str, Any]]:
    """The latest plan limits of each tool that sent one: ``{tool:
    {five_hour, seven_day, read_at, read_at_text, age_min, stale, expired,
    plan, source, series, accounts_n, models_n}}``. The limits are the
    account's, so ``series`` holds what each account holds, newest first —
    ``[{account, model, five_hour, seven_day, read_at, read_at_text,
    age_min, stale, expired, plan, source, session}]`` (``model`` and
    ``session`` those of the reading it was read at) — and the tool's own
    fields are the newest one's (what one series answered before);
    ``models_n`` counts the models the shown series' lines named
    (information only). A window is ``{used,
    resets_at, in, expired, span_s, resets_text, expired_text}`` (``used``
    None when the tool gave no number) or None when the tool did not give
    it. ``expired``: the window's reset passed and no reading came since,
    so its percentage no longer holds. ``stale``: the reading is older than
    15 minutes."""
    ref = at or now()
    reader = _limits_of(data_root)
    with reader.lock:
        latest: dict[str, list[dict[str, Any]]] = {}
        for sk, rows in reader.srows.items():
            if rows:
                latest.setdefault(sk[0], []).append(_held(rows[-1], reader.held[sk][-1]))
        models = {sk: set(m) for sk, m in reader.models.items()}
    out: dict[str, dict[str, Any]] = {}
    for tool, lines in sorted(latest.items()):
        series = _series(lines, ref)
        top = {k: v for k, v in series[0].items() if k not in ("account", "model", "session")}
        seen = set().union(*(models.get((tool, x["account"]), set()) for x in series))
        out[tool] = {
            **top,
            "series": series,
            "accounts_n": len({x["account"] for x in series}),
            "models_n": len(seen),
        }
    return out


def _limit_at(reader: _Limits, tool: str, at: str) -> dict[str, float]:
    """The tool's limits at a moment: the last reading up to a minute after
    it (the status line reads the limits right after the reply), and at
    most 30 minutes before — what its account's series held then: each
    window's highest reading of its newest reset (``_beats``). Stamps are
    normalized (``_iso``), so they compare as text. The caller holds
    ``reader.lock``."""
    if not at:
        return {}
    try:
        moment = datetime.fromisoformat(at)
    except ValueError:
        return {}
    upto = (moment + timedelta(seconds=60)).isoformat()
    since = (moment - timedelta(minutes=LIMIT_AT_MAX_MIN)).isoformat()
    keys = reader.keys.get(tool) or []
    i = bisect_right(keys, upto) - 1
    if i < 0 or keys[i] < since:
        return {}
    sk = (tool, reader.rows[tool][i]["account"])
    j = bisect_right(reader.skeys.get(sk) or [], upto) - 1
    if j < 0:
        return {}
    pick = (sk, j)
    win = reader.held[pick[0]][pick[1]]
    out: dict[str, float] = {}
    for w, (_rank_of, line) in win.items():
        v = line[w]
        if v.get("used") is not None:
            resets = v.get("resets_at") or ""
            if not resets or resets > at:
                out[w] = float(v["used"])
    return out


# ---------------------------------------------------------------------------
# Small files beside
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    try:
        got = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def chat_meta(folder: Path) -> dict[str, Any]:
    return _read_json(Path(folder) / "meta.json")


def _session_path(data_root: Path, tool: str, session_id: str) -> Path | None:
    if not tool or not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
        return None
    return Path(data_root) / USAGE_DIR / SESSIONS_DIR / f"{tool}-{session_id}.json"


def session_state(data_root: Path, tool: str, session_id: str) -> dict[str, Any]:
    """The open chat's state from the status line (context, prompt cache); {} without one."""
    path = _session_path(data_root, tool, session_id)
    return _read_json(path) if path is not None else {}


def _chat_tool(meta: dict[str, Any], cu: dict[str, Any]) -> str:
    return str(meta.get("tool") or (cu["tools"][-1] if cu["tools"] else ""))


def show_usage(data_root: Path, folder: Path | None = None) -> bool:
    """Is the line after each reply shown: the chat's #usage-on / #usage-off
    when it set one, else the setting ``agent.usage_show``."""
    if folder is not None:
        meta = chat_meta(folder)
        if isinstance(meta.get("usage_show"), bool):
            return bool(meta["usage_show"])
    settings = _read_json(Path(data_root) / "settings.json")
    agent = settings.get("agent")
    if isinstance(agent, dict) and isinstance(agent.get("usage_show"), bool):
        return bool(agent["usage_show"])
    flat = settings.get("agent.usage_show")
    return bool(flat) if isinstance(flat, bool) else False


def miss_cause_text(cause: Any) -> str:
    """Claude Code's ``last_miss_cause`` as words: text as it is; an object
    as its true or valued keys (``system prompt changed, tools: 2``); a list
    joined."""
    if isinstance(cause, str):
        return cause.strip()
    if isinstance(cause, dict):
        parts = []
        for k, v in cause.items():
            if v is True:
                parts.append(str(k))
            elif v not in (None, False, "", 0, [], {}):
                parts.append(f"{k}: {v}")
        return ", ".join(parts)
    if isinstance(cause, (list, tuple)):
        return ", ".join(str(x) for x in cause if x not in (None, ""))
    return ""


# ---------------------------------------------------------------------------
# One chat, turn by turn
# ---------------------------------------------------------------------------


def _ttl_s(ttl: str) -> int:
    return 3600 if ttl == "1h" else 300


def _rebuild_cause(prev: dict[str, Any], cur: dict[str, Any], session: dict[str, Any],
                   ttl: str) -> dict[str, str]:
    """Why the cache was built again: the first reason that fits. ``ttl`` is
    the last cache lifetime the chat asked for before this turn."""
    first, last = cur["first"], prev["last"]
    at = _moment(first["at"])
    pc: dict[str, Any] = session["prompt_cache"] if isinstance(session.get("prompt_cache"), dict) else {}
    cause = miss_cause_text(pc.get("last_miss_cause"))
    miss_at = _moment(pc.get("last_miss_at"))
    if cause and at is not None and miss_at is not None and abs((miss_at - at).total_seconds()) <= MISS_WINDOW_S:
        return {"cause": cause, "kind": "tool"}
    before = _moment(last["at"])
    if at is not None and before is not None:
        gap_s = (at - before).total_seconds()
        if gap_s > _ttl_s(ttl):
            mins = math.ceil(gap_s / 60)
            return {"cause": f"cache expired: {span_text(timedelta(minutes=mins))} since the last turn",
                    "kind": "expired"}
    if first["model"] and last["model"] and first["model"] != last["model"]:
        return {"cause": f"model changed: {last['model']} → {first['model']}", "kind": "model"}
    if cur["compacted"]:
        return {"cause": "context compacted", "kind": "compacted"}
    return {"cause": "cause not recorded", "kind": "unknown"}


_EVENT_WORDS = {"expired": "cache expired", "model": "model changed", "compacted": "context compacted"}


def turn_line(tu: dict[str, Any], prev: dict[str, Any] | None = None) -> str:
    """The line after a reply: ``→ 1.9k ↑ 512 ↓ (108k)`` — new input up,
    output down, cache in brackets — with ``· cache expired`` (or why else
    the cache was built again) on a rebuild, ``+ helpers 300k`` when helpers
    ran, and ``· 5-hour 70%`` when the 5-hour percentage, as shown (the
    nearest whole number, a tie down), passed a ten since the turn before."""
    text = (f"→ {format_tokens(tu.get('new', 0))} ↑ {format_tokens(tu.get('output', 0))} ↓ "
            f"({format_tokens(tu.get('cache', 0))})")
    rb = tu.get("rebuild")
    if rb:
        text += " · " + _EVENT_WORDS.get(str(rb.get("kind") or ""), "cache rebuilt")
    helpers = tu.get("helpers") or {}
    if helpers.get("n"):
        text += f" + helpers {format_tokens(helpers.get('new_output', 0))}"
    five = _finite((tu.get("limit") or {}).get("five_hour"))
    before = _finite(((prev or {}).get("limit") or {}).get("five_hour"))
    if five is not None and before is not None:
        shown, was = _pct(five / 100), _pct(before / 100)
        if shown // 10 > was // 10:
            text += f" · 5-hour {shown}%"
    return text


def _derive(cu: dict[str, Any], session: dict[str, Any], reader: _Limits | None) -> dict[int, dict[str, Any]]:
    """The TurnUsage of every turn (see chat_turns)."""
    out: dict[int, dict[str, Any]] = {}
    prev: dict[str, Any] | None = None        # the last turn of the main agent
    prev_limit: dict[str, Any] | None = None  # the last turn with a limits reading
    ttl = ""                                  # the last cache lifetime the chat asked for
    for n in sorted(cu["turns"]):
        t = cu["turns"][n]
        m = t["main"]
        limit = t["limit"] or t["helper_limit"]
        if not limit and reader is not None:
            limit = _limit_at(reader, t["tool"], t["at"]) or None
        rebuild = None
        if prev is not None and t["first"] is not None:
            pl = prev["last"]
            base = pl["cache"] + pl["cache_write"]
            if base > REBUILD_FLOOR and t["first"]["cache"] < REBUILD_SHARE * base:
                rebuild = _rebuild_cause(prev, t, session, ttl)
        h = t["helpers"]
        tu = {
            "turn": n, "at": t["at"], "tool": t["tool"],
            **{k: m[k] for k in _SUMS},
            "model": t["model"], "models": list(t["models"]), "messages": t["messages"], "ttl": t["ttl"],
            "helpers": {"n": len(t["helper_ids"]), "new_output": h["new"] + h["output"], "cache": h["cache"]},
            "context_tokens": (t["last"]["new"] + t["last"]["cache"]) if t["last"] else 0,
            "share": share(m["cache"], m["new"]), "rebuild": rebuild,
            "limit": dict(limit) if limit else None, "compacted": t["compacted"], "line": "",
        }
        tu["line"] = turn_line(tu, prev_limit)
        if t["last"] is not None:
            prev = t
        if t["last_ttl"]:
            ttl = t["last_ttl"]
        if tu["limit"]:
            prev_limit = tu
        out[n] = tu
    return out


def _sig_of(path: Path | None) -> str:
    if path is None:
        return "-"
    try:
        st = path.stat()
    except OSError:
        return "-"
    return f"{st.st_mtime_ns}:{st.st_size}:{st.st_ino}"


# folder → (key, turns): the derived turns, kept while nothing they read moved.
_derived: dict[str, tuple[tuple[Any, ...], dict[int, dict[str, Any]]]] = {}


def turns_in(folder: Path, data_root: Path) -> dict[int, dict[str, Any]]:
    """The usage of every turn of the chat kept in ``folder``. Kept until
    the usage file, the chat's status-line file or the limits move; the
    answer is shared, read it only."""
    folder = Path(folder)
    cu = chat_usage(folder / USAGE_FILE)
    if not cu["turns"]:
        return {}
    meta = chat_meta(folder)
    tool = _chat_tool(meta, cu)
    spath = _session_path(data_root, tool, str(meta.get("session_ref") or ""))
    reader = _limits_of(data_root)
    key = (cu.get("sig"), _sig_of(spath), id(reader), reader.version)
    fkey = str(folder / USAGE_FILE)
    with _lock:
        hit = _derived.get(fkey)
    if hit is not None and hit[0] == key:
        return hit[1]
    state = _read_json(spath) if spath is not None else {}
    with reader.lock:   # the limits are not appended to while a turn looks them up
        got = _derive(cu, state, reader)
    with _lock:
        _derived[fkey] = (key, got)
    return got


def _folder_of(src: Any, project: str, agent_id: str) -> tuple[Path, Path | None]:
    """(data_root, the chat's folder) from a store or a data root."""
    if hasattr(src, "data_root") and hasattr(src, "agents"):
        root = Path(src.data_root)
        for a in src.agents():
            if str(a.get("agent_id") or "") == agent_id:
                return root, chat_folder(a)
        return root, None
    root = Path(src)
    folder = root / "projects" / project / "chats" / agent_id
    return root, folder if folder.is_dir() else None


def chat_folder(agent: dict[str, Any]) -> Path | None:
    """The folder of an agent row's chat; None when the row has no chat path
    (never the server's own folder)."""
    raw = str(agent.get("_chat_path") or "").strip()
    if not raw or raw == ".":
        return None
    parent = Path(raw).parent
    return parent if str(parent) not in ("", ".") else None


def chat_turns(src: Any, project: str, agent_id: str) -> dict[int, dict[str, Any]]:
    """``{turn: TurnUsage}`` for one chat. ``src`` is the store or the data root.

    TurnUsage: ``{turn, at, tool, new, output, cache, cache_write, thinking,
    model, models, messages, ttl, helpers: {n, new_output, cache},
    context_tokens, share, rebuild: {cause, kind} | None,
    limit: {five_hour?, seven_day?} | None, compacted, line}``. The main
    agent's numbers; helpers apart."""
    root, folder = _folder_of(src, project, agent_id)
    return turns_in(folder, root) if folder is not None else {}


# ---------------------------------------------------------------------------
# Many chats: the usual day
# ---------------------------------------------------------------------------


def usual_day(chats: list[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    """The usual day: the median, over the active days (any new, output or
    cache) of the last 90 calendar days before today — at most the 30 most
    recent of them — of the main agents' new + output (and cache). An even
    count takes the mean of the two middle days, floored. ``chats`` are
    chat_usage() answers."""
    ref = today or now().date()
    today_key = yymm_dd(ref)
    reach = yymm_dd(ref - timedelta(days=USUAL_REACH))
    days: dict[str, list[int]] = {}
    for cu in chats:
        for (_turn, day, _tool), b in cu["buckets"].items():
            if day >= today_key or day < reach:
                continue
            v = days.setdefault(day, [0, 0, 0])
            m = b["main"]
            v[0] += m["new"] + m["output"]
            v[1] += m["cache"]
            v[2] += m["new"]
    active = [d for d in sorted(days) if days[d][0] + days[d][1] > 0][-USUAL_DAYS:]
    if not active:
        return {"new_output": 0, "cache": 0, "share": None, "days_used": 0}
    cache = sum(days[d][1] for d in active)
    new = sum(days[d][2] for d in active)
    return {
        "new_output": int(statistics.median(days[d][0] for d in active)),
        "cache": int(statistics.median(days[d][1] for d in active)),
        "share": share(cache, new),
        "days_used": len(active),
    }


def _project_folders(data_root: Path, project: str) -> list[Path]:
    chats = Path(data_root) / "projects" / project / "chats"
    try:
        return sorted(p for p in chats.iterdir() if (p / USAGE_FILE).exists())
    except OSError:
        return []


# ---------------------------------------------------------------------------
# The #usage block (D1)
# ---------------------------------------------------------------------------


def _limit_lines(tool: str, got: dict[str, Any] | None, ref: datetime, own: bool,
                 head: str = "") -> list[str]:
    """One tool's two windows. With ``head`` (one of several series) the
    series' name takes a line of its own and the windows go under it."""
    label = f"  {TOOL_LABELS.get(tool, tool):<11}  "
    pad = " " * len(label)
    if not got:
        return [label + "no limits recorded"]
    if head:
        label = pad
    lines: list[str] = []
    for i, w in enumerate(WINDOWS):
        v = got.get(w)
        word = WINDOW_WORDS[w]
        if v is None:
            body = f"{word}   {DASH}"
        elif v["expired"]:
            body = f"{word}   {DASH}  {v['expired_text']}"
        else:
            used = v.get("used")
            body = f"{word}  {_pct(used / 100):>2}%" if used is not None else f"{word}   {DASH}"
            if v.get("resets_text"):
                body += f"  resets {v['resets_text']}"
                if own and w == "five_hour" and v.get("in"):
                    body += f", in {v['in']}"
        lines.append((label if i == 0 else pad) + body)
    stamp = f"(read {got.get('read_at_text') or DASH})"
    # The reading's time at column 58: on the first line for the chat's own
    # tool (the one with "in …"), on the last for the others.
    at = 0 if own else len(lines) - 1
    lines[at] += " " * max(2, READ_COLUMN - len(lines[at])) + stamp
    return [f"  {head}"] + lines if head else lines


def _series_lines(tool: str, got: dict[str, Any] | None, ref: datetime, own: bool) -> list[str]:
    """A tool's limits in the block: as one reading, or — when it holds
    several accounts' — one part per account, newest first, named
    ``Claude Code · account 2403ec81``. "in …" goes with the first part of
    the chat's tool."""
    series = (got or {}).get("series") or []
    if len(series) <= 1 or int((got or {}).get("accounts_n") or 0) <= 1:
        return _limit_lines(tool, got, ref, own)
    out: list[str] = []
    for i, one in enumerate(series):
        head = f"{TOOL_LABELS.get(tool, tool)} · account {(one['account'] or DASH)[:8]}"
        out.extend(_limit_lines(tool, one, ref, own and i == 0, head))
    return out


def _cache_text(pc: dict[str, Any], ref: datetime) -> str:
    """``cache warm, 3 min left`` · ``cache cold`` · ``cache —``. With an
    expiry the clock decides, never the stored flag."""
    expires = _moment(pc.get("expires_at"))
    if expires is not None:
        if expires > ref:
            return f"cache warm, {span_text(expires - ref)} left"
        return "cache cold"
    if "warm" in pc:
        return "cache warm" if pc.get("warm") is True else "cache cold"
    return f"cache {DASH}"


def usage_block(data_root: Path, project: str, agent_id: str, server_url: str,
                now: datetime | None = None, folder: Path | None = None) -> str:
    """What #usage prints: this chat, the plan limits, the project's day."""
    data_root = Path(data_root)
    ref = now or _now()
    folder = folder or data_root / "projects" / project / "chats" / agent_id
    meta = chat_meta(folder)
    cu = chat_usage(folder / USAGE_FILE)
    tool = _chat_tool(meta, cu)
    session = session_state(data_root, tool, str(meta.get("session_ref") or ""))
    turns = turns_in(folder, data_root) if cu["turns"] else {}
    out: list[str] = []

    # This chat.
    if turns:
        n = len(turns)
        last = [t for t in cu["turns"].values() if t["last"] is not None and t["model"]]
        model = max(last, key=lambda t: (t["last"]["at"], t["model"]))["model"] if last else DASH
        out.append(f"This chat · {n} turn{'s' if n != 1 else ''} · {model}")
        new = sum(t["main"]["new"] for t in cu["turns"].values())
        output = sum(t["main"]["output"] for t in cu["turns"].values())
        cache = sum(t["main"]["cache"] for t in cu["turns"].values())
        helpers = sum(t["helpers"]["new"] + t["helpers"]["output"] for t in cu["turns"].values())
        line = (f"  new {format_tokens(new)} · output {format_tokens(output)} · cache {format_tokens(cache)}"
                f" · share {pct_text(share(cache, new))}")
        if any(t["helper_ids"] for t in cu["turns"].values()):
            line += f" · helpers {format_tokens(helpers)}"
        out.append(line)
    else:
        out.append("This chat · no usage recorded yet")
    ctx = session.get("context") if isinstance(session.get("context"), dict) else {}
    pc: dict[str, Any] = session["prompt_cache"] if isinstance(session.get("prompt_cache"), dict) else {}
    used, size = _finite(ctx.get("used_pct")), _finite(ctx.get("size"))
    context = (f"context {_pct(used / 100)}%" if used is not None else f"context {DASH}") + (
        f" of {format_tokens(size)}" if size else "")
    rebuilds = sum(1 for t in turns.values() if t.get("rebuild"))
    out.append(f"  {context} · {_cache_text(pc, ref)} · "
               + ("no rebuilds" if rebuilds == 0 else f"{rebuilds} rebuild{'s' if rebuilds != 1 else ''}"))

    # Plan limits.
    out.append("Plan limits")
    got = limits(data_root, ref)
    for t in LIMIT_TOOLS:
        out.extend(_series_lines(t, got.get(t), ref, own=(t == tool)))

    # The project's day.
    every = [chat_usage(f / USAGE_FILE) for f in _project_folders(data_root, project)]
    today_key = yymm_dd(ref.date())
    usual = usual_day(every, ref.date())
    new = output = cache = 0
    chats = 0
    for one in every:
        mine = [b["main"] for (_n, day, _t), b in one["buckets"].items() if day == today_key]
        if any(m["new"] + m["output"] + m["cache"] for m in mine):
            chats += 1
        new += sum(m["new"] for m in mine)
        output += sum(m["output"] for m in mine)
        cache += sum(m["cache"] for m in mine)
    head = f"{project} today"
    if usual["days_used"] >= USUAL_MIN_DAYS and usual["new_output"] > 0:
        head += f" · {ratio_text(new + output, usual['new_output'])}× your usual day"
    out.append(head)
    out.append(f"  new + output {format_tokens(new + output)} · cache {format_tokens(cache)}"
               f" · share {pct_text(share(cache, new))} · {chats} chat{'s' if chats != 1 else ''}")
    out.append(f"  Usage page: {server_url.rstrip('/')}/usage")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The page: summary over a range (needs the store)
# ---------------------------------------------------------------------------


def _title(a: dict[str, Any]) -> str:
    aid = str(a.get("agent_id") or "")
    name = str(a.get("agent_name") or "")
    return (str(a.get("chat_title") or "").strip() or (name if name and name != aid else "")
            or str(a.get("l1_headline") or "").strip())


class _Tasks:
    """The one task each turn of a chat worked on, as taskwork.py and
    donelib.py draw a task's stretch:

    1. a task the operator named at that very turn (a #now card started
       there first; then one whose #done stretch holds the turn; then the
       lowest id);
    2. else the #done stretch that holds the turn (the one that started
       last; a ledger row without ``start_turn`` starts after the chat's
       previous #done);
    3. else the task the operator named last before it, until a #done closes
       it; after a pause only into a session that names the task again.

    A turn that only filed a task (#task, #now-todo, #undo) opens and closes
    nothing. So a turn counts in one task at most, and the tasks of a chat
    never add up to more than the chat."""

    def __init__(self, store: Any, agents: set[str]) -> None:
        from . import donelib, nowlib, taskwork

        self.marks: dict[str, dict[int, set[str]]] = {}
        self.keys: dict[str, list[int]] = {}
        self.cards: dict[tuple[str, int], set[str]] = {}
        self.session_of: dict[tuple[str, int], str] = {}
        self.named_in: dict[str, set[str]] = {}
        self.done: dict[str, list[tuple[str, int, int]]] = {}
        if not agents:
            return
        q = ",".join("?" for _ in agents)
        filing: set[tuple[str, int]] = set()
        for row in store.query(f"SELECT id, agent_id, turns_json FROM sessions WHERE agent_id IN ({q})",
                               tuple(agents)):
            agent, sid = str(row.get("agent_id") or ""), str(row.get("id") or "")
            try:
                ns = [_int(t.get("n")) for t in json.loads(row.get("turns_json") or "[]")]
            except (ValueError, TypeError, AttributeError):
                ns = []
            for n in ns:
                self.session_of[(agent, n)] = sid
            filing |= {(agent, n) for n in taskwork._filing_turns(row)}

        def mark(agent: str, turn: int, task: str, sid: str, user: bool, card: bool = False) -> None:
            if (agent, turn) in filing:
                return
            self.named_in.setdefault(task, set()).add(self.session_of.get((agent, turn)) or sid)
            if user:
                self.marks.setdefault(agent, {}).setdefault(turn, set()).add(task)
            if card:
                self.cards.setdefault((agent, turn), set()).add(task)

        for m in store.query(
                f"SELECT agent_id, session_id, turn, task_id, role FROM task_mentions "
                f"WHERE agent_id IN ({q}) AND task_id LIKE 'tk_%'", tuple(agents)):
            mark(str(m["agent_id"] or ""), _int(m["turn"]), str(m["task_id"]),
                 str(m.get("session_id") or ""), str(m.get("role") or "") == "user")
        for n in nowlib.rows(store):
            if n.get("agent_id") in agents and n.get("column") == "doing" and n.get("task_id"):
                mark(str(n["agent_id"]), _int(n.get("turn")), str(n["task_id"]),
                     str(n.get("session_id") or ""), True, card=True)
        for agent, turn, tid in nowlib.card_turns(store, agents, ("started",), skip_server=True):
            mark(agent, turn, tid, "", True, card=True)
        for agent, marks in self.marks.items():
            self.keys[agent] = sorted(marks)
        rows: dict[str, list[tuple[int, int, str]]] = {}
        for r in donelib.rows(store):
            if r.get("result") in donelib.RESOLVED and r.get("agent_id") in agents and r.get("task_id"):
                rows.setdefault(str(r["agent_id"]), []).append(
                    (_int(r.get("turn")), _int(r.get("start_turn")), str(r["task_id"])))
        for agent, got in rows.items():
            got.sort()
            stretches = []
            for i, (hi, lo, tid) in enumerate(got):
                if lo <= 0:
                    # No start in the ledger: after the chat's previous #done.
                    lo = max((h for h, _l, _t in got[:i] if h < hi), default=0) + 1
                stretches.append((tid, lo, hi))
            self.done[agent] = stretches

    def of(self, agent: str, turn: int) -> str:
        here = (self.marks.get(agent) or {}).get(turn)
        stretches = [(lo, hi, tid) for tid, lo, hi in self.done.get(agent, []) if lo <= turn <= hi]
        if here:
            cards = self.cards.get((agent, turn), set()) & here
            if cards:
                return min(cards)
            inside = sorted((s for s in stretches if s[2] in here), key=lambda s: (-s[0], s[1], s[2]))
            return inside[0][2] if inside else min(here)
        if stretches:
            return sorted(stretches, key=lambda s: (-s[0], s[1], s[2]))[0][2]
        keys = self.keys.get(agent) or []
        i = bisect_right(keys, turn) - 1
        if i < 0:
            return ""
        key = keys[i]
        sid = self.session_of.get((agent, turn))
        running = []
        for task in self.marks[agent][key]:
            if sid and sid not in self.named_in.get(task, set()):
                continue
            # A #done of this task after it was named closes it.
            if any(t == task and key <= hi < turn for t, _lo, hi in self.done.get(agent, [])):
                continue
            running.append(task)
        return min(running) if running else ""


def _helpers(ids: set[Any], sums: dict[str, int]) -> dict[str, int]:
    return {"n": len(ids), "new_output": sums["new"] + sums["output"], "cache": sums["cache"]}


class _Row:
    """What one row of the page adds up: the main agent's sums, its turns,
    the helpers apart, the models and tools seen."""

    __slots__ = ("main", "helpers", "helper_ids", "turns", "models", "tools", "rebuilds")

    def __init__(self) -> None:
        self.main = _sums()
        self.helpers = _sums()
        self.helper_ids: set[Any] = set()
        self.turns: set[tuple[str, int]] = set()
        self.models: set[str] = set()
        self.tools: set[str] = set()
        self.rebuilds = 0

    def out(self) -> dict[str, Any]:
        m = self.main
        return {"new": m["new"], "output": m["output"], "cache": m["cache"],
                "cache_write": m["cache_write"], "thinking": m["thinking"],
                "rebuilt": m["rebuilt"], "rebuilds": self.rebuilds,
                "new_output": m["new"] + m["output"], "share": share(m["cache"], m["new"]),
                "turns": len(self.turns), "helpers": _helpers(self.helper_ids, self.helpers),
                # In dollars at API prices: the main agent by kind, the helpers
                # apart, and the whole row with them.
                "cost": {"new": _usd(m["cost_new"]), "rebuilt": _usd(m["cost_rebuilt"]),
                         "warm": _usd(m["cost_warm"]), "output": _usd(m["cost_output"]),
                         "helpers": _usd(sum(self.helpers[k] for k in _COSTS))},
                "cost_usd": _usd(sum(m[k] + self.helpers[k] for k in _COSTS)),
                "unpriced": m["unpriced"] + self.helpers["unpriced"]}


def _usd(micro: int) -> float:
    return round(micro / 1_000_000, 2)


def _analysis(store: Any, ref: datetime, bands: dict[int, list[Any]], resumes: dict[str, Any],
              resume_chats: dict[str, list[int]], agent_rows: dict[str, dict[str, Any]],
              tools: list[dict[str, Any]], totals: dict[str, Any], chats: list[dict[str, Any]],
              chat_costs: dict[str, dict[tuple[str, str], int]]) -> dict[str, Any]:
    from . import usageanalysis, usagewarn
    got = usageanalysis.build(store, ref, bands, resumes, resume_chats, agent_rows, tools, totals, chats,
                              chat_costs)
    # The hook reads the units for the warnings under a reply (usagewarn.py).
    usagewarn.write_units(Path(store.data_root), got.get("units"))
    return got


def _prices_shown(book: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
    """The newest price of each model in the range; a model with none is named apart."""
    seen = sorted({x["model"] for tl in tools for x in tl["models"] if x["model"]})
    rows, missing = [], []
    for model in seen:
        known = book["models"].get(model)
        if known:
            rows.append({"model": model, **{k: known[-1][1].get(k) for k in (*PRICE_FIELDS, "over_tokens")}})
        else:
            missing.append(model)
    return {"as_of": book["as_of"], "sources": book["sources"], "models": rows, "missing": missing}


def _key_of(row: dict[str, Any]) -> tuple[int, int]:
    return (-row["new_output"], -row["helpers"]["new_output"])


def _active_chats(store: Any, ids: set[str], first: date, last: date) -> set[str]:
    """The chats with an operator's turn in the range (by the turn's own time)."""
    if not ids:
        return set()
    q = ",".join("?" for _ in ids)
    lo, hi = first.isoformat(), (last + timedelta(days=1)).isoformat()
    try:
        rows = store.query(
            f"SELECT DISTINCT agent_id FROM turn_prints WHERE agent_id IN ({q}) AND at_ts >= ? AND at_ts < ?",
            (*ids, lo, hi))
    except Exception:  # noqa: BLE001 — a store without the table counts no one
        return set()
    return {str(r["agent_id"] or "") for r in rows}


def summary(store: Any, project: str | None, rng: str = "today", now: datetime | None = None) -> dict[str, Any]:
    """The Usage page for a project (or all, with None): totals over the
    range, by tool and model, the chats and tasks that used the most, the
    usual day, the plan limits and what was not recorded."""
    ref = now or _now()
    rng = rng if rng in RANGES else "today"
    days = range_days(rng, ref.date())
    book = use_prices(Path(store.data_root))
    causes: dict[str, dict[str, Any]] = {}
    bands: dict[int, list[Any]] = {}
    resumes: dict[str, Any] = {"events": 0, "cost": 0, "context": 0, "by_model": {}}
    resume_chats: dict[str, list[int]] = {}
    wanted = set(days)
    data_root = Path(store.data_root)
    scope = [a for a in store.agents() if project in (None, "", "all") or str(a.get("project") or "") == project]

    totals = _Row()
    by_tool: dict[str, _Row] = {}
    by_model: dict[tuple[str, str], _Row] = {}
    # (tool, model) → {effort: new input + output}, the main agent's and its helpers'.
    model_efforts: dict[tuple[str, str], dict[str, int]] = {}
    per_chat: dict[str, _Row] = {}
    chat_model: dict[str, tuple[str, str]] = {}
    chat_tool: dict[str, str] = {}
    # Each chat's dollars (helpers included) by (tool, model): the analysis
    # prices a chat's share of the 5-hour window model by model.
    chat_costs: dict[str, dict[tuple[str, str], int]] = {}
    per_turn: dict[tuple[str, int], _Row] = {}
    every: list[dict[str, Any]] = []
    notes_bad: dict[str, list[int]] = {}
    notes_time: dict[str, list[int]] = {}
    notes_unreadable: dict[str, int] = {}
    agent_rows: dict[str, dict[str, Any]] = {}

    for a in scope:
        aid = str(a.get("agent_id") or "")
        folder = chat_folder(a)
        if not aid or folder is None:
            continue
        cu = chat_usage(folder / USAGE_FILE)
        kind = str(a.get("tool") or "") or (cu["tools"][-1] if cu["tools"] else "") or "unknown"
        if cu["unreadable"]:
            notes_unreadable[kind] = notes_unreadable.get(kind, 0) + 1
            continue
        if cu["bad"]:
            u = notes_bad.setdefault(kind, [0, 0])
            u[0] += cu["bad"]
            u[1] += 1
        if cu["no_time"]:
            u = notes_time.setdefault(kind, [0, 0])
            u[0] += cu["no_time"]
            u[1] += 1
        if not cu["turns"]:
            continue
        every.append(cu)
        agent_rows[aid] = a
        for (turn, day, rtool), b in cu["buckets"].items():
            if day not in wanted:
                continue
            key = (aid, turn)
            tool = rtool or str(a.get("tool") or "") or "unknown"
            rows = (totals, by_tool.setdefault(tool, _Row()), per_chat.setdefault(aid, _Row()),
                    per_turn.setdefault(key, _Row()))
            for row in rows:
                row.turns.add(key)
                _add_sums(row.main, b["main"])
                _add_sums(row.helpers, b["helpers"])
                row.helper_ids |= {(aid, h) for h in b["helper_ids"]}
                row.tools.add(tool)
                row.rebuilds += sum(c["events"] for c in b["causes"].values())
            for band, (n_msgs, c_micro, c_models) in b["ctx"].items():
                got_b = bands.setdefault(band, [0, 0, {}])
                got_b[0] += n_msgs
                got_b[1] += c_micro
                for model, c_m in c_models.items():
                    got_b[2][model] = got_b[2].get(model, 0) + c_m
            rs = b["resumes"]
            if rs["events"]:
                resumes["events"] += rs["events"]
                resumes["cost"] += rs["cost"]
                resumes["context"] += rs["context"]
                for model, c_micro in rs["by_model"].items():
                    resumes["by_model"][model] = resumes["by_model"].get(model, 0) + c_micro
                chat_r = resume_chats.setdefault(aid, [0, 0])
                chat_r[0] += rs["events"]
                chat_r[1] += rs["cost"]
            for kind, c in b["causes"].items():
                got = causes.setdefault(kind, {"rebuilt": 0, "cost": 0, "events": 0, "chats": set()})
                got["rebuilt"] += c["rebuilt"]
                got["cost"] += c["cost"]
                got["events"] += c["events"]
                got["chats"].add(aid)
            for (model, is_helper), ms in b["models"].items():
                cc = chat_costs.setdefault(aid, {})
                cc[(tool, model)] = cc.get((tool, model), 0) + sum(ms[k] for k in _COSTS)
                mr = by_model.setdefault((tool, model), _Row())
                mr.turns.add(key)
                me = model_efforts.setdefault((tool, model), {})
                for effort, used in (ms.get("efforts") or {}).items():
                    me[effort] = me.get(effort, 0) + used
                if is_helper:
                    _add_sums(mr.helpers, ms)
                    mr.helper_ids |= {(aid, h) for h in ms["helper_ids"]}
                else:
                    _add_sums(mr.main, ms)
                for row in rows[2:]:
                    row.models.add(model)
            if b["model"] and b["model_at"] >= chat_model.get(aid, ("", ""))[0]:
                chat_model[aid] = (b["model_at"], b["model"])
            chat_tool.setdefault(aid, tool)

    tools = []
    for tool, s in by_tool.items():
        models = [{**r.out(), "model": model, "efforts": model_efforts.get((t, model), {})}
                  for (t, model), r in by_model.items() if t == tool]
        models.sort(key=lambda m: (*_key_of(m), m["model"]))
        tools.append({**s.out(), "tool": tool, "models": models})
    tools.sort(key=lambda r: (*_key_of(r), r["tool"]))

    # The tasks: each turn in one task at most.
    tasks_of = _Tasks(store, set(per_chat))
    chat_task: dict[str, dict[str, int]] = {}
    task_rows: dict[str, _Row] = {}
    task_chats: dict[str, set[str]] = {}
    for (aid, turn), tr in per_turn.items():
        tid = tasks_of.of(aid, turn)
        if not tid:
            continue
        used = tr.main["new"] + tr.main["output"]
        chat_task.setdefault(aid, {}).setdefault(tid, 0)
        chat_task[aid][tid] += used
        row = task_rows.setdefault(tid, _Row())
        _add_sums(row.main, tr.main)
        _add_sums(row.helpers, tr.helpers)
        row.helper_ids |= tr.helper_ids
        row.rebuilds += tr.rebuilds
        row.turns |= tr.turns
        row.models |= tr.models
        row.tools |= tr.tools
        task_chats.setdefault(tid, set()).add(aid)

    chats = []
    for aid, c in per_chat.items():
        a = agent_rows.get(aid, {})
        best = sorted((chat_task.get(aid) or {}).items(), key=lambda kv: (-kv[1], kv[0]))
        chats.append({
            **c.out(),
            "agent_id": aid, "project": str(a.get("project") or ""), "title": _title(a),
            "tool": chat_tool.get(aid, ""), "model": chat_model.get(aid, ("", ""))[1],
            "models": sorted(c.models), "tools": sorted(c.tools),
            "helpers_n": len(c.helper_ids), "task_id": best[0][0] if best else "",
        })
    chats.sort(key=lambda r: (*_key_of(r), r["agent_id"]))

    tasks = []
    if task_rows:
        from . import donelib
        q = ",".join("?" for _ in task_rows)
        info = {str(r["id"]): r for r in store.query(
            f"SELECT id, title, status, project FROM tasks_mutual WHERE id IN ({q})", tuple(task_rows))}
        done_at: dict[str, str] = {}
        for r in donelib.rows(store):
            if r.get("task_id") in info and r.get("result") in donelib.RESOLVED:
                done_at[str(r["task_id"])] = max(done_at.get(str(r["task_id"]), ""), str(r.get("at") or ""))
        for tid, tr in task_rows.items():
            t = info.get(tid)
            if t is None:
                continue
            tasks.append({
                **tr.out(),
                "id": tid, "title": str(t.get("title") or ""), "project": str(t.get("project") or ""),
                "status": str(t.get("status") or ""), "done_at": done_at.get(tid, ""),
                "chats": len(task_chats.get(tid, set())),
                "models": sorted(tr.models), "tools": sorted(tr.tools),
            })
        tasks.sort(key=lambda r: (*_key_of(r), r["id"]))

    # What was not recorded.
    seen = set(per_chat)
    ids = {str(a.get("agent_id") or "") for a in scope} - {""}
    first_day = ref.date() - timedelta(days=RANGES[rng] - 1)
    active = _active_chats(store, ids, first_day, ref.date()) | seen

    def label(tool: str) -> str:
        return TOOL_LABELS.get(tool, tool)

    def chats_n(k: int) -> str:
        return f"{k} chat{'s' if k != 1 else ''}"

    notes = [f"{label(tool)}: the usage of {chats_n(k)} could not be read"
             for tool, k in sorted(notes_unreadable.items())]
    notes += [f"{label(tool)}: {n} line{'s' if n != 1 else ''} in {chats_n(k)} could not be read"
              for tool, (n, k) in sorted(notes_bad.items())]
    notes += [f"{label(tool)}: {n} line{'s' if n != 1 else ''} in {chats_n(k)} without a time, on no day"
              for tool, (n, k) in sorted(notes_time.items())]
    _hist, bad_limits = limit_history(data_root)
    if bad_limits:
        notes.append(f"plan limits: {bad_limits} line{'s' if bad_limits != 1 else ''} could not be read")

    def from_log(aid: str) -> bool:
        """Lines filled afterwards from the tool's own log (usagebackfill.py)."""
        folder = chat_folder(agent_rows.get(aid, {}))
        mark = chat_meta(folder).get("usage_backfill") if folder is not None else None
        return isinstance(mark, dict) and _int(mark.get("lines")) > 0

    t = totals.out()
    return {
        "range": rng,
        "project": project or "all",
        "days": days,
        "limits": limits(data_root, ref),
        "usual": usual_day(every, ref.date()),
        "totals": {**{k: t[k] for k in ("new", "output", "cache", "cache_write", "thinking", "rebuilt",
                                        "new_output", "share", "turns", "cost_usd", "cost", "unpriced")},
                   "chats": len(seen), "helpers": t["helpers"]},
        "by_tool": tools,
        "analysis": _analysis(store, ref, bands, resumes, resume_chats, agent_rows, tools, t, chats, chat_costs),
        "by_cause": sorted(({"cause": k, "rebuilt": c["rebuilt"], "cost_usd": _usd(c["cost"]),
                             "events": c["events"], "chats": len(c["chats"])} for k, c in causes.items()),
                           key=lambda x: (-x["rebuilt"], x["cause"])),
        "api_prices": _prices_shown(book, tools),
        "chats": chats[:TOP_CHATS],
        "chats_total": len(chats),
        "tasks": tasks[:TOP_TASKS],
        "tasks_total": len(tasks),
        "coverage": {
            "chats_recorded": len(seen),
            "chats_without_usage": len(active - seen),
            "chats_from_log": sum(1 for aid in seen if from_log(aid)),
            "unreadable": notes,
        },
    }


def clock_marks(data_root: Path, at: datetime, folder: Path | None = None) -> str:
    """What changes with the clock inside a minute, for the ETags: each
    limits window passed its reset or not, each reading stale or not, and
    the chat's prompt cache warm or not."""
    marks = []
    for tool, got in limits(data_root, at).items():
        for one in got.get("series") or [got]:
            marks.append(tool + "".join("1" if (one.get(w) or {}).get("expired") else "0" for w in WINDOWS)
                         + ("s" if one["stale"] else ""))
    if folder is not None:
        meta = chat_meta(folder)
        state = session_state(data_root, _chat_tool(meta, chat_usage(Path(folder) / USAGE_FILE)),
                              str(meta.get("session_ref") or ""))
        pc: dict[str, Any] = state["prompt_cache"] if isinstance(state.get("prompt_cache"), dict) else {}
        marks.append("warm" if _cache_text(pc, at).startswith("cache warm") else "cold")
    return ",".join(marks)


def signature(data_root: Path, folder: Path | None = None) -> str:
    """What the answers here depend on besides the store: the limits file;
    for one chat also its usage file, its meta, its status-line file and
    the settings (whether its line is shown)."""
    root = Path(data_root)
    paths: list[Path | None] = [root / USAGE_DIR / LIMITS_FILE, root / USAGE_DIR / PRICES_FILE]
    if folder is not None:
        folder = Path(folder)
        meta = chat_meta(folder)
        tool = str(meta.get("tool") or "")
        if not tool:
            cu = chat_usage(folder / USAGE_FILE)
            tool = cu["tools"][-1] if cu["tools"] else ""
        paths += [folder / USAGE_FILE, folder / "meta.json",
                  _session_path(root, tool, str(meta.get("session_ref") or "")), root / "settings.json"]
    return "|".join(_sig_of(p) for p in paths)
