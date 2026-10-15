"""UI preferences — the operator's view choices, durable on the server.

localStorage is per-origin: localhost vs 127.0.0.1, :5173 vs :8123, or a
Vite port bump to :5174 each read a different, possibly empty store — which
looks like "the dashboard forgot my settings". The server is the one place
every origin shares, so the browser becomes a cache: the app hydrates
localStorage from here at boot and syncs writes back.

Storage is ``ui_prefs.json`` at the data root — flat string→string, the
exact semantics of localStorage. Single operator by design; no scoping.
"""

from __future__ import annotations

from typing import Any

import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from ..db import ViewStore
from ..file_safety import edit_json, safe_read_json
from .deps import etag_for, get_store, json_response, maybe_304

router = APIRouter()
PREFS_FILE = "ui_prefs.json"
_MAX_KEYS = 512
_MAX_KEY_LEN = 128
_MAX_VALUE_LEN = 8192


def _clean(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float, bool))}


def _read(store: ViewStore) -> dict[str, str]:
    try:
        return _clean(safe_read_json(store.data_root / PREFS_FILE))
    except (OSError, ValueError):
        return {}


@router.get("/api/prefs")
def prefs_get(request: Request, store: ViewStore = Depends(get_store)) -> Response:
    prefs = _read(store)
    # Prefs change outside the CSV watcher's view — hash the content itself.
    etag = etag_for("prefs:" + str(hash(json.dumps(prefs, sort_keys=True))), store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response({"prefs": prefs}, etag)


@router.post("/api/prefs")
def prefs_set(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{values: {key: value}}`` — merge; a null value deletes the key."""
    values = body.get("values")
    if not isinstance(values, dict) or not values:
        raise HTTPException(status_code=422, detail="send values as an object with at least one key")
    def change(raw: dict) -> dict:
        prefs = _clean(raw)
        for k, v in values.items():
            key = str(k)[:_MAX_KEY_LEN]
            if v is None:
                prefs.pop(key, None)
            else:
                prefs[key] = str(v)[:_MAX_VALUE_LEN]
        if len(prefs) > _MAX_KEYS:
            # Oldest-key trimming would need timestamps; refuse instead — this
            # ceiling exists to catch a runaway loop, not real usage.
            raise HTTPException(status_code=422, detail=f"too many preference keys (max {_MAX_KEYS})")
        return prefs

    # One read-modify-write cycle under one lock (file_safety.edit_json):
    # two tabs saving at once used to keep only the later one's keys.
    prefs = edit_json(store.data_root / PREFS_FILE, change)
    return {"saved": len(values), "total": len(prefs)}
