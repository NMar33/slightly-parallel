"""The entry points written before ways in existed: their ways in are read
out of the record once, where a line is unambiguous; the record itself is
not touched; the run is backed up beside the data root, done once, and
refused whole when a file cannot be read.

The nine shapes are the live ones of 2611-11: a good English record (the
films), a good Russian one (the site text console), a duplicate with no
text, fragments with no headline and no text, a pasted message with a
record of two versions, records whose links are claude.ai artifacts, and
an archived one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import entrypointlib as E
from backend.csvio import append_row, read_rows
from backend.docs_md import build_detail, read_detail
from backend.entities import ENTITIES

FILMS = """## What
The films of Slightly Parallel and the publishing of v0.1.0.

## Where
- The launch checklist: `brand/channel/launch.md` → `brand/channel/launch.html` (rebuilt by `python3 brand/channel/launch.py`)
- Review pages: the frames https://claude.ai/artifact/AAA, the ground variants https://claude.ai/artifact/BBB
- The films online: short https://youtu.be/NmtQgkg-D-E, long https://youtu.be/eZ0_f1sKaLE (both Unlisted)
- The repository: https://github.com/NMar33/slightly-parallel; the publish folder `~/main/05 projects/slightly_parallel`

## How
- A film: Tour → custom (`/tour/custom`) → pick the cut → 1920px → render MP4

## State
Voiced; not uploaded.
"""

CONSOLE = """## What

Консоль текстов getbewrite.com и метод вырезок.

## Where

- Приложение: `120-app-mvp/tool/console/` (`src/App.tsx`, `build_data.py`).

## How

Запуск из `120-app-mvp/tool/console`: `npm run dev`, адрес http://localhost:8120. Обновить данные из `120-app-mvp`: `python3 tool/console/build_data.py`.

## State

Работает локально.
"""

ONE_LINE = """## How
Запуск из `tool/console`: `npm run dev`, адрес http://localhost:8120
"""

DRAFTS = """## What
A place for drafts.

## Where
- `brand/channel/drafts/drafts.html` — the page, published at https://claude.ai/artifact/LbtvoEAVA1QFrhs4dukrMb
- Communication: https://claude.ai/artifact/648vYaNT2nMYBuAFSgZjF4
"""

SHAPES = [
    # (id, l1, topic, text, archived)
    ("ep_446b4a5a", "с темой «видео и публикация»", "The films and the launch", FILMS, ""),
    ("ep_c8021fc2", "tk_ad5bc0ca допиши к этой задаче", "", CONSOLE, ""),
    ("ep_18fc27f9", "с темой «видео и публикация»", "", "", ""),
    ("ep_5d7425db", "", "", "", ""),
    ("ep_93ec1a57", "", "", "", ""),
    ("ep_43327a23", '<pasted_content id="afc9">', "", DRAFTS, ""),
    ("ep_0132d809", "Про хват", "", "## How\n- open http://127.0.0.1:5173/tour/custom\n", ""),
    ("ep_8270d1a9", "имел ввиду", "", "## What\nA fragment.\n", ""),
    ("ep_334a2ccd", "так, выбирать", "", "## Where\n- Features: https://claude.ai/artifact/6JRgbwRC3Z2FdfJ1qMCDev\n", ""),
    ("ep_deadbeef", "archived one", "", "## How\nrun http://localhost:9000 now\n", "2611-11 12:00"),
]


def _seed(root: Path, shapes=SHAPES) -> None:
    ent = ENTITIES["entrypoint"]
    for eid, l1, topic, text, archived in shapes:
        # Not "x…": test_doc_paths looks for stray x*.md files in the whole temp folder.
        md_ref = f"{ent.detail_dir}/261016-1913__merkhet__cc-1__{eid}.md"
        row = {"id": eid, "created_date": "2610-16", "created_time": "19:13", "project": "merkhet",
               "agent_id": "cc-1", "l1": l1, "topic": topic, "status": "open", "md_ref": md_ref,
               "source": "captured", "session_id": "s1", "source_turn": 3,
               "versions_n": 1 if text else 0, "tags": "", "archived_at": archived}
        if text or l1:
            path = root / md_ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(build_detail({**row, "l2": text, "l4": l1}, eid), encoding="utf-8")
        # The live file has the old header: no state, no_project, home.
        append_row(root / ent.csv, ent.columns[:15], row)


@pytest.fixture()
def root(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("SP_BACKUP_ROOT", str(tmp_path / "backups"))
    r = tmp_path / "data"
    r.mkdir()
    _seed(r)
    return r


def _ways(root: Path) -> list[dict[str, str]]:
    return read_rows(root / E.WAYS_FILE)


def test_the_nine_shapes_migrate_once_and_the_records_stay(root: Path, tmp_path: Path) -> None:
    before = {p: p.read_bytes() for p in (root / "entrypoint_details").iterdir()}
    got = E.migrate(root)
    assert sorted(got["migrated"]) == sorted(s[0] for s in SHAPES if not s[4])
    ways = _ways(root)
    by = {}
    for w in ways:
        by.setdefault(w["entrypoint_id"], []).append(w)
    # The films: only the repository line says one thing; lines with two URLs say nothing.
    assert [(w["name"], w["kind"], w["url"]) for w in by["ep_446b4a5a"]] == [
        ("The repository", "site", "https://github.com/NMar33/slightly-parallel")]
    # The console: its URL and port; two commands and two folders in the paragraph: neither taken.
    (c,) = by["ep_c8021fc2"]
    assert (c["kind"], c["url"], c["port"], c["command"], c["folder"]) == ("page", "http://localhost:8120", "8120", "", "")
    # A claude.ai link under a label is an artifact; a path line with a link and no label is not read.
    assert [(w["name"], w["kind"]) for w in by["ep_43327a23"]] == [("Communication", "artifact")]
    assert [(w["name"], w["kind"]) for w in by["ep_334a2ccd"]] == [("Features", "artifact")]
    assert by["ep_0132d809"][0]["port"] == "5173"
    # No text, a fragment, an archived row: no ways.
    for eid in ("ep_18fc27f9", "ep_5d7425db", "ep_93ec1a57", "ep_8270d1a9", "ep_deadbeef"):
        assert eid not in by
    assert all(w["actor"] == "migration" for w in ways)
    # The record is not touched; state is not written (it reads from status).
    assert {p: p.read_bytes() for p in (root / "entrypoint_details").iterdir()} == before
    assert all(E.state_of(r) == "active" for r in read_rows(root / "entrypoints.csv"))
    # Backed up beside the data root, never inside it.
    (bk,) = list((tmp_path / "backups").iterdir())
    assert bk.name.startswith("entrypoints-migration-") and (bk / "entrypoints.csv").is_file()
    assert not (root / "backups").exists()
    # Once: a second run writes nothing, and a record kept later is never parsed.
    marker = (root / E.MIGRATION_FILE).read_bytes()
    _seed(root, [("ep_11111111", "later", "", "## How\nopen http://localhost:7000\n", "")])
    assert E.migrate(root) == {"migrated": [], "ways": 0}
    assert _ways(root) == ways and (root / E.MIGRATION_FILE).read_bytes() == marker


def test_a_rerun_after_a_crash_writes_no_second_copy(root: Path) -> None:
    """Killed after the ways were written, before the marker: the rerun
    mints the same ids and adds nothing twice (ten questions, 6)."""
    E.migrate(root)
    first = _ways(root)
    (root / E.MIGRATION_FILE).unlink()
    E.migrate(root)
    assert _ways(root) == first


def test_a_record_that_cannot_be_read_stops_the_run_before_any_write(root: Path, tmp_path: Path) -> None:
    doc = next((root / "entrypoint_details").glob("*ep_446b4a5a.md"))
    doc.write_bytes(b"\xff\xfe not utf-8 \x80")
    with pytest.raises(RuntimeError, match="cannot be read"):
        E.migrate(root)
    assert not (root / E.WAYS_FILE).exists() and not (root / E.MIGRATION_FILE).exists()
    assert not (tmp_path / "backups").exists()


def test_a_marker_that_cannot_be_read_refuses_the_run(root: Path) -> None:
    (root / E.MIGRATION_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        E.migrate(root)
    assert not (root / E.WAYS_FILE).exists()


def test_nothing_to_migrate_writes_no_backup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SP_BACKUP_ROOT", str(tmp_path / "backups"))
    r = tmp_path / "data"
    r.mkdir()
    assert E.migrate(r) == {"migrated": [], "ways": 0}
    _seed(r, [("ep_22222222", "x", "", "## What\nno links\n", "")])
    E.migrate(r)
    assert not (tmp_path / "backups").exists()
    assert json.loads((r / E.MIGRATION_FILE).read_text(encoding="utf-8"))["version"] == 1


def test_the_server_migrates_at_start_but_never_the_shipped_fixtures(root: Path) -> None:
    from backend.db import FIXTURES
    from backend.server import create_app
    create_app(data_root=root, watch=False)
    assert (root / E.MIGRATION_FILE).is_file() and _ways(root)
    create_app(data_root=FIXTURES, watch=False)
    assert not (FIXTURES / E.MIGRATION_FILE).exists() and not (FIXTURES / E.WAYS_FILE).exists()


@pytest.mark.parametrize("line, want", [
    ("Run from `tool/console`: `npm run dev`, then http://localhost:8120", ("http://localhost:8120", "npm run dev", "tool/console")),
    ("Open http://127.0.0.1:8765/app/ after `.venv/bin/offkey serve`", ("http://127.0.0.1:8765/app/", ".venv/bin/offkey serve", "")),
    # A Windows folder is kept as written.
    (r"Start in `C:\Users\nick\site`: `npm run dev` → http://localhost:3000", ("http://localhost:3000", "npm run dev", r"C:\Users\nick\site")),
    (r"Start `npm run dev` → http://localhost:3000", ("http://localhost:3000", "npm run dev", "")),
    (r"From `C:\Users\nick\site`: `npm run dev` → http://localhost:3000", ("http://localhost:3000", "npm run dev", r"C:\Users\nick\site")),
])
def test_one_local_line_gives_its_url_command_and_folder(line: str, want: tuple[str, str, str]) -> None:
    (w,) = E.parse_ways(f"## How\n{line}\n")
    assert (w["url"], w["command"], w["folder"]) == want


@pytest.mark.parametrize("text", [
    "## How\nhttp://localhost:8120 and http://localhost:8121\n",          # two URLs
    "## How\n`curl http://localhost:8120/api`\n",                          # the URL is inside a command
    "## How\nhttps://example.com/docs\n",                                  # not local, not under Where
    "## Where\nhttps://example.com/docs\n",                                # no label
    "## Where\n- Thing http://x.org: https://example.com\n",               # the label holds a URL
    "## State\nhttp://localhost:8120 is down\n",                           # not Where or How
])
def test_ambiguous_lines_say_nothing(text: str) -> None:
    assert E.parse_ways(text) == []


def test_read_detail_of_the_seed_is_the_record(root: Path) -> None:
    doc = next((root / "entrypoint_details").glob("*ep_c8021fc2.md"))
    l2, _l3, _l4 = read_detail(root, str(doc.relative_to(root)))
    assert E.what_of(l2) == "Консоль текстов getbewrite.com и метод вырезок."


def test_ways_the_migration_wrote_do_not_make_a_topic_look_worked_on_today(root: Path) -> None:
    from backend.db import ViewStore
    E.migrate(root)
    store = ViewStore(data_root=root)
    store.rebuild()
    (t,) = [x for x in E.desk(store, "merkhet")["topics"] if x["id"] == "ep_446b4a5a"]
    assert t["ways"] and t["last_at"] == "2026-10-16T19:13:00"
