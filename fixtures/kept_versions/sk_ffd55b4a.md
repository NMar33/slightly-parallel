---
id: sk_ffd55b4a
kind: skill
---

## Version 1 · 2609-25 14:31 · edited
> Built into Slightly Parallel

---
name: update-the-architecture
description: "Bring a project's Slightly Parallel architecture up to date: the architecture form for the last scan, the architecture page and the map of the program, each only when it is out of date. Use when the operator types #architecture (also #page or #map)."
---

The architecture is three things, and `#architecture` keeps all three
current. You do only the parts that are out of date; the server says which.

1. **Ask the server.** Call `architecture_status`. The answer has `form`,
   `page` and `map`, each with `needed` and `why`. With nothing needed,
   tell the operator in one sentence that the architecture is up to date,
   with the three versions, and stop.
2. **The form**, when `form.needed`. It is owed for the last scan
   (`form.scan_id`). Read that scan (`search` with its id), then write
   `write_entry {lens: "architecture"}` with the scan's id as
   `trigger_id`. The eight groups are under *Architecture* below.
3. **The page**, when `page.needed`. Call `architecture_material` and
   write the next version with `architecture_page {text, note}`. The
   skill `keep-the-architecture-page` holds the steps; follow them.
4. **The map**, when `map.needed`. Do not ask the operator: the server
   found that the program's shape changed. Start one helper agent on the
   model `map_material` names; it follows the skill `map-the-program`
   from its step 2 and writes with `map_write`. While it reads, go on.
5. **Tell the operator** in one line per part: what changed, or that it
   was already current and why — the `why` from step 1.

`#page` and `#map` still work and do their one part: `#page` is step 3,
`#map` is step 4 without the check (the operator asked for it).

**Architecture — `write_entry {lens: "architecture"}`** (the third half of
`#scan`, after the scan and the file entry). One form per scan. It answers
one question: what did you do to the shape of the system since the
previous scan? Not "this turn" — the whole window the scan covers.

Go through eight groups. Each group either appears in `checked` (you
looked, nothing changed) or has entries in `changes`:

```
does        feature · fix
owes        debt · action-needed
runs        service · runtime · config · deploy
stores      database · files · cache · queue
talks       endpoint · integration · hook · command
built with  framework · library · module
faces       surface · auth · job
holds       rule · tests
```

An entity is a thing of one of these types with a name: `feature: copy a
chat message`, `endpoint: /api/tasks/{id}/report`, `database:
task_evidence`, `config: SCAN_DATA_ROOT`, `module: features/agents`. A
feature is something a user can now do, do differently, or no longer do —
name it the way the user would say it, and give the `task` that asked for
it when there is one. A fix is named by the symptom that is gone. A debt
is what you left fragile, stubbed or untested — write it yourself, with
the `risk` of ignoring it; `remove` it when it is paid off. An
action-needed is something the operator must do (restart, migrate,
re-run setup) — `action` is the exact step. Everything else is named the
way the code names it. Endpoints are families (`/api/tasks/*`) unless one
route is the whole change; libraries are the ones the design leans on,
not every package; a module is a folder with one responsibility.

Each change: `op` (add · change · remove), `type`, `name`, `path` (1–5
entries: a file, a folder, or `file:Symbol` — class or function name,
never a line number; every entry must exist in the project folder; not
required on a remove), `note` (one line: what it does, or what is
different), plus the type's fields:

```
feature      surface · task        fix            surface · task
debt         risk                  action-needed  action · by_when
service      start · port          endpoint       method · route · service
runtime      version               integration    direction · auth
config       read_in · default     hook           host · event
deploy       command               command        usage
database     engine · tables       framework      version
files        format · writer       library        version · why
cache        from · rebuilt        module         owns · depends_on
queue        producer · consumer   surface        route · service
auth         mechanism · checked_in    job        schedule · trigger
rule         enforced_in · check   tests          command · covers
```

Not a change: a bug fix that keeps the shape (that is a `fix` only if
user-visible), a refactor, styling, copy, a new test in an existing suite
(a `change` to the suite only if it now covers something new). When in
doubt, it is not an entity — say so in the scan's `why` instead.
`decision`: a `dc_` id when a logged decision produced the change.

```json
{"lens":"architecture","fields":{"trigger_id":"sn_…",
  "checked":["owes","runs","built with","faces"],
  "changes":[
   {"op":"add","type":"feature","name":"report a task done, with evidence",
    "path":["backend/routers/evidence.py"],"surface":"kanban card",
    "task":"tk_…","note":"agent reports; operator sees a badge and 1–3 items"},
   {"op":"add","type":"endpoint","name":"/api/tasks/{id}/report",
    "path":["backend/routers/evidence.py:report_task"],"method":"POST",
    "note":"records the claim; status stays the operator's"},
   {"op":"add","type":"database","name":"task_evidence",
    "path":["backend/entities.py"],"engine":"csv",
    "note":"what an agent showed for a finished task"},
   {"op":"change","type":"tests","name":"backend pytest",
    "path":["backend/tests/test_evidence.py"],"command":"pytest -q",
    "note":"+ test_evidence.py"}
  ]}}
```

The server refuses (naming the problem): an unknown `type` or `op`; a
missing `name` or required field; a `path` entry not found in the project
folder (or a symbol not found in its file); a group in neither `checked`
nor `changes`. Fix and write again — writes are idempotent. All eight
groups checked with an empty `changes` is a valid answer: it says you
looked. The screening is `GET /api/architecture/state?project=…` — every
scan with its answer, and the standing debt / action-needed rows on top.

Mistakes to avoid: redoing a part the server says is current; asking the
operator before the map when the server says it is needed; writing the
form from memory instead of from the scan; writing the page yourself when
the skill `keep-the-architecture-page` holds its steps.

## Version 2 · 2610-06 19:49 · edited
> Built into Slightly Parallel

---
name: update-the-architecture
description: "Bring a project's Slightly Parallel architecture up to date: the architecture form for the last scan, the architecture page and the map of the program, each only when it is out of date. Use when the operator types #architecture (also #page or #map)."
---

The architecture is three things, and `#architecture` keeps all three
current. You do only the parts that are out of date; the server says which.

1. **Ask the server.** Call `architecture_status`. The answer has `form`,
   `page` and `map`, each with `needed` and `why`. With nothing needed,
   tell the operator in one sentence that the architecture is up to date,
   with the three versions, and stop.
2. **The form**, when `form.needed`. It is owed for the last scan
   (`form.scan_id`). Read that scan (`search` with its id), then write
   `write_entry {lens: "architecture"}` with the scan's id as
   `trigger_id`. The eight groups are under *Architecture* below.
3. **The page**, when `page.needed`. Call `architecture_material` and
   write the next version with `architecture_page {text, note}`. The
   skill `keep-the-architecture-page` holds the steps; follow them.
4. **The map**, when `map.needed`. Do not ask the operator: the server
   found that the program's shape changed. Start one helper agent on the
   model `map_material` names; it follows the skill `map-the-program`
   from its step 2 and writes with `map_write`. While it reads, go on.
5. **Tell the operator** in one line per part: what changed, or that it
   was already current and why — the `why` from step 1.

`#page` and `#map` still work and do their one part: `#page` is step 3,
`#map` is step 4 without the check (the operator asked for it).

**Architecture — `write_entry {lens: "architecture"}`** (the third half of
`#scan`, after the scan and the file entry). One form per scan. It answers
one question: what did you do to the shape of the system since the
previous scan? Not "this turn" — the whole window the scan covers.

Go through eight groups. Each group either appears in `checked` (you
looked, nothing changed) or has entries in `changes`:

```
does        feature · fix
owes        debt · action-needed
runs        service · runtime · config · deploy
stores      database · files · cache · queue
talks       endpoint · integration · hook · command
built with  framework · library · module
faces       surface · auth · job
holds       rule · tests
```

An entity is a thing of one of these types with a name: `feature: copy a
chat message`, `endpoint: /api/tasks/{id}/report`, `database:
task_evidence`, `config: SCAN_DATA_ROOT`, `module: features/agents`. A
feature is something a user can now do, do differently, or no longer do —
name it the way the user would say it, and give the `task` that asked for
it when there is one. A fix is named by the symptom that is gone. A debt
is what you left fragile, stubbed or untested — write it yourself, with
the `risk` of ignoring it; `remove` it when it is paid off. An
action-needed is something the operator must do (restart, migrate,
re-run setup) — `action` is the exact step. Everything else is named the
way the code names it. Endpoints are families (`/api/tasks/*`) unless one
route is the whole change; libraries are the ones the design leans on,
not every package; a module is a folder with one responsibility.

Each change: `op` (add · change · remove), `type`, `name`, `path` (1–5
entries: a file, a folder, or `file:Symbol` — class or function name,
never a line number; every entry must exist in the project folder; not
required on a remove), `note` (one line: what it does, or what is
different), plus the type's fields:

```
feature      surface · task        fix            surface · task
debt         risk                  action-needed  action · by_when
service      start · port          endpoint       method · route · service
runtime      version               integration    direction · auth
config       read_in · default     hook           host · event
deploy       command               command        usage
database     engine · tables       framework      version
files        format · writer       library        version · why
cache        from · rebuilt        module         owns · depends_on
queue        producer · consumer   surface        route · service
auth         mechanism · checked_in    job        schedule · trigger
rule         enforced_in · check   tests          command · covers
```

Not a change: a bug fix that keeps the shape (that is a `fix` only if
user-visible), a refactor, styling, copy, a new test in an existing suite
(a `change` to the suite only if it now covers something new). When in
doubt, it is not an entity — say so in the scan's `why` instead.
`decision`: a `dc_` id when a logged decision produced the change.

```json
{"lens":"architecture","fields":{"trigger_id":"sn_…",
  "checked":["owes","runs","built with","faces"],
  "changes":[
   {"op":"add","type":"feature","name":"report a task done, with evidence",
    "path":["backend/routers/evidence.py"],"surface":"kanban card",
    "task":"tk_…","note":"agent reports; operator sees a badge and 1–3 items"},
   {"op":"add","type":"endpoint","name":"/api/tasks/{id}/report",
    "path":["backend/routers/evidence.py:report_task"],"method":"POST",
    "note":"records the claim; status stays the operator's"},
   {"op":"add","type":"database","name":"task_evidence",
    "path":["backend/entities.py"],"engine":"csv",
    "note":"what an agent showed for a finished task"},
   {"op":"change","type":"tests","name":"backend pytest",
    "path":["backend/tests/test_evidence.py"],"command":"pytest -q",
    "note":"+ test_evidence.py"}
  ]}}
```

The server refuses (naming the problem): an unknown `type` or `op`; a
missing `name` or required field; a `path` entry not found in the project
folder (or a symbol not found in its file); a group in neither `checked`
nor `changes`. Fix and write again — writes are idempotent. All eight
groups checked with an empty `changes` is a valid answer: it says you
looked. The screening is `GET /api/architecture/state?project=…` — every
scan with its answer, and the standing debt / action-needed rows on top.

Mistakes to avoid: redoing a part the server says is current; asking the
operator before the map when the server says it is needed; writing the
form from memory instead of from the scan; writing the page yourself when
the skill `keep-the-architecture-page` holds its steps.
