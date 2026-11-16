"""The Usage page's feed of insights: short messages about how the plan limits
were used, kept in ``<data root>/.usage/insights.json``.

A message is written once and keeps its numbers. The feed gets at most one
ordinary message a day (the heaviest kind not shown in the last seven days),
and a message for each 5-hour window that ran out in the last three days, at
most two a day. The page reads the feed with GET, which writes the day's
messages first when the day has none yet. The operator pins a message, hides
one, or hides every message that is not pinned.

The texts are the page's (frontend features/usage/LimitsAnalysis.tsx,
``said``): a message here holds its kind and its numbers.
"""

from __future__ import annotations

import copy

import json
import logging
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import file_safety, hookshared, usagelib

log = logging.getLogger("backend.usageinsights")

FILE = "insights.json"
REPEAT_DAYS = 7
CAP_DAYS = 3
CAPS_A_DAY = 2

# Threads of this server; the file lock beside insights.json holds against
# another process (a second server on the same data root).
_lock = threading.Lock()


class Unreadable(Exception):
    """insights.json is there and cannot be read: nothing is written over it."""


def _path(data_root: Path) -> Path:
    return Path(data_root) / usagelib.USAGE_DIR / FILE


def _read(data_root: Path) -> dict[str, Any]:
    """The feed's file; a new one when there is none. A file that cannot be
    read, or is not a feed, raises Unreadable: written back as empty it
    would lose every pinned message."""
    path = _path(data_root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"items": [], "day": ""}
    except (OSError, UnicodeDecodeError) as exc:
        raise Unreadable(f"{path}: {exc}") from exc
    try:
        got = json.loads(text)
    except ValueError as exc:
        raise Unreadable(f"{path}: {exc}") from exc
    if not isinstance(got, dict) or not isinstance(got.get("items"), list):
        raise Unreadable(f"{path}: not a feed of insights (an object with items)")
    got["items"] = [i for i in got["items"] if isinstance(i, dict)]
    return got


def _held(data_root: Path) -> Any:
    path = _path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    return hookshared.locked(path)


def _write(data_root: Path, doc: dict[str, Any]) -> None:
    # A unique temp name beside the file, replaced patiently on Windows, deleted on a failure.
    file_safety.atomic_write(_path(data_root), json.dumps(doc, ensure_ascii=False, indent=1))


def candidates(a: dict[str, Any]) -> list[dict[str, Any]]:
    """The ordinary messages the analysis supports today, the heaviest first:
    ``[{kind, weight, params}]``; weight is the share of everything used."""
    out: list[dict[str, Any]] = []
    total = (a.get("mix") or {}).get("total_pct") or 0
    if not total:
        return out
    prices = a.get("prices") or []
    price = {p["key"]: p for p in prices if p["key"] != "message"}
    msgs = [p for p in prices if p["key"] == "message"]
    fable = next((p for p in msgs if "fable" in (p.get("model") or "")), None)
    opus = next((p for p in msgs if "opus" in (p.get("model") or "")), None)
    if fable and opus and opus["each_pct"] > 0:
        out.append({"kind": "model", "weight": fable["total_pct"] / total, "params": {
            "k": round(fable["each_pct"] / opus["each_pct"]), "f": fable["each_pct"], "o": opus["each_pct"],
            "n": fable["times"], "total": fable["total_pct"]}})
    big, small = price.get("reply_over_500k"), price.get("reply_under_100k")
    part = {p["key"]: p["pct"] for p in (a.get("mix") or {}).get("parts") or []}
    if big and small and small["each_pct"] > 0:
        out.append({"kind": "context", "weight": part.get("over_500k", 0) / total, "params": {
            "k": round(big["each_pct"] / small["each_pct"]), "big": big["each_pct"], "small": small["each_pct"],
            "n": big["times"], "share": round(part.get("over_500k", 0) / total * 100)}})
    r = price.get("resume")
    if r:
        out.append({"kind": "resume", "weight": r["total_pct"] / total, "params": {
            "each": r["each_pct"], "n": r["times"], "total": r["total_pct"],
            "ctx": (a.get("resumes") or {}).get("avg_context", 0)}})
    h = price.get("helper")
    if h:
        out.append({"kind": "helpers", "weight": h["total_pct"] / total, "params": {
            "share": round(h["total_pct"] / total * 100), "n": h["times"], "each": h["each_pct"], "total": h["total_pct"]}})
    chats = a.get("chats") or []
    if chats and chats[0]["pct"] / total >= 0.15:
        c = chats[0]
        out.append({"kind": "chat", "weight": c["pct"] / total, "params": {
            "share": round(c["pct"] / total * 100), "pct": c["pct"], "title": c["title"], "agent_id": c["agent_id"]}})
    if big and small and small["each_pct"] > 0:
        out.append({"kind": "cheap", "weight": 0.0, "params": {
            "each": small["each_pct"], "k": round(big["each_pct"] / small["each_pct"])}})
    return sorted(out, key=lambda c: -c["weight"])


def caps(a: dict[str, Any], ref: datetime) -> list[dict[str, Any]]:
    """The 5-hour windows of the last three days that ran out."""
    since = ref - timedelta(days=CAP_DAYS)
    out = []
    for w in a.get("history") or []:
        start = usagelib._moment(w.get("start"))
        if w.get("capped") and start is not None and start >= since:
            out.append({"kind": "cap", "key": w["resets_at"], "weight": 1.0, "params": {
                "start": w["start"], "reset": w["resets_at"], "fable": "fable" in (w.get("model") or "")}})
    return out


def _new(kind: str, params: dict[str, Any], at: str, key: str = "") -> dict[str, Any]:
    return {"id": "in_" + secrets.token_hex(4), "at": at, "kind": kind, "key": key, "params": params,
            "pinned": False, "hidden_at": ""}


def write_day(doc: dict[str, Any], a: dict[str, Any], ref: datetime) -> list[dict[str, Any]]:
    """Today's messages into ``doc``: the window that ran out first, then one
    ordinary message whose kind was not shown in the last seven days."""
    at = ref.replace(microsecond=0).isoformat()
    items = doc["items"]
    added: list[dict[str, Any]] = []
    seen_caps = {i.get("key") for i in items if i.get("kind") == "cap"}
    for c in caps(a, ref):
        if len(added) >= CAPS_A_DAY:
            break
        if c["key"] not in seen_caps:
            added.append(_new("cap", c["params"], at, c["key"]))
    recent = {i.get("kind") for i in items if (usagelib._moment(i.get("at")) or ref) >= ref - timedelta(days=REPEAT_DAYS)}
    for c in candidates(a):
        if c["kind"] not in recent:
            added.append(_new(c["kind"], c["params"], at))
            break
    items.extend(added)
    doc["day"] = ref.date().isoformat()
    return added


def feed(store: Any, ref: datetime | None = None) -> dict[str, Any]:
    """The feed, newest first, pinned ones on top; the day's messages are
    written first when the day has none yet."""
    ref = ref or usagelib.now()
    root = Path(store.data_root)
    with _lock, _held(root):
        try:
            doc = _read(root)
        except Unreadable as exc:
            log.warning("insights not read, nothing written: %s", exc)
            return {"items": [], "hidden": 0}
        if doc.get("day") != ref.date().isoformat():
            # The day's messages are a later step: when it fails (the
            # analysis, a message, the disk), the feed as it was is shown and
            # kept, and the next read tries the day again (round 5).
            kept = copy.deepcopy(doc)
            try:
                a = usagelib.summary(store, None, "7d", now=ref).get("analysis") or {}
                write_day(doc, a, ref)
                _write(root, doc)
            except Exception as exc:  # noqa: BLE001 — any failure of the day's step
                log.warning("the day's insights not written, the feed shown as it was: %s", exc)
                doc = kept
    shown = [i for i in doc["items"] if not i.get("hidden_at")]
    shown.sort(key=lambda i: str(i.get("at") or ""), reverse=True)
    shown.sort(key=lambda i: not i.get("pinned"))     # stable: pinned on top, each part newest first
    return {"items": shown, "hidden": len(doc["items"]) - len(shown)}


def change(store: Any, item_id: str, *, pinned: bool | None = None, hide: bool = False) -> dict[str, Any]:
    root = Path(store.data_root)
    with _lock, _held(root):
        doc = _read(root)
        item = next((i for i in doc["items"] if i.get("id") == item_id), None)
        if item is None:
            raise LookupError(item_id)
        if pinned is not None:
            item["pinned"] = bool(pinned)
        if hide:
            item["hidden_at"] = usagelib.now().replace(microsecond=0).isoformat()
            item["pinned"] = False
        _write(root, doc)
    return item


def clear(store: Any) -> int:
    """Hide every message that is not pinned; how many."""
    root = Path(store.data_root)
    with _lock, _held(root):
        doc = _read(root)
        at = usagelib.now().replace(microsecond=0).isoformat()
        n = 0
        for i in doc["items"]:
            if not i.get("pinned") and not i.get("hidden_at"):
                i["hidden_at"] = at
                n += 1
        _write(root, doc)
    return n
