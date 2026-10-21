# Performance

What was measured, how, and what came of it. One entry per question, newest
first. Each entry is short and holds what is needed to measure it again.

## Audit for memory and delays (2026-10-20)

**How.** The server over a copy of the data root (31 MB, 88 chats), every GET
route three times with `tracemalloc` on; the long-lived modules read by Codex
(server, monitor, git caches, search, analytics, watcher, db, timer).

**Found.** No growth from request to request: Python's own memory stayed at
106 MB from the second round to the third. Fixed: JSON-lines files read whole
(transcripts, work stamps, hook errors), caches the data root swap did not
clear (search, file owners), the request body copied at every chunk, the
monitor's database left open on stop, a watcher callback per quiet window
during a long rebuild, the whole git log read for the first commit's date.

**Open — they grow with the history, not with uptime; fine at 30 MB:**
- `db.py` keeps every chat parsed, its derived rows and the DuckDB tables;
  a changed chat rebuilds the derived rows of all of them.
- The search index holds two copies of every message, with no total limit.
- The Analytics copy is rebuilt as a whole, under one lock, on the next
  query after the chats or the tasks change (since 2026-10-20 not after any
  write; timer entries share the tasks' stamp and still renew it).
- `git status -uall` in the smart timer lists every untracked file of a folder.

Measure again past 300 MB of data, or when the report's memory history
climbs: `python sp.py report` holds it.

## Memory at start (2026-10-20)

**Question.** The live server held 600–730 MB and had peaked at 2.8 GB
(`VmHWM` in `/proc/<pid>/status`) within 15 minutes of a restart; the load
test below never passed 300 MB.

**How.** The server over a copy of the data root, its RSS read every 0.5 s
for 5 minutes from the start, with no page open: as a test server
(`SP_SANDBOX=1`) and as the served app (system monitor and smart timer on).

**Found.** The test server stays at 193 MB. The served app also starts
`turntimes.backfill`, which times old Claude Code turns from their
transcripts. It read each transcript whole and parsed it into one list:
this chat's transcript is 329 MB. RSS went 83 → 2511 MB in 27 s, and glibc
kept 477 MB of it after.

| | Peak | After 5 min |
|---|---|---|
| before | 2511 MB | 477 MB |
| transcripts read one line at a time | 193 MB | 186 MB |

**Decided.** JSON-lines files are read one line at a time
(`turntimes._lines`). The activity times read from them stay cached, the
least recently used dropped past 500 000 times: every transcript on this
machine, 446 files and 2.4 GB with the helpers', holds 101 208 of them in
5 MB. A cap by file count failed a chat with 174 helper transcripts. Measured with the system monitor on, so the monitor's own share is in
the 186 MB.

## Slow pages (2026-10-19)

**Question.** Which GET routes are slow, and why. Same copy of the data
root, each route once, cold then warm.

| Route | Before | Why | Now |
|---|---|---|---|
| `/api/timelapse` | 2.6 s every open (live: 4–10 s) | read and folded the whole `git log --numstat` of the span on each open | 0.13 s; live 0.09–0.14 s |
| `/api/stats/tasks` | 5.4 s on the first open | attributes commits to 296 sessions | unchanged: already warmed |

**Decided.** The timelapse keeps its git part per (folder, span, HEAD), 16
entries: a new commit or a moved span end reads it again. The task
statistics are warmed at start (`server._warm_git`); 5.4 s was the test
server, which starts without the warm-up. After a chat or a task changes,
they are recomputed in about 150 ms.

## Server memory (2026-10-19)

**Question.** The server held 584 MB after nine hours, over a data root of
about 30 MB (without `tour_shots/` and `monitor/`).

**How.** `scripts/perf/memory_load.py <data root> [VAR=value …]`: the server
on port 8131 over a copy of the data root, every GET route of the API, 12 at
a time, 6 rounds. Memory is the process's RSS. Machine: Linux, 14 cores,
33 GB.

**Where it goes.**

| | MB |
|---|---|
| Python, FastAPI, DuckDB imported | 92 |
| The app started, views built | 150 |
| Every page read once, one at a time | 240 |
| Live objects Python keeps after that (tracemalloc) | +37 |
| DuckDB (`duckdb_memory()`) | 23 |

The rest of the growth is memory the code freed and glibc kept: one malloc
arena per thread, and the server runs about 40. `malloc_trim(0)` returned
little.

**Tried.**

| Setting | After 6 rounds | Median | p95 |
|---|---|---|---|
| as it was | 357 MB, still growing | 151 ms | 3132 ms |
| `MALLOC_ARENA_MAX=2` | 294 MB, flat from round 3 | 140 ms | 2977 ms |
| + 16 threads instead of 40 | 305 MB | 158 ms | 2975 ms |

**Decided.** `sp.py` starts the server with `MALLOC_ARENA_MAX=2` (glibc only;
macOS and Windows ignore it). The thread limit gave nothing at this load and
was dropped.

**Open.** The live server reached more than the load test did (584 MB). Most
of it was the transcript read at start (Memory at start, above). Measure the
live server after a day again.
