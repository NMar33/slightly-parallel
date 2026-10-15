---
id: sk_b9d4f00d
kind: skill
---

## Version 1 · 2609-20 12:40 · edited
> Built into Slightly Parallel

---
name: task-evidence
description: "Attach evidence to a Slightly Parallel task: the proof the operator asked for, plus what the task touched and what it did. Use when the operator types #evidence, or when a task_report answer says evidence is wanted."
---

Evidence is the operator's framework. The instructions are theirs; you
follow them. Two ways in, the same steps.

1. Get the instructions.
   - After `task_report {id, summary}`: the answer carries
     `evidence_prompt` and `evidence_extra`.
   - After `#evidence`: call `task_evidence_ask {id}` for the task being
     worked on. Same two fields, plus `work`: the files the repository saw.
2. Follow `evidence_prompt` first. It is the operator's text, verbatim.
   Usually 1–3 items, each with a one-line title saying what it shows:
   - `{kind: "text", title, body}`: markdown. Output, a request and its
     response, what you verified. Under a screenful.
   - `{kind: "image", title, data_base64, ext}`: a screenshot.
3. When `evidence_extra` is there, add two more items. Keep them short.
   - One `files` item: what was touched. Start from `work.files` (or call
     `task_work {id}`) and judge it: keep the files that matter, drop the
     rest. Per file: `path`, `action` (created · modified · deleted ·
     renamed), `lines_add`, `lines_del`, `importance` 1–5, and `why` in
     one sentence. Optional: `blast_radius` 1–10, `test_coverage`
     (covered · partial · untested), `security_surface`. Add
     `start_here`: the one file or `file:Symbol` to open first.
   - One `change` item: what landed. Per change: `op` (add · change ·
     remove), `type` (feature, fix, endpoint, command, module, config,
     database, tests, debt, and the rest of the architecture vocabulary),
     `name`, `path`, and `note` in one line. A fix is a type: its op is
     `add`.
4. Send everything in one call: `task_evidence {id, items}`. The same item
   sent twice is one item. A refusal names what is wrong: fix it and send
   again.

Example of the two extra items:

```json
[
  {"kind": "files", "title": "What the change touched",
   "start_here": "backend/routers/evidence.py:evidence_ask",
   "paths": [
     {"path": "backend/routers/evidence.py", "action": "modified",
      "lines_add": 40, "lines_del": 6, "importance": 5,
      "why": "The shared ask for both ways in."}
   ]},
  {"kind": "change", "title": "What landed",
   "changes": [
     {"op": "add", "type": "endpoint", "name": "GET /api/tasks/{id}/evidence/ask",
      "path": ["backend/routers/evidence.py"],
      "note": "the instructions for #evidence"}
   ]}
]
```

Check: open the task in Slightly Parallel. The proof comes first, the files and the
changes sit under it. A file marked "not in git" is one the repository did
not see in this task's turns: make sure you meant it.

Mistakes to avoid: listing every file instead of the ones that matter;
writing a long text where a test output would do; using a type as an op;
changing the task's status yourself.

## Version 2 · 2609-20 14:39 · edited
> Built into Slightly Parallel

---
name: task-evidence
description: "Attach evidence to a Slightly Parallel task: the proof the operator asked for, plus what the task touched and what it did. Use when the operator types #evidence, or when a task_report answer says evidence is wanted."
---

Evidence is the operator's framework. The instructions are theirs; you
follow them. Two ways in, the same steps.

1. Get the instructions.
   - After `task_report {id, summary}`: the answer carries
     `evidence_prompt` and `evidence_extra`.
   - After `#evidence`: call `task_evidence_ask {id}` for the task being
     worked on. Same two fields, plus `work`: the files the repository saw.
2. Follow `evidence_prompt` first. It is the operator's text, verbatim.
   Usually 1–3 items, each with a one-line title saying what it shows.
   Prove what the task asked for, not that the suite is green:
   - `{kind: "text", title, body}`: markdown. Output, a request and its
     response, what you verified. Under a screenful.
   - `{kind: "image", title, data_base64, ext}`: a screenshot.
3. When `evidence_extra` is there, add two more items. Keep them short.
   - One `files` item: what was touched. Start from `work.files` (or call
     `task_work {id}`) and judge it: keep up to seven files that matter,
     drop the rest. Per file: `path`, `action` (created · modified · deleted ·
     renamed), `lines_add`, `lines_del`, `importance` 1–5, and `why` in
     one sentence. Optional: `blast_radius` 1–10, `test_coverage`
     (covered · partial · untested), `security_surface`. Add
     `start_here`: the one file or `file:Symbol` to open first.
   - One `change` item: what landed. Per change: `op` (add · change ·
     remove), `type` (feature, fix, endpoint, command, module, config,
     database, tests, debt, and the rest of the architecture vocabulary),
     `name`, `path`, and `note` in one line. A fix is a type: its op is
     `add`.
4. Send everything in one call: `task_evidence {id, items}`. The same item
   sent twice is one item. A refusal names what is wrong: fix it and send
   again.

Example of the two extra items:

```json
[
  {"kind": "files", "title": "What the change touched",
   "start_here": "backend/routers/evidence.py:evidence_ask",
   "paths": [
     {"path": "backend/routers/evidence.py", "action": "modified",
      "lines_add": 40, "lines_del": 6, "importance": 5,
      "why": "The shared ask for both ways in."}
   ]},
  {"kind": "change", "title": "What landed",
   "changes": [
     {"op": "add", "type": "endpoint", "name": "GET /api/tasks/{id}/evidence/ask",
      "path": ["backend/routers/evidence.py"],
      "note": "the instructions for #evidence"}
   ]}
]
```

Check: open the task in Slightly Parallel. The proof comes first, the files and the
changes sit under it. A file marked "not in git" is one the repository did
not see in this task's turns: make sure you meant it.

Mistakes to avoid: listing every file instead of the ones that matter;
writing a long text where a test output would do; using a type as an op;
changing the task's status yourself.

## Version 3 · 2609-20 17:18 · edited
> Built into Slightly Parallel

---
name: task-evidence
description: "Attach evidence to a Slightly Parallel task: the proof the operator asked for, plus what the task touched and what it did. Use when the operator types #evidence, or when a task_report answer says evidence is wanted."
---

Evidence is the operator's framework. The instructions are theirs; you
follow them. Two ways in, the same steps.

1. Get the instructions.
   - After `task_report {id, summary}`: the answer carries
     `evidence_prompt` and `evidence_extra`.
   - After `#evidence`: the `[slightly-parallel] #evidence` notice names the task.
     Call `task_evidence_ask {id}` for it. If the notice names none, ask
     the user which task. Same two fields, plus `work`: the files the repository saw.
2. Follow `evidence_prompt` first. It is the operator's text, verbatim.
   Usually 1–3 items, each with a one-line title saying what it shows.
   Prove what the task asked for, not that the suite is green:
   - `{kind: "text", title, body}`: markdown. Output, a request and its
     response, what you verified. Under a screenful.
   - `{kind: "image", title, data_base64, ext}`: a screenshot.
3. When `evidence_extra` is there, add two more items. Keep them short.
   - One `files` item: what was touched. Start from `work.files` (or call
     `task_work {id}`) and judge it: keep up to seven files that matter,
     drop the rest. Per file: `path`, `action` (created · modified · deleted ·
     renamed), `lines_add`, `lines_del`, `importance` 1–5, and `why` in
     one sentence. Optional: `blast_radius` 1–10, `test_coverage`
     (covered · partial · untested), `security_surface`. Add
     `start_here`: the one file or `file:Symbol` to open first.
   - One `change` item: what landed. Per change: `op` (add · change ·
     remove), `type` (feature, fix, endpoint, command, module, config,
     database, tests, debt, and the rest of the architecture vocabulary),
     `name`, `path`, and `note` in one line. A fix is a type: its op is
     `add`.
4. Send everything in one call: `task_evidence {id, items}`. The same item
   sent twice is one item. A refusal names what is wrong: fix it and send
   again.

Example of the two extra items:

```json
[
  {"kind": "files", "title": "What the change touched",
   "start_here": "backend/routers/evidence.py:evidence_ask",
   "paths": [
     {"path": "backend/routers/evidence.py", "action": "modified",
      "lines_add": 40, "lines_del": 6, "importance": 5,
      "why": "The shared ask for both ways in."}
   ]},
  {"kind": "change", "title": "What landed",
   "changes": [
     {"op": "add", "type": "endpoint", "name": "GET /api/tasks/{id}/evidence/ask",
      "path": ["backend/routers/evidence.py"],
      "note": "the instructions for #evidence"}
   ]}
]
```

Check: open the task in Slightly Parallel. The proof comes first, the files and the
changes sit under it. A file marked "not in git" is one the repository did
not see in this task's turns: make sure you meant it.

Mistakes to avoid: listing every file instead of the ones that matter;
writing a long text where a test output would do; using a type as an op;
changing the task's status yourself.

## Version 4 · 2609-22 19:21 · edited
> Built into Slightly Parallel

---
name: task-evidence
description: "Attach evidence to a Slightly Parallel task: the proof the operator asked for, plus what the task touched and what it did. Use when the operator types #evidence, or when a task_report answer says evidence is wanted."
---

Evidence is the operator's framework. The instructions are theirs; you
follow them. Two ways in, the same steps. The contract's own text on
reporting and evidence is under *Finishing a task* below.

1. Get the instructions.
   - After `task_report {id, summary}`: the answer carries
     `evidence_prompt` and `evidence_extra`.
   - After `#evidence`: the `[slightly-parallel] #evidence` notice names the task.
     Call `task_evidence_ask {id}` for it. If the notice names none, ask
     the user which task. Same two fields, plus `work`: the files the repository saw.
2. Follow `evidence_prompt` first. It is the operator's text, verbatim.
   Each item carries a one-line title saying what it shows. Prove what the
   task asked for, not that the suite is green:
   - `{kind: "text", title, body}`: markdown. Output, a request and its
     response, what you verified. Under a screenful.
   - `{kind: "image", title, data_base64, ext}`: a screenshot.
3. When `evidence_extra` is there, add two more items. Keep them short.
   - One `files` item: what was touched. Start from `work.files` (or call
     `task_work {id}`) and judge it: keep up to seven files that matter,
     drop the rest. Per file: `path`, `action` (created · modified · deleted ·
     renamed), `lines_add`, `lines_del`, `importance` 1–5, and `why` in
     one sentence. Optional: `blast_radius` 1–10, `test_coverage`
     (covered · partial · untested), `security_surface`. Add
     `start_here`: the one file or `file:Symbol` to open first.
   - One `change` item: what landed. Per change: `op` (add · change ·
     remove), `type` (feature, fix, endpoint, command, module, config,
     database, tests, debt, and the rest of the architecture vocabulary),
     `name`, `path`, and `note` in one line. A fix is a type: its op is
     `add`.
4. Send everything in one call: `task_evidence {id, items}`. The same item
   sent twice is one item. A refusal names what is wrong: fix it and send
   again.

**Finishing a task — `task_report {id, summary}`.** Task status belongs to
the operator: never change a task's `status` yourself. When you believe a
task is done, report it — `summary` is one line: what shipped. The server
records your opinion (the operator sees a badge), moves the card to
*review* only if the operator switched auto-manage on for that task, and
answers with `evidence: true|false`. When evidence is wanted, the answer
carries the operator's instructions verbatim — follow them with
`task_evidence {id, items}`: each item is `{kind: "text", title, body}`
(markdown) or `{kind: "image", title, data_base64, ext}` (a screenshot).
At most 8 items per post; the operator's prompt usually asks for 1–3.
The same item written twice is one item.

**`#evidence`** is the same thing asked by hand. Call
`task_evidence_ask {id}` for the task the `[slightly-parallel] #evidence` notice
names: it returns the same instructions a done-report would have
carried. Follow them the same way.

Under the operator's instructions the answer may carry `evidence_extra`:
say what the task touched and what it did, as one `files` item and one
`change` item beside the proof. `task_work {id}` returns the files the
repository saw in the turns that named the task: read it before writing
the `files` item, so you judge the list instead of hunting for it. The
skill `task-evidence` holds the fields and an example. Keep both short: up
to seven files that matter, not every file.

Story notes on the Storyboard are the operator's field — write one only
when asked, and the ask arrives as a *press release request*: a prompt
from the operator that names a request id (`sr_…`). Answer it with
`task_story {id, request_id, body, images}` — markdown body; a screenshot
goes into the text as `![title](image:1)`, 1-based. Without an open
request id the write is refused; one piece per request, and the kind of
note is the one the operator asked for.

Example of the two extra items:

```json
[
  {"kind": "files", "title": "What the change touched",
   "start_here": "backend/routers/evidence.py:evidence_ask",
   "paths": [
     {"path": "backend/routers/evidence.py", "action": "modified",
      "lines_add": 40, "lines_del": 6, "importance": 5,
      "why": "The shared ask for both ways in."}
   ]},
  {"kind": "change", "title": "What landed",
   "changes": [
     {"op": "add", "type": "endpoint", "name": "GET /api/tasks/{id}/evidence/ask",
      "path": ["backend/routers/evidence.py"],
      "note": "the instructions for #evidence"}
   ]}
]
```

Check: open the task in Slightly Parallel. The proof comes first, the files and the
changes sit under it. A file marked "not in git" is one the repository did
not see in this task's turns: make sure you meant it.

Mistakes to avoid: listing every file instead of the ones that matter;
writing a long text where a test output would do; using a type as an op;
changing the task's status yourself.

## Version 5 · 2610-06 19:49 · edited
> Built into Slightly Parallel

---
name: task-evidence
description: "Attach evidence to a Slightly Parallel task: the proof the operator asked for, plus what the task touched and what it did. Use when the operator types #evidence, or when a task_report answer says evidence is wanted."
---

Evidence is the operator's framework. The instructions are theirs; you
follow them. Two ways in, the same steps. The contract's own text on
reporting and evidence is under *Finishing a task* below.

1. Get the instructions.
   - After `task_report {id, summary}`: the answer carries
     `evidence_prompt` and `evidence_extra`.
   - After `#evidence`: the `[slightly-parallel] #evidence` notice names the task.
     Call `task_evidence_ask {id}` for it. If the notice names none, ask
     the user which task. Same two fields, plus `work`: the files the repository saw.
2. Follow `evidence_prompt` first. It is the operator's text, verbatim.
   Each item carries a one-line title saying what it shows. Prove what the
   task asked for, not that the suite is green:
   - `{kind: "text", title, body}`: markdown. Output, a request and its
     response, what you verified. Under a screenful.
   - `{kind: "image", title, data_base64, ext}`: a screenshot.
3. When `evidence_extra` is there, add two more items. Keep them short.
   - One `files` item: what was touched. Start from `work.files` (or call
     `task_work {id}`) and judge it: keep up to seven files that matter,
     drop the rest. Per file: `path`, `action` (created · modified · deleted ·
     renamed), `lines_add`, `lines_del`, `importance` 1–5, and `why` in
     one sentence. Optional: `blast_radius` 1–10, `test_coverage`
     (covered · partial · untested), `security_surface`. Add
     `start_here`: the one file or `file:Symbol` to open first.
   - One `change` item: what landed. Per change: `op` (add · change ·
     remove), `type` (feature, fix, endpoint, command, module, config,
     database, tests, debt, and the rest of the architecture vocabulary),
     `name`, `path`, and `note` in one line. A fix is a type: its op is
     `add`.
4. Send everything in one call: `task_evidence {id, items}`. The same item
   sent twice is one item. A refusal names what is wrong: fix it and send
   again.

**Finishing a task — `task_report {id, summary}`.** Task status belongs to
the operator: never change a task's `status` yourself. When you believe a
task is done, report it — `summary` is one line: what shipped. The server
records your opinion (the operator sees a badge), moves the card to
*review* only if the operator switched auto-manage on for that task, and
answers with `evidence: true|false`. When evidence is wanted, the answer
carries the operator's instructions verbatim — follow them with
`task_evidence {id, items}`: each item is `{kind: "text", title, body}`
(markdown) or `{kind: "image", title, data_base64, ext}` (a screenshot).
At most 8 items per post; the operator's prompt usually asks for 1–3.
The same item written twice is one item.

**`#evidence`** is the same thing asked by hand. Call
`task_evidence_ask {id}` for the task the `[slightly-parallel] #evidence` notice
names: it returns the same instructions a done-report would have
carried. Follow them the same way.

Under the operator's instructions the answer may carry `evidence_extra`:
say what the task touched and what it did, as one `files` item and one
`change` item beside the proof. `task_work {id}` returns the files the
repository saw in the turns that named the task: read it before writing
the `files` item, so you judge the list instead of hunting for it. The
skill `task-evidence` holds the fields and an example. Keep both short: up
to seven files that matter, not every file.

Story notes on the Storyboard are the operator's field — write one only
when asked, and the ask arrives as a *press release request*: a prompt
from the operator that names a request id (`sr_…`). Answer it with
`task_story {id, request_id, body, images}` — markdown body; a screenshot
goes into the text as `![title](image:1)`, 1-based. Without an open
request id the write is refused; one piece per request, and the kind of
note is the one the operator asked for.

Example of the two extra items:

```json
[
  {"kind": "files", "title": "What the change touched",
   "start_here": "backend/routers/evidence.py:evidence_ask",
   "paths": [
     {"path": "backend/routers/evidence.py", "action": "modified",
      "lines_add": 40, "lines_del": 6, "importance": 5,
      "why": "The shared ask for both ways in."}
   ]},
  {"kind": "change", "title": "What landed",
   "changes": [
     {"op": "add", "type": "endpoint", "name": "GET /api/tasks/{id}/evidence/ask",
      "path": ["backend/routers/evidence.py"],
      "note": "the instructions for #evidence"}
   ]}
]
```

Check: open the task in Slightly Parallel. The proof comes first, the files and the
changes sit under it. A file marked "not in git" is one the repository did
not see in this task's turns: make sure you meant it.

Mistakes to avoid: listing every file instead of the ones that matter;
writing a long text where a test output would do; using a type as an op;
changing the task's status yourself.

## Version 6 · 2610-06 20:00 · edited
> Built into Slightly Parallel

---
name: task-evidence
description: "Attach evidence to a Slightly Parallel task: the proof the operator asked for, plus what the task touched and what it did. Use when the operator types #evidence, or when a task_report answer says evidence is wanted."
---

Evidence is the operator's framework. The instructions are theirs; you
follow them. Two ways in, the same steps. The contract's own text on
reporting and evidence is under *Finishing a task* below.

1. Get the instructions.
   - After `task_report {id, summary}`: the answer carries
     `evidence_prompt` and `evidence_extra`.
   - After `#evidence`: the `[slightly-parallel] #evidence` notice names the task.
     Call `task_evidence_ask {id}` for it. If the notice names none, ask
     the user which task. Same two fields, plus `work`: the files the repository saw.
2. Follow `evidence_prompt` first. It is the operator's text, verbatim.
   Each item carries a one-line title saying what it shows. Prove what the
   task asked for, not that the suite is green:
   - `{kind: "text", title, body}`: markdown. Output, a request and its
     response, what you verified. Under a screenful.
   - `{kind: "image", title, data_base64, ext}`: a screenshot.
3. When `evidence_extra` is there, add two more items. Keep them short.
   - One `files` item: what was touched. Start from `work.files` (or call
     `task_work {id}`) and judge it: keep up to seven files that matter,
     drop the rest. Per file: `path`, `action` (created · modified · deleted ·
     renamed), `lines_add`, `lines_del`, `importance` 1–5, and `why` in
     one sentence. Optional: `blast_radius` 1–10, `test_coverage`
     (covered · partial · untested), `security_surface`. Add
     `start_here`: the one file or `file:Symbol` to open first.
   - One `change` item: what landed. Per change: `op` (add · change ·
     remove), `type` (feature, fix, endpoint, command, module, config,
     database, tests, debt, and the rest of the architecture vocabulary),
     `name`, `path`, and `note` in one line. A fix is a type: its op is
     `add`.
4. Send everything in one call: `task_evidence {id, items}`. The same item
   sent twice is one item. A refusal names what is wrong: fix it and send
   again.

**Finishing a task — `task_report {id, summary}`.** Task status belongs to
the operator: never change a task's `status` yourself. When you believe a
task is done, report it — `summary` is one line: what shipped. The server
records your opinion (the operator sees a badge), moves the card to
*review* only if the operator switched auto-manage on for that task, and
answers with `evidence: true|false`. When evidence is wanted, the answer
carries the operator's instructions verbatim — follow them with
`task_evidence {id, items}`: each item is `{kind: "text", title, body}`
(markdown) or `{kind: "image", title, data_base64, ext}` (a screenshot).
At most 8 items per post; the operator's prompt usually asks for 1–3.
The same item written twice is one item.

**`#evidence`** is the same thing asked by hand. Call
`task_evidence_ask {id}` for the task the `[slightly-parallel] #evidence` notice
names: it returns the same instructions a done-report would have
carried. Follow them the same way.

Under the operator's instructions the answer may carry `evidence_extra`:
say what the task touched and what it did, as one `files` item and one
`change` item beside the proof. `task_work {id}` returns the files the
repository saw in the turns that named the task: read it before writing
the `files` item, so you judge the list instead of hunting for it. The
skill `task-evidence` holds the fields and an example. Keep both short: up
to seven files that matter, not every file.

Story notes on the Storyboard are the operator's field — write one only
when asked, and the ask arrives as a *press release request*: a prompt
from the operator that names a request id (`sr_…`). Answer it with
`task_story {id, request_id, body, images}` — markdown body; a screenshot
goes into the text as `![title](image:1)`, 1-based. Without an open
request id the write is refused; one piece per request, and the kind of
note is the one the operator asked for.

Example of the two extra items:

```json
[
  {"kind": "files", "title": "What the change touched",
   "start_here": "backend/routers/evidence.py:evidence_ask",
   "paths": [
     {"path": "backend/routers/evidence.py", "action": "modified",
      "lines_add": 40, "lines_del": 6, "importance": 5,
      "why": "The shared ask for both ways in."}
   ]},
  {"kind": "change", "title": "What landed",
   "changes": [
     {"op": "add", "type": "endpoint", "name": "GET /api/tasks/{id}/evidence/ask",
      "path": ["backend/routers/evidence.py"],
      "note": "the instructions for #evidence"}
   ]}
]
```

Check: open the task in Slightly Parallel. The proof comes first, the files and the
changes sit under it. A file marked "not in git" is one the repository did
not see in this task's turns: make sure you meant it.

Mistakes to avoid: listing every file instead of the ones that matter;
writing a long text where a test output would do; using a type as an op;
changing the task's status yourself.
