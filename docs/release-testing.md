# Release testing

What is checked before a release, by whom, and what is planned. CI covers
most of it on Linux, macOS and Windows (`.github/workflows/ci.yml`); the
fresh-user test (`scripts/fresh_user`) installs from a clone and drives
Setup and real agents. This file holds the rest: the checks a person does,
the checks still to build, and the limits the release notes must name.

## Before every release

1. **One candidate.** Freeze the commit; run the whole CI on it
   (`scripts/publish-ci.sh ci-windows "…"`, then
   `gh workflow run ci.yml --ref ci-windows`). Every job green on the same
   commit, no unexplained retry: `scripts/release-ready.sh ci-windows vX.Y.Z`
   checks that for the branch's head commit and prints the merge and tag
   commands.
2. **Real agents.** Run `Agents` (`.github/workflows/agents.yml`) by hand:
   Claude Code, Codex and OpenCode on cheap models, eight messages each,
   `#sp` among them.
3. **By hand on Windows and macOS** — the list below, about half an hour each.
4. **A late fix** makes a new candidate: CI again, the failing case shown
   fixed, and the stages it touches run again.
5. **Release notes** name the known limits (below) and the tested versions
   of the systems, Python and the agent tools.

## By hand, on real Windows and macOS

What is left here needs a person, a real computer or a login CI does not
have; each item says which. A standard user account, no developer shell set
up. Follow the README as written.

- [ ] Clone, `sp up` (Windows: `sp.cmd up`): the app opens, the demo is there.
      *A person:* CI's runners are administrator accounts with the developer
      tools already installed, and nobody reads the README there.
- [ ] Setup: a data folder, a project folder with a space and a non-English
      letter in its path; integrate Claude Code (and Codex if installed).
      *A person:* the same flow runs in CI (Fresh user, on three systems),
      but not on a standard account with the tools installed the README's way.
- [ ] A chat in that folder: the first message shows on Agents; `#now` makes
      a card; `#sp` answers "All fine" or names what is not.
      *A login:* a real agent spends tokens; `Agents` (agents.yml) runs it by hand.
- [ ] Start at login on; **restart the computer and log in**: the server is
      up without doing anything.
      *A real login:* CI runs the command the login entry holds
      (Launcher, `autostart_check.py`) but cannot restart and log in.
- [ ] Sleep and wake: the app answers, the monitor goes on, the chat after
      waking is recorded. *A real computer:* a runner cannot sleep.
- [ ] Windows: the terminal says it needs macOS or Linux, and nothing else
      breaks without it. *Not built yet:* the page's message is read by a person.
- [ ] Codex logged in through ChatGPT (Windows and macOS): run
      `python scripts/ci/check_codex_limits.py`; it prints the plan, the
      5-hour and the weekly percentages. On Windows, with Codex installed by
      `npm install -g @openai/codex`, Usage › "Read now" on the Codex row shows
      the same. *A login:* only a ChatGPT login has plan limits; CI logs in
      with an API key, so it proves the read works and ends, not the percentages.
- [ ] macOS, a real sleep of over an hour with the server running: after
      waking, the Codex row is read again within a few minutes, and Monitor ›
      Server shows no error for the poll. *A real computer:* a runner cannot sleep.

### Moved into CI (2026-11-10)

- **Codex's Read now through the real server** — in CI (job Real Codex,
  `scripts/ci/codex_server_check.py`, three systems): the server on an empty
  data folder, `POST /api/usage/limits/refresh` as the page sends it, the
  Codex row answers (with the key login: "not signed in" or Codex's own
  sentence), no codex or node process from the read is left, no temporary
  file in `.usage`.
- **Network off** — in CI (job Launcher, `scripts/ci/offline_check.py`,
  three systems): new outgoing connections dropped by the system firewall
  (iptables, pf; on Windows a rule for the Python programs, since a
  machine-wide rule would cut the runner's own connection), 127.0.0.1
  kept. The pages and the main reads answer within 15 s, Monitor reports no
  connection, in a browser no page asks another host. The network comes
  back in an always() step.
- **Back up and restore into a new data folder** — in CI (job Fresh user,
  stage backup): Back up now through the API, the archive downloaded and
  restored into a new folder; projects, chats and tasks compared.
- **The server report** — in CI (job Fresh user, stage report): a key in
  the environment and in a chat, a marked sentence in a chat and a search;
  none in the report, home paths from `~`.
- **Disconnect keeps the user's own files** — in CI (job Fresh user, stage
  disconnect): a folder with its own AGENTS.md, CLAUDE.md, hooks and MCP
  server is byte for byte as before after Disconnect, and `git status` is clean.
- **The desktop shortcut** — in CI (job Launcher, `scripts/ci/autostart_check.py`,
  three systems): opened as a double click would (the .lnk through Windows,
  the .desktop's Exec line, the macOS app's program), with a stand-in
  browser. Down, it starts the server and the page answers; up, it only
  opens, the supervisor the same process. Not covered: a real desktop's
  double click and the system's default browser.

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

- **The soak test** (`scripts/soak/run.py`, run by hand on the candidate,
  `--hours 24`): four simulated agents write through the API and the capture
  hook while pages are read; a backup every 30 minutes, a restart every 2
  hours (every second one a kill), a restore checked every 6 hours, a ledger
  outside the server. `report.md` says whether nothing acknowledged was lost,
  every restore was complete, memory held after warm-up, reads stayed fast,
  and no server error came.

## To build (not automated yet)

In order of risk. Each becomes a stage of the fresh-user test when built.

| Check | What it proves | State |
|---|---|---|
| Cursor in the real-agent run | The fourth tool works end to end | only its hook format is tested |
| Low memory (4 GB), a slow disk | Usable on a small laptop | not tested |

## The blank-machine kit (scripts/machine)

One command installs everything, asks for the agents' logins and runs every
check; `.github/workflows/machine.yml` runs it on GitHub's runners (5 runs,
or 9 with `full`; about $4–8 for 9 at haiku and gpt-6-luna). Not done yet:
a check that each login works before the run starts; a real log-out and
log-in for start at login; spotting an agent stuck in a loop and retrying
its turn once, reported apart from a product failure; pinned versions of the
agent CLIs in the report.

## Known limits (for the release notes)

- The terminal runs on macOS and Linux only; on Windows the rest of the app works.
- One server per data folder: a second one on the same folder refuses to start.
- OpenCode, in a project whose path has a space: it escapes the space in a shell
  command and then asks permission for its own folder as an outside one; with
  nobody to answer (a script), the command is refused. The fresh-user test
  therefore makes its folder without a space when OpenCode is in the run.
- Tested on the systems CI runs (Ubuntu, macOS and Windows, current runners)
  with Python 3.11+ and Node 20.
