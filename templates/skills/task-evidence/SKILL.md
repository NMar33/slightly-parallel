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

{{part:report}}

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
