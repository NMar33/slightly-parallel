"""Agent prompt files: read, edit, version, restore (Settings → Agent prompts).

SLIGHTLY-PARALLEL.md is composed from parts; its detail carries them, and writes go
to ``contract.<part>`` keys (the part's body as ``text``, ``enabled`` to
switch the block on or off). Every part write recomposes the file.

Not the operator's prompt library — that is ``routers/promptlib.py``, under
``/api/prompt-library``. The two are one word apart, and the newer one took
the new name: renaming a published endpoint to free a nicer one for new work
breaks whatever was already calling it, and buys only the nicer name.

The contract's key is ``contract`` (``contract.<part>`` for a part); the
old spelling ``merkhet`` / ``merkhet.<part>`` is still answered, as the same
records — a caller from before the rename keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from ..prompts import MAX_BYTES, PROMPT_FILES, PromptFile, PromptStore

router = APIRouter()


def _store(request: Request) -> PromptStore:
    return PromptStore(
        request.app.state.settings.data_root,
        getattr(request.app.state, "prompt_root", None),
    )


def _spec(store: PromptStore, key: str) -> PromptFile:
    spec = store.spec(key)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"unknown prompt file {key} — one of: "
                + ", ".join(p.key for p in PROMPT_FILES)
                + ", or contract.<part>"
            ),
        )
    return spec


_COMPOSED = (
    "SLIGHTLY-PARALLEL.md is composed from its parts (prompts/contract/) — edit a part "
    "(key contract.<part>) and the file is rewritten"
)


@router.get("/api/prompts")
def list_prompts(request: Request) -> dict:
    """Every prompt file with its size, whether it differs from the original,
    and how many versions the data root holds."""
    store = _store(request)
    return {"files": [store.summary(p) for p in PROMPT_FILES]}


@router.get("/api/prompts/{key}")
def get_prompt(key: str, request: Request) -> dict:
    """The live text plus the version list, newest first. For ``contract``,
    the parts too — each with its body, metadata, original and versions."""
    store = _store(request)
    return store.detail(_spec(store, key))


@router.get("/api/prompts/{key}/versions/{vid}")
def get_prompt_version(key: str, vid: str, request: Request) -> dict:
    """One kept version (``original`` or a version id) — read-only."""
    store = _store(request)
    spec = _spec(store, key)
    text = store.version_text(spec, vid)
    if text is None:
        raise HTTPException(status_code=404, detail=f"version not found for {key}: {vid}")
    meta = next((h for h in store.history(spec) if h.get("id") == vid), None)
    return {"key": key, "id": vid, "text": text, **({"at": meta["at"], "note": meta.get("note", "")} if meta else {})}


@router.post("/api/prompts/{key}")
def save_prompt(key: str, request: Request, body: dict = Body(...)) -> dict:
    """Replace the live file (a part: its body). The content it replaces is
    kept as a version; the very first save also keeps it as the original.
    A part also takes ``enabled`` (true/false) to switch the block."""
    store = _store(request)
    spec = _spec(store, key)
    if store.composed(spec):
        raise HTTPException(status_code=422, detail=_COMPOSED)
    if not store.path(spec).exists():
        raise HTTPException(status_code=422, detail=f"{store.path(spec)} does not exist")

    out: dict = {"action": "unchanged", "version": None}
    text = body.get("text")
    if text is not None:
        if not isinstance(text, str):
            raise HTTPException(status_code=422, detail="text must be a string")
        if not text.strip():
            raise HTTPException(status_code=422, detail="The text is empty. To go back to the original, restore it instead.")
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise HTTPException(status_code=422, detail=f"text exceeds {MAX_BYTES // 1024} KB")
        out = store.save(spec, text, str(body.get("note") or ""))
    if "enabled" in body:
        if not spec.part:
            raise HTTPException(status_code=422, detail="only a part (contract.<part>) can be switched on or off")
        if not isinstance(body["enabled"], bool):
            raise HTTPException(status_code=422, detail="enabled must be true or false")
        switched = store.set_enabled(spec, body["enabled"])
        if switched["action"] != "unchanged":
            out = switched if out["action"] == "unchanged" else {**out, "switched": switched["version"]}
    if text is None and "enabled" not in body:
        raise HTTPException(status_code=422, detail="send text and/or enabled")
    return {**out, **store.detail(spec)}


@router.post("/api/prompts/{key}/restore")
def restore_prompt(key: str, request: Request, body: dict = Body(...)) -> dict:
    """Put a kept version back as the live file (``version: "original"`` or an id).
    What it replaces is kept as a version too — a restore is never a loss."""
    vid = str(body.get("version") or "original")
    store = _store(request)
    spec = _spec(store, key)
    if store.composed(spec):
        raise HTTPException(status_code=422, detail=_COMPOSED)
    try:
        out = store.restore(spec, vid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"version not found for {key}: {vid}")
    return {**out, **store.detail(spec)}
