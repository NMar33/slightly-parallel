# Performance

What was measured, how, and what came of it. One entry per question, newest
first. Each entry is short and holds what is needed to measure it again.

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

**Open.** The live server reaches more than the load test does (584 MB): the
monitor, the file watchers, terminals and real repositories are not in the
test. Measure the live server after a day with the setting.
