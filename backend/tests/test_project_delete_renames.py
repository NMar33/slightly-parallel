"""A project delete moves every folder and file to the trash by one rename,
never a copy and a delete (tk_dc394600).

``shutil.move`` falls back to copy + rmtree when ``os.rename`` fails, and
on Windows any handle open inside the folder (a running hook's lock) makes
the rename fail; the rmtree then stops partway and leaves the live project
half deleted behind a full copy in ``.trash``. Now a failed rename stops
the delete, puts back what it already moved, in reverse order, and the
answer names the failed path and the state.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import project_admin
from backend.csvio import append_row, read_rows
from backend.db import ViewStore
from backend.entities import ENTITIES
from backend.server import create_app

TRASH = project_admin.TRASH_DIR
Refused = getattr(project_admin, "DeleteRefused", Exception)


def tree(root: Path) -> dict[str, str]:
    """Every file outside the trash, by its path, with its sha256."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.endswith(".lock")
            and TRASH not in p.relative_to(root).parts}


def trash_files(root: Path) -> list[str]:
    t = root / TRASH
    return sorted(p.relative_to(t).as_posix() for p in t.rglob("*") if p.is_file()) if t.exists() else []


def _touch(root: Path, rel: str, text: str = "x") -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture()
def world(data_root: Path) -> Path:
    """ALPHA with something at every rename the delete makes: the project
    folder, a task's detail document, its kept versions (file and folder),
    evidence and story folders, a note's side folders, a story image filed
    under another task; BETA's files stay."""
    task = ENTITIES["task"]
    append_row(data_root / task.csv, task.columns,
               {"id": "tk_alpha_doc", "project": "ALPHA", "title": "With a document", "status": "todo",
                "md_ref": "task_details/tk_alpha_doc.md"})
    _touch(data_root, "task_details/tk_alpha_doc.md", "---\nid: tk_alpha_doc\n---\nbody\n")
    _touch(data_root, "kept_versions/tk_alpha_doc.md", "v1\n")
    _touch(data_root, "kept_versions/tk_alpha_doc/SKILL.md", "a kept skill\n")
    _touch(data_root, "task_evidence/tk_alpha_doc/shot.png", "png")
    _touch(data_root, "task_story/tk_alpha_doc/prompt.md", "story\n")
    note = ENTITIES["note"]
    append_row(data_root / note.csv, note.columns,
               {"id": "nt_alpha0001", "project": "ALPHA", "title": "A note", "kind": "plan"})
    _touch(data_root, "note_details/nt_alpha0001/v001.md", "a note\n")
    _touch(data_root, "note_images/nt_alpha0001/ni_1.png", "png")
    _touch(data_root, "task_story/tk_x/si_x.png", "png")
    (data_root / "story_images.csv").write_text(
        "id,note_id,task_id,project,title,path,width,height,bytes,created_at\n"
        "si_x,nt_x,tk_x,ALPHA,A shot,task_story/tk_x/si_x.png,10,10,3,2026-09-22T10:00:00\n",
        encoding="utf-8")
    _touch(data_root, "task_details/tk_beta_x.md", "beta\n")
    return data_root


def _trash_renames(monkeypatch, fail_at: int | None = None, held: list[Path] | None = None,
                   back_fails: bool = False) -> list[tuple[Path, Path]]:
    """Wrap ``os.rename``. The renames into the trash are counted; the
    ``fail_at``-th fails the way Windows does (WinError 5). With ``held``,
    a rename of a folder that holds one of those open files fails, and so
    does deleting the file or its folders (Windows, a running hook's lock).
    With ``back_fails``, a rename out of the trash (the rollback) fails."""
    real_rename, real_unlink, real_rmdir = os.rename, os.unlink, os.rmdir
    seen: list[tuple[Path, Path]] = []
    held = [Path(h) for h in (held or [])]

    def holds(p: Path) -> bool:
        return any(h == p or h.is_relative_to(p) for h in held)

    def rename(a, b, *rest, **kw):
        a, b = Path(a), Path(b)
        if TRASH in b.parts:
            seen.append((a, b))
            if len(seen) == fail_at or holds(a):
                raise PermissionError(13, "Access is denied", str(a))
        elif TRASH in a.parts and back_fails:
            raise PermissionError(13, "Access is denied", str(a))
        return real_rename(a, b, *rest, **kw)

    def unlink(p, *rest, **kw):
        # shutil.rmtree unlinks by name beside a dir_fd: match the name.
        if held and Path(p).name in {h.name for h in held}:
            raise PermissionError(13, "The process cannot access the file", str(p))
        return real_unlink(p, *rest, **kw)

    def rmdir(p, *rest, **kw):
        if held and kw.get("dir_fd") is None and holds(Path(p)):
            raise OSError(145, "The directory is not empty", str(p))
        return real_rmdir(p, *rest, **kw)

    monkeypatch.setattr(os, "rename", rename)
    monkeypatch.setattr(os, "unlink", unlink)
    monkeypatch.setattr(os, "rmdir", rmdir)
    return seen


def _delete(root: Path) -> tuple[dict | None, BaseException | None]:
    try:
        return project_admin.delete_project_data(ViewStore(data_root=root), "ALPHA"), None
    except Exception as e:  # noqa: BLE001 - the old code raises whatever shutil raised
        return None, e


def test_every_rename_of_a_delete_is_one_rename_into_the_trash(world: Path, monkeypatch) -> None:
    seen = _trash_renames(monkeypatch)
    out, err = _delete(world)
    assert err is None, err
    moved = {a.relative_to(world).as_posix() for a, _b in seen}
    assert {"projects/ALPHA", "task_details/tk_alpha_doc.md", "kept_versions/tk_alpha_doc.md",
            "kept_versions/tk_alpha_doc", "task_evidence/tk_alpha_doc", "task_story/tk_alpha_doc",
            "note_details/nt_alpha0001", "note_images/nt_alpha0001", "task_story/tk_x/si_x.png"} <= moved
    assert out is not None and out["moved"]["projects_folder"] == 1
    assert (world / "task_details/tk_beta_x.md").exists()


def test_a_rename_failing_at_any_step_leaves_the_project_whole(world: Path, tmp_path: Path,
                                                               monkeypatch) -> None:
    """The N-th rename into the trash fails, for N = each step: every file is
    byte for byte where it was, nothing in the trash is the only copy, and
    the answer names the failed path in one line."""
    pristine = tmp_path / "pristine"
    shutil.copytree(world, pristine)
    with monkeypatch.context() as m:
        counted = _trash_renames(m)
        _delete(world)
    steps = len(counted)
    assert steps >= 9
    before = tree(pristine)
    for n in range(1, steps + 1):
        root = tmp_path / f"n{n}"
        shutil.copytree(pristine, root)
        with monkeypatch.context() as m:
            seen = _trash_renames(m, fail_at=n)
            _out, err = _delete(root)
        assert tree(root) == before, f"step {n} ({seen[n - 1][0].relative_to(root)}): the project changed"
        assert trash_files(root) == [], f"step {n}: {trash_files(root)}"
        assert isinstance(err, Refused) and err is not None, f"step {n}: {err!r}"
        detail = getattr(err, "detail", str(err))
        assert "\n" not in detail
        assert seen[n - 1][0].relative_to(root).as_posix() in detail, detail
        assert "nothing deleted" in detail, detail


def test_a_lock_held_open_inside_the_project_deletes_nothing(world: Path, monkeypatch) -> None:
    """A hook holds a lock inside the project's chats (Windows: the folder
    will not rename, the file will not delete). Before: copy, then an
    rmtree that stopped at the lock — a half-deleted project."""
    lock = world / "projects/ALPHA/chats/alpha-lead-2608-01/meta.json.lock"
    before = tree(world)
    with open(lock, "a", encoding="utf-8"):
        _trash_renames(monkeypatch, held=[lock])
        _out, err = _delete(world)
        monkeypatch.undo()
    assert tree(world) == before
    assert trash_files(world) == []
    assert isinstance(err, Refused), repr(err)
    assert "projects/ALPHA" in err.detail and "nothing deleted" in err.detail  # type: ignore[attr-defined]


@pytest.mark.parametrize("helper", ["_archive_folder", "_archive_file"])
def test_the_archive_helpers_never_copy(world: Path, monkeypatch, helper: str) -> None:
    """A rename that fails leaves the folder or file whole where it is, and
    no copy in the trash."""
    rel = "note_details/nt_alpha0001" if helper == "_archive_folder" else "task_details/tk_alpha_doc.md"
    trash = world / TRASH / "ALPHA-x"
    trash.mkdir(parents=True)
    before = tree(world)
    _trash_renames(monkeypatch, fail_at=1)
    assert getattr(project_admin, helper)(world, trash, rel) is False
    monkeypatch.undo()
    assert tree(world) == before
    assert trash_files(world) == []


def test_a_rollback_that_fails_names_what_is_where(world: Path, monkeypatch) -> None:
    _trash_renames(monkeypatch, fail_at=3, back_fails=True)
    _out, err = _delete(world)
    monkeypatch.undo()
    assert isinstance(err, Refused), repr(err)
    detail = err.detail  # type: ignore[attr-defined]
    assert "\n" not in detail and "nothing deleted" not in detail
    # The two that moved are named, each with where it is now.
    assert "projects/ALPHA" in detail and str(world / TRASH) in detail, detail
    assert (world / TRASH).exists() and not (world / "projects/ALPHA").exists()


def test_a_folder_on_another_volume_is_refused_not_copied(world: Path, monkeypatch) -> None:
    before = tree(world)
    real = project_admin._volume
    monkeypatch.setattr(project_admin, "_volume",
                        lambda p: -1 if Path(p).name == "nt_alpha0001" else real(p))
    _out, err = _delete(world)
    monkeypatch.undo()
    assert isinstance(err, Refused), repr(err)
    assert "another volume" in err.detail and "nothing deleted" in err.detail  # type: ignore[attr-defined]
    assert tree(world) == before and trash_files(world) == []


def test_the_api_refuses_in_one_line_and_changes_nothing(world: Path, monkeypatch) -> None:
    app = create_app(data_root=world, watch=False)
    with TestClient(app) as c:
        before = tree(world)
        _trash_renames(monkeypatch, fail_at=2)
        r = c.post("/api/setup/delete-data", json={"project_code": "ALPHA", "confirm": "ALPHA"})
        monkeypatch.undo()
        assert r.status_code == 409, r.text
        assert "nothing deleted" in r.json()["detail"]
        assert tree(world) == before
        assert {x["id"] for x in read_rows(world / "tasks.csv")} >= {"tk_alpha_auth", "tk_alpha_doc"}
        # And with the handle gone, the delete goes ahead.
        r = c.post("/api/setup/delete-data", json={"project_code": "ALPHA", "confirm": "ALPHA"})
        assert r.status_code == 200, r.text
        assert not (world / "projects/ALPHA").exists()


def test_a_refused_delete_gives_the_members_from_elsewhere_their_membership_back(world: Path,
                                                                                  monkeypatch) -> None:
    """Rule 2's leave needs the project to exist, so it is written before
    the renames; a delete then refused writes the join back."""
    from backend import membership_fold as mf
    from backend import memberships
    from tests.conftest import make_chat
    agent = "cc-bbbb2222"
    make_chat(world, "BETA", agent, [("2026-11-20T10:00:00", "start", "started")])
    memberships.write(world, agent, "join", "ALPHA")
    _trash_renames(monkeypatch, fail_at=1)
    _out, err = _delete(world)
    monkeypatch.undo()
    assert isinstance(err, Refused), repr(err)
    rows, _ = mf.read(world / mf.LEDGER)
    assert [(x["op"], x["project"], x["value"]) for x in rows] == [
        ("join", "ALPHA", ""), ("leave", "ALPHA", mf.DELETED), ("join", "ALPHA", project_admin.REJOINED)]
    m = mf.load(world, memberships.existing_codes(world), {agent: "BETA"})
    assert "ALPHA" in m.members(agent)


def test_a_ledger_phase_failure_names_the_trash_and_a_retry_finishes_into_it(world: Path,
                                                                            monkeypatch) -> None:
    """The renames went through, then a ledger's lock times out (csvio's
    flock, FileSafetyError). Not a 503 «held by a chat move»: a 500 naming
    the trash folder and what is where. A second delete finishes into the
    same folder, so one archive holds the whole project."""
    from backend.file_safety import FileSafetyError
    real = project_admin.rewrite_rows

    def busy(path, *a, **k):
        if Path(path).name == "tasks.csv":
            raise FileSafetyError("could not acquire lock on tasks.csv.lock within 10s")
        return real(path, *a, **k)

    app = create_app(data_root=world, watch=False)
    with TestClient(app) as c:
        monkeypatch.setattr(project_admin, "rewrite_rows", busy)
        r = c.post("/api/setup/delete-data", json={"project_code": "ALPHA", "confirm": "ALPHA"})
        monkeypatch.undo()
        assert r.status_code == 500, r.text
        detail = r.json()["detail"]
        folders = sorted(p for p in (world / TRASH).glob("ALPHA-*") if p.is_dir())
        assert len(folders) == 1 and str(folders[0]) in detail, detail
        assert "\n" not in detail and "try again" not in detail.lower(), detail
        assert "tasks" in detail and "still live" in detail, detail
        assert (folders[0] / "projects" / "ALPHA").is_dir()
        r = c.post("/api/setup/delete-data", json={"project_code": "ALPHA", "confirm": "ALPHA"})
        assert r.status_code == 200, r.text
        assert sorted(p for p in (world / TRASH).glob("ALPHA-*") if p.is_dir()) == folders
        assert Path(r.json()["trash"]) == folders[0]
        assert {x["id"] for x in read_rows(folders[0] / "tasks.csv")} >= {"tk_alpha_auth", "tk_alpha_doc"}
        assert all(x["project"] != "ALPHA" for x in read_rows(world / "tasks.csv"))
        assert not list((world / TRASH).glob("*.unfinished"))
