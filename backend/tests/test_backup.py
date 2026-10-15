"""Backups: the rotation ladder, the archive round trip, and the guards.

The rotation planner is pure, so it is tested against a synthetic year
rather than against the clock. Everything that touches the disk is tested
by making an archive and putting it back — a backup nobody has restored is
not known to be a backup.
"""

from __future__ import annotations

import tarfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend import backup


@pytest.fixture(autouse=True)
def _no_env_backup_root(monkeypatch):
    """The operator's own SP_BACKUP_ROOT must never steer a test."""
    monkeypatch.delenv("SP_BACKUP_ROOT", raising=False)


def _archive(at: datetime, kind: str = "auto", pinned: bool = False) -> backup.Archive:
    return backup.Archive(
        name=backup.archive_name(at, kind), at=at, kind=kind, pinned=pinned,
    )


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------


def test_name_round_trips_through_slightly_parallel_date_format():
    at = datetime(2026, 9, 7, 15, 18, 33)
    name = backup.archive_name(at, "manual")
    assert name == "2609-07-151833__manual"
    assert backup.parse_name(name) == (at, "manual")


@pytest.mark.parametrize("name", [
    "", "notes", "2609-07-151833", "2609-07-151833__weekly",
    "2609-07-1518__auto", "../../etc/passwd", "2699-99-999999__auto",
])
def test_names_that_are_not_ours_parse_to_nothing(name):
    assert backup.parse_name(name) is None


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


def test_a_year_of_daily_backups_leaves_a_restore_point_at_every_rung():
    """The operator asked for a day, 3 days, a week, 2 weeks, a month, 3 months."""
    now = datetime(2026, 9, 7, 12, 0)
    archives = [_archive(now - timedelta(days=d)) for d in range(365)]

    keep, drop = backup.plan_prune(archives, now)

    ages = sorted(int((now - a.at).total_seconds() // 86400) for a in keep)
    assert ages == [0, 2, 6, 13, 29, 89]
    assert [a.reasons[-1] for a in keep] == [
        "a day", "3 days", "a week", "2 weeks", "a month", "3 months",
    ]
    assert keep[0].reasons[0] == "newest"
    # Bounded whatever the history: six rungs, and the newest fills the first.
    assert len(keep) == 6
    assert len(drop) == len(archives) - len(keep)


def test_every_rung_is_still_fed_after_a_year_of_pruning_every_day():
    """The gap between two rungs must not eat the archive that has to cross it.

    A daily backup, rotated daily — the real duty cycle. Keeping the *newest*
    archive in each interval passes on day one and starves here: nothing ever
    survives long enough to reach the deep rungs.
    """
    start = datetime(2026, 1, 1, 12, 0)
    archives: list[backup.Archive] = []
    for day in range(400):
        now = start + timedelta(days=day)
        archives.append(_archive(now))
        archives, _ = backup.plan_prune(archives, now)

    now = start + timedelta(days=399)
    ages = sorted(int((now - a.at).total_seconds() // 86400) for a in archives)
    assert len(ages) == 6
    assert ages[0] == 0
    for low, high in ((1, 3), (3, 7), (7, 14), (14, 30), (30, 90)):
        assert any(low <= a < high for a in ages), f"nothing left in [{low}, {high})"


def test_nothing_survives_past_the_horizon():
    now = datetime(2026, 9, 7, 12, 0)
    archives = [_archive(now - timedelta(days=d)) for d in range(365)]
    keep, _ = backup.plan_prune(archives, now, {"horizon_days": 14})
    ages = [int((now - a.at).total_seconds() // 86400) for a in keep]
    assert max(ages) < 14 and len(keep) == 4


def test_every_survivor_says_why_it_is_being_kept():
    now = datetime(2026, 9, 7, 12, 0)
    keep, _ = backup.plan_prune(
        [_archive(now - timedelta(days=d)) for d in range(120)], now
    )
    assert all(a.reasons for a in keep)
    assert keep[0].reasons == ["newest", "a day"]
    assert any("3 months" in a.reasons for a in keep)


def test_a_pin_overrules_the_ladder_on_an_automatic_archive_too():
    """The page offers Pin on every row; it has to mean something on each."""
    now = datetime(2026, 9, 7, 12, 0)
    doomed = _archive(now - timedelta(days=200))
    keep, drop = backup.plan_prune([_archive(now), doomed], now)
    assert doomed in drop

    doomed.pinned = True
    keep, drop = backup.plan_prune([_archive(now), doomed], now)
    assert doomed in keep and doomed.reasons == ["pinned"] and drop == []


def test_manual_backups_are_kept_by_count_and_a_pinned_one_forever():
    now = datetime(2026, 9, 7, 12, 0)
    old = _archive(now - timedelta(days=400), kind="manual", pinned=True)
    manuals = [_archive(now - timedelta(hours=h), kind="manual") for h in range(1, 20)]

    keep, drop = backup.plan_prune([old, *manuals], now, {"manual": 3})

    assert old in keep and "pinned" in old.reasons
    assert sum(1 for a in keep if a.kind == "manual" and not a.pinned) == 3
    assert len(drop) == 16


def test_an_archive_stamped_in_the_future_is_kept_not_reasoned_about():
    now = datetime(2026, 9, 7, 12, 0)
    ahead = _archive(now + timedelta(days=2))
    keep, drop = backup.plan_prune([ahead, _archive(now)], now)
    assert ahead in keep and drop == []


# ---------------------------------------------------------------------------
# Making one
# ---------------------------------------------------------------------------


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "00-agents"
    (data / "projects" / "ALPHA").mkdir(parents=True)
    (data / "tasks.csv").write_text("id,title\ntk_1,Ship it\n", encoding="utf-8")
    (data / "tasks.csv.lock").write_text("", encoding="utf-8")
    (data / "projects" / "ALPHA" / "log.md").write_text("рекогниция\n", encoding="utf-8")
    (data / "empty_dir").mkdir()
    (data / "tour_shots").mkdir()
    (data / "tour_shots" / "overview.png").write_bytes(b"\x89PNG" + b"0" * 900)
    return data, backup.backup_root_for(data)


def test_the_archive_is_a_plain_tarball_under_one_top_directory(roots):
    data, dest = roots
    archive = backup.create(data, dest, kind="manual", label="before the risky bit")

    assert dest == data.parent / "00-agents-backups"
    assert archive.path is not None and archive.path.exists()
    with tarfile.open(archive.path, "r:gz") as tar:
        names = tar.getnames()
    assert {n.split("/")[0] for n in names} == {"00-agents"}
    assert "00-agents/tasks.csv" in names
    assert "00-agents/projects/ALPHA/log.md" in names
    assert "00-agents/empty_dir" in names
    assert not any(n.endswith(".lock") for n in names), "lock files are not data"
    # Regenerable page photographs, two thirds of the archive by size.
    assert not any("tour_shots" in n for n in names)
    assert archive.label == "before the risky bit"
    assert archive.sha256 and archive.files == 2


def test_an_interrupted_archive_never_appears_in_the_listing(roots, monkeypatch):
    data, dest = roots
    backup.create(data, dest, kind="manual")

    boom = dest / (backup.archive_name(datetime(2026, 1, 1, 0, 0, 0), "auto")
                   + backup.ARCHIVE_SUFFIX + backup.PART_SUFFIX)
    boom.write_bytes(b"half an archive")

    assert [a.name for a in backup.list_archives(dest)] == [
        a.name for a in backup.list_archives(dest) if not a.name.startswith("2601")
    ]
    assert len(backup.list_archives(dest)) == 1


def test_a_listing_survives_losing_the_sidecar(roots):
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")
    (dest / (archive.name + backup.SIDECAR_SUFFIX)).unlink()

    listed = backup.list_archives(dest)
    assert len(listed) == 1
    assert listed[0].name == archive.name and listed[0].bytes > 0
    assert listed[0].sha256 == "", "the checksum is what a lost sidecar costs"


def test_a_backup_root_inside_the_data_root_is_refused(tmp_path):
    data = tmp_path / "00-agents"
    (data / "projects").mkdir(parents=True)
    with pytest.raises(backup.BackupError, match="inside the data root"):
        backup.create(data, data / "backups", kind="manual")


# ---------------------------------------------------------------------------
# Proving one is good, and using it
# ---------------------------------------------------------------------------


def test_verify_catches_a_corrupted_archive(roots):
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")
    assert backup.verify(dest, archive.name)["ok"] is True

    assert archive.path is not None
    archive.path.write_bytes(archive.path.read_bytes()[:-40] + b"\x00" * 40)
    report = backup.verify(dest, archive.name)
    assert report["ok"] is False
    assert any("checksum" in p for p in report["problems"])


def test_restore_puts_the_data_root_back_exactly(roots):
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")

    (data / "tasks.csv").write_text("id,title\ntk_1,RUINED\n", encoding="utf-8")
    (data / "projects" / "ALPHA" / "log.md").unlink()
    (data / "garbage.csv").write_text("x\n", encoding="utf-8")

    report = backup.restore(dest, archive.name, data)

    assert (data / "tasks.csv").read_text(encoding="utf-8").endswith("Ship it\n")
    assert (data / "projects" / "ALPHA" / "log.md").read_text(
        encoding="utf-8") == "рекогниция\n"
    assert not (data / "garbage.csv").exists(), "restore replaces, it does not merge"
    assert report["files"] == 2


def test_restore_is_refused_before_it_touches_anything(roots):
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")
    assert archive.path is not None
    archive.path.write_bytes(b"not a tarball at all")

    with pytest.raises(backup.BackupError):
        backup.restore(dest, archive.name, data)
    assert (data / "tasks.csv").exists(), "the live data was not touched"


def test_restore_keeps_the_data_root_directory_itself(roots):
    """The running server watches this inode; swapping it out orphans the watch."""
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")
    before = data.stat().st_ino
    backup.restore(dest, archive.name, data)
    assert data.stat().st_ino == before


def test_restore_leaves_what_no_archive_holds_in_place(roots):
    """The tour's photographs, the machine's monitor and terminals and the
    lock files are not in the archive, nor in the safety archive a restore
    takes first: moved aside with the rest, they would be deleted for good."""
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")
    (data / "monitor").mkdir()
    (data / "monitor" / "monitor.sqlite").write_bytes(b"samples")
    (data / "terminal").mkdir()
    (data / "terminal" / "open.json").write_text("{}", encoding="utf-8")

    backup.restore(dest, archive.name, data)

    assert (data / "tour_shots" / "overview.png").read_bytes().startswith(b"\x89PNG")
    assert (data / "monitor" / "monitor.sqlite").read_bytes() == b"samples"
    assert (data / "terminal" / "open.json").exists()
    assert (data / "tasks.csv.lock").exists()
    assert (data / "tasks.csv").read_text(encoding="utf-8").endswith("Ship it\n")


def test_a_file_rewritten_while_it_is_archived_leaves_a_whole_archive(roots, monkeypatch):
    """An atomic write that lands between the header and the copy used to
    end the copy early, leave half a member in the stream and make every
    member after it unreadable."""
    data, dest = roots
    (data / "zz_after.csv").write_text("id\nlast\n", encoding="utf-8")
    target = data / "tasks.csv"
    real = tarfile.TarFile.gettarinfo

    def rewrite_after_stat(self, name=None, arcname=None, fileobj=None):
        info = real(self, name, arcname, fileobj)
        if (arcname or "").endswith("/tasks.csv"):
            tmp = target.with_name("tasks.csv.tmp~")
            tmp.write_text("id\n", encoding="utf-8")     # shorter, then swapped in
            tmp.replace(target)
        return info

    monkeypatch.setattr(tarfile.TarFile, "gettarinfo", rewrite_after_stat)
    archive = backup.create(data, dest, kind="manual")
    monkeypatch.undo()

    assert backup.verify(dest, archive.name)["ok"] is True
    assert archive.path is not None
    with tarfile.open(archive.path, "r:gz") as tar:
        tasks = tar.extractfile("00-agents/tasks.csv")
        after = tar.extractfile("00-agents/zz_after.csv")
        assert tasks is not None and after is not None
        assert tasks.read().decode() == "id,title\ntk_1,Ship it\n", "the file as it was opened"
        assert after.read().decode() == "id\nlast\n"


def test_a_truncated_archive_is_refused_and_the_data_is_untouched(roots):
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")
    assert archive.path is not None
    raw = archive.path.read_bytes()
    archive.path.write_bytes(raw[: len(raw) // 2])
    (dest / (archive.name + backup.SIDECAR_SUFFIX)).unlink()   # no checksum to catch it

    with pytest.raises(backup.BackupError, match="will not read"):
        backup.restore(dest, archive.name, data)
    assert (data / "tasks.csv").read_text(encoding="utf-8").endswith("Ship it\n")
    assert not [p for p in dest.iterdir() if p.name.startswith("sp-")], "no staging left behind"


def test_the_command_line_prunes_with_the_operators_budget(roots):
    """scripts/backup.py is the cron path; pruning with the defaults there
    deleted the manual archives Settings said to keep."""
    import importlib.util

    from backend import app_settings

    data, dest = roots
    app_settings.save(data, {"backup.keep_manual": 12})
    start = datetime(2026, 3, 1, 9, 0, 0)
    for i in range(12):
        backup.create(data, dest, kind="manual", now=start + timedelta(minutes=i))

    script = Path(__file__).resolve().parents[2] / "scripts" / "backup.py"
    spec = importlib.util.spec_from_file_location("sp_backup_cli", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--root", str(data), "--dest", str(dest), "prune"]) == 0

    assert len(backup.list_archives(dest)) == 12


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------


def test_two_backups_in_the_same_second_are_two_backups(roots):
    """A restore archives the state it is about to destroy, then reads the
    archive it is restoring — both inside one call, often one clock second."""
    data, dest = roots
    first = backup.create(data, dest, kind="manual", label="one")
    second = backup.create(data, dest, kind="manual", label="two")
    assert first.name != second.name
    assert {a.label for a in backup.list_archives(dest)} == {"one", "two"}


def test_the_schedule_needs_both_the_clock_and_a_change():
    now = datetime(2026, 9, 7, 12, 0)
    assert backup.due([], now, 6, 100.0)[0] is True

    last = _archive(now - timedelta(hours=2))
    last.source_mtime = 100.0
    assert backup.due([last], now, 6, 200.0) == (False, "next in 240 min")

    stale = _archive(now - timedelta(hours=7))
    stale.source_mtime = 100.0
    assert backup.due([stale], now, 6, 100.0)[0] is False, "nothing changed"
    assert backup.due([stale], now, 6, 200.0)[0] is True
    assert backup.due([stale], now, 0, 200.0)[0] is False, "interval 0 is off"


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------


def test_the_state_endpoint_describes_the_ladder_and_the_source(client):
    body = client.get("/api/backup").json()
    assert body["archives"] == [] and body["count"] == 0
    assert body["due"] is True and "no automatic backup yet" in body["due_reason"]
    assert body["source"]["files"] > 0
    assert [r["days"] for r in body["rungs"]] == [1, 3, 7, 14, 30, 90]
    assert body["keep"]["manual"] == 10
    assert body["excluded"] == ["*.lock", "operator.token", "tour_shots/", "monitor/", "terminal/"]
    assert body["backup_root"].endswith("-backups")


def test_run_verify_pin_and_delete_over_the_api(client):
    made = client.post("/api/backup/run", json={"label": "by hand"}).json()
    name = made["archive"]["name"]
    assert made["archive"]["kind"] == "manual"
    assert made["state"]["count"] == 1

    report = client.post(f"/api/backup/{name}/verify").json()
    assert report["ok"] is True and report["files"] > 0

    pinned = client.post(f"/api/backup/{name}/pin", json={"pinned": True}).json()
    assert pinned["archive"]["pinned"] is True
    assert "pinned" in pinned["state"]["archives"][0]["reasons"]

    blob = client.get(f"/api/backup/{name}/download")
    assert blob.status_code == 200
    assert blob.headers["content-type"] == "application/gzip"
    assert len(blob.content) > 0

    assert client.post(f"/api/backup/{name}/delete").json()["state"]["count"] == 0


def test_an_archive_the_ladder_will_drop_is_still_listed(client, data_root):
    """Otherwise the one archive worth pinning is the one you cannot see.

    Taken through the engine rather than the endpoint: ``/run`` prunes as it
    goes, so a doomed archive only exists between a backup and a rotation —
    after a settings change, a hand-copied file, or a run from the CLI.
    """
    dest = backup.backup_root_for(data_root)
    now = datetime.now()
    made = [
        backup.create(data_root, dest, kind="auto",
                      now=now - timedelta(hours=h)).name
        for h in (3, 2, 1)
    ]

    body = client.get("/api/backup").json()
    listed = {a["name"]: a for a in body["archives"]}
    assert set(made) == set(listed), "every archive on disk is listed"

    # All three inside the first rung: the newest is held for being newest,
    # the oldest for being the one about to cross into "3 days", and the
    # middle one has no job.
    assert body["expiring"] == [made[1]]
    assert listed[made[1]]["expiring"] is True
    assert listed[made[0]]["reasons"] == ["a day"]
    assert listed[made[2]]["reasons"] == ["newest"]

    after = client.post(f"/api/backup/{made[1]}/pin", json={"pinned": True}).json()
    assert after["state"]["expiring"] == []


def test_restore_over_the_api_demands_the_name_and_leaves_a_way_back(client, data_root):
    name = client.post("/api/backup/run", json={"label": "good state"}).json()["archive"]["name"]

    refused = client.post(f"/api/backup/{name}/restore", json={})
    assert refused.status_code == 422
    assert "confirm" in refused.json()["detail"]

    (data_root / "tasks.csv").write_text("id,title\n", encoding="utf-8")
    ok = client.post(f"/api/backup/{name}/restore", json={"confirm": name}).json()

    assert "tk_alpha_auth" in (data_root / "tasks.csv").read_text(encoding="utf-8")
    assert ok["safety"]["label"] == f"before restoring {name}"
    assert client.get("/api/tasks").json(), "the views were rebuilt after the restore"


def test_a_refused_restore_leaves_no_safety_archive_behind(client, data_root):
    """Manual archives are kept by count: a "before restoring" archive per
    failed try would push the operator's own bookmarks out."""
    name = client.post("/api/backup/run", json={"label": "good state"}).json()["archive"]["name"]
    path = backup.backup_root_for(data_root) / (name + backup.ARCHIVE_SUFFIX)
    path.write_bytes(path.read_bytes()[:-200])
    before = (data_root / "tasks.csv").read_bytes()

    for _ in range(3):
        refused = client.post(f"/api/backup/{name}/restore", json={"confirm": name})
        assert refused.status_code == 409
        assert "checksum" in refused.json()["detail"]

    assert [a["name"] for a in client.get("/api/backup").json()["archives"]] == [name]
    assert (data_root / "tasks.csv").read_bytes() == before


def test_reveal_opens_the_backup_folder_on_every_platform(client, monkeypatch):
    """Three platforms, three commands — and the path is never the caller's."""
    name = client.post("/api/backup/run").json()["archive"]["name"]
    seen: list[list[str]] = []
    monkeypatch.setattr(backup.subprocess, "Popen",
                        lambda argv, **kw: seen.append(argv))
    # macOS and Windows can select the archive; Linux has no portable way to,
    # so it opens the folder holding it. All three open something.
    for platform, wants, selects in (
        ("darwin", ["open", "-R"], True),
        ("win32", ["explorer"], True),
        ("linux", ["xdg-open"], False),
    ):
        monkeypatch.setattr(backup.sys, "platform", platform)
        monkeypatch.setattr(backup.shutil, "which", lambda _: "/usr/bin/xdg-open")
        body = client.post("/api/backup/reveal", json={"name": name}).json()
        assert body["opened"] is True
        assert seen[-1][:len(wants)] == wants
        argv = " ".join(seen[-1])
        assert (name in argv) is selects
        assert "00-agents-backups" in argv, "always inside the backup folder"


def test_reveal_hands_back_the_path_when_nothing_can_open_it(client, monkeypatch):
    client.post("/api/backup/run")
    monkeypatch.setattr(backup.sys, "platform", "linux")
    monkeypatch.setattr(backup.shutil, "which", lambda _: None)

    body = client.post("/api/backup/reveal", json={}).json()
    assert body["opened"] is False
    assert body["path"].endswith("-backups"), "the path, to copy"


def test_reveal_refuses_a_name_that_is_not_an_archive(client):
    client.post("/api/backup/run")
    assert client.post("/api/backup/reveal", json={"name": "../../etc"}).status_code == 404


@pytest.mark.parametrize("name", ["nonsense", "2609-07-1518__auto",
                                  "2609-07-151833__auto"])
def test_a_name_that_is_not_an_archive_is_a_404(client, name):
    """Two ways to miss: not a backup name at all, and a name with no file."""
    for verb in ("verify", "pin", "delete"):
        assert client.post(f"/api/backup/{name}/{verb}").status_code == 404
    assert client.get(f"/api/backup/{name}/download").status_code == 404
