# Release testing

What is checked before a release, by whom, and what is planned. CI covers
most of it on Linux, macOS and Windows (`.github/workflows/ci.yml`); the
fresh-user test (`scripts/fresh_user`) installs from a clone and drives
Setup and real agents. This file holds the rest: the checks a person does,
the checks still to build, and the limits the release notes must name.

## Before every release

1. **One candidate.** Freeze the commit; run the whole CI on it
   (`scripts/release.sh --tree <publish folder>`, push `ci-windows`, run CI
   by hand there). Every job green on the same commit, no unexplained retry.
2. **Real agents.** Run `Agents` (`.github/workflows/agents.yml`) by hand:
   Claude Code, Codex and OpenCode on cheap models, eight messages each,
   `#sp` among them.
3. **By hand on Windows and macOS** — the list below, about half an hour each.
4. **A late fix** makes a new candidate: CI again, the failing case shown
   fixed, and the stages it touches run again.
5. **Release notes** name the known limits (below) and the tested versions
   of the systems, Python and the agent tools.

## By hand, on real Windows and macOS

A standard user account, no developer shell set up. Follow the README as
written.

- [ ] Clone, `sp up` (Windows: `sp.cmd up`): the app opens, the demo is there.
- [ ] Setup: a data folder, a project folder with a space and a non-English
      letter in its path; integrate Claude Code (and Codex if installed).
- [ ] A chat in that folder: the first message shows on Agents; `#now` makes
      a card; `#sp` answers "All fine" or names what is not.
- [ ] Start at login on; **restart the computer and log in**: the server is
      up without doing anything.
- [ ] The desktop shortcut: with the server down it starts it and opens the
      app; with it up it only opens the app.
- [ ] Sleep and wake: the app answers, the monitor goes on, the chat after
      waking is recorded.
- [ ] Network off: the app works; the monitor shows no connection.
- [ ] Settings › Backups › Back up now, then restore it into a new data
      folder: the project, its chats and tasks are there.
- [ ] Monitor › Server › download report: read it — no chat text, no
      secrets, paths from `~`.
- [ ] Disconnect the project in Setup: its folder is as before, the user's
      own hooks and AGENTS.md text are kept.
- [ ] Windows: the terminal says it needs macOS or Linux, and nothing else
      breaks without it.

## Built

- **Upgrade from the last release.** The fresh-user test, in CI on all
  three systems, installs the newest release tag in the candidate's history
  (on `ci-windows`: v0.2.0), uses it, then `git pull`s the candidate: the
  data, project, chat, task and old hook are kept, every page opens, the new
  built-in skills reach the home folder, integrating again makes the files
  current, and `#sp` finds the folder, contract and hooks fine.

- **A backup under load, restored on a clean install** (`backend/tests/test_backup_under_load.py`,
  every CI run on three systems): tasks through the API and messages through
  the capture hook from three threads while two backups run; the second is
  restored into an empty folder; every task and message acknowledged before
  it started is there, the data check finds no damaged file, a new write works.

- **A crash in the middle of a write** (`backend/tests/test_crash_mid_write.py`):
  the server killed four times at random moments while tasks are written and
  a backup runs, and the capture hook killed while it writes a message. After
  each kill nothing acknowledged is lost, the data check finds nothing
  damaged, an interrupted archive is never listed, and the next write works.
  `SP_CRASH_SEED` picks other moments; seeds 1–5 passed. A killed process is
  not a power cut.

- **Storage faults** (`backend/tests/test_storage_faults.py`): a ledger with a
  quote left open is not rewritten (409, the record named) and the data check
  names it — before, a task edit wrote it back without the rows the quote hid;
  a full disk answers 507 and a read-only folder 503, saying what to do, with
  the files unchanged; the next write works once the fault is gone. The check
  for hidden rows finds none in 179 ledgers of a long-lived data folder.

- **Paths with a space and a non-English letter**: the fresh-user test makes
  all its folders under such a path, on all three systems.
- **The start-up memory spike** (`backend/tests/test_start_memory.py`): timing a
  60 MB transcript may grow the peak by half its size at most; the old
  whole-file read grew it by 194 MB.
- **Two servers on one data folder**: the second is refused, saying why
  (`server.lock`, held by the served app, gone with its process).

## To build (not automated yet)

In order of risk. Each becomes a stage of the fresh-user test when built.

| Check | What it proves | State |
|---|---|---|
| 24–48 h run: simulated agents write through hooks and MCP, pages read; an outside ledger counts every message; memory, threads, files measured | Nothing is lost or grows over days | measured by hand for a few hours (docs/performance.md) |
| Cursor in the real-agent run | The fourth tool works end to end | only its hook format is tested |
| Low memory (4 GB), a slow disk | Usable on a small laptop | not tested |

## Known limits (for the release notes)

- The terminal runs on macOS and Linux only; on Windows the rest of the app works.
- One server per data folder: a second one on the same folder refuses to start.
- Tested on the systems CI runs (Ubuntu, macOS and Windows, current runners)
  with Python 3.11+ and Node 20.
