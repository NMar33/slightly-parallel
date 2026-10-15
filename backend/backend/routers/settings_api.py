"""Operator settings endpoints — backing the Settings page."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from .. import app_settings, example
from ..db import ViewStore
from .deps import get_store
from .terminal import enabled as terminal_on

router = APIRouter()


@router.get("/api/settings")
def get_settings(
    request: Request,
    store: ViewStore = Depends(get_store),
) -> dict:
    """The full schema (grouped) with current values — the page renders
    generically from this, so new settings need no frontend change.

    ``environment`` lists the boot/security configuration (read-only here;
    set via .env and restart) so the page shows the whole picture.
    """
    payload = app_settings.describe(store.data_root)
    settings = request.app.state.settings
    payload["environment"] = [
        {"key": "SP_DATA_ROOT", "label": "Data root",
         "value": str(settings.data_root)},
        # The names config.py reads first; the SCAN_* spellings still work.
        {"key": "HOST / SP_PORT", "label": "Bind address",
         "value": f"{settings.host}:{settings.port}"},
        {"key": "SP_CORS_ORIGINS", "label": "CORS origins",
         "value": ", ".join(settings.cors_origins)},
        # The variable forces the terminal on; without it the switch in
        # Settings decides. The token is the server's own (terminal.token_of),
        # so there is no "enabled but no token" state to report.
        {"key": "SP_ENABLE_TERMINAL", "label": "Terminal",
         "value": (
             "enabled" if settings.terminal_enabled
             else "not set — switched on in Settings" if terminal_on(request.app)
             else "disabled"
         )},
    ]
    return payload


@router.post("/api/settings")
def update_settings(
    request: Request,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Apply updates ``{"values": {"agent.contract_refresh_turns": 30}}``.

    All-or-nothing: any invalid value rejects the whole request with 422.
    """
    updates = body.get("values")
    if not isinstance(updates, dict) or not updates:
        raise HTTPException(status_code=422, detail="values object is required")
    try:
        values = app_settings.save(store.data_root, updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # The example project is data, not a display choice: the setting
    # builds it or removes it (both do nothing when it already is so).
    if example.SETTING in updates:
        example.apply(request.app, bool(values.get(example.SETTING)))
    return {"saved": True, "values": values}


@router.get("/api/example")
def example_state(request: Request) -> dict:
    """The example project: switched on, there, being played."""
    return example.describe(request.app)


@router.get("/api/example/source")
def example_source(
    agent_id: str, date: str, time: str = "", kind: str = "", store: ViewStore = Depends(get_store),
) -> dict:
    """The chat message an entry of the example project was written after;
    ``kind`` (scan, decision, standup, task) names the command to look for."""
    return {"source": example.source(store, agent_id, date, time, kind)}
