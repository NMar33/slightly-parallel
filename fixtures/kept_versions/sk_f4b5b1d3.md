---
id: sk_f4b5b1d3
kind: skill
---

## Version 1 · 2609-21 01:12 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what changed in the project since the last scan, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds the last
   scan, every commit since it, the files with line counts, the
   uncommitted files, the `counters` already counted, and the
   `instructions` for all three entries. Follow those instructions: they
   are the operator's current ones. With no commits since the last scan
   and nothing uncommitted, tell the operator there is nothing to scan,
   and stop.
2. **Write the scan** — `write_entry {lens: "scan", fields: {summary, why,
   deltas, proof, files_n, lines_add, lines_del, decisions_n}}`. Group the
   commits into themes first: each theme is one delta, or one "Not
   covered" line under `proof`. Copy the counters from the answer as they
   are. Keep the scan's id from the reply.
3. **Write the file entry** — `write_entry {lens: "file", fields:
   {trigger_lens: "scan", trigger_id: <the scan's id>, summary, narrative,
   paths}}`. `paths` is your judgment of the files that matter, one record
   each: path, action, importance 1–5, blast_radius 1–10, test_coverage,
   why. Not every file: the ones a reviewer should open.
4. **Write the architecture form** — `write_entry {lens: "architecture",
   fields: {trigger_id: <the scan's id>, checked, changes}}`. Go through
   the eight groups. A group with nothing new goes in `checked`. A group
   with something new lists its changes. All eight checked is a valid
   answer.
5. **Tell the operator** the scan's summary line, in one sentence.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 2 · 2609-21 17:37 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what changed in the project since the last scan, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds the last
   scan, every commit since it, the files with line counts, the
   uncommitted files, the `counters` already counted, and the
   `instructions` for all three entries. Follow those instructions: they
   are the operator's current ones. With no commits since the last scan
   and nothing uncommitted, tell the operator there is nothing to scan,
   and stop. Commits under `already_described` are work the last scan
   covered before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan", fields: {summary, why,
   deltas, proof, files_n, lines_add, lines_del, decisions_n}}`. Group the
   commits into themes first: each theme is one delta, or one "Not
   covered" line under `proof`. Copy the counters from the answer as they
   are. Keep the scan's id from the reply.
3. **Write the file entry** — `write_entry {lens: "file", fields:
   {trigger_lens: "scan", trigger_id: <the scan's id>, summary, narrative,
   paths}}`. `paths` is your judgment of the files that matter, one record
   each: path, action, importance 1–5, blast_radius 1–10, test_coverage,
   why. Not every file: the ones a reviewer should open.
4. **Write the architecture form** — `write_entry {lens: "architecture",
   fields: {trigger_id: <the scan's id>, checked, changes}}`. Go through
   the eight groups. A group with nothing new goes in `checked`. A group
   with something new lists its changes. All eight checked is a valid
   answer.
5. **Tell the operator** the scan's summary line, in one sentence.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 3 · 2609-21 18:58 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what changed in the project since the last scan, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds the last
   scan, every commit since it, the files with line counts, the
   uncommitted files, the `counters` already counted, and the
   `instructions` for all three entries. Follow those instructions: they
   are the operator's current ones. With no commits since the last scan
   and nothing uncommitted, tell the operator there is nothing to scan,
   and stop. Commits under `already_described` are work the last scan
   covered before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan", fields: {summary, why,
   deltas, proof, files_n, lines_add, lines_del, decisions_n}}`. Group the
   commits into themes first: each theme is one delta, or one "Not
   covered" line under `proof`. Copy the counters from the answer as they
   are. Keep the scan's id from the reply.
3. **Write the file entry** — `write_entry {lens: "file", fields:
   {trigger_lens: "scan", trigger_id: <the scan's id>, summary, narrative,
   paths}}`. `paths` is your judgment of the files that matter, one record
   each: path, action, importance 1–5, blast_radius 1–10, test_coverage,
   why. Not every file: the ones a reviewer should open.
4. **Write the architecture form** — `write_entry {lens: "architecture",
   fields: {trigger_id: <the scan's id>, checked, changes}}`. Go through
   the eight groups. A group with nothing new goes in `checked`. A group
   with something new lists its changes. All eight checked is a valid
   answer.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 4 · 2609-22 19:21 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what changed in the project since the last scan, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds the last
   scan, every commit since it, the files with line counts, the
   uncommitted files, the `counters` already counted, and the
   `instructions` for all three entries. Follow those instructions: they
   are the operator's current ones. With no commits since the last scan
   and nothing uncommitted, tell the operator there is nothing to scan,
   and stop. Commits under `already_described` are work the last scan
   covered before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at session end, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

First group every commit since the last scan into themes. Each theme gets
one delta, or one line under `proof`: "Not covered: …". Nothing is left
out silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older sessions and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```

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

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 5 · 2609-23 14:42 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what changed in the project since the last scan, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds the last
   scan, every commit since it, the files with line counts, the
   uncommitted files, the `counters` already counted, and the
   `instructions` for all three entries. Follow those instructions: they
   are the operator's current ones. With no commits since the last scan
   and nothing uncommitted, tell the operator there is nothing to scan,
   and stop. Commits under `already_described` are work the last scan
   covered before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at the end of a chat, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

First group every commit since the last scan into themes. Each theme gets
one delta, or one line under `proof`: "Not covered: …". Nothing is left
out silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older chats and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```

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

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 6 · 2610-06 19:49 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what changed in the project since the last scan, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds the last
   scan, every commit since it, the files with line counts, the
   uncommitted files, the `counters` already counted, and the
   `instructions` for all three entries. Follow those instructions: they
   are the operator's current ones. With no commits since the last scan
   and nothing uncommitted, tell the operator there is nothing to scan,
   and stop. Commits under `already_described` are work the last scan
   covered before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at the end of a chat, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

First group every commit since the last scan into themes. Each theme gets
one delta, or one line under `proof`: "Not covered: …". Nothing is left
out silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older chats and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```

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

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 7 · 2610-07 00:03 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what changed in the project since the last scan, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds your last
   scan of the project, this chat's commits since it (`window` says how it
   was drawn), the files with line counts, the uncommitted files, the
   `counters` already counted, and the `instructions` for all three
   entries. Follow those instructions: they are the operator's current
   ones. `others_commits_n` are commits made outside this chat since your
   last scan: not yours to describe. With no commits of your own and
   nothing uncommitted, tell the operator there is nothing to scan, and
   stop. Commits under `already_described` are work the last scan covered
   before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at the end of a chat, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

The window is yours: this chat's commits since your last scan of the
project, and what this chat changed that is not committed. Another agent's
commits are not in it — they are that agent's scan. A scan is written from
the work, not from git: what was done but not committed is in the scan too,
said as not committed. Group the work into themes. Each theme gets one
delta, or one line under `proof`: "Not covered: …". Nothing is left out
silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older chats and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```

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

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 8 · 2610-07 00:04 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what this chat changed in the project since its last scan, committed or not, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds your last
   scan of the project, this chat's commits since it (`window` says how it
   was drawn), the files with line counts, the uncommitted files, the
   `counters` already counted, and the `instructions` for all three
   entries. Follow those instructions: they are the operator's current
   ones. `others_commits_n` are commits made outside this chat since your
   last scan: not yours to describe. With no commits of your own and
   nothing uncommitted, tell the operator there is nothing to scan, and
   stop. Commits under `already_described` are work the last scan covered
   before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at the end of a chat, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

The window is yours: this chat's commits since your last scan of the
project, and what this chat changed that is not committed. Another agent's
commits are not in it — they are that agent's scan. A scan is written from
the work, not from git: what was done but not committed is in the scan too,
said as not committed. Group the work into themes. Each theme gets one
delta, or one line under `proof`: "Not covered: …". Nothing is left out
silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older chats and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```

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

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 9 · 2610-07 00:33 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what this chat changed in the project since its last scan, committed or not, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds your last
   scan of the project, this chat's commits since it (`window` says how it
   was drawn), the files with line counts, the uncommitted files, the
   `counters` already counted, and the `instructions` for all three
   entries. Follow those instructions: they are the operator's current
   ones. `others_commits_n` are commits made outside this chat since your
   last scan: not yours to describe. `touched` lists the files this
   chat's tools changed, git or no git; without a repository it is the
   file list, and the file entry's `paths` come from it. With no commits
   of your own, nothing uncommitted and nothing touched, tell the operator
   there is nothing to scan, and stop. Commits under `already_described` are work the last scan covered
   before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at the end of a chat, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

The window is yours: this chat's commits since your last scan of the
project, and what this chat changed that is not committed. Another agent's
commits are not in it — they are that agent's scan. A scan is written from
the work, not from git: what was done but not committed is in the scan too,
said as not committed. Without a repository the material still lists the
files this chat's tools changed. Group the work into themes. Each theme gets one
delta, or one line under `proof`: "Not covered: …". Nothing is left out
silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older chats and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```

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

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 10 · 2610-07 00:45 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what this chat changed in the project since its last scan, committed or not, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds your last
   scan of the project, this chat's commits since it (`window` says how it
   was drawn), the files with line counts, the uncommitted files, the
   `counters` already counted, and the `instructions` for all three
   entries. Follow those instructions: they are the operator's current
   ones. `others_commits_n` are commits made outside this chat since your
   last scan: not yours to describe. `touched` lists the files this
   chat's tools changed, git or no git; without a repository it is the
   file list, and the file entry's `paths` come from it. An uncommitted
   file with `mine: false` was changed by someone else in the same
   folder: leave it out. With no commits
   of your own, nothing uncommitted and nothing touched, tell the operator
   there is nothing to scan, and stop. Commits under `already_described` are work the last scan covered
   before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at the end of a chat, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

The window is yours: this chat's commits since your last scan of the
project, and what this chat changed that is not committed. Another agent's
commits are not in it — they are that agent's scan. A scan is written from
the work, not from git: what was done but not committed is in the scan too,
said as not committed. Without a repository the material still lists the
files this chat's tools changed. Group the work into themes. Each theme gets one
delta, or one line under `proof`: "Not covered: …". Nothing is left out
silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older chats and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```

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

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.

## Version 11 · 2610-07 01:05 · edited
> Built into Slightly Parallel

---
name: make-a-scan
description: "Write a Slightly Parallel scan: what this chat changed in the project since its last scan, committed or not, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds your last
   scan of the project, this chat's commits since it (`window` says how it
   was drawn), the files with line counts, the uncommitted files, the
   `counters` already counted, and the `instructions` for all three
   entries. Follow those instructions: they are the operator's current
   ones. `others_commits_n` are commits made outside this chat since your
   last scan: not yours to describe. `touched` lists the files this
   chat's tool calls changed (its helpers' too), git or no git. Without a
   repository `changed` adds the files found changed in the folder during
   this chat's turns — a shell command's edits, and anyone else's: keep
   only what this chat did. The file entry's `paths` come from the two. An uncommitted
   file with `mine: false` was changed by someone else in the same
   folder: leave it out. With no commits
   of your own, nothing uncommitted and nothing touched, tell the operator
   there is nothing to scan, and stop. Commits under `already_described` are work the last scan covered
   before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at the end of a chat, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

The window is yours: this chat's commits since your last scan of the
project, and what this chat changed that is not committed. Another agent's
commits are not in it — they are that agent's scan. A scan is written from
the work, not from git: what was done but not committed is in the scan too,
said as not committed. Without a repository the material still lists the
files this chat's tool calls changed and the files changed in the folder
during its turns. Group the work into themes. Each theme gets one
delta, or one line under `proof`: "Not covered: …". Nothing is left out
silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older chats and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```

**File entry — `write_entry {lens: "file"}`** (the second half of `#scan`).
The scan says what the work did; the file entry says *where in the code*
and how much each move matters — the judgment only you have. One
`paths` record per file you modified: `importance` 1–5,
`blast_radius` 1–10, `test_coverage` covered/partial/untested, `novelty`
new/pattern-follow/pattern-break, `security_surface`, `why`. Git supplies
what it can (action, line counts, the `diff`) — you supply the
assessment. `trigger_lens` = `"scan"`, `trigger_id` = the scan's id; the
scan answer shows `files_entry: null` until this is written. `summary`:
`N files · +X/−Y · theme`. `narrative`: the overall story, then a line
per file. `per_file`: one item per file, the functions and classes
touched, the ordering, and why.

```json
{"lens":"file","fields":{
  "summary":"3 files · +187/−4 · Redis rate-limit middleware",
  "narrative":"Redis-backed limiter landed on the request path. …",
  "per_file":["app/middleware/rate_limit.py — RateLimitMiddleware.dispatch: INCR+EXPIRE pipeline, 429 with Retry-After",
       "app/main.py — stack order CORS → Auth → RateLimit → router"],
  "trigger_lens":"scan","trigger_id":"sn_…","files_important_n":2,"files_ignored_n":1,
  "paths":[
   {"path":"app/middleware/rate_limit.py","importance":4,"blast_radius":10,
    "test_coverage":"covered","novelty":"new","security_surface":true,
    "why":"Every request passes through it; a bug here is an outage."},
   {"path":"app/main.py","importance":2,"blast_radius":6,"test_coverage":"covered",
    "why":"Middleware order — auth must run before the limiter."}]}}
```

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

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.
