#!/usr/bin/env python3
"""sp-backup — the data root, tarred and rotated, from the command line.

The dashboard has a Backups page that does all of this. This exists because
the day you need a backup is disproportionately likely to be the day the
dashboard will not start: a corrupt CSV, a bad deploy, a half-finished
migration. Nothing here imports FastAPI, touches the port, or needs the
server to be running.

    ./scripts/backup.py list                  what is on disk, and why
    ./scripts/backup.py run [--label "…"]     take one now (manual)
    ./scripts/backup.py run --auto            take one as the scheduler would
    ./scripts/backup.py verify <name>         re-hash it and read its contents
    ./scripts/backup.py restore <name>        put it back over the data root
    ./scripts/backup.py prune                 apply the ladder, delete the rest

Roots resolve the same way the server resolves them:

    --root / SP_DATA_ROOT / SCAN_DATA_ROOT      the data root
    --dest / SP_BACKUP_ROOT              where archives go
                                              (default: <root>-backups)

It is also the thing to put in cron if you would rather not rely on the
server being up:

    0 */6 * * *  cd /path/to/slightly-parallel && ./scripts/backup.py run --auto --quiet

Exit codes: 0 fine · 1 the operation failed · 2 could not run at all.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

try:
    from backend import backup
except ImportError as exc:  # pragma: no cover — a broken checkout
    print(f"cannot import the backup engine: {exc}", file=sys.stderr)
    raise SystemExit(2) from exc


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _env_file_root() -> str:
    """SP_DATA_ROOT from the repository's .env, as sp.py reads it — the
    script said "no data root" on every default install."""
    env = Path(__file__).resolve().parents[1] / ".env"
    try:
        lines = env.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    for raw in lines:
        line = raw.strip().removeprefix("export ").strip()
        key, _, value = line.partition("=")
        if key.strip() in ("SP_DATA_ROOT", "SCAN_DATA_ROOT") and value.strip():
            return value.strip().strip("'\"")
    return ""


def resolve_root(explicit: str | None) -> Path:
    raw = (explicit or os.environ.get("SP_DATA_ROOT") or os.environ.get("SCAN_DATA_ROOT")
           or os.environ.get("DATA_ROOT") or _env_file_root())
    if not raw and (Path.home() / ".slightly-parallel").is_dir():
        raw = str(Path.home() / ".slightly-parallel")   # where sp.py puts it when nothing names a folder
    if not raw:
        raise SystemExit(
            "no data root — pass --root or set SP_DATA_ROOT"
        )
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"data root does not exist: {root}")
    return root


def cmd_list(root: Path, dest: Path, args) -> int:
    archives = backup.list_archives(dest)
    keep, drop = backup.plan_prune(archives, datetime.now(), backup.keep_budget(root))
    print(f"data root   {root}")
    print(f"backups     {dest}")
    if not archives:
        print("\nno backups yet — ./scripts/backup.py run")
        return 0
    print(f"\n{len(archives)} archives · {human(sum(a.bytes for a in archives))}\n")
    for a in sorted(archives, key=lambda a: a.at, reverse=True):
        age = datetime.now() - a.at
        why = ", ".join(a.reasons) if a in keep else "expiring at the next prune"
        pin = " 📌" if a.pinned else ""
        print(f"  {a.name}{pin}  {human(a.bytes):>9}  "
              f"{int(age.total_seconds() // 3600):>4}h old   {why}")
        if a.label:
            print(f"      {a.label}")
    if drop:
        print(f"\n{len(drop)} would be removed by the next prune.")
    return 0


def cmd_run(root: Path, dest: Path, args) -> int:
    kind = "auto" if args.auto else "manual"
    if args.auto:
        _, _, mtime = backup.source_stats(root)
        ready, why = backup.due(
            backup.list_archives(dest), datetime.now(), args.every, mtime
        )
        if not ready:
            if not args.quiet:
                print(f"skipped — {why}")
            return 0
    archive = backup.create(root, dest, kind=kind, label=args.label or "")
    pruned = backup.prune(dest, datetime.now(), backup.keep_budget(root))
    if not args.quiet:
        print(f"{archive.name}  {human(archive.bytes)}  {archive.files} files")
        print(f"  {dest / (archive.name + backup.ARCHIVE_SUFFIX)}")
        if pruned:
            print(f"  pruned {len(pruned)}: {', '.join(pruned)}")
    return 0


def cmd_verify(root: Path, dest: Path, args) -> int:
    report = backup.verify(dest, args.name)
    if report["ok"]:
        print(f"{args.name} — ok, {report['files']} files, "
              f"sha256 {report['sha256'][:16]}…")
        return 0
    print(f"{args.name} — NOT OK", file=sys.stderr)
    for problem in report["problems"]:
        print(f"  · {problem}", file=sys.stderr)
    return 1


def cmd_restore(root: Path, dest: Path, args) -> int:
    archive = backup.find(dest, args.name)
    if archive is None:
        print(f"no such backup: {args.name}", file=sys.stderr)
        return 1
    print(f"This replaces everything in {root}")
    print(f"with {args.name} ({human(archive.bytes)}, taken {archive.at:%Y-%m-%d %H:%M}).")
    if not args.yes:
        # Typing the name, not "y": the list is a column of similar dates.
        if input("Type the backup name to confirm: ").strip() != args.name:
            print("nothing was changed.")
            return 1
    report, safety = backup.restore_with_safety(dest, args.name, root)
    print(f"current state archived as {safety.name}")
    print(f"restored — {report['files']} files, {human(report['bytes'])}")
    print("restart the server (or wait for the watcher) to rebuild the views.")
    return 0


def cmd_prune(root: Path, dest: Path, args) -> int:
    gone = backup.prune(dest, datetime.now(), backup.keep_budget(root))
    print(f"pruned {len(gone)}" + (": " + ", ".join(gone) if gone else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backup.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", help="data root (default: SP_DATA_ROOT)")
    parser.add_argument("--dest", help="backup root (default: <root>-backups)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="what is on disk, and why each one is kept")

    run = sub.add_parser("run", help="take a backup now")
    run.add_argument("--auto", action="store_true",
                     help="behave as the scheduler: skip unless due and changed")
    run.add_argument("--every", type=int, default=6,
                     help="hours between automatic backups (with --auto)")
    run.add_argument("--label", help="a note to remember why you took it")
    run.add_argument("--quiet", action="store_true", help="say nothing on success")

    ver = sub.add_parser("verify", help="re-hash an archive and read its contents")
    ver.add_argument("name")

    res = sub.add_parser("restore", help="put an archive back over the data root")
    res.add_argument("name")
    res.add_argument("--yes", action="store_true", help="skip the confirmation")

    sub.add_parser("prune", help="apply the ladder and delete the rest")

    args = parser.parse_args(argv)
    root = resolve_root(args.root)
    dest = (Path(args.dest).expanduser().resolve() if args.dest
            else backup.backup_root_for(root))

    handlers = {"list": cmd_list, "run": cmd_run, "verify": cmd_verify,
                "restore": cmd_restore, "prune": cmd_prune}
    try:
        backup.check_roots(root, dest)
        return handlers[args.cmd](root, dest, args)
    except backup.BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted — nothing was changed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
