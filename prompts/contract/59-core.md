---
key: core
section: 4
title: Cores
enabled: true
command: #core-new <text> | A new core of the program, the thing the text names: give it a short name, a type and the files you know; the server saves the message as its first note (MCP tool core_new; the skill keep-a-core)
command: #core-note <text> | A note on a core: read `cores`, choose the matching core, add the message as typed with your one-line comment (core_note); if two match, ask the operator to choose by number first
command: #core | Attach this message, and this chat's task when it has one, to the matching core (core_attach); if two match, ask the operator to choose by number first
command: #core-off <words> | Remove a core from view: choose the matching core, ask the operator to confirm its number, then core_off; the notes and links are kept
brief: **Cores** (`#core-new <text>`, `#core-note <text>`, `#core`, `#core-off`). The program's core elements the operator keeps in view — a capability, a feature, a store, a part of the interface — each with its notes, tasks and commits. `#core-new` makes one: a short name, a type (capability · feature · interface · store · integration · internals · workflow · experiment), the files you know, the message as its first note (`core_new`). `#core-note` adds the message, as typed, with your one line (`core_note`); `#core` attaches the message and this chat's task (`core_attach`); `#core-off` removes one from view after the operator confirms (`core_off`). Read `cores` first and choose the matching core; if two match, ask the operator to choose by number. When the hook's notice names a tracked core and finished work changes it, add one line with `core_note {kind: "auto"}`. The skill `keep-a-core` holds the steps.
---

**Cores — the program's core elements, kept in view by the operator.** A
core is a thing in the program: chat capture, the ### suppressor, the
CSV + DuckDB store, the kanban. The operator names it; the server collects
what happens to it: notes, the tasks linked to it with their commits and
files, the commits in its files, the releases it went into. It is not a
feature tracker (no readiness, no dates), not a monitor (no alerts), not a
second board. The page is Architecture › cores.

- `#core-new <text>` → `core_new {name, type, reason?, anchors?, text, task_id?}`.
  `name`: short, at most 60 characters, the thing in the operator's words.
  `type`: one of capability · feature · interface · store · integration ·
  internals · workflow · experiment. `anchors`: the files or `file:symbol`
  paths this core is in, as far as you know from this chat (the server lists
  commits in those files apart from the notes). `text`: the operator's
  message as typed; the server saves it as the first note. Answer in one
  line: `cr_… · <name> · <type>`, with the files you set. The same name in
  view answers with the existing core: say so and add nothing.
- `#core-note <text>` → read `cores`, choose the core the text is about, then
  `core_note {id, text, comment}`: `text` the message as typed, `comment`
  your one line — what you did with it ("added to the release draft as a
  candidate") or what it means. Answer: `added → <name> (cr_…)`. If two
  cores match, ask first, in one line with numbers (`1 · <name>  2 · <name>
  3 · a new core "<words>"`), and wait. If none matches, offer a new core
  the same way. If there are no cores yet, say so and offer to make one.
- `#core` alone in a message → `core_attach {id, turn, task_id?}`: the
  message, and this chat's task when it has one, attached to the matching
  core. Choose as above.
- `#core-off <words>` → choose the matching core, ask the operator to
  confirm its number, then `core_off {id}`. The notes and links are kept;
  the operator restores it on its page.
- **Tracking.** The capture hook's notice on your first turn names the
  cores the operator tracks now. When work you *finish* (a task reported
  done, a `#done`, a revert) changes one of them, add one line:
  `core_note {id, comment, kind: "auto", task_id}` — what changed. Only
  finished work, not plans and not what you looked at; at most one note per
  task. With tracking off the server refuses an auto note: notes then come
  from the operator's `#core-note` only. Your notes wait for the operator's
  approval on the core's page; the operator's own count as approved.

Never: change a core's name, type or tracking (the operator does, on the
page); write a note about work you have not finished; attach by a word
match — attach what the message or the task is about.
