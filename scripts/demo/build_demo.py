#!/usr/bin/env python3
"""Build Slightly Parallel's demo dataset: a month of work on three projects.

    backend/.venv/bin/python scripts/demo/build_demo.py <target_dir> [--force]

Creates ``<target>/data`` (a complete Slightly Parallel data root) and
``<target>/repos/<project>`` (git repositories whose commits are dated
across September 2026). The month is *played*, not written as rows: at each
simulated moment the operator types, an agent answers and commits, a card
moves, a scan is written — through the capture core and the server's own
API (in-process), with the clock faked. The result is deterministic apart
from git object ids' dependence on the absolute repo path.

Serve it (never on the operator's own port):

    SP_SANDBOX=1 SP_DATA_ROOT=<target>/data SHELL=/bin/sh \\
      backend/.venv/bin/python -m uvicorn backend.server:app --app-dir backend --port 8126

See scripts/demo/README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from engine import CLOCK, D, Repo, Sim  # noqa: E402
from world import World  # noqa: E402

PROJECTS = ("shopfront", "tg-notify", "price-etl")


def build(target: Path) -> Sim:
    import shopfront_chats_a
    import shopfront_chats_b
    import shopfront_chats_c
    import shopfront_lenses
    import shopfront_standups
    import shopfront_story
    import shopfront_tasks
    import small_projects
    from shopfront_repo import SKELETON

    t0 = time.time()
    sim = Sim(target)
    w = World(sim)

    # The first read of the month: #done and friends count from here on.
    sim.at(D(1, 7, 31), sim.adopt)

    repo = Repo(sim.repos_dir / "shopfront", email="operator@shopfront.dev")
    for rel, text in SKELETON.items():
        repo.write(rel, text)
    repo.commit("Initial skeleton: Next.js app, FastAPI service, compose", D(1, 8, 20))
    sim.repos["shopfront"] = repo

    small_projects.setup(sim, w)

    # Setup's registry: each project points at its repository.
    started = {"shopfront": "2609-01", "tg-notify": "2609-14", "price-etl": "2609-08"}
    rows = ["project,path,created_date"] + [
        f"{code},{sim.repos[code].path.resolve()},{started[code]}" for code in PROJECTS]
    (sim.root / "integrations.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    K: dict = {}
    shopfront_tasks.setup(sim, w)
    shopfront_chats_a.setup(sim, w, repo, K)
    shopfront_chats_b.setup(sim, w, repo, K)
    shopfront_chats_c.setup(sim, w, repo, K)
    shopfront_lenses.setup(sim, w, repo, K)
    shopfront_standups.setup(sim, w, K)
    shopfront_story.setup(sim, w, repo, K)
    small_projects.link_cross(sim, w)
    extras(sim, w, K)

    sim.run()
    finish(sim)
    print(f"played the month in {time.time() - t0:.0f} s")
    return sim


def extras(sim: Sim, w: World, K: dict) -> None:
    """The operator's own arrangements: a saved board, the board's view."""
    def board() -> None:
        sim.post("/api/boards", {"name": "Storefront + notifications", "projects": ["shopfront", "tg-notify"],
                                 "actor": "operator"})
    sim.at(D(24, 9, 5), board)

    def prefs() -> None:
        guides = ["kanban", "calendar", "decisions", "scans", "standups", "prompts", "files", "chats",
                  "artifacts", "architecture", "agents", "sprints", "skills", "visions", "rules", "problems"]
        values = {f"sp-guide-{g}-hidden": "yes" for g in guides}
        values.update({"sp-kanban-desc": "1", "sp-kanban-view": "workflow"})
        sim.post("/api/prefs", {"values": values})
    sim.at(D(30, 10, 20), prefs)

    # Why one chat sits next to another on the timeline.
    for when, a, b, kind, note in [
        (D(16, 11, 40), "c9", "c10", "handoff", "the signature fix handed over from the webhook chat"),
        (D(22, 14, 45), "c12", "c13", "same-work", "Stripe Tax went live with the first payment"),
        (D(30, 9, 12), "c14", "c20", "branch", "partial refunds continue the refunds chat"),
        (D(28, 14, 35), "c15", "c18", "relates", "outbound events reuse the webhook queue"),
    ]:
        def link(a=a, b=b, kind=kind, note=note) -> None:
            sim.post("/api/agents/links", {"from": K[a].agent_id, "to": K[b].agent_id, "kind": kind,
                                           "note": note, "actor": "operator"})
        sim.at(when, link)


def finish(sim: Sim) -> None:
    """After the month: files in the repositories carry the date of the last
    commit that touched them (the architecture page compares file times with
    its own), and the server's derived ledgers are brought up to date."""
    for repo in sim.repos.values():
        files = repo.git("ls-files").splitlines()
        for rel in files:
            ts = repo.git("log", "-1", "--format=%ct", "--", rel).strip()
            if ts:
                os.utime(repo.path / rel, (int(ts), int(ts)))
    CLOCK.now = D(30, 10, 25)
    sim.adopt()
    # The server seeds example visions, rules and problems into a root that
    # never had them; the operator of this demo removed them long ago.
    from backend import examples
    examples.seed(sim.store)
    examples.remove(sim.store)
    sim.store.rebuild()


def report(sim: Sim) -> None:
    g = sim.get
    out = {}
    for p in PROJECTS:
        tasks = g(f"/api/tasks?project={p}&limit=5000")["tasks"]
        out[p] = {
            "tasks": len([t for t in tasks if t["project"] == p]),
            "scans": len(g(f"/api/scans?project={p}").get("scans", [])),
            "standups": g(f"/api/standups?project={p}")["total"],
            "decisions": g(f"/api/decisions?project={p}")["total"],
            "chats": len([a for a in sim.store.agents() if a.get("project") == p]),
            "commits": int(sim.repos[p].git("rev-list", "--count", "HEAD").strip()),
        }
    out["all"] = {
        "visions": g("/api/visions")["total"], "rules": g("/api/rules")["total"],
        "problems": g("/api/problems")["total"], "skills": g("/api/skills")["total"],
        "artifacts": g("/api/artifacts")["total"], "prompts": len(g("/api/prompt-library").get("prompts", [])),
        "time_entries": g("/api/time-entries")["total"], "sprints": g("/api/sprints")["total"],
    }
    print(json.dumps(out, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", type=Path, help="folder to create data/ and repos/ in")
    ap.add_argument("--force", action="store_true", help="empty the target first")
    args = ap.parse_args()
    target = args.target.resolve()
    if target.exists() and any(target.iterdir()):
        if not args.force:
            raise SystemExit(f"{target} is not empty — pass --force to rebuild it")
        for child in target.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    target.mkdir(parents=True, exist_ok=True)
    sim = build(target)
    report(sim)
    sim.client.close()
    print(f"demo ready: {target}/data  (repos in {target}/repos)")


if __name__ == "__main__":
    main()
