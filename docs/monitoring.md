# Monitoring and logs

What Slightly Parallel records about itself and the machine, where it goes,
for how long, and where to look when something is wrong. None of it holds
the text of a chat or an entry. The defaults below are settings (Settings ›
Monitor) unless they say otherwise.

## What is written, and where

| What | Where | How often | Kept |
|---|---|---|---|
| Machine readings: CPU, load, memory, swap, disk space and speed, network, ping, temperature, battery, the server's own memory and CPU | `<data root>/monitor/monitor.sqlite`, table `samples` | every 5 s | every sample 6 h; minute averages and peaks 7 days; 15-minute ones 180 days |
| The heaviest processes | same file, table `processes` | every 30 s | with the samples |
| Unusual episodes: CPU, memory, disk, network, temperature, leak, swap, battery, "unusual for this machine", gaps | same file, table `events`: start, end, peak, the processes of that moment | when one starts or ends | 730 days |
| Every request: method, path, status, milliseconds | server log `.sp/sp.log` (JSON lines) and a ring of the last 4 000 in memory | each request | file: 5 MB × 4 (rotated); ring: until restart |
| Slow requests (≥ 300 ms) and slow rebuilds (≥ 2 s) | same log, as warnings | when they happen | as above |
| The server's memory, peak, threads, open files (`sp.memory`) | same log | every 5 min | as above |
| Warnings and errors, with the exception's message | same log; also on stdout, which the supervisor writes to `.sp/server.log` | when they happen | as above |
| The supervisor's output: starts, restarts, crashes before the log exists | `.sp/server.log` | when they happen | cut to its last 1 MB past 5 MB |
| Capture hook failures (a turn not kept, a write refused) | `<data root>/.capture/errors.jsonl` | when they happen | the older half dropped past 256 KB |
| Test servers (`SP_SANDBOX=1`: browser tests, measurements) | `.sp/sandbox/` | — | — |

The monitor folder is left out of backups and of the file watcher: it is
this machine's record, not project data. The monitor costs about 1 ms a
sample and 60 ms a process scan; Monitor shows its own cost.

## What raises a warning

- **Monitor** (`events`, Monitor page, top bar): CPU ≥ 90 % for 2 minutes;
  memory in use ≥ 90 % for 1 minute; a disk with < 10 % free; a process
  growing ≥ 50 MB an hour for a whole hour (a leak); swapping; no ping answer
  three times; a reading far from this machine's own baseline; a sensor
  above its limit.
- **Server log**: a request ≥ 300 ms; a rebuild ≥ 2 s; the server's memory
  ≥ 1 GB, or 300 MB more than 5 minutes before; any error.
- **Capture**: every failed hook write, and chats in a registered folder
  that nothing recorded (Monitor › Capture).

## Where to look

| Seen | Look at |
|---|---|
| The machine is slow, the fan runs | Monitor: the heaviest programs, the events of today |
| A page is slow | Monitor › Server: slowest requests; the log's `ms` |
| The server holds a lot of memory | Monitor › Server (memory now, peak); the log's `sp.memory` lines; `docs/performance.md` |
| A chat or its answer is missing | Monitor › Capture; `.capture/errors.jsonl` |
| The server does not start | `.sp/server.log`; `python sp.py status` |
| Data looks wrong | Internals › Data check (`/api/doctor`) |

## Is it working

`#sp` in a chat: the agent calls the MCP tool `checkup` and says what works and
what is a concern for this chat and folder — messages recorded, MCP, hooks,
the contract, skills, data, disk, backups, the server's memory and errors.
What could not be checked is said, never called fine. `#sp <what worries you>`
also looks into that; nothing is changed without your yes. `python sp.py
check` runs the same checks from a terminal, and when the server does not
answer it looks from outside: the supervisor, the port, the data folder, the
disk, the end of the supervisor's log.

## To send when something is wrong

`python sp.py report`, or Monitor › Server › **download report**: one
Markdown file with the machine, the server's memory now and at its peak,
memory and load hour by hour for a day, monitor events of 7 days, the log's
memory lines, slow requests and warnings, hook errors, data and transcript
sizes, the settings and the supervisor's output. No chat text, nothing from
`.env`; paths under the home folder start with `~`. When the server does not
answer, the command builds it from the files alone. **copy for AI** on the
same page gives the running server's summary as text.

## For a developer

- `GET /api/monitor/now`, `/series`, `/events`, `/processes`, `/storage` —
  the monitor (routers/monitor.py).
- `GET /api/logs`, `/api/logs/text` — the summary and the log's tail;
  `GET /api/diagnostics/report` — the report (routers/logs.py).
- `GET /api/capture/health` — capture (capturewatch.py).
- `python sp.py logs` follows the server log; `python sp.py status` shows the
  supervisor and the health check.
- Code: `backend/sysmon.py` and `sysmon_detect.py` (monitor),
  `backend/logbook.py` (log, memory line), `backend/diagnostics.py`
  (report), `scripts/hooks/capture.py` `record_failure` (hook errors).
