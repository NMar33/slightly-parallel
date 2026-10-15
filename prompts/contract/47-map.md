---
key: map
section: 4
title: Map of the program
enabled: true
command: #map | Map the program: ask the operator first, then a helper agent calls map_material, then map_write (the skill map-the-program)
brief: **Map** (part of `#architecture`; `#map` still asks for it alone). For a project that is a program: every part as a row in one table (runtime, entry, surface, api, module, service, store, external, config, build, deploy, test …), and what connects to what. It reads up to 40 files, on a helper agent on the model Settings names. Under `#architecture` it runs when `architecture_status` says the program's shape changed, without asking; a bare `#map` is the operator asking. The helper calls `map_material`, then `map_write {map, note}`. The skill `map-the-program` holds the steps.
---

**Map of the program — `map_material`, then `map_write {map, note}`** (`#map`). The
architecture page says what the project is in prose. The map is the table: every part of
the program as a row of one kind, and what connects to what. It is for programs only.
Mapping reads up to 40 files: ask the operator before it starts (the skill says how), and
a helper agent does the reading. The map is kept in versions; a new version replaces the
table and the page shows what came and went.

## What you are given

**Computed facts** (`map_material` returns them): languages by file count, the manifests found and what they declare (name, version, dependencies), build and CI files, services in compose files, test folders, environment variable names the code reads, ports the code names, nested repositories, the git history. A program computed them: trust them over any document, and do not recount them. Rows the facts already give you are marked `evidence: computed`; you keep them and add what only reading shows.

## Step 1 — pick the template

One template, by what the program is. Each template lists the row kinds it must answer. A kind with nothing real gets one row `name: none` with `evidence: searched <what you looked for>` — never an invented row, never a silent gap.

| template | must answer |
|---|---|
| **web-service** — a server that answers requests, with or without a web UI | runtime · framework · entry · surface · api · module · service · store · external · config · build · deploy · test · auth · job |
| **app** — a program a person runs on a device: mobile, desktop | runtime · framework · entry · surface · module · store · external · config · build · deploy · test · auth |
| **tool** — a command, a script, a bot, run by hand or on a schedule | runtime · entry · surface · module · data-in · data-out · config · build · test · external |
| **library** — code other programs import | runtime · api · module · build · test · external |
| **pipeline** — data in, steps, data out, on a schedule or by hand | runtime · framework · entry · step · data-in · store · data-out · job · config · test · external |
| **research** — experiments, models, notebooks, a paper | runtime · framework · entry · data-in · model · step · data-out · store · external · test |
| **site** — pages built from content | framework · entry · build · deploy · surface · data-in |

A repository that holds several programs: map the main one with its template, and give each other program one `module` row that says what it is and where. Say which is the main one and why in `notes`.

## Step 2 — the rows

One row per part. At most 50 rows: `module` at most 10, `library` at most 6, `entry` at most 5, `surface` at most 6. Columns:

- **kind** — one of: `runtime` (language and its version) · `framework` (what the code is written against) · `library` (a library the design leans on; at most 6) · `entry` (how it starts: a script, a main file, a launcher, a notebook) · `surface` (where a person meets it: a web page at a port, commands, screens, a report) · `api` (where a program meets it: a route family, tools offered, a plugin interface, hooks) · `module` (a folder with one responsibility; 4 to 12 rows) · `service` (a process that runs: server, worker, watcher) · `store` (where data lives: engine and what; files count) · `data-in` (data from outside) · `data-out` (what it produces for others) · `external` (an outside service it needs) · `config` (how it is configured: variables, files, a settings page) · `build` (how it is built or packaged) · `deploy` (where and how it runs for real) · `test` (how it is checked, with the command) · `auth` (who may do what) · `job` (scheduled or triggered work) · `model` (trained weights) · `step` (a pipeline stage, numbered).
- **name** — the concrete thing, in the words the code uses. A row a reader can find.
- **what** — up to 12 words: what it is or does. Plain words. No praise.
- **where** — one path relative to the repository, or one URL. A folder for a module, a file for the rest. A store or service that lives outside the repository (a data folder, a database, a cloud) points at the file that names it, and `note` says it is outside.
- **version** — only when the facts or a manifest state it.
- **evidence** — how you know: `computed` · `opened <file>` · `ran <command>` · `per <file> of <date>, not checked`. A row you did not open is not written.
- **note** — up to 20 words, only when there is something the reader must know: a limit, a state, a caveat. Never a restatement of `what`.

Which kind: a script or command a person runs is an `entry`; a `surface` is what a person sees or uses while the program runs; a `job` is work started by time or by an event, not a computation inside a request; a `library` is code the program imports, a `module` is code the program owns; a document that tells an agent how to use the program is `config`, not an entry.

## Step 3 — the relations

What connects to what, at most 30, each `from · verb · to`, where `from` and `to` are row names, and `verb` is one of: `starts` · `serves` · `calls` · `reads` · `writes` · `uses` · `feeds` · `builds` · `deploys-to` · `tests` · `triggers`. Only relations you saw in the code or in a config file. The main path first: how a request, a run or a record moves from the entry to the output.

## Step 4 — the notes

Up to 5 lines, plain sentences:
1. **Shape:** the program in one sentence, naming the rows that matter most.
2. **Main path:** the relations of the main path, as one sentence.
3. **Runs on:** one machine, a cloud, a store, a device; and who can reach it.
4. **Not found:** what the template asked for that the repository does not have, and what you searched.
5. **Not read:** folders you did not open.

## How to work

- Read the computed facts first. Then the manifests, the entry files, the top folders. Open up to 40 files. A file you did not open cannot be a row.
- The code and the newest file win over a README. A README claim you did not check is written with `evidence: per README, not checked`.
- Say each thing once. A module is a folder, not a file list. A library the code imports in one place is not a row.
- Numbers only when computed or in a manifest.
- Send the map with `map_write {map, note}` as one JSON object:

```json
{"template": "web-service",
 "rows": [{"kind": "runtime", "name": "Python 3.12", "what": "backend language", "where": "backend/pyproject.toml", "version": "3.12", "evidence": "computed"}],
 "relations": [{"from": "sp.sh", "verb": "starts", "to": "FastAPI server"}],
 "notes": {"shape": "…", "main_path": "…", "runs_on": "…", "not_found": "…", "not_read": "…"}}
```
