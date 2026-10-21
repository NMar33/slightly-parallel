# Slightly Parallel — briefing for work on Slightly Parallel's own code

This file is for an agent or a developer who changes Slightly Parallel itself. An
agent that works in an observed project follows `SLIGHTLY-PARALLEL.md` instead. Every
path below is relative to the repo root unless it starts with `/`.

## 1. What this is

Slightly Parallel is a self-hosted dashboard that records what coding agents do across
one operator's projects, on one machine. Tool hooks record the chats word for
word. Chats and hours are read from the timestamps. Agents write entries
(scans, decisions, standups, tasks, the architecture page) through the MCP
server `slightly-parallel`, by field name. Everything is stored
as CSV and Markdown files in one data folder. There is no database server.

## 2. Install and run

Requirements: Python ≥ 3.11, Node ≥ 20, git (optional in observed
projects; see §7 and §8).

```bash
git clone https://github.com/nmar33/slightly-parallel.git slightly-parallel && cd slightly-parallel
./sp.sh up --dev        # backend :8123 + hot-reload UI :5173, supervised
./sp.sh up              # prod: builds the UI, serves everything from :8123
./sp.sh status | logs | restart | down
./sp.sh terminal on|off # the terminal switch (also in Settings › Terminal)
```

`run.sh` is the unsupervised equivalent (`./run.sh` dev, `./run.sh --prod`). Both run `sp.py`, which also runs on Windows as `sp …` (sp.cmd).
Healthy = `curl -s http://127.0.0.1:8123/api/health` returns `{"ok":true,…}`.
Backend edits need `./sp.sh restart` (no Python hot-reload); the UI
hot-reloads in dev.

Configuration is `.env` (template `.env.example`). The data root can also be
set in the UI (Setup, Settings). Host, port, CORS and the terminal are set in
`.env` only: they are security settings, and a web page cannot change them.

| Variable | Default | Purpose |
|---|---|---|
| `SP_DATA_ROOT` | `~/.slightly-parallel` | Where all records live; made on the first start, and the example project is played into it (`backend/backend/example.py`). `SCAN_DATA_ROOT` is also read |
| `HOST` / `SP_PORT` | `127.0.0.1` / `8123` | Backend address and port. `SCAN_PORT` and `PORT` are also read |
| `SP_CORS_ORIGINS` | localhost dev origins | CORS allowlist. `SCAN_CORS_ORIGINS` is also read |
| `SP_ENABLE_TERMINAL` | off | Turns the terminal on (otherwise a switch in Settings); its token is new at every start |

A fresh clone starts on a new data folder with the example project in it
(`scripts/demo/build_example.py`: the shopfront month, played with the clock
ending yesterday), so every page shows something before anything is set up.
`fixtures/` is test data: the end-to-end tests serve a copy of it. Tests and experiments use temporary
data roots, never a real one; the test suite guards `.env`.

## 3. Layout, and how a write flows

How a write flows:

1. **Hook.** `scripts/hooks/capture.py` appends each message to `chat.md`,
   keeps a tagged message (`#vision`, `#rule`, `#problem`, `#skill`,
   `#artifact`), and prints `[slightly-parallel]` notices into the agent's context.
   Adapters: `claude-code-capture.py`, `codex-capture.py`,
   `cursor-capture.py`, `slightly-parallel-opencode.js`, `capture-cli.py`.
2. **MCP translator.** `backend/backend/mcp.py` is a stdio process started
   with the agent's chat. It builds `write_entry` from `GET /api/schema`,
   stamps project, agent id, date and time, refuses an unknown field or
   value, and forwards to the HTTP API with the header `X-SP-Via: mcp`.
   `mcp.TOOLS` is the one list of tools. It starts with the chat, so an
   open chat does not see a tool added later until it reconnects.
3. **Server.** `backend/backend/server.py` refuses a write that names an
   agent and lacks that header (setting `agents.mcp_only`).
   `routers/deps.py` holds the one reading of who is writing
   (`identity_of`) and the operator check (`operator_only`).
4. **Files.** A create appends one CSV row and one Markdown detail file,
   under a lock, atomically. `entities.py` is the registry: each lens's CSV,
   detail folder, id prefix, columns and mutable fields.
   `entry_fields.py` maps an entry's field names (`why`, `alternatives`,
   `deltas`) to its storage slots; nothing agent-facing names the slots.
5. **Tables and pages.** `db.py` builds DuckDB tables from the CSV files
   (`*_mutual`, `sessions`, `time_blocks`). `routers/lenses.py` gives every
   lens `GET /api/<base>`, `GET /api/<base>/{id}`, the create and
   `…/{id}/update`. The pages poll the API.

Where things are:

- `backend/backend/routers/` — one router per feature: `scans.py`,
  `standups.py`, `evidence.py`, `architecture.py` (what each scan changed, and the page),
  `skills.py`, `artifacts.py`, `keep.py` (kept messages), `tasks_extra.py`,
  `sessions_api.py` (derived, read-only), `files_extra.py`, `setup.py`,
  `settings_api.py`, `schema_api.py`, `core.py`, `backup.py`, `promptlib.py`,
  `terminal.py`, `monitor.py`, `stats.py`, `done.py` (`#done`), `marks.py`
  (`#important`), `analytics.py`, `logs.py`, and more beside them.
- `backend/backend/` libraries behind them: `skilllib.py`, `artifactlib.py`,
  `keeplib.py`, `standuplib.py`, `scanlib.py`, `archpage.py`,
  `projectfacts.py`, `taskwork.py`, `gitwork.py`, `promptlib.py`,
  `backup.py`, `termlib.py`, `sysmon.py`, `statslib.py`, `donelib.py`,
  `marklib.py`, `logbook.py` (the server's log).
- `frontend/src/` — React, Vite, Tailwind, TanStack Query. `pages/` are
  routes, `features/` what they are made of.
  `lenses/config.tsx` declares each lens: title, command, what an entry
  holds, the agent prompt. `features/guide/pages.ts` and
  `features/visions/guides.ts` hold what each page says about itself.
- `prompts/contract/` — the contract parts. `templates/skills/` — the
  built-in skills. `SLIGHTLY-PARALLEL.md` — the composed contract (§6).
- `sp.py` — the launcher (`up`, `down`, `status`, `run`); `sp.sh`, `sp.cmd` and `run.sh` call it. State in `.sp/`.

Data root layout (`SP_DATA_ROOT`):

```
projects/<code>/chats/<agent_id>/chat.md   verbatim turns (## Turn N · ts / **User** / **Agent**)
projects/<code>/chats/<agent_id>/meta.json agent_id, agent_name, chat_title, counters
scans.csv + snapshots/*.md                 checkpoints (a row + the text)
<lens>.csv + <lens>_details/*.md           decisions, sprints, problems, rules, visions,
                                           files,
                                           tasks (+ task_events.csv), time_entries, snippets
projects/<code>/artifacts/<name>/          folders an agent wrote for #artifact
projects/<code>/architecture/vNNN.md       the architecture page, one file per version
task_evidence.csv + task_evidence/         what an agent attached to a finished task
kept_versions/<id>.md                      versions of kept messages and skills
integrations.csv                           project code → registered folder
settings.json                              UI-editable settings (agent signals, kanban, chats)
.trash/<code>-<stamp>/                     archived projects (Setup → Delete data)
```

Ids are deterministic (`sha256(created_date|created_time|project|agent_id|headline)[:8]`
with a lens prefix). The same entry written twice is one entry: the second
write answers `200` with `existing: true`, a new one `201`.

## 4. Integrate a project (what Setup does, callable without a browser)

```bash
curl -s -X POST http://127.0.0.1:8123/api/setup/integrate \
  -H 'Content-Type: application/json' \
  -d '{"project_code":"my-app","project_dir":"/abs/path/to/my-app",
       "write_agents":true,"write_claude_bridge":true,"write_claude_hooks":true,
       "write_opencode_plugin":false,"dry_run":false}'
```

Writes, in that folder: a fenced `<!-- slightly-parallel:begin/end -->` block in
`AGENTS.md`, the `@AGENTS.md` bridge line in `CLAUDE.md`, the two capture
hooks in `.claude/settings.local.json`, and the MCP server entry in
`.mcp.json` (`write_mcp`, on by default); records the folder in
`integrations.csv`. `dry_run:true` previews. `write_codex_hooks` adds
`.codex/hooks.json` and `write_cursor_hooks` adds `.cursor/hooks.json`
(Cursor's three events, answered with the JSON Cursor reads) and the same
MCP server entry in `.cursor/mcp.json`, the file Cursor reads. The legacy
Codex capture is global (`POST /api/setup/codex`, edits
`~/.codex/config.toml` `notify`).

Things to know:

- **Hooks are per folder.** Claude Code loads `.claude/settings.local.json`
  from the folder it is *started in*, not from a parent. Start the agent in
  the integrated folder. The first turn of a recorded chat prints
  `[slightly-parallel] project <code> · your agent_id is <id> · now <date> <time>`.
  No line: the chat is not recorded.
- **`agent_id` is the chat** (`cc-<8>`, `oc-<8>`, `codex-<8>`, `cursor-<8>`). The MCP
  translator stamps it on every entry; that is what links a checkpoint to
  its chat.
- Removing: `POST /api/setup/forget {project_code,path}` disconnects (undoes
  the files above, keeps data); `POST /api/setup/delete-data
  {project_code,confirm}` archives all of the project's data to `.trash/`.

## 5. The pages

`frontend/src/features/guide/pages.ts` lists every product route with what
it shows, and the in-app Guide renders it. The HTTP API and the MCP tools
are in `docs/api.md`; interactive API docs at `http://127.0.0.1:8123/docs`;
the live tool list is `GET /api/schema` → `tools`. The project page is
`/project/<code>` with tabs; the Architecture tab and `/architecture` open
on the architecture page; the map and the changes are one switch away.

## 6. The contract, the skills, and the places that must agree

`SLIGHTLY-PARALLEL.md` is what an observed agent follows. **Never edit it.** It is
composed from the parts in `prompts/contract/` by
`backend/backend/contract_parts.py`; recompose from `backend/` with
`.venv/bin/python -c "from pathlib import Path; from backend.contract_parts import write_contract; write_contract(Path('..'))"`.

- A part's frontmatter carries `key`, `section`, `title`, `enabled`, and one
  `command:` line per command (`#scan | what it does`). The command table
  and the MCP prompts are built from those lines.
- A part may carry `brief:`. The composed contract then shows the brief,
  and the whole body reaches an agent only when needed: through a tool
  (`scan_material`, `standup_material`, `architecture_material` return
  `instructions`) or through a skill.
- `31-writing.md` holds the writing rules for every entry: for a team lead
  who was not in the chat, short, each term explained, only what is known.
- Built-in skills live in `templates/skills/<name>/SKILL.md`. A template may
  say `{{part:<key>}}` and gets that contract part's body when it is
  seeded, so a skill and the contract have one source. Seeding runs on
  every start (`skilllib.seed_builtin_skills`); the served app installs
  each skill once into the home skill folders (`autoinstall_builtin`).
- A server started on `fixtures/` seeds the skills into it, the test
  data. **Commit the changed copy with the template**; a test fails
  when they differ.

To add a lens, a tool or a command, these must agree:

| Adding | Touch |
|---|---|
| a lens | `entities.py` (the entity), `entry_fields.py` (its field names), a contract part, `frontend/src/lenses/config.tsx`, `docs/api.md` |
| an MCP tool | `mcp.py`: `TOOLS`, `tool_defs`, the call; a test holds `TOOLS` equal to what is served |
| a command | a `command:` line in a contract part; the Guide (`features/guide/pages.ts`); if the hook must react, `scripts/hooks/capture.py` and its parity test `backend/tests/test_hook_parity.py` |
| a built-in skill | `templates/skills/<name>/`, then commit the seeded files under `fixtures/` |

Signals arrive as `[slightly-parallel]` notices in the agent's context: identity
(turn 1: `[slightly-parallel] project <code> · your agent_id is <id>`), no standup
for yesterday, a decision hint, contract refresh, a file entry or an
architecture form owed after a `#scan`, a kept message with the id to
interpret, `#evidence` with its task. Dates are `YYMM-DD`, times `HH:MM`.
Never write the CSV files directly.

## 7. Operating and verifying

```bash
cd backend && .venv/bin/python -m pytest -q tests # temp data roots; about a minute on six workers
cd frontend && npm run typecheck && npm test      # tsc + vitest
cd frontend && npm run e2e                        # playwright, own backend on :8129
```

- Git and commits are optional in observed projects. With git, a scan lists
  the chat's commits and a file entry fills its line counts (diff against the
  working tree). Without git, the hook stamps each turn with the files its
  tool calls changed and the files changed in the folder, and a scan lists
  those.
- Every capture adapter catches every error: at worst a turn is missing, and
  the chat goes on.
- What can break (see `/internals` → What can break): hooks installed
  mid-chat apply to the *next* chat; starting in a subfolder captures
  nothing; restarting a chat is a new agent lane (rename it; the id stays);
  backend edits need a restart.
- The code and the newest file win. When this file and the code disagree,
  the code is right. This file has a test that checks its cited paths and
  routes still exist (`backend/tests/test_agent_readme.py`).

## 8. Symptom → where to look

| Symptom | Check | Usual cause |
|---|---|---|
| Nothing captured for a project | `ls <data_root>/projects/<code>/chats/` and `GET /api/sessions?project=<code>` | Agent started outside the integrated folder (hooks are per directory); or hooks installed mid-session — they apply to the *next* session |
| No `[slightly-parallel] … your agent_id is …` on turn 1 | `cat <folder>/.claude/settings.local.json` — both `UserPromptSubmit` and `Stop` must call `claude-code-capture.py` | Same as above, or the hook path moved (repo relocated → re-integrate from Setup) |
| Messages recorded but answers missing | `chat.md` has `**User**` without `**Agent**` | The Stop event did not fire (the chat was killed) or the transcript had no final text; the turn stays open, nothing else is affected |
| Chats look split oddly | `settings.json` → `sessions.gap_minutes`; a chat ends at a gap > N minutes or a date change | Long thinking turns count from the *prompt* time; a 6-hour turn looks like a gap |
| Scan written, Files page empty | `GET /api/scans/{id}` → `files_entry` is null; the answer's `warnings` say what to write | The agent stopped after the first of the scan's three entries; the next captured turn raises `files_due` |
| Heatmap column has no chat | entry `agent_id` ≠ recorded agent name, or `created_time` invented | The agent wrote with an old id; the identity notice on turn 1 gives the right one |
| File entry says `git: not a repo — agent counts` | Setup row shows `no git`; `git -C <folder> rev-parse --is-inside-work-tree` | Registered folder is not a repo (fine) or the wrong folder is registered |
| Line counts look wrong on a file entry | detail `commit_from → commit_to`, `range_basis`, `dirty` | Range is previous entry → working tree; an explicit `commit_from` narrows it |
| UI shows old behaviour after a backend change | `./sp.sh status`, then `./sp.sh restart` | No Python hot-reload |
| The example project is missing or half there | `GET /api/example` → `building`, `error` | It is played in the background on the first start (about a minute); the server log names a failed build. Settings › Example project off, then on, plays it again |
| A write returns 422 | response `detail` names the field or the MCP tool to use | An agent write that bypassed MCP; an unknown field or value; missing `project`; `confirm` ≠ code |
| An agent lacks a tool that exists | `GET /api/schema` → `tools` lists it | The MCP translator started before the tool was added: reconnect it (`/mcp` in Claude Code) |
| `POST /api/time/start` returns 409 | `GET /api/time/running` | One open timer per project — stop or delete it |
| `POST /api/setup/codex` returns 409 | `~/.codex/config.toml` `notify` | A foreign notify is set; Slightly Parallel never overwrites it |
| The terminal says it is off | Settings › Terminal, or the drawer (`) | One switch; `./sp.sh terminal on` does the same |
| A whole project vanished | `ls <data_root>/.trash/` | Setup → Delete data archives there; move the folder's contents back to restore |
| Server log | `./sp.sh logs` (JSON lines: `req` with path/status/ms, `views rebuilt`) | — |
| Everything else | `/internals` → What can break; `docs/api.md`; `http://127.0.0.1:8123/docs` | — |

## 9. Scenarios

**Onboard a project.** Setup step 2 (or the curl in §4) with the folder the
agent will be started in → open a *new* chat there → see the
`[slightly-parallel]` identity line → work → the operator types `#scan` before a
risky change and at the end (the scan, its file entry, its architecture
form) and `#page` for the architecture page. Check
`/project/<code>#sessions`, `#files` and `#architecture`.

**Morning.** Overview for all projects. The first agent of a new day is
told that yesterday has no standup; it asks the operator to write it now
or postpone, and a helper agent writes one standup for the project from
every chat of that day (`standuplib.py`). `GET /api/sessions?project=<code>&from_date=<YYMM-DD>`
for the raw time axis.

**A chat restarted mid-task.** A new chat is a new agent lane
(`cc-<new>`); the old lane keeps its history. Rename lanes from the
timeline pencil (or `POST /api/agents/{id}/rename`); a Claude Code
`/rename` shows up automatically as the lane's default name.

**Verify capture works right now.** Send any message; then
`GET /api/sessions?project=<code>` — the newest chat's `turns_n` grew.
Or fire the hook by hand:
`echo '{"session_id":"selftest","hook_event_name":"UserPromptSubmit","prompt":"x"}' | python3 scripts/hooks/claude-code-capture.py --project <code> --data-root <root>`
(then delete `projects/<code>/chats/cc-selftest`).

**Recover a deleted project.** `mv <data_root>/.trash/<code>-<stamp>/* <data_root>/`
(the archive keeps relative paths; CSV rows are appended files — merge them
back into the live CSVs by appending their data lines), then
`./sp.sh restart`.

**Move the data root.** Copy the folder; `POST /api/setup/data-root
{"path": "/new/abs/path"}` (or Setup step 1). Applies live; stored in
`.env`. Integrated projects keep working — the hooks carry the data root
as an argument, so re-integrate them to point at the new one.

**Several projects at once (operator time).** Project → Tools → Time
tracker: start with a share % per project; attributed = elapsed × share.
`GET /api/time/summary?project=<code>` for today / 7d.

**Ask the dashboard a question from a shell.** Every lens is
`GET /api/<lens>?project=&from_date=&to_date=`; a detail answer carries
`text`, the entry by its field names; `GET /api/search?q=` across tasks, decisions, agents;
`GET /api/snapshot` for the cross-project overview.

## 10. Id glossary

`cc-` Claude Code chat · `oc-` OpenCode · `codex-` Codex · `cursor-` Cursor (8 hex of the
tool's session id) · `ses_` derived session · `sn_` scan · `fl_` file entry
· `dc_` decision · `sp_` sprint · `pb_` problem · `rl_` rule ·
`vs_` vision · `sk_` skill · `ar_` artifact or architecture change · `st_` standup · `tk_` task · `tev_` task evidence · `tm_` time
entry · `snp_` snippet · `nt_` story note · `sr_` press-release request ·
`si_` story image · `pre_` story preset · `ce_` calendar entry · `ms_` milestone
· `mt_` milestone–task link.

## 11. Constraints you must respect when working on Slightly Parallel itself

- Do not write to a real data root from tests or experiments; use temp
  roots. Do not create rows in the operator's projects without deleting
  them after.
- `.env` holds security levers; only the data root is web-editable.
- No personal traces in shipped files (paths, emails, names) except
  `LICENSE`.
- Capture adapters must never raise; the hook's stdout is model context.
- After backend changes: `./sp.sh restart`; then verify by API or
  measurement, not by eye.
- Agents write through the MCP tools only, by field name. No text an agent
  reads may offer it a raw HTTP write or numbered levels.
- The pages are the truth. Rewrite texts from the pages and the code.
- Slightly Parallel runs on one laptop. Do not design for remote or multi-user use.
- A published route is never deleted or repointed. Add a new one
  (`/sessions` still answers; `/chats` is the page).
- Agents never change a task's status. They report; the operator moves it.
- Add capability; do not reduce or replace what the operator built.
- Product text is English and follows `docs/wording.md`: short plain sentences, no metaphors.
