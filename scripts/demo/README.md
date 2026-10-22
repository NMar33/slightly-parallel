# Demo dataset and the example project

A month of work on invented projects, played on a fake clock through the
product's own code, so every page of Slightly Parallel has something
real-looking to show.

## The example project

`build_example.py --root <data root>` plays one project, shopfront, with the
dates ending yesterday (`--end` names another day), and adds it to the data
root as an ordinary project with its repository at `<root>/example/shopfront`.
The server runs it on a new data folder and from Settings › Example project
(`backend/backend/example.py`); every tour walks and photographs it. The
content writes its dates as tokens (`{dm:22}`, `{iso:22}`, …) that are
filled in when it is played (`engine.dated`).

## The demo dataset

September 2026, three projects. It is what the screenshots for the article
are taken against. Nothing here touches your own data root.

## Run it

```bash
backend/.venv/bin/python scripts/demo/build_demo.py ~/sp-demo          # new folder
backend/.venv/bin/python scripts/demo/build_demo.py ~/sp-demo --force  # rebuild
```

It needs the backend's virtualenv: the script imports the server in-process.
It takes about a minute and prints what it made. The output:

- `<target>/data/` — a complete Slightly Parallel data root.
- `<target>/repos/{shopfront,tg-notify,price-etl}/` — git repositories. Every
  commit is dated in September 2026.

The data holds absolute paths to the repositories: in `integrations.csv`, in
each chat's `cwd` and on artifact records. So do not move the folder; rebuild
it where you want it. Pick a short path, because the agent pages print the
`cd` line. Two builds into the same folder are byte-identical, git hashes
included.

Serve it beside your real Slightly Parallel, never on its port:

```bash
export SHELL=/bin/sh SP_SANDBOX=1 SP_DATA_ROOT=~/sp-demo/data \
       SP_CORS_ORIGINS=http://127.0.0.1:5176
backend/.venv/bin/python -m uvicorn backend.server:app --app-dir backend --port 8126
cd frontend && SP_API=http://127.0.0.1:8126 npx vite --port 5176 --strictPort
```

The history ends on 30 September 2026 at 10:25. Pages that count days back
from today look right on that date and drift after it.

## How it is made

The month is played in time order, not written as rows. `engine.py` fakes the
clock: while the build runs, every `datetime.now()`, `date.today()` and
`time.time()` in the backend returns the simulated moment. At each moment one
of these happens:

- the operator types a message and an agent answers, through the capture core
  (`scripts/hooks/capture.py`). This writes `chat.md`, `meta.json`,
  `turns.jsonl` (active, helper and busy times) and `work.jsonl` (git stamps);
- an agent commits to a repository, with author and committer dates set to
  that moment;
- a write goes through the server's own API, in-process: a task is created or
  moved, a decision, scan, file entry, architecture form, page or map is
  written, a standup, evidence, a story note or a timer.

Derived records come from the product's own code: task events, `#done`
stretches, kept visions/rules/problems, the prompt library, marks. Agent
writes carry the MCP header, the way the MCP server sends them.

| file | what it holds |
|---|---|
| `build_demo.py` | entry point: order of setup, the saved board, preferences, final touches |
| `engine.py` | the clock, the event queue, git repos, chats through the capture core |
| `world.py` | one helper per kind of write (task, move, scan, standup …) |
| `codegen.py`, `common.py` | plausible code for commits |
| `shopfront_*.py` | the main project: repo skeleton, tasks, 20 chats, lenses, standups, architecture page and map |
| `small_projects.py` | tg-notify and price-etl |

## What it contains

- **shopfront** — a small EU store: Next.js, FastAPI, Postgres, Stripe.
  - 75 tasks in every column. Lanes by task type (ui, checkout, api, infra,
    content), plus four cards agents wrote themselves.
  - Priorities, impact/effort, due dates, today marks, two resurfacing cards,
    three stacks, 13 links, evidence (text and screenshots), story notes, and
    second rounds on four tasks.
  - 20 chats (Claude Code, Codex, OpenCode) with 84 commits between them.
  - 7 scans, each with a file entry and an architecture form. Architecture
    page v1–v3, program map v1–v2.
  - 14 decisions, 21 standups, 21 timer entries and 5 automatic ones, and 10
    calendar entries.
  - Milestones: one reached, two active, one planned.
- **tg-notify** (a Telegram notification bot) and **price-etl** (a supplier
  price pipeline): 15 tasks, 4 chats, 2 scans, 7 standups and 2–3 decisions
  each. Each has an architecture page; tg-notify also has a map.
- Across projects:
  - 4 sprints: two ended with retros, two running, one shared by shopfront
    and tg-notify.
  - A saved board "Storefront + notifications".
  - 7 visions, 8 rules (2 for all agents) and 5 problems (2 resolved), each
    with its interpretation.
  - 2 drafted skills beside the built-in ones, 4 prompts sent 7 times, and 2
    artifacts.
  - `#important` marks, and agent links on the timeline.
- Page guides are dismissed, and the kanban opens in the 5-column view.

The human is `operator`. Agent ids follow the capture hook (`cc-`, `codex-`,
`oc-` plus eight hex digits). No real names.
