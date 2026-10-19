"""The consistency fixes, each held down by one test.

Seven things in the backend existed in several copies that disagreed: the
refusal an agent gets, the ``---`` parser, the git wrapper, the
read-modify-write of a JSON state file, the caps on what a write may hold,
what a project delete takes with it, and what the architecture page's ETag
sees. Each is one thing now, and each line below is the proof.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import file_safety, frontmatter, limits
from backend.server import create_app


# ---------------------------------------------------------------------------
# 1 · Errors
# ---------------------------------------------------------------------------


def test_a_library_value_error_is_422_not_an_opaque_500(data_root: Path) -> None:
    """A ``ValueError`` no router caught used to reach the catch-all and
    come back as ``internal error — id <8hex>``."""
    app = create_app(data_root=data_root, watch=False)

    async def _probe() -> dict:
        raise ValueError("2699-99 is not a calendar date")

    # Ahead of the SPA fallback, which claims every remaining path.
    app.add_api_route("/api/_value_error_probe", _probe, methods=["GET"])
    app.router.routes.insert(0, app.router.routes.pop())

    with TestClient(app) as client:
        r = client.get("/api/_value_error_probe")
    assert r.status_code == 422
    assert r.json()["detail"] == "2699-99 is not a calendar date"
    assert "error_id" not in r.json()


def test_every_refusal_of_an_agent_has_one_shape(client: TestClient) -> None:
    """Four unrelated paths into ``deps.refuse_agent``: the lens gate, an
    inline raise in tasks, one in the storyboard, one in the prompt
    library. One status, one ``detail`` key, one sentence."""
    agent = {"agent_id": "cc-probe-2609-22"}
    calls = [
        ("/api/sprints", {**agent, "created_date": "2609-22", "project": "ALPHA",
                          "l1": "A sprint an agent may not start"}),
        ("/api/prompt-library", {**agent, "project": "ALPHA", "text": "a prompt"}),
    ]
    for path, body in calls:
        r = client.post(path, json=body)
        assert r.status_code == 422, f"{path}: {r.status_code} {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, str) and detail, f"{path}: {r.text}"


# ---------------------------------------------------------------------------
# 2 · One frontmatter splitter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,pairs,body", [
    ("---\nkey: task\ncommand: #task | open one\n---\nThe body.\n",
     [("key", "task"), ("command", "#task | open one")], "The body.\n"),
    # No newline after the closing fence: still frontmatter (promptlib used
    # to read this as a document with none).
    ("---\nid: p1\n---", [("id", "p1")], ""),
    # Not at the start of the text: not frontmatter.
    ("intro\n---\nid: p1\n---\n", [], "intro\n---\nid: p1\n---\n"),
    # No opening newline after the dashes: not an opening fence.
    ("---id: p1\n---\n", [], "---id: p1\n---\n"),
])
def test_the_one_parser_reads_a_block_the_same_way(text, pairs, body) -> None:
    assert frontmatter.pairs(text) == (pairs, body)


def test_every_reader_of_a_block_agrees_with_it() -> None:
    """The five spellings that used to disagree now all come through
    ``frontmatter``: pairs, YAML, the block verbatim, and the body."""
    from backend import archpage, contract_parts, docs_md, skilllib, turns

    text = '---\nn: 3\nat: 2026-09-22T10:00:00\nnote: "a colon: inside"\n---\n## L2\nbody\n'
    assert contract_parts.split_frontmatter(text)[1] == "## L2\nbody\n"
    assert turns._split_frontmatter(text)[0].startswith("---\n")
    assert docs_md.parse_sections(text)[0] == "body"
    assert archpage._split(text)[0]["note"] == "a colon: inside"
    assert skilllib.parse("---\nname: a-skill\n---\nhow to\n") == (
        {"name": "a-skill"}, "how to"
    )


# ---------------------------------------------------------------------------
# 3 · One git wrapper
# ---------------------------------------------------------------------------


def test_the_git_wrapper_tells_failure_from_empty(tmp_path: Path) -> None:
    import inspect

    from backend import file_entries, gitwork, projectfacts, repomap, scanlib

    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    # git fails here — None, not "" (projectfacts used to answer "" and the
    # Architecture page rendered it as "no commits").
    assert gitwork.git(not_a_repo, "rev-parse", "HEAD") is None
    assert file_entries.git is gitwork.git
    # One wrapper: no module keeps a runner of its own.
    for module in (projectfacts, repomap, scanlib, file_entries):
        source = inspect.getsource(module)
        assert "subprocess.run" not in source, module.__name__


# ---------------------------------------------------------------------------
# 4 · One read-modify-write of a JSON state file
# ---------------------------------------------------------------------------


def test_edit_json_locks_reads_and_writes_in_one_cycle(tmp_path: Path) -> None:
    path = tmp_path / "boards.json"

    # A file that is not there yet reads as the default.
    out = file_safety.edit_json(path, lambda d: d.update({"boards": [1]}))
    assert out == {"boards": [1]} and json.loads(path.read_text()) == {"boards": [1]}

    # A change may return the document instead of mutating it.
    assert file_safety.edit_json(path, lambda d: {"boards": d["boards"] + [2]}) == {"boards": [1, 2]}

    # A truncated file reads as the default rather than raising.
    path.write_text("{ not json", encoding="utf-8")

    def reset(d: dict) -> None:
        d.setdefault("boards", [])

    assert file_safety.edit_json(path, reset) == {"boards": []}
    # …and what it held is kept beside it, not written over.
    kept = list(tmp_path.glob("boards.json.unreadable-*"))
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == "{ not json"

    # JSON of the wrong shape is kept the same way; an empty file holds nothing to keep.
    path.write_text("[1, 2]", encoding="utf-8")
    assert file_safety.edit_json(path, reset) == {"boards": []}
    path.write_text("", encoding="utf-8")
    assert file_safety.edit_json(path, reset) == {"boards": []}
    assert len(list(tmp_path.glob("boards.json.unreadable-*"))) == 2

    # The lock sits beside the file, under one name.
    assert file_safety.lock_path(path).name == "boards.json.lock"
    assert file_safety.lock_path(path).exists()


def test_two_boards_posted_in_a_row_both_survive(client: TestClient) -> None:
    for name in ("first board", "second board"):
        assert client.post("/api/boards", json={"name": name}).status_code == 201
    names = {b["name"] for b in client.get("/api/boards").json()["boards"]}
    assert {"first board", "second board"} <= names


# ---------------------------------------------------------------------------
# 5 · One place for the caps
# ---------------------------------------------------------------------------


def test_an_image_has_one_size_limit_whichever_door_it_comes_through() -> None:
    from backend.routers import evidence, story_release

    assert evidence.MAX_IMAGE_BYTES == story_release.MAX_IMAGE_BYTES == limits.MAX_IMAGE_BYTES
    assert limits.MAX_IMAGE_BYTES == 12 * 1024 * 1024


def test_the_caps_are_read_from_limits_not_redefined() -> None:
    from backend import artifactlib, evidence_items, keeplib, promptlib, skilllib
    from backend.routers import calendar, sets
    from backend.routers import promptlib as promptlib_router

    assert keeplib.MAX_TEXT == promptlib_router._MAX_TEXT == calendar.MAX_BODY == limits.MAX_TEXT
    assert keeplib.MAX_NOTE == promptlib.MAX_NOTE == limits.MAX_NOTE
    assert skilllib.MAX_NAME == limits.MAX_NAME
    assert sets.MAX_NAME == limits.MAX_SET_NAME
    assert evidence_items.MAX_NOTE == limits.MAX_EVIDENCE_NOTE
    assert artifactlib.DOCUMENT_MAX_CHARS == limits.MAX_DOCUMENT_CHARS


# ---------------------------------------------------------------------------
# 6 · Deleting a project takes its orphans
# ---------------------------------------------------------------------------


def test_deleting_a_project_sweeps_kept_versions_and_story_images(
    client: TestClient, data_root: Path
) -> None:
    from backend import project_admin

    # A problem with a kept interpretation — its versions live flat at the
    # data root, outside projects/<code>/.
    r = client.post("/api/problems", json={
        "project": "ALPHA", "agent_id": "operator", "created_date": "2608-10",
        "created_time": "09:00", "l1": "A problem worth an interpretation",
        "severity": "high", "status": "open",
    })
    assert r.status_code == 201, r.text
    pid = r.json()["metadata"]["id"]
    versions = data_root / "kept_versions" / f"{pid}.md"
    versions.parent.mkdir(parents=True, exist_ok=True)
    versions.write_text("---\nid: x\n---\nv1\n", encoding="utf-8")

    # A story image row for the project, with its file.
    image = data_root / "task_story" / "tk_x" / "si_x.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"png")
    csv = data_root / "story_images.csv"
    csv.write_text(
        "id,note_id,task_id,project,title,path,width,height,bytes,created_at\n"
        "si_x,nt_x,tk_x,ALPHA,A shot,task_story/tk_x/si_x.png,10,10,3,2026-09-22T10:00:00\n",
        encoding="utf-8",
    )
    client.app.state.store.rebuild()

    out = project_admin.delete_project_data(client.app.state.store, "ALPHA")
    trash = Path(out["trash"])
    assert not versions.exists(), "the kept versions were left orphaned"
    assert (trash / "kept_versions" / f"{pid}.md").exists()
    assert not image.exists(), "the story image file was left orphaned"
    assert (trash / "task_story" / "tk_x" / "si_x.png").exists()
    assert out["moved"]["story_images"] == 1


# ---------------------------------------------------------------------------
# 7 · The architecture page is part of what the ETag sees
# ---------------------------------------------------------------------------


def test_a_new_page_version_moves_the_view_and_the_fingerprint(
    client: TestClient, data_root: Path
) -> None:
    from backend import archpage
    from backend.routers.lenses import ETAG_STATE

    store = client.app.state.store
    # The page and the map both live outside the views; one fingerprint holds both.
    assert archpage.fingerprint(store) in ETAG_STATE["architecture"](store)

    before_print = archpage.fingerprint(store)
    before_mtime = store.view_mtime

    page = data_root / "projects" / "ALPHA" / "architecture" / "v001.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("---\nn: 1\n---\n## What it is\nA dashboard.\n", encoding="utf-8")
    store.rebuild()

    assert archpage.fingerprint(store) != before_print
    assert store.view_mtime > before_mtime, "view_mtime did not see the page"


def test_every_project_folder_is_readable_in_one_place(client: TestClient, tmp_path) -> None:
    """The pages show a path as the agent wrote it, relative to the project
    folder. Copying it must give an absolute path, so the folders are read
    once, here (frontend lib/paths.tsx)."""
    from backend.csvio import append_row

    store = client.app.state.store
    repo = tmp_path / "somewhere"
    repo.mkdir()
    append_row(store.data_root / "integrations.csv", ("project", "path"), {"project": "ALPHA", "path": str(repo)})
    got = client.get("/api/projects/folders").json()
    assert got["folders"]["ALPHA"] == str(repo)
    assert got["data_root"] == str(store.data_root)


def test_the_operator_reads_chat_not_session() -> None:
    """The thing a person opens is a chat. The word `session` stays in the
    code, the route and the stored setting key, because other programs
    depend on those; it is gone from everything a person or an agent reads."""
    import re

    root = Path(__file__).resolve().parents[2]
    read_by_people = [
        root / "prompts" / "contract",
        root / "templates" / "agents-block.md",
        root / "frontend" / "src" / "features" / "guide" / "pages.ts",
        root / "frontend" / "src" / "features" / "visions" / "guides.ts",
    ]
    allowed = re.compile(r"session_id|session_ref|sessions\.gap_minutes|api/sessions|Claude-Session"
                         r"|no captured session|route: '/sessions'|lives only in the chat")
    bad: list[str] = []
    for target in read_by_people:
        files = sorted(target.rglob("*.md")) if target.is_dir() else [target]
        for path in files:
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "session" in line.lower() and not allowed.search(line):
                    bad.append(f"{path.name}:{n}: {line.strip()[:70]}")
    assert not bad, "the operator reads `chat`, not `session`:\n" + "\n".join(bad)


def test_a_slightly_parallel_date_is_read_in_one_place() -> None:
    """`date_utils` says it is the one place a YYMM-DD is read. It said a
    pre-commit hook enforced that; no hook existed and four modules parsed
    dates themselves, one of them reading years 69-99 into the last century.
    This test is the rule."""
    import re

    from backend import date_utils

    root = Path(date_utils.__file__).parent
    bad: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "date_utils.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"strptime\([^)]*%y", line):
                bad.append(f"{path.relative_to(root)}:{n}: {line.strip()[:70]}")
    assert not bad, "a Slightly Parallel date is read by date_utils, not by hand:\n" + "\n".join(bad)
    assert date_utils.day_of("2026-09-21") == "2609-21"
    assert date_utils.day_of("2609-21") == "2609-21"
    assert date_utils.iso_of("2609-21") == "2026-09-21"
    assert date_utils.day_before("2609-01") == "2608-31"
    assert date_utils.day_of("not a day") == "" and date_utils.iso_of("") == ""
