"""The tour — scripts the operator writes, shots the app poses for.

A tour is one ordered list of beats. Each beat names a page, optionally an
element on it, and one sentence about what the reader is looking at. The
same script has two exits: rendered to a film, or played live over the real
app. Nothing here knows about either — this router keeps the scripts and
takes the photographs.

Capture shells out to Playwright (``frontend/scripts/tour_capture.mjs``),
which is already in the frontend's toolchain. It opens the running app, so
the pictures are the product, not a drawing of it.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

from ..db import ViewStore
from ..file_safety import edit_json, safe_read_json
from .deps import etag_for, get_store, json_response, maybe_304, not_found

router = APIRouter()

SCRIPTS_FILE = "tour_scripts.json"
SHOTS_DIR = "tour_shots"
SHOT_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,120}\.png$")
SCRIPT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

def _last_line(text: str, fallback: str) -> str:
    """The last non-empty line of a subprocess's output, at most 200 chars.

    What reaches the operator is a toast, and a Node or Python traceback is
    a wall; the last line is where those tools put the sentence that says
    what actually went wrong.
    """
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    return (lines[-1][:200] if lines else "") or fallback


# A tour is a teaching aid, not an archive: a script that needs more than
# this many beats has stopped being one video.
MAX_BEATS = 60
CAPTURE_TIMEOUT = 600


def _repo_root() -> Path:
    """The checkout this backend was started from — where the frontend lives."""
    return Path(__file__).resolve().parents[3]


def _read(store: ViewStore) -> dict[str, Any]:
    try:
        data = safe_read_json(store.data_root / SCRIPTS_FILE)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _edit(store: ViewStore, change) -> dict[str, Any]:
    """Read-modify-write tour_scripts.json under one lock
    (file_safety.edit_json)."""
    return edit_json(store.data_root / SCRIPTS_FILE, change)


@router.get("/api/tour/scripts")
def tour_scripts(request: Request, store: ViewStore = Depends(get_store)) -> Response:
    """Every saved script, newest first by name order the operator chose."""
    data = _read(store)
    etag = etag_for("tour:" + str(hash(json.dumps(data, sort_keys=True))), store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response({"scripts": list(data.values())}, etag)


@router.post("/api/tour/scripts")
def tour_script_save(
    body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{script: {id, name, ...}}`` — the whole script, replacing any prior one."""
    script = body.get("script")
    if not isinstance(script, dict):
        raise HTTPException(status_code=422, detail="script must be an object")
    sid = str(script.get("id") or "").strip()
    if not SCRIPT_ID.match(sid):
        raise HTTPException(status_code=422, detail="id must be a lowercase slug (letters, digits, dashes, underscores)")
    beats = script.get("beats")
    if not isinstance(beats, list) or not beats:
        raise HTTPException(status_code=422, detail="a script needs at least one beat")
    # A script carries the whole library, the beats it leaves out switched
    # off: only the ones it plays make it one video, and only those count.
    playing = [b for b in beats if not (isinstance(b, dict) and b.get("on") is False)]
    if len(playing) > MAX_BEATS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_BEATS} beats switched on")
    data = _edit(store, lambda d: d.update({sid: script}))
    return {"saved": sid, "n": len(data), "warnings": []}


@router.post("/api/tour/scripts/{script_id}/delete")
def tour_script_delete(
    script_id: str, store: ViewStore = Depends(get_store),
) -> dict:
    def drop(data: dict) -> None:
        if script_id not in data:
            raise not_found("script", script_id)
        data.pop(script_id)

    data = _edit(store, drop)
    return {"deleted": script_id, "n": len(data)}


@router.get("/api/tour/shots")
def tour_shots(store: ViewStore = Depends(get_store)) -> dict:
    """What has already been photographed — and where each subject sat.

    The rectangle matters as much as the picture: it is what the film zooms
    to and what the live tour would have spotlighted, measured in the same
    browser that took the shot.
    """
    shots = store.data_root / SHOTS_DIR
    if not shots.is_dir():
        return {"files": [], "shots": [], "at": "", "view": {}, "scale": 0}
    files = sorted(p.name for p in shots.glob("*.png"))
    manifest: dict[str, Any] = {}
    path = shots / "manifest.json"
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            manifest = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            manifest = {}
    at = str(manifest.get("at") or "")
    if not at and path.is_file():
        # An older manifest predates the stamp; the file's own time is the
        # honest answer and beats telling the studio "never captured".
        at = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    return {
        "files": files,
        "shots": manifest.get("shots", []),
        "at": at,
        "view": manifest.get("view", {}),
        "scale": manifest.get("scale", 0),
    }


@router.get("/api/tour/shot/{name}")
def tour_shot(name: str, store: ViewStore = Depends(get_store)) -> FileResponse:
    if not SHOT_NAME.match(name):
        raise HTTPException(
            status_code=422,
            detail="name must be a .png file name (letters, digits, dots, dashes, underscores)",
        )
    path = store.data_root / SHOTS_DIR / name
    if not path.is_file():
        raise not_found("shot", name)
    # A re-shot beat keeps its file name. Without this the browser shows the
    # old picture from its cache for hours (heuristic freshness from
    # Last-Modified) and the studio looks as if the capture changed nothing.
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})


def capture_mask(world: Path, repo: Path, home: Path) -> list[dict[str, str]]:
    """This computer's paths, and what the pictures say instead.

    The tour world (its working copy, and the clean copy its files were
    copied from, which they still name) reads as a data root in the home
    folder, the example's repository as a checkout under ~/code, this
    server's own checkout likewise, and the home folder as ``~``; the
    example's folder shortened to its last two names reads as
    ``code/shopfront``. Longest first, so a folder inside another is
    replaced before its parent, and a whole path before its short form.
    """
    places: dict[str, str] = {}
    for root in (world, world.parent / "clean"):
        places[str(root / "example" / "shopfront")] = "~/code/shopfront"
        places[str(root)] = "~/.slightly-parallel"
    places[str(repo)] = "~/code/slightly-parallel"
    places[str(home)] = "~"
    # Narrow cards print a folder by its last two names ("ran in
    # example/shopfront", "…/example/shopfront/AGENTS.md"), which no full
    # path above matches. The reader's checkout ends in code/shopfront.
    example = world / "example" / "shopfront"
    places["/".join(example.parts[-2:])] = "code/shopfront"
    # A root as short as "/" would rewrite every slash on the page.
    pairs = [{"from": k, "to": v} for k, v in places.items() if len(k.strip("/")) > 1]
    return sorted(pairs, key=lambda p: -len(p["from"]))


@router.post("/api/tour/capture")
async def tour_capture(
    request: Request, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """Photograph the beats. Slow and deliberate — one real page load each."""
    beats = body.get("beats")
    if not isinstance(beats, list) or not beats:
        raise HTTPException(status_code=422, detail="beats must be a non-empty list")
    if len(beats) > MAX_BEATS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_BEATS} beats")
    try:
        width, height, scale = (int(body.get("width") or 1440), int(body.get("height") or 900),
                                int(body.get("scale") or 2))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="width, height and scale must be whole numbers") from None

    frontend = _repo_root() / "frontend"
    script = frontend / "scripts" / "tour_capture.mjs"
    if not script.is_file():
        raise HTTPException(status_code=500, detail="capture script missing")

    # The browser it drives opens pages of this computer only.
    base = str(body.get("base") or "http://127.0.0.1:5173")
    parts = urlsplit(base)
    if parts.scheme != "http" or (parts.hostname or "") not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(status_code=422, detail="base must be a page on this computer: http://127.0.0.1:<port>")

    # The pictures are of the example project alone, in a world of its own
    # (tour_world), a fresh copy each capture: never of the operator's data.
    # "reseed" plays the month again rather than reusing today's.
    from .. import tour_world

    home = tour_world.world_home(int(getattr(request.app.state.settings, "port", 8123)))
    world, error = await asyncio.to_thread(tour_world.prepare, home, bool(body.get("reseed")))
    if error:
        raise HTTPException(status_code=503, detail=f"The example project could not be played: {error}")

    job = {
        "base": base,
        "out": str(store.data_root / SHOTS_DIR),
        "width": width,
        "height": height,
        "scale": scale,
        "colorScheme": str(body.get("color_scheme") or ""),
        "manifest": True,
        "beats": beats,
        "api": "",
        "mask": capture_mask(world, _repo_root(), Path.home()),
    }
    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(script)],
            cwd=str(frontend), input=json.dumps(job),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=CAPTURE_TIMEOUT, check=False,
        )

    def shoot() -> subprocess.CompletedProcess[str]:
        with tour_world.server(world) as api:
            job["api"] = api
            return run()

    try:
        # Off the event loop, always: the pages being photographed load from
        # this server too (its own files), and a blocked loop leaves every
        # page captured mid-skeleton.
        proc = await asyncio.to_thread(shoot)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=f"capture could not run: {exc}") from exc
    if proc.returncode != 0:
        raise HTTPException(status_code=503, detail=_last_line(proc.stderr, "capture failed"))
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="The capture gave no result.") from exc
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=_last_line(str(result.get("error")), "capture failed"))
    return result
