---
key: report
section: 4
title: Finishing a task
enabled: true
command: #evidence | Get the operator's instructions with task_evidence_ask, then attach the evidence (Finishing a task, section 4)
---

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

A Storyboard document comes to you as a *pack*: one markdown the operator
copied, with the doc id (`dc_…`) on its second line. Make the document
final in the pack's shape, then post the whole text with
`doc_version {id, body, note}` — markdown body; `note` is one line on what
this version changed. Each post is the next version; the operator reads
and compares them on the Storyboard. An unknown id is refused.
