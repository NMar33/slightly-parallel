"""Shared request-scope helpers: store access, ETags, JSON responses."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable, TypeVar

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from .. import frontmatter
from ..db import ViewStore
from ..docs_md import parse_sections, resolve_under
from ..entities import DONE_STATUSES
# Store readers the libraries use too, kept outside the routers (a library
# never imports a router); re-exported here for the routers that read them.
from ..date_utils import iso_moment  # noqa: F401
from ..viewrows import AGENT_ORIGIN_FIELDS, agents_by_id, attach_agent, clean, rows_or_empty  # noqa: F401
from ..actors import (  # noqa: F401
    AGENT_REFUSED, HOUSE_ACTORS, identity_of, is_agent, operator_only, refuse_agent, written_by_agent,
)
from ..answers import create_answer, mint_id, not_found  # noqa: F401
from ..rowedit import rewrite_one  # noqa: F401

log = logging.getLogger("sp.readers")

# A finished task in SQL, from the one list of done statuses (entities).
DONE_SQL = "(" + ", ".join(f"'{s}'" for s in DONE_STATUSES) + ")"

M = TypeVar("M", bound=BaseModel)

# The ledgers keep a day as YYMM-DD and a stamp as ISO. These three are how
# a router reads either; each had four or five private copies.


def ymd(short: Any) -> str:
    """'2608-20' → '2026-08-20'. Anything else passes through as written."""
    s = str(short or "")
    return f"20{s[:2]}-{s[2:4]}-{s[5:7]}" if len(s) == 7 and s[4] == "-" else s


def day_date(value: Any) -> date | None:
    """The day of a YYMM-DD, an ISO day or an ISO stamp; None when it is none."""
    try:
        return date.fromisoformat(ymd(str(value))[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Whose request is this — Slightly Parallel's own pages, or somebody else's
# ---------------------------------------------------------------------------
#
# Slightly Parallel has no login: it listens on this computer only, and what keeps
# another site's page out is the browser's own word about where a request
# comes from. Three headers carry it. ``Host`` is the name the browser
# dialled — a page that re-points its own name at 127.0.0.1 (DNS rebinding)
# still sends its own name. ``Origin`` is the page that made the request.
# ``Sec-Fetch-Site`` is the browser's verdict on the two together.

LOOPBACK_NAMES: tuple[str, ...] = ("127.0.0.1", "localhost", "[::1]")


def own_origins(settings: Any) -> frozenset[str]:
    """The origins Slightly Parallel's pages are served from: the CORS list (the Vite
    dev server among them) and the address the server itself is bound to."""
    port = getattr(settings, "port", 8123)
    out = {str(o).rstrip("/").lower() for o in getattr(settings, "cors_origins", ())}
    out.update(f"http://{name}:{port}" for name in LOOPBACK_NAMES)
    host = str(getattr(settings, "host", "") or "")
    if host and host not in ("0.0.0.0", "::"):
        out.add(f"http://{'[' + host + ']' if ':' in host else host}:{port}".lower())
    return frozenset(out)


def own_hosts(settings: Any) -> frozenset[str]:
    """Every ``Host`` a request to this server may name: the host part of
    each origin above. Anything else was dialled under a foreign name."""
    return frozenset(o.split("://", 1)[-1] for o in own_origins(settings))


def foreign_host(host: str, settings: Any) -> bool:
    """The request was dialled under a name that is not this computer's and
    not one of Slightly Parallel's. A loopback name passes on any port (the Vite dev
    server forwards its own): no other site can make a browser send it."""
    name = host.strip().lower()
    bare = name.rsplit(":", 1)[0] if name.rsplit(":", 1)[-1].isdigit() else name
    if bare in LOOPBACK_NAMES:
        return False
    return name not in own_hosts(settings)


def foreign_origin(headers: Any, settings: Any) -> bool:
    """Another site's page made this request: it names an origin that is not
    one of Slightly Parallel's (``null`` — a sandboxed page — included), or the browser
    marks it cross-site. A request with neither header is not a browser's."""
    origin = str(headers.get("origin", "") or "").strip().lower()
    if origin and origin not in own_origins(settings):
        return True
    return str(headers.get("sec-fetch-site", "") or "").strip().lower() == "cross-site"


# A project code is a folder name under ``projects/``: letters, digits and
# a few punctuation marks, never a path. The same shape ``artifactlib``
# has always enforced — the other three guards checked only ``is_dir()``,
# and ``..`` passes that (``<data_root>/projects/..`` is a directory), so a
# write addressed to project ".." landed outside the projects tree.
PROJECT_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def known_project(store: ViewStore, project: Any) -> str:
    """The code of a project that exists, or 404. The one guard.

    Three byte-identical copies of it lived in ``standups``,
    ``architecture`` and (inlined) ``scans``; none of them rejected ``..``.
    """
    code = str(project or "").strip()
    if not PROJECT_CODE_RE.match(code) or not (store.data_root / "projects" / code).is_dir():
        raise not_found("project", code)
    return code


def rows_as(
    model: type[M],
    rows: list[dict[str, Any]],
    *,
    source: str,
    prepare: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> list[M]:
    """Validate rows into models, skipping what cannot be read.

    The read side is where one malformed row used to take a whole aggregate
    endpoint down — the Overview, the sidebar and search all died together.
    A row that fails validation is logged and dropped instead: the page
    renders without it, and /api/doctor names it.
    """
    out: list[M] = []
    prep = prepare or clean
    for r in rows:
        try:
            out.append(model(**prep(r)))
        except ValidationError as exc:
            bad = ", ".join(str(e["loc"][0]) for e in exc.errors()[:3])
            log.warning(
                "skipping unreadable %s row id=%s in %s (fields: %s)",
                model.__name__, r.get("id") or r.get("agent_id"), source, bad,
            )
    return out


def get_store(request: Request) -> ViewStore:
    store = request.app.state.store
    # Scheduled task resurfacing rides the request path (throttled inside) —
    # no cron, no browser dependency; the lazy import avoids a cycle.
    from ..tasklib import maybe_resurface
    maybe_resurface(store)
    return store


def adopt_when_changed(store: ViewStore, name: str, adopt: Callable[[ViewStore], Any]) -> Any:
    """Run an adoption (keeplib, donelib, promptlib, marklib) unless it
    already ran on exactly this data.

    The list reads adopt on the way past, and every page asks its lists
    again whenever a file moves — so each adoption ran once per request,
    re-reading its ledgers, before the ETag could answer 304. An adoption
    is idempotent: on data it has seen it finds nothing. The stamps say
    whether the data is the data it saw. A run that added something is not
    remembered, so the next read runs it once more on what it wrote.
    """
    seen: dict[str, Any] = store.__dict__.setdefault("_adopted_on", {})
    key = (store.view_mtime, tuple(sorted(store.stamps.items())))
    if seen.get(name) == key:
        return []
    added = adopt(store)
    if not added:
        seen[name] = key
    return added


def etag_for(endpoint: str, store: ViewStore, *areas: str) -> str:
    """The tag for an answer: the endpoint and when its data last changed.

    Named ``areas`` (chats, tasks, scans, rest — db.ViewStore._area) key
    the tag on those areas' stamps, so a change elsewhere still answers
    304. Without them the tag follows the whole store, which is never
    wrong. An answer that names areas must read nothing outside them.
    """
    if areas:
        stamps = store.stamps
        stamp = max((stamps.get(a, 0.0) for a in areas), default=0.0) or store.view_mtime
    else:
        stamp = store.view_mtime
    raw = f"{stamp:.6f}:{endpoint}".encode()
    return 'W/"' + hashlib.sha256(raw).hexdigest()[:16] + '"'


def maybe_304(request: Request, etag: str) -> Response | None:
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        resp = Response(status_code=304)
        resp.headers["ETag"] = etag
        return resp
    return None


def json_response(payload: Any, etag: str) -> Response:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    resp = JSONResponse(payload)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def clean_agent(a: dict[str, Any]) -> dict[str, Any]:
    """Strip private ``_*`` keys and explicit nulls before model validation."""
    return {
        k: v for k, v in a.items() if not k.startswith("_") and v is not None
    }


# path and kind → (what the file was when read, what was made of it).
_PARSED: dict[tuple[str, str], tuple[tuple[int, int, int], Any]] = {}
_PARSED_MAX = 8192


def parsed_file(path: Path | None, kind: str, parse: Callable[[str], Any], missing: Any = None) -> Any:
    """What ``parse`` makes of a file's text, kept until the file changes
    (its time, size or inode — a rewrite is a new file).

    For the reads that open one document per row: the scans page, the file
    heatmap, a list with its descriptions. They parsed every document again
    whenever any file anywhere moved. ``missing`` is the answer for a file
    that is not there or cannot be read. What comes back is shared with the
    next caller: read it, do not change it.
    """
    if path is None:
        return missing
    try:
        st = path.stat()
    except OSError:
        return missing
    key, sig = (str(path), kind), (st.st_mtime_ns, st.st_size, st.st_ino)
    hit = _PARSED.get(key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    try:
        value = parse(path.read_text(encoding="utf-8"))
    except OSError:
        return missing
    if len(_PARSED) >= _PARSED_MAX:
        _PARSED.clear()
    _PARSED[key] = (sig, value)
    return value


def detail_cached(data_root: Path, md_ref: str) -> tuple[str, list[str], str]:
    """``docs_md.read_detail`` for a loop over many rows: parsed once per
    version of the document."""
    l2, l3, l4 = parsed_file(resolve_under(data_root, md_ref), "detail", parse_sections, ("", [], ""))
    return l2, list(l3), l4


def frontmatter_cached(data_root: Path, md_ref: str) -> dict[str, Any] | None:
    """A detail document's frontmatter as YAML, parsed once per version of
    the document. None when there is no document or no readable block."""
    return parsed_file(resolve_under(data_root, md_ref), "frontmatter",
                       lambda text: frontmatter.meta(text)[0], None)


def to_int(v: Any, default: int = 0) -> int:
    """A whole number out of a CSV cell or a query value; ``default`` when
    there is none or it is not one."""
    try:
        return int(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def task_brief(store: ViewStore, task_id: str) -> dict[str, Any] | None:
    """The few fields a note, a story or a document needs of a task."""
    return store.query_one(
        "SELECT id, title, status, project, projects, md_ref FROM tasks_mutual WHERE id = ?",
        (task_id,),
    )


def scalar(store: ViewStore, sql: str, params: tuple = ()) -> Any:
    row = store.query_one(sql, params) or {}
    if not row:
        return 0
    return next(iter(row.values()))


def scalar_str(store: ViewStore, sql: str, params: tuple = ()) -> str:
    v = scalar(store, sql, params)
    return str(v) if v not in (None, 0) else ""
