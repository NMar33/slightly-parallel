#!/usr/bin/env python3
"""Build the example project into a data root: a month of work on shopfront.

    backend/.venv/bin/python scripts/demo/build_example.py --root <data root> [--end YYYY-MM-DD]

The example project shows a new user how every part of Slightly Parallel
works, on a project that looks like theirs will: chats where the operator
types #scan, #decision or #task and the agent writes the entry, a board with
tasks in every column, sprints, standups, the architecture page and the map.

The month is played (engine.py) with the clock ending on ``--end``, yesterday
by default, so the newest activity is a day old. It is played in a folder of
its own, archived there with the server's own delete, and restored into the
data root (project_admin.restore_project_archive): the data root gets the
project's rows and files and nothing else — no preferences, boards or other
global state. The repository lives at ``<data root>/example/shopfront``.

The server runs this when a data root is made and when the operator turns
the example project back on (backend/example.py). Never on a data root that
already holds a project called shopfront.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import engine  # noqa: E402

CODE = "shopfront"
REPO_DIR = "example"


def play(target: Path, repos_dir: Path, end: date) -> engine.Sim:
    # Day 30 of the played month is ``end``. Set before the content modules
    # are imported: some compute their moments at import.
    engine.set_start(end - timedelta(days=29))
    from engine import D, Sim
    from world import World
    from shopfront_month import create_shopfront_repo, schedule_links, schedule_shopfront

    sim = Sim(target, repos_dir=repos_dir)
    w = World(sim)
    sim.at(D(1, 7, 31), sim.adopt)

    repo = create_shopfront_repo(sim, CODE)
    # Registered in the played folder too: a file entry's lines and a scan's
    # counts are read from the repository the registry names.
    register(sim.root, repo.path, end - timedelta(days=29))

    K = schedule_shopfront(sim, w, repo)
    schedule_links(sim, K)

    sim.run()

    for rel in repo.git("ls-files").splitlines():
        ts = repo.git("log", "-1", "--format=%ct", "--", rel).strip()
        if ts:
            os.utime(repo.path / rel, (int(ts), int(ts)))
    engine.CLOCK.now = D(30, 10, 25)
    sim.adopt()
    sim.store.rebuild()
    return sim


def only_this_project(root: Path) -> None:
    """A sprint shared with another project of the demo world belongs to
    this one alone here: the delete below would otherwise leave it behind."""
    from backend.csvio import rewrite_rows
    from backend.entities import ENTITIES
    sprint = ENTITIES["sprint"]

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            members = [p.strip() for p in str(r.get("projects") or "").split(",") if p.strip()]
            if CODE in members:
                r["projects"] = CODE
        return True

    if (root / sprint.csv).exists():
        rewrite_rows(root / sprint.csv, sprint.columns, mutate)


def relocate(src: Path, dst: Path) -> None:
    """A path the server wrote into the played folder (an artifact's folder)
    names the data root the example is restored into, not the temporary one."""
    old, new = str(src), str(dst)
    for path in sorted(src.rglob("*")):
        if path.is_file() and path.suffix in (".csv", ".md", ".json", ".jsonl"):
            text = path.read_text(encoding="utf-8", errors="surrogateescape")
            if old in text:
                path.write_text(text.replace(old, new), encoding="utf-8", errors="surrogateescape")


def build(root: Path, end: date) -> dict:
    root = root.resolve()
    if (root / "projects" / CODE).exists():
        raise SystemExit(f"{root} already has a project called {CODE}: the example is not built over it")
    repos_dir = root / REPO_DIR
    if (repos_dir / CODE).exists():
        shutil.rmtree(repos_dir / CODE)  # a repository left by an example that was hidden
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="sp-example-") as tmp:
        sim = play(Path(tmp), repos_dir, end)
        from backend import project_admin
        from backend.db import ViewStore
        only_this_project(sim.root)
        relocate(sim.root, root)
        sim.store.rebuild()
        archived = project_admin.delete_project_data(sim.store, CODE)
        sim.client.close()
        target = ViewStore(data_root=root)
        restored = project_admin.restore_project_archive(target, Path(archived["trash"]))
        carry_scan_marks(sim.root, root, Path(archived["trash"]))
    register(root, repos_dir / CODE, end - timedelta(days=29))
    quiet_timer(root)
    return {"project": CODE, "repo": str(repos_dir / CODE), "seconds": round(time.time() - t0),
            "rows": restored["rows"], "files": restored["files"]}


def carry_scan_marks(src: Path, dst: Path, archive: Path) -> None:
    """What the working tree held at each scan (scanlib.mark): the next scan
    of the example counts its commits from the last one."""
    from backend.csvio import read_rows
    from backend.file_safety import edit_json, safe_read_json
    from backend.scanlib import MARKS_FILE
    ids = {r.get("id") for r in read_rows(archive / "scans.csv")}
    marks = {k: v for k, v in (safe_read_json(src / MARKS_FILE) or {}).items() if k in ids}
    if marks:
        edit_json(dst / MARKS_FILE, lambda data: {**data, **marks})


def quiet_timer(root: Path) -> None:
    """The example's timer is manual: browsing it counts no time, and its
    task windows do not ask whether to track time (timeauto.set_mode)."""
    from backend.file_safety import atomic_write
    path = root / "timer" / "modes.json"
    try:
        modes = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        modes = {}
    if CODE not in modes:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, json.dumps({**modes, CODE: "manual"}, indent=1, sort_keys=True))


def register(root: Path, repo: Path, started: date) -> None:
    """Setup's registry row: the project points at its repository."""
    from backend.csvio import append_row, read_rows
    path = root / "integrations.csv"
    if any(r.get("project") == CODE for r in read_rows(path)):
        return
    append_row(path, ("project", "path", "created_date"),
               {"project": CODE, "path": str(repo.resolve()), "created_date": engine.yymmdd(
                   engine._RealDT(started.year, started.month, started.day))})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True, help="the data root to add the example project to")
    ap.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1),
                    help="the last day of the played month (default: yesterday)")
    args = ap.parse_args()
    print(json.dumps(build(args.root, args.end)))


if __name__ == "__main__":
    main()
