"""DuckDB view materialisation over the agents filesystem.

Design notes
------------
- Filesystem is the source of truth. DuckDB is a disposable in-memory cache.
- One canonical view per entity in the ``entities`` registry. Each view is
  built header-aware from the CSVs that actually exist (mutual file at the
  data root, plus per-project overlays for goals/decisions/activity), so
  legacy column layouts keep working and endpoint code always sees one
  canonical schema.
- ``view_mtime`` = max(mtime of all source files). ETag = sha256(view_mtime,
  endpoint_name). Moved by a rebuild that found something new.
- Reads are cheap. A rebuild is incremental: a table is built again only
  when a file behind it changed (see ``ViewStore``).
- Missing project or missing CSV degrades to a typed empty view — never 500.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb

from .entities import ENTITIES, LEDGERS, Entity

log = logging.getLogger("sp.db")

_REPO_ROOT = Path(__file__).resolve().parents[2]

# A rebuild over this is named slow in the log (logbook.py has the request bar).
SLOW_REBUILD_MS = 2000


#: The shipped test data: the end-to-end tests and the tools serve a copy of it.
FIXTURES = _REPO_ROOT / "fixtures"

def home_data_root() -> Path:
    """Where the data lives when nothing names a folder: ``~/.slightly-parallel``,
    outside the repository, so a user's chats never sit inside a clone."""
    return Path.home() / ".slightly-parallel"


def default_data_root() -> Path:
    """Resolve the data root from the environment at call time.

    Order: ``SP_DATA_ROOT`` → ``SCAN_DATA_ROOT`` (the product's former
    name, in every operator's .env) → ``DATA_ROOT`` (older still) →
    ``~/.slightly-parallel``. The new name is read first and the old ones keep
    working: nobody's .env breaks.
    """
    named = os.environ.get("SP_DATA_ROOT") or os.environ.get("SCAN_DATA_ROOT") or os.environ.get("DATA_ROOT")
    return Path(named).expanduser() if named else home_data_root()


def make_data_root(root: Path) -> bool:
    """Make the data root when it is not there yet: an empty folder, which
    the server fills with the example project on its first start
    (example.py). A folder that is there, even empty, is left alone: it is
    the user's. True when made."""
    if root.exists():
        return False
    root.mkdir(parents=True)
    return True


# ---------------------------------------------------------------------------
# Schema-normalising CSV loaders
# ---------------------------------------------------------------------------
#
# Users point Slightly Parallel at their own data, and per-project CSVs have shipped in
# two layouts over time:
#
#   canonical goals.csv    ⇒ id, goal_text, parent_goal_id, related, time_est,
#                            confidence_pct, success_comment, created_date,
#                            agent_id, status, retro_date, retro_notes
#   canonical decisions.csv⇒ id, decision_text, rationale, source, agent_id,
#                            related_goal_id, tags, created_date
#   canonical activity_log ⇒ id, agent_id, activity_type, duration_min,
#                            files_touched, related_goal_id, created_date
#
#   legacy decisions.csv   ⇒ ... date ... (instead of created_date), no tags
#   legacy activity_log    ⇒ date, start_time, end_time, duration_min,
#                            goal_id, summary, agent_id (no id/type/files)
#
# Instead of assuming one layout (and crashing DuckDB's binder on the other),
# we read each file's header row and build the SELECT from the columns that
# actually exist: legacy names are mapped to canonical ones, and columns that
# are absent are synthesised with stable defaults. Endpoint code therefore
# always sees one canonical schema regardless of what is on disk.


def _read_csv_header(path: Path) -> list[str]:
    """First row of a CSV as a list of column names ([] on any error)."""
    import csv as _csv

    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            row = next(_csv.reader(fh), [])
    except (OSError, UnicodeDecodeError, _csv.Error) as exc:
        # A torn or mis-encoded file must degrade to "no columns", never
        # sink the caller — one bad CSV used to stop the server booting.
        log.warning("unreadable CSV header %s: %s", path, exc)
        return []
    return [c.strip() for c in row if c.strip()]


def _q(col: str) -> str:
    """Quote a column identifier for DuckDB."""
    return '"' + col.replace('"', '""') + '"'


def _first(header: set[str], *candidates: str) -> str | None:
    """First candidate column present in the header, else None."""
    for c in candidates:
        if c in header:
            return c
    return None


def _text_expr(header: set[str], *candidates: str, default: str = "''") -> str:
    """COALESCE(col, '') for the first present candidate, else the default."""
    col = _first(header, *candidates)
    return f"COALESCE({_q(col)}, '')" if col else default


def _from_clause(path: Path) -> str:
    # Dialect is stated explicitly (comma + double-quote) and strict mode is
    # off: DuckDB's sniffer hard-fails on files with mixed \r\n and \n line
    # endings, which older Slightly Parallel versions could produce, and lenient
    # parsing keeps such legacy rows readable (needs duckdb >= 1.2).
    return (
        f"FROM read_csv_auto('{_sql_escape(str(path))}', "
        "header=True, all_varchar=True, ignore_errors=True, "
        "delim=',', quote='\"', escape='\"', strict_mode=false)"
    )


def _default_if_blank(qcol: str | None, default: str) -> str:
    """Column value, falling back to `default` when NULL/'' or column absent."""
    if qcol is None:
        return f"'{default}'"
    return f"COALESCE(NULLIF({qcol}, ''), '{default}')"


def _derived_retro_outcome(h: set[str]) -> str:
    """Infer hit/miss/mixed from retro_notes prose when no explicit column."""
    if "retro_notes" not in h:
        return "'unknown'"
    rn = _q("retro_notes")
    return f"""CASE
        WHEN {rn} IS NULL OR {rn} = '' THEN 'unknown'
        WHEN regexp_matches(LOWER({rn}), '\\bhit\\b') THEN 'hit'
        WHEN regexp_matches(LOWER({rn}), '\\bmiss\\b') THEN 'miss'
        WHEN regexp_matches(LOWER({rn}), '\\bmixed\\b') THEN 'mixed'
        ELSE 'unknown'
    END"""


def _synth_activity_id(h: set[str]) -> str:
    """Stable synthetic id for legacy activity rows that carry none."""
    return (
        "md5(concat_ws('|', "
        f"{_text_expr(h, 'agent_id')}, {_text_expr(h, 'created_date', 'date')}, "
        f"{_text_expr(h, 'start_time')}, {_text_expr(h, 'summary')}))"
    )


def _entity_col_expr(
    ent: Entity, col: str, h: set[str], project_code: str | None
) -> str:
    """SQL expression producing canonical column `col` from header set `h`."""
    if col == "project" and project_code is not None:
        return f"'{_sql_escape(project_code)}'"
    src = _first(h, col, *ent.aliases.get(col, ()))
    qsrc = _q(src) if src else None

    # Semantically-loaded columns get explicit fallbacks so downstream
    # Literal-typed models never see blank values.
    if ent.name == "goal" and col == "status":
        return _default_if_blank(qsrc, "unknown")
    if ent.name == "goal" and col == "retro_outcome":
        return _default_if_blank(qsrc, "unknown") if src else _derived_retro_outcome(h)
    if ent.name == "decision" and col == "source":
        return _default_if_blank(qsrc, "explicit")
    if ent.name == "activity" and col == "activity_type":
        return _default_if_blank(qsrc, "work")
    if ent.name == "activity" and col == "id" and src is None:
        return _synth_activity_id(h)

    if src is None:
        return f"CAST(NULL AS {ent.sql_type(col)})"
    if ent.sql_type(col) != "VARCHAR":
        return f"TRY_CAST({qsrc} AS {ent.sql_type(col)})"
    return qsrc


def _entity_select(
    ent: Entity, path: Path, project_code: str | None = None
) -> str | None:
    """Header-aware SELECT normalising one CSV to the entity's view schema."""
    h = set(_read_csv_header(path))
    if not h:
        return None
    exprs = [
        f"{_entity_col_expr(ent, col, h, project_code)} AS {_q(col)}"
        for col in ent.view_columns
    ]
    return "SELECT\n    " + ",\n    ".join(exprs) + "\n" + _from_clause(path)


def _wrap_goal_children(ent: Entity, src_sql: str) -> str:
    """Wrap the goals union so ``children_n`` is computed, not stored."""
    cols = ", ".join(
        f"COALESCE(c.n, 0) AS {_q(col)}" if col == "children_n" else f"s.{_q(col)}"
        for col in ent.view_columns
    )
    return f"""
WITH src AS ({src_sql})
SELECT {cols}
FROM src s
LEFT JOIN (
    SELECT parent_goal_id AS pid, COUNT(*) AS n
    FROM src
    WHERE parent_goal_id IS NOT NULL AND parent_goal_id <> ''
    GROUP BY parent_goal_id
) c ON c.pid = s.id
"""


def _empty_entity_sql(ent: Entity) -> str:
    """Typed zero-row view so queries never hit unknown-column binder errors."""
    cols = ", ".join(
        f"CAST(NULL AS {ent.sql_type(c)}) AS {_q(c)}" for c in ent.view_columns
    )
    return f"SELECT {cols} WHERE FALSE"


# scans.csv lives at data_root / "scans.csv" and is append-only across all
# projects (SCAN pyramid entries). Cast numeric columns; force VARCHAR on
# everything else so DuckDB doesn't guess types from a short header sample.
_SCANS_SELECT = """
SELECT
    id                             AS id,
    CAST(created_date AS VARCHAR)  AS created_date,
    COALESCE(CAST(created_time AS VARCHAR), '') AS created_time,
    COALESCE(project, '')          AS project,
    COALESCE(agent_id, '')         AS agent_id,
    COALESCE(l1, '')               AS l1,
    COALESCE(TRY_CAST(files_n AS INTEGER), 0)     AS files_n,
    COALESCE(TRY_CAST(lines_add AS INTEGER), 0)   AS lines_add,
    COALESCE(TRY_CAST(lines_del AS INTEGER), 0)   AS lines_del,
    COALESCE(TRY_CAST(decisions_n AS INTEGER), 0) AS decisions_n,
    COALESCE(scope, '')            AS scope,
    COALESCE(md_ref, '')           AS md_ref
FROM read_csv_auto('{path}', header=True, all_varchar=True, ignore_errors=True,
                   delim=',', quote='"', escape='"', strict_mode=false)
"""


def _sql_escape(path: str) -> str:
    return path.replace("'", "''")


# ---------------------------------------------------------------------------
# ViewStore
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectFolder:
    code: str
    path: Path
    goals_csv: Path | None
    decisions_csv: Path | None
    activity_csv: Path | None
    log_md: Path | None
    chats_dir: Path | None

    @classmethod
    def discover(cls, path: Path) -> "ProjectFolder":
        def _if_exists(p: Path) -> Path | None:
            return p if p.exists() else None

        return cls(
            code=path.name,
            path=path,
            goals_csv=_if_exists(path / "goals.csv"),
            decisions_csv=_if_exists(path / "decisions.csv"),
            activity_csv=_if_exists(path / "activity_log.csv"),
            log_md=_if_exists(path / "log.md"),
            chats_dir=_if_exists(path / "chats"),
        )



# Every file a reader depends on that is not behind a view, in one place.
# A write to one moves the store's stamp (and every ETag keyed on it) the
# same way a write to a view's CSV does; nothing else has to remember it.
FILE_SOURCES: tuple[str, ...] = (
    "marks.csv",        # the ★ (marklib.py)
    "done.csv",         # #done in a chat (donelib.py): statistics and analytics read it
)
# Documents kept as numbered versions under a project (versioned.py).
VERSIONED_KINDS: tuple[str, ...] = ("map",)


# time_blocks — the one time axis every consumer reads: derived sessions
# unioned with externally-posted activity rows.
_TIME_BLOCKS_SQL = """CREATE OR REPLACE VIEW time_blocks AS
    SELECT id, project, agent_id, created_date, start_time, end_time,
           duration_min, l1 AS summary, 'session' AS activity_type,
           turns_n, agent_min, waiting_min
    FROM sessions
    UNION ALL
    -- A posted activity block is the work itself: all of it is agent time.
    SELECT id, project, agent_id, created_date, start_time, end_time,
           duration_min, summary, activity_type,
           CAST(NULL AS INTEGER) AS turns_n,
           duration_min AS agent_min, CAST(0 AS INTEGER) AS waiting_min
    FROM activity_mutual"""

class ViewStore:
    """Owns the DuckDB connection + a per-endpoint mtime hash.

    Thread-safe. FastAPI is async but our queries are synchronous+fast; we
    serialise access to the DuckDB connection with a re-entrant lock. A
    rebuild never holds that lock while it works: it builds on a cursor of
    its own, into staging tables, and swaps them in together at the end, so
    a request waits for a swap, never for a parse — and sees every table of
    one build, never a mix.

    A rebuild is incremental: a table is built again only when a file behind
    it changed (its time, size or inode — ``_file_sig``), and the tables
    derived from the chats only when a chat did. A task update rebuilds the
    task tables and nothing else; a rebuild after nothing moved rebuilds
    nothing.
    """

    def __init__(self, data_root: Path | None = None):
        self.data_root = Path(data_root) if data_root else default_data_root()
        self._lock = threading.RLock()
        self._con = self._connect()
        # What each table was last built from, and the errors that build
        # recorded (kept, so a table not rebuilt still reports its damage).
        self._sigs: dict[str, tuple] = {}
        self._view_errors: dict[str, list[dict[str, str]]] = {}
        # The derived rows the session tables were last written from.
        self._derived_written: dict[str, list[tuple]] | None = None
        self._view_mtime: float = 0.0
        self._stamps: dict[str, float] = {}
        self._projects: list[ProjectFolder] = []
        self._agents_cache: list[dict[str, Any]] | None = None
        # What the last session derivation was built from — see _chats_signature.
        self._chats_sig: tuple | None = None
        # What that derivation produced: the rows of every derived table,
        # inserted on each build until a transcript moves (see _derive).
        self._derived: dict[str, list[tuple]] | None = None
        # chat path → (its stat and settings, its sessions); see _derive.
        self._chat_cache: dict[str, tuple[tuple, list]] = {}
        # file path → the area its change is felt in; see _collect_stamps.
        self._area_memo: dict[str, str] = {}
        # The tables the build under way made (the ``__n`` copies the swap
        # renames), and the errors each recorded; see _rebuild_inner.
        self._built: dict[str, tuple] = {}
        self._built_errors: dict[str, list[dict[str, str]]] = {}
        # Per-version caches the chat pages keep (produced.posts,
        # task_mentions, marks): (view_mtime, value).
        self._mentions_cache: tuple[float, dict[str, int]] | None = None
        self._marks_cache: tuple[float, dict[str, dict[str, int]]] | None = None
        self._posts_cache: tuple[float, dict[str, list[tuple[str, str, str]]]] | None = None
        # Files that failed to load on the last rebuild — each one degraded
        # to an empty view instead of an error. Surfaced by /api/health and
        # /api/doctor so degradation is visible, never silent.
        self.load_errors: list[dict[str, str]] = []
        # One build at a time, off the read lock — see rebuild().
        self._build_cv = threading.Condition()
        self._building = False
        self._requested = 0
        self._completed = 0
        self.rebuild()

    @staticmethod
    def _connect() -> duckdb.DuckDBPyConnection:
        con = duckdb.connect(":memory:")
        # One thread: every query runs on the caller's. The data is small,
        # and handing tiny queries to workers costs more than it saves — a
        # rebuild of the real root is ~210 ms on one thread against ~310 on
        # four (2026-09-25). Left alone, DuckDB starts one worker per core.
        con.execute("SET threads TO 1")
        return con

    # ------------------------------------------------------------------
    # Rebuild / invalidate
    # ------------------------------------------------------------------

    def _projects_root(self) -> Path:
        return self.data_root / "projects"

    def _scans_csv(self) -> Path:
        return self.data_root / "scans.csv"

    def _snapshots_dir(self) -> Path:
        return self.data_root / "snapshots"

    def _mutual_csv_path(self, ent: Entity) -> Path:
        return self.data_root / ent.csv

    def _discover_projects(self) -> list[ProjectFolder]:
        root = self._projects_root()
        if not root.exists():
            return []
        out: list[ProjectFolder] = []
        for p in sorted(root.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                out.append(ProjectFolder.discover(p))
        return out

    def _chats_signature(self, projects: Iterable[ProjectFolder]) -> tuple:
        """What session derivation actually depends on: the chat logs, the
        agent metas, skill uses and turn times beside them, and the gap setting. Parsing every
        transcript costs ~300 ms, so a rebuild triggered by a task write —
        which cannot change any of this — should skip it."""
        from . import app_settings
        parts: list[tuple[str, float, int]] = []
        for pf in projects:
            if pf.chats_dir is None:
                continue
            for f in sorted(pf.chats_dir.glob("*/*")):
                if f.name not in ("meta.json", "chat.md", "skills.jsonl", "work.jsonl", "turns.jsonl"):
                    continue
                try:
                    st = f.stat()
                    parts.append((str(f), st.st_mtime, st.st_size))
                except OSError:
                    pass
        gap = app_settings.load(self.data_root).get("sessions.gap_minutes", 30)
        return (tuple(parts), gap)

    # Where a file's change is felt. The browser asks for the stamps and
    # reloads only the pages that read that area; a file nobody has placed
    # counts as "rest", which every page listens to.
    @staticmethod
    def _area(rel: Path) -> str:
        parts = rel.parts
        if parts and parts[0] == "projects":
            if len(parts) >= 3 and parts[2] == "chats":
                return "chats"
            if "architecture" in parts:
                return "scans"
            return "rest"
        n = parts[0].lower() if parts else ""
        if any(w in n for w in ("task", "sprint", "milestone", "evidence", "story", "board", "time_")):
            return "tasks"
        if any(w in n for w in ("scan", "snapshot", "file", "architecture")):
            return "scans"
        return "rest"

    def _collect_stamps(self, projects: Iterable[ProjectFolder]) -> dict[str, float]:
        """max(mtime) per area across every source file we materialise."""
        stamps = {"chats": 0.0, "tasks": 0.0, "scans": 0.0, "rest": 0.0}
        root = self.data_root

        areas = self._area_memo

        def note(f: Path) -> None:
            try:
                m = f.stat().st_mtime
            except OSError:
                return
            # A file's area never changes: worked out once per path.
            key = str(f)
            area = areas.get(key)
            if area is None:
                try:
                    area = self._area(f.relative_to(root))
                except ValueError:
                    area = "rest"
                areas[key] = area
            if m > stamps[area]:
                stamps[area] = m

        for pf in projects:
            for f in (pf.goals_csv, pf.decisions_csv, pf.activity_csv, pf.log_md):
                if f is not None:
                    note(f)
            if pf.chats_dir is not None:
                # skills.jsonl and work.jsonl are appended by the hook after
                # meta.json is written; each feeds a table of its own.
                for name in ("*/meta.json", "*/skills.jsonl", "*/work.jsonl"):
                    for f in pf.chats_dir.glob(name):
                        note(f)
            # The architecture page: markdown versions under the project,
            # written by an MCP tool and by no CSV. Without them here, a new
            # version left view_mtime where it was and every page that keys
            # its ETag off view_mtime answered 304 with the old picture.
            arch = pf.path / "architecture"
            if arch.is_dir():
                for md in arch.glob("*.md"):
                    note(md)
            # Versioned documents beside it (versioned.py): the map's versions.
            for kind in VERSIONED_KINDS:
                d = pf.path / kind
                if d.is_dir():
                    for f in d.glob("v*.*"):
                        note(f)
        # scans.csv + snapshots/*.md live outside per-project trees.
        scans = self._scans_csv()
        if scans.exists():
            note(scans)
        snap_dir = self._snapshots_dir()
        if snap_dir.exists():
            for md in snap_dir.glob("*.md"):
                note(md)
        # Mutual CSVs + their MD detail folders live at data_root. If any of
        # them changes, view_mtime MUST bump so ETag invalidates browser
        # cache — otherwise mutations return stale 304 responses.
        mutual_files = [self._mutual_csv_path(ent) for ent in ENTITIES.values()]
        mutual_files.extend(self.data_root / csv_name for _, csv_name, _ in LEDGERS)
        # Files read directly, not through a view — they still decide what
        # an answer holds, so they move the stamp like a view's CSV does.
        mutual_files.extend(self.data_root / name for name in FILE_SOURCES)
        for csv in mutual_files:
            if csv.exists():
                note(csv)
        # JSON ledgers at the data root — sets, where sets and skills are
        # written, the examples marker. A write to one of them changes what
        # endpoints answer, so it must bump view_mtime like a CSV does.
        for js in self.data_root.glob("*.json"):
            note(js)
        for ent in ENTITIES.values():
            detail_dir = self.data_root / ent.detail_dir
            if detail_dir.exists():
                for md in detail_dir.glob("*.md"):
                    note(md)
        return stamps

    def rebuild(self) -> None:
        """Build again what changed, in staging tables, then swap them in.

        One build runs at a time, on the caller's thread, and it never holds
        the read lock. A call that lands during a build asks for one more
        and returns once that one is in: a writer that rebuilds and reads
        back reads its own write, and a storm of file events costs two
        builds, not one each.

        Never raises: a file that cannot be loaded becomes a typed empty view
        and a ``load_errors`` entry, and a catastrophic failure keeps the
        previous views serving. The dashboard degrades; it does not die.
        """
        with self._build_cv:
            self._requested += 1
            want = self._requested
            if self._building:
                while self._completed < want:
                    self._build_cv.wait()
                return
            self._building = True
        try:
            while True:
                with self._build_cv:
                    target = self._requested
                self._build_once()
                with self._build_cv:
                    self._completed = target
                    if self._requested == target:
                        self._building = False
                    self._build_cv.notify_all()
                    if not self._building:
                        return
        except BaseException:
            with self._build_cv:
                self._building = False
                self._completed = self._requested
                self._build_cv.notify_all()
            raise

    def _build_once(self) -> None:
        try:
            self._rebuild_inner()
        except Exception as exc:  # noqa: BLE001 — the store must survive anything
            log.exception("rebuild failed — keeping previous views")
            with self._lock:
                self.load_errors = [{
                    "file": str(self.data_root), "stage": "rebuild",
                    "error": f"{type(exc).__name__}: {exc}",
                }]

    @staticmethod
    def _file_sig(paths: Iterable[Path]) -> tuple:
        """What a table is built from: each file's time, size and inode (an
        atomic rewrite is a new inode even in the same second at the same size)."""
        out = []
        for p in paths:
            try:
                st = p.stat()
                out.append((str(p), st.st_mtime_ns, st.st_size, st.st_ino))
            except OSError:
                out.append((str(p), None))
        return tuple(out)

    def _stage(self, con: duckdb.DuckDBPyConnection, name: str, sql: str, empty_sql: str,
               source: Path | None, errors: list[dict[str, str]]) -> None:
        """Build ``name`` as the table ``name__n``, from a view that is proved
        readable first — a bad file becomes an empty table and an error."""
        v = f"{name}__v"
        try:
            con.execute(f"CREATE OR REPLACE VIEW {v} AS {sql}")
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to register %s view: %s", name, exc)
            errors.append({"file": str(source) if source else name, "stage": "register",
                           "error": f"{type(exc).__name__}: {exc}"})
            con.execute(f"CREATE OR REPLACE VIEW {v} AS {empty_sql}")
        # Copying the view reads the file: a file that cannot be read fails
        # here, and the table is empty instead (the probe this replaces read
        # every file twice).
        try:
            con.execute(f"CREATE OR REPLACE TABLE {name}__n AS SELECT * FROM {v}")
        except Exception as exc:  # noqa: BLE001 — any reader failure counts
            errors.append({"file": str(source) if source else name, "stage": "view",
                           "error": f"{type(exc).__name__}: {exc}"})
            log.warning("view %s unreadable (%s) — degraded to empty", name, exc)
            con.execute(f"CREATE OR REPLACE TABLE {name}__n AS {empty_sql}")
        con.execute(f"DROP VIEW IF EXISTS {v}")

    def _rebuild_inner(self) -> None:
        t0 = time.perf_counter()
        con = self._con.cursor()
        self._built = {}
        self._built_errors = {}
        try:
            errors, projects, agents, derived, chats_sig, collected, stamps = self._build_views(con)
        finally:
            con.close()
        swaps = list(self._built)

        with self._lock:
            # The swap: every table this build made, at once — in one
            # transaction, so a failure part way leaves the old tables and
            # not some old, some new and one missing.
            self._con.execute("BEGIN TRANSACTION")
            try:
                for name in swaps:
                    self._con.execute(f"DROP TABLE IF EXISTS {name}")
                    self._con.execute(f"ALTER TABLE {name}__n RENAME TO {name}")
                self._con.execute("COMMIT")
            except BaseException:
                try:
                    self._con.execute("ROLLBACK")
                except Exception:
                    log.exception("view swap: rollback failed")
                raise
            self._sigs.update({k: v for k, v in self._built.items() if v is not None})
            self._view_errors.update(self._built_errors)
            self._con.execute("CREATE OR REPLACE VIEW scans_mutual AS SELECT * FROM scans")
            self._con.execute(_TIME_BLOCKS_SQL)
            if derived is not None:
                self._derived_written = derived
            self._projects = projects
            self._agents_cache = agents
            self._derived = derived
            rederived = chats_sig != self._chats_sig
            self._chats_sig = chats_sig
            self.load_errors = errors
            # The stamp moves when a file did, and — never the same stamp
            # twice for different tables — when the chats were re-derived
            # with no mtime to show for it (a settings change). A rebuild
            # that found nothing new keeps it: the browser reads the stamp
            # to know whether to ask again, and every ETag hangs off it.
            previous = self._view_mtime
            fresh = collected or (0.0 if previous else time.time())
            if fresh > previous:
                self._view_mtime = fresh
            elif rederived or not previous:
                self._view_mtime = previous + 1e-6
            stamp = self._view_mtime
            # The same rule per area: a file moved, or the chats were
            # re-derived without one.
            for area, m in stamps.items():
                was = self._stamps.get(area, 0.0)
                if m > was:
                    self._stamps[area] = m
                elif area == "chats" and rederived:
                    self._stamps[area] = was + 1e-6
                else:
                    self._stamps.setdefault(area, was)
        if errors:
            log.warning("rebuild degraded: %d source(s) unreadable", len(errors))
        ms = int((time.perf_counter() - t0) * 1000)
        log.log(
            logging.WARNING if ms >= SLOW_REBUILD_MS else logging.INFO,
            "views rebuilt: projects=%d tables=%d view_mtime=%.3f", len(projects), len(swaps), stamp,
            extra={"ms": ms, **({"why": "slow rebuild"} if ms >= SLOW_REBUILD_MS else {})},
        )

    def _build_views(self, con: duckdb.DuckDBPyConnection) -> tuple[
        list[dict[str, str]], list[ProjectFolder], list[dict[str, Any]] | None,
        dict[str, list[tuple]] | None, tuple | None, float, dict[str, float],
    ]:
        """Every view and derived table on ``con``, which nobody reads yet."""
        errors: list[dict[str, str]] = []
        projects = self._discover_projects()

        # One canonical view per registered entity. Each view unions the
        # mutual CSV at data_root with any per-project overlay CSVs
        # (goals/decisions/activity also live under projects/<code>/),
        # every source normalised to the entity's canonical schema.
        for ent in ENTITIES.values():
            mutual = self._mutual_csv_path(ent)
            overlays = [getattr(pf, ent.project_overlay) for pf in projects] if ent.project_overlay else []
            sig = self._file_sig([mutual, *[o for o in overlays if o is not None]])
            if self._sigs.get(ent.view) == sig:
                errors.extend(self._view_errors.get(ent.view, []))
                continue
            view_errors: list[dict[str, str]] = []
            errors_all, errors = errors, view_errors
            parts: list[str] = []
            sources: list[Path] = []
            if mutual.exists():
                try:
                    sql = _entity_select(ent, mutual)
                except Exception as exc:  # noqa: BLE001
                    sql = None
                    errors.append({"file": str(mutual), "stage": "header",
                                   "error": f"{type(exc).__name__}: {exc}"})
                if sql:
                    parts.append(sql)
                    sources.append(mutual)
                elif mutual.stat().st_size > 0:
                    # The file exists and holds bytes, yet no header could
                    # be read — that is corruption, not emptiness.
                    errors.append({"file": str(mutual), "stage": "header",
                                   "error": "no readable header row"})
            if ent.project_overlay:
                for pf in projects:
                    src = getattr(pf, ent.project_overlay)
                    if src is not None:
                        try:
                            sql = _entity_select(ent, src, project_code=pf.code)
                        except Exception as exc:  # noqa: BLE001
                            sql = None
                            errors.append({"file": str(src), "stage": "header",
                                           "error": f"{type(exc).__name__}: {exc}"})
                        if sql:
                            parts.append(sql)
                            sources.append(src)
                        elif src.stat().st_size > 0:
                            errors.append({"file": str(src), "stage": "header",
                                           "error": "no readable header row"})
            body = (
                "\n    UNION ALL\n".join(parts)
                if parts
                else _empty_entity_sql(ent)
            )
            if ent.name == "goal":
                # children_n is derived from actual child rows so the
                # count is always truthful, whatever the CSV column says.
                body = _wrap_goal_children(ent, body)
            self._stage(con, ent.view, body, _empty_entity_sql(ent), sources[0] if sources else None, errors)
            errors = errors_all
            errors.extend(view_errors)
            self._built[ent.view], self._built_errors[ent.view] = sig, view_errors

        # Ledgers — append-only CSVs that are not full Entities (no MD
        # detail, no generic create) but need the same typed-empty view.
        for view_name, csv_name, cols in LEDGERS:
            ledger_csv = self.data_root / csv_name
            sig = self._file_sig([ledger_csv])
            if self._sigs.get(view_name) == sig:
                errors.extend(self._view_errors.get(view_name, []))
                continue
            empty_sql = (
                "SELECT "
                + ", ".join(f"CAST(NULL AS VARCHAR) AS {_q(c)}" for c in cols)
                + " WHERE FALSE"
            )
            # Header-aware, like the entities: a column the schema grew
            # after the file was written reads as NULL instead of
            # sinking the whole view (and every row in it).
            present = set(_read_csv_header(ledger_csv)) if ledger_csv.exists() else set()
            full_sql = (
                "SELECT " + ", ".join(
                    _q(c) if c in present else f"CAST(NULL AS VARCHAR) AS {_q(c)}" for c in cols
                )
                + " " + _from_clause(ledger_csv)
            ) if ledger_csv.exists() and present else empty_sql
            view_errors = []
            self._stage(con, view_name, full_sql, empty_sql, ledger_csv, view_errors)
            errors.extend(view_errors)
            self._built[view_name], self._built_errors[view_name] = sig, view_errors

        # scans view — one CSV that all projects/agents append to.
        scans_csv = self._scans_csv()
        sig = self._file_sig([scans_csv])
        if self._sigs.get("scans") == sig:
            errors.extend(self._view_errors.get("scans", []))
        else:
            scans_sql = _SCANS_SELECT.format(path=_sql_escape(str(scans_csv))) if scans_csv.exists() else _empty_scans_sql()
            view_errors = []
            self._stage(con, "scans", scans_sql, _empty_scans_sql(), scans_csv, view_errors)
            errors.extend(view_errors)
            self._built["scans"], self._built_errors["scans"] = sig, view_errors
        # (scans_mutual, the alias call sites use, is a view made at the swap.)

        # agents + sessions: parsed only when the transcripts themselves
        # moved. Everything above is a view over CSVs and costs
        # milliseconds; the parse reads every chat log, so it runs on its
        # own signal and its rows are kept for the builds in between. The
        # mtime snapshot is taken before the parse, not after: a hook write
        # landing during the parse must bump the next build's ETag, not be
        # folded into this one's while the tables predate it.
        stamps = self._collect_stamps(projects)
        collected = max(stamps.values(), default=0.0)
        chats_sig = self._chats_signature(projects)
        with self._lock:
            agents = self._agents_cache
            derived = self._derived
            old_sig = self._chats_sig
        if chats_sig != old_sig or agents is None or derived is None:
            try:
                agents = self._load_agents(projects)
                derived = self._derive(agents)
            except Exception as exc:  # noqa: BLE001 — chat logs are foreign input
                errors.append({"file": "chats", "stage": "sessions",
                               "error": f"{type(exc).__name__}: {exc}"})
                log.exception("session derivation failed — keeping previous sessions")
                chats_sig = old_sig
        # The session tables are written again only from new derived rows.
        if derived is not self._derived_written or "sessions" not in self._sigs:
            self._materialize_sessions(con, derived)
            for table in self._DERIVED_TABLES:
                self._built[table], self._built_errors[table] = ("derived", id(derived)), []
        return errors, projects, agents, derived, chats_sig, collected, stamps

    def _derive(self, agents: list[dict[str, Any]]) -> dict[str, list[tuple]]:
        """Everything the chat logs say, parsed once: the rows of every
        derived table, keyed by table. Pure Python and no connection, so it
        runs off the lock; the result is inserted on every build until a
        transcript moves."""
        from . import app_settings
        from . import turntimes
        from .sessions import cluster as cluster_turns, derive_sessions
        from .skilllib import read_uses

        gap = int(app_settings.load(self.data_root).get("sessions.gap_minutes", 30))
        # A chat imported from a tool's own log afterwards (sessionimport.py)
        # is read, never acted on: a #done or #vision in an old message must
        # not close a task or keep a vision weeks later.
        imported = {str(a.get("agent_id") or "") for a in agents if a.get("capture") == "import"}
        chats = []
        for a in agents:
            chat_path = Path(a.get("_chat_path") or "")
            if chat_path.exists():
                chats.append(
                    (str(a.get("project") or ""), str(a.get("agent_id") or ""), chat_path)
                )
        # One chat is parsed again only when its file moved. A new turn in
        # one chat used to re-read all forty-six.
        kept: dict[str, tuple[tuple, list]] = {}
        rows = []
        for project, agent_id, chat_path in chats:
            try:
                st = chat_path.stat()
            except OSError:
                continue
            key = str(chat_path)
            # The turn times beside the chat change a session's numbers too.
            sig = (st.st_mtime_ns, st.st_size, gap, project, agent_id, turntimes.signature(chat_path.parent))
            hit = self._chat_cache.get(key)
            if hit is None or hit[0] != sig:
                hit = (sig, derive_sessions([(project, agent_id, chat_path)], gap_minutes=gap))
            kept[key] = hit
            rows.extend(hit[1])
        self._chat_cache = kept

        # Near-duplicate clustering, once, across every project's log. A
        # prompt is re-sent with a line changed far more often than byte
        # for byte, so "how many times did I send this" is a question
        # about the cluster, never about the fingerprint.
        prints = [p for r in rows for p in r.turn_prints]
        for p in prints:
            p["key"] = f"{p['project']}|{p['agent_id']}|{p['session_id']}|{p['turn']}"
        groups = cluster_turns(
            [(p["key"], p["shingles"], p["words"]) for p in prints if p["shingles"]]
        )
        return {
            "sessions": [
                (r.id, r.project, r.agent_id, r.created_date, r.start_time, r.end_time,
                 r.duration_min, r.turns_n, r.l1, json.dumps(r.turns, ensure_ascii=False),
                 r.chat_start_line, r.chat_end_line, r.agent_min, r.waiting_min, r.timed, r.helper_min)
                for r in rows
            ],
            "task_mentions": [
                (m["task_id"], m["project"], m["agent_id"], m["session_id"], m["turn"],
                 m["at"], m["role"], m["excerpt"], int(m.get("task_turn") or 0))
                for r in rows for m in r.mentions
            ],
            "prompt_marks": [
                (m["project"], m["agent_id"], m["session_id"], m["turn"], m["at"],
                 m["title"], m["body"], m["print"])
                for r in rows if r.agent_id not in imported for m in r.prompt_marks
            ],
            "keep_marks": [
                (k["kind"], k["project"], k["agent_id"], k["session_id"], k["turn"],
                 k["at"], k["title"], k["body"])
                for r in rows if r.agent_id not in imported for k in r.keep_marks
            ],
            "important_tags": [
                (k["kind"], k["project"], k["agent_id"], k["session_id"], k["turn"],
                 k["at"], k["excerpt"], k["tasks"])
                for r in rows if r.agent_id not in imported for k in r.important_tags
            ],
            "done_tags": [
                (k["project"], k["agent_id"], k["session_id"], k["turn"], k["at"],
                 k["excerpt"], k["tasks"])
                for r in rows if r.agent_id not in imported for k in r.done_tags
            ],
            "skill_uses": [tuple(u) for u in read_uses(chats, rows)],
            "turn_prints": [
                (p["print"], p["project"], p["agent_id"], p["session_id"], p["turn"],
                 p["at"], p["words"], p["head"], groups.get(p["key"], ""), p["body"])
                for p in prints
            ],
        }

    # The tables derived from the chat logs, in the column order _derive
    # writes them. Real tables, not views over files: the source is
    # Python-parsed chat.md content.
    #
    # sessions      — the work sessions, each with its turns as JSON.
    # task_mentions — every task id seen in a captured turn, by role; a
    #                 task's chat history is one query away, no ledger.
    # prompt_marks  — turns the operator tagged #prompt; turn_prints — a
    #                 fingerprint of every user turn, which is how the
    #                 prompt library counts the times a saved prompt was
    #                 sent again.
    # keep_marks    — turns tagged #vision, #rule, #problem or #skill;
    #                 keeplib.py adopts them into their ledgers on read.
    # important_tags — turns tagged #important[-agent|-task|-message];
    #                 marklib.py adopts them into marks.csv on read.
    # done_tags     — turns tagged #done; donelib.py applies them to the
    #                 board and records each task's stretch of the chat.
    # skill_uses    — the skills that ran in each turn, from skills.jsonl
    #                 beside each chat; a use without a turn is placed in
    #                 its session by time.
    _DERIVED_TABLES: dict[str, dict[str, str]] = {
        "sessions": {
            "id": "VARCHAR", "project": "VARCHAR", "agent_id": "VARCHAR",
            "created_date": "VARCHAR", "start_time": "VARCHAR", "end_time": "VARCHAR",
            "duration_min": "INTEGER", "turns_n": "INTEGER", "l1": "VARCHAR",
            "turns_json": "VARCHAR", "chat_start_line": "INTEGER", "chat_end_line": "INTEGER",
            # duration_min is the session; these are the agent's share of it,
            # the wait on the person, and exact/approx (sessions.py).
            "agent_min": "INTEGER", "waiting_min": "INTEGER", "timed": "VARCHAR",
            "helper_min": "INTEGER",
        },
        "task_mentions": {
            "task_id": "VARCHAR", "project": "VARCHAR", "agent_id": "VARCHAR",
            "session_id": "VARCHAR", "turn": "INTEGER", "at_ts": "VARCHAR", "role": "VARCHAR",
            "excerpt": "VARCHAR", "task_turn": "INTEGER",
        },
        "prompt_marks": {
            "project": "VARCHAR", "agent_id": "VARCHAR", "session_id": "VARCHAR",
            "turn": "INTEGER", "at_ts": "VARCHAR", "title": "VARCHAR", "body": "VARCHAR",
            "print": "VARCHAR",
        },
        "keep_marks": {
            "kind": "VARCHAR", "project": "VARCHAR", "agent_id": "VARCHAR",
            "session_id": "VARCHAR", "turn": "INTEGER", "at_ts": "VARCHAR",
            "title": "VARCHAR", "body": "VARCHAR",
        },
        "important_tags": {
            "kind": "VARCHAR", "project": "VARCHAR", "agent_id": "VARCHAR",
            "session_id": "VARCHAR", "turn": "INTEGER", "at_ts": "VARCHAR",
            "excerpt": "VARCHAR", "tasks": "VARCHAR",
        },
        "done_tags": {
            "project": "VARCHAR", "agent_id": "VARCHAR", "session_id": "VARCHAR",
            "turn": "INTEGER", "at_ts": "VARCHAR", "excerpt": "VARCHAR", "tasks": "VARCHAR",
        },
        "skill_uses": {
            "project": "VARCHAR", "agent_id": "VARCHAR", "session_id": "VARCHAR",
            "turn": "INTEGER", "at_ts": "VARCHAR", "skill": "VARCHAR", "how": "VARCHAR",
        },
        "turn_prints": {
            "print": "VARCHAR", "project": "VARCHAR", "agent_id": "VARCHAR",
            "session_id": "VARCHAR", "turn": "INTEGER", "at_ts": "VARCHAR",
            "words": "INTEGER", "head": "VARCHAR", "cluster": "VARCHAR", "body": "VARCHAR",
        },
    }

    def _materialize_sessions(
        self, con: duckdb.DuckDBPyConnection, derived: dict[str, list[tuple]] | None,
    ) -> None:
        """The derived tables, staged on ``con`` as ``<table>__n``, from what
        _derive last produced. (time_blocks, the view over them, is made at
        the swap.)"""
        for table, columns in self._DERIVED_TABLES.items():
            con.execute(
                f"CREATE OR REPLACE TABLE {table}__n ("
                + ", ".join(f"{c} {t}" for c, t in columns.items()) + ")"
            )
            self._bulk_insert(con, f"{table}__n", columns, (derived or {}).get(table) or [])

    @staticmethod
    def _bulk_insert(
        con: duckdb.DuckDBPyConnection, table: str, columns: dict[str, str],
        rows: list[tuple],
    ) -> None:
        """Rows into ``table`` through DuckDB's JSON reader, from a temp file.

        ``executemany`` binds row by row: 10k sessions took ~20 s that way,
        and 850 turn prints were most of a 3 s rebuild — against ~30 ms
        staged through a file. JSON rather than CSV because a turn's text
        holds newlines and quotes, and NULL, '' and a string are three
        different things that all come back as written.
        """
        if not rows:
            return
        import tempfile

        keys = list(columns)
        fd, tmp_path = tempfile.mkstemp(prefix="sp-rows-", suffix=".ndjson")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(dict(zip(keys, r)), ensure_ascii=False))
                    fh.write("\n")
            spec = "{" + ", ".join(f"'{c}':'{t}'" for c, t in columns.items()) + "}"
            con.execute(
                f"INSERT INTO {table} SELECT * FROM read_ndjson("
                f"'{_sql_escape(tmp_path)}', columns={spec})"
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _load_agents(self, projects: Iterable[ProjectFolder]) -> list[dict[str, Any]]:
        agents: list[dict[str, Any]] = []
        for pf in projects:
            if pf.chats_dir is None:
                continue
            for meta_path in sorted(pf.chats_dir.glob("*/meta.json")):
                try:
                    with open(meta_path, encoding="utf-8") as fh:
                        obj = json.load(fh)
                except (OSError, json.JSONDecodeError) as e:
                    log.warning("skip agent %s: %s", meta_path, e)
                    continue
                # Normalise + fill defaults so response models never explode.
                obj.setdefault("agent_id", meta_path.parent.name)
                obj.setdefault("agent_name", obj["agent_id"])
                obj.setdefault("chat_title", "")
                obj.setdefault("tool", "")
                obj.setdefault("session_ref", "")
                obj.setdefault("cwd", "")
                obj.setdefault("agent_group", "")
                obj.setdefault("project", pf.code)
                obj.setdefault("parent_agent_id", None)
                obj.setdefault("created_date", "")
                obj.setdefault("last_active", "")
                obj.setdefault("message_count", 0)
                obj.setdefault("l1_headline", "")
                obj.setdefault("files_touched", [])
                obj.setdefault("tags", [])
                obj.setdefault("goals_declared", [])
                obj.setdefault("decisions_made", [])
                obj.setdefault("root_goal_id", None)
                obj.setdefault("schema_version", 1)
                obj["_chat_path"] = str(meta_path.parent / "chat.md")
                obj["_folder"] = meta_path.parent.name
                agents.append(obj)
        return agents

    # ------------------------------------------------------------------
    # Public read helpers
    # ------------------------------------------------------------------

    @property
    def view_mtime(self) -> float:
        return self._view_mtime

    @property
    def stamps(self) -> dict[str, float]:
        """When each area last changed: chats, tasks, scans, rest."""
        with self._lock:
            return dict(self._stamps)

    @property
    def projects(self) -> list[ProjectFolder]:
        with self._lock:
            return list(self._projects)

    @property
    def scans_csv_path(self) -> Path:
        return self._scans_csv()

    def agents(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._agents_cache or [])

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._con.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def query_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Empty-view fall-backs (so endpoints never 500 when data is missing)
# ---------------------------------------------------------------------------


def _empty_scans_sql() -> str:
    return """
SELECT
    CAST(NULL AS VARCHAR) AS id,
    CAST(NULL AS VARCHAR) AS created_date,
    CAST(NULL AS VARCHAR) AS created_time,
    CAST(NULL AS VARCHAR) AS project,
    CAST(NULL AS VARCHAR) AS agent_id,
    CAST(NULL AS VARCHAR) AS l1,
    CAST(NULL AS INTEGER) AS files_n,
    CAST(NULL AS INTEGER) AS lines_add,
    CAST(NULL AS INTEGER) AS lines_del,
    CAST(NULL AS INTEGER) AS decisions_n,
    CAST(NULL AS VARCHAR) AS scope,
    CAST(NULL AS VARCHAR) AS md_ref
WHERE FALSE
"""
