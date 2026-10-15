"""Backups under pressure: a write that lands during a restore, two
operations at once, what an interrupted run leaves, and archives that hold
what no archive of ours holds."""

from __future__ import annotations

import io
import json
import os
import tarfile
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from backend import backup


@pytest.fixture(autouse=True)
def _no_env_backup_root(monkeypatch):
    monkeypatch.delenv("SP_BACKUP_ROOT", raising=False)


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "00-agents"
    (data / "projects" / "ALPHA").mkdir(parents=True)
    (data / "tasks.csv").write_text("id,title\ntk_1,Ship it\n", encoding="utf-8")
    (data / "decisions.csv").write_text("id,title\nd_1,Keep it\n", encoding="utf-8")
    (data / "projects" / "ALPHA" / "log.md").write_text("one\n", encoding="utf-8")
    return data, backup.backup_root_for(data)


def _snapshot(root: Path) -> dict[str, bytes | None]:
    out: dict[str, bytes | None] = {}
    for p in sorted(root.rglob("*")):
        out[p.relative_to(root).as_posix()] = p.read_bytes() if p.is_file() else None
    return out


# ---------------------------------------------------------------------------
# C1 — a write in the gap of a restore
# ---------------------------------------------------------------------------


def test_a_write_in_the_gap_fails_the_restore_and_leaves_the_data_as_it_was(roots, monkeypatch):
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")
    (data / "tasks.csv").write_text("id,title\ntk_1,Ship it\ntk_2,Later\n", encoding="utf-8")
    before = _snapshot(data)

    real_move = backup.shutil.move
    planted: list[str] = []

    def move(src: str, dst: str):
        src_p = Path(src)
        if not planted and "sp-restore-" in src and Path(dst).parent == data:
            # The first piece of the archive moves in; a hook writes the
            # others' names into the emptied data root before they follow.
            for other in src_p.parent.iterdir():
                if other.name == src_p.name:
                    continue
                if other.is_dir():
                    (data / other.name).mkdir()
                    (data / other.name / "gap.md").write_text("written in the gap\n", encoding="utf-8")
                else:
                    (data / other.name).write_text("written in the gap\n", encoding="utf-8")
                planted.append(other.name)
        return real_move(src, dst)

    monkeypatch.setattr(backup.shutil, "move", move)
    with pytest.raises(backup.BackupError) as err:
        backup.restore(dest, archive.name, data)
    assert planted
    assert "while the restore ran" in str(err.value)
    assert "The data is as it was before." in str(err.value)
    assert _snapshot(data) == before
    # What was written in the gap is kept, and shown.
    aside = backup.kept_aside(dest)
    assert [a["name"][:11] for a in aside] == ["sp-arrived-"]
    arrived = Path(aside[0]["path"])
    assert sorted(p.name for p in arrived.iterdir()) == sorted(planted)
    # The emptied sp-replaced- folder went with the success of the way back.
    assert not list(dest.glob("sp-replaced-*"))


# ---------------------------------------------------------------------------
# C2 — one operation at a time
# ---------------------------------------------------------------------------


def test_a_second_backup_waits_for_the_first(roots):
    data, dest = roots
    done = threading.Event()
    with backup.BUSY:
        t = threading.Thread(target=lambda: (backup.create(data, dest, kind="manual"), done.set()))
        t.start()
        time.sleep(0.3)
        assert not done.is_set(), "it ran while another operation held the lock"
    t.join(10)
    assert done.is_set()


def test_the_scheduled_backup_skips_its_turn_while_another_runs(roots, caplog):
    from backend import server

    data, dest = roots
    result: list = []
    with backup.BUSY:
        t = threading.Thread(target=lambda: result.append(server._scheduled_backup(data, dest, 6)))
        t.start()
        t.join(10)
    assert result == [(None, "another backup operation is running")]
    assert backup.list_archives(dest) == []
    assert "scheduled backup skipped" in caplog.text
    made, _ = server._scheduled_backup(data, dest, 6)
    assert made is not None


def test_a_name_whose_archive_is_still_being_written_is_taken(roots):
    data, dest = roots
    at = datetime(2026, 10, 12, 9, 0, 0)
    dest.mkdir(parents=True)
    (dest / (backup.archive_name(at, "manual") + backup.ARCHIVE_SUFFIX + backup.PART_SUFFIX)).write_bytes(b"")
    made = backup.create(data, dest, kind="manual", now=at)
    assert made.name == backup.archive_name(datetime(2026, 10, 12, 9, 0, 1), "manual")


# ---------------------------------------------------------------------------
# C3 — leftovers
# ---------------------------------------------------------------------------


def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_stale_leftovers_are_removed_and_the_operators_data_is_listed(roots):
    data, dest = roots
    dest.mkdir(parents=True)
    old_part = dest / "2610-12-090000__auto.tar.gz.part"
    young_part = dest / "2610-12-100000__auto.tar.gz.part"
    for p in (old_part, young_part):
        p.write_bytes(b"half")
    old_restore = dest / "sp-restore-abc"
    old_trial = dest / "sp-trial-abc"
    replaced = dest / "sp-replaced-abc"
    for d in (old_restore, old_trial, replaced):
        d.mkdir()
        (d / "tasks.csv").write_text("x\n", encoding="utf-8")
    for p in (old_part, old_restore, old_trial, replaced):
        _age(p, 2 * 3600)

    gone = backup.prune(dest, datetime.now())
    assert gone == []
    assert not old_part.exists() and not old_restore.exists() and not old_trial.exists()
    assert young_part.exists(), "a run still going keeps its part"
    assert (replaced / "tasks.csv").exists(), "the operator's previous data is never deleted"
    assert [a["name"] for a in backup.kept_aside(dest)] == ["sp-replaced-abc"]


def test_the_state_lists_folders_a_failed_restore_left(client, data_root):
    dest = backup.backup_root_for(data_root)
    (dest / "sp-replaced-xyz").mkdir(parents=True)
    body = client.get("/api/backup").json()
    assert [a["name"] for a in body["kept_aside"]] == ["sp-replaced-xyz"]


# ---------------------------------------------------------------------------
# C4 — the trial unpacks beside the archives
# ---------------------------------------------------------------------------


def test_the_trial_unpacks_beside_the_archives(data_root, monkeypatch):
    dest = backup.backup_root_for(data_root)
    made = backup.create(data_root, dest, kind="manual")
    seen: list[Path] = []
    real = backup._extract

    def extract(path, into):
        seen.append(Path(into))
        return real(path, into)

    monkeypatch.setattr(backup, "_extract", extract)
    got = backup.trial(dest, made.name)
    assert got["ok"], got["problems"]
    assert seen and seen[0].parent == dest and seen[0].name.startswith("sp-trial-")
    assert not list(dest.glob("sp-trial-*"))


# ---------------------------------------------------------------------------
# C5 — links in an archive
# ---------------------------------------------------------------------------


def _crafted(dest: Path, top: str, link: tarfile.TarInfo) -> str:
    """An archive under our name that holds a link next to real data."""
    name = backup.archive_name(datetime(2026, 1, 2, 3, 4, 5), "manual")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest / (name + backup.ARCHIVE_SUFFIX), "w:gz") as tar:
        d = tarfile.TarInfo(top)
        d.type = tarfile.DIRTYPE
        tar.addfile(d)
        body = b"id,title\n"
        f = tarfile.TarInfo(f"{top}/tasks.csv")
        f.size = len(body)
        tar.addfile(f, io.BytesIO(body))
        tar.addfile(link)
    return name


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_an_archive_with_a_link_is_refused_whole(roots, kind):
    data, dest = roots
    link = tarfile.TarInfo(f"{data.name}/projects/evil")
    link.type = kind
    link.linkname = "../.." if kind == tarfile.SYMTYPE else f"{data.name}/tasks.csv"
    name = _crafted(dest, data.name, link)
    before = _snapshot(data)

    assert not backup.verify(dest, name)["ok"]
    with pytest.raises(backup.BackupError, match="link"):
        backup.restore(dest, name, data)
    with pytest.raises(backup.BackupError, match="link"):
        backup.restore_with_safety(dest, name, data)
    assert _snapshot(data) == before
    assert [a.name for a in backup.list_archives(dest)] == [name], "no safety archive was taken"
    got = backup.trial(dest, name)
    assert not got["ok"] and any("link" in p for p in got["problems"])
    assert not list(dest.glob("sp-restore-*")) and not list(dest.glob("sp-trial-*"))


# ---------------------------------------------------------------------------
# C6 — a Python without the unpack filter
# ---------------------------------------------------------------------------


def test_a_python_without_the_filter_is_refused_before_the_safety_archive(roots, monkeypatch):
    data, dest = roots
    made = backup.create(data, dest, kind="manual")
    monkeypatch.delattr(tarfile, "data_filter")
    with pytest.raises(backup.BackupError, match="3.11.4"):
        backup.restore_with_safety(dest, made.name, data)
    assert [a.name for a in backup.list_archives(dest)] == [made.name]


# ---------------------------------------------------------------------------
# C7 — links in the data root are counted
# ---------------------------------------------------------------------------


def test_links_in_the_data_root_are_counted_not_silently_skipped(roots):
    data, dest = roots
    (data / "shortcut.csv").symlink_to(data / "tasks.csv")
    (data / "projects" / "ALPHA" / "elsewhere").symlink_to(data.parent)
    made = backup.create(data, dest, kind="manual")
    assert made.skipped_links == 2
    side = json.loads((dest / (made.name + backup.SIDECAR_SUFFIX)).read_text(encoding="utf-8"))
    assert side["skipped_links"] == 2
    assert backup.find(dest, made.name).skipped_links == 2


def test_the_state_shows_how_many_links_are_left_out(client, data_root):
    assert client.get("/api/backup").json()["source"]["skipped_links"] == 0
    (data_root / "linked").symlink_to(data_root.parent)
    assert client.get("/api/backup").json()["source"]["skipped_links"] == 1
