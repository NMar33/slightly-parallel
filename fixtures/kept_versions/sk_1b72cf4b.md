---
id: sk_1b72cf4b
kind: skill
---

## Version 1 · 2610-25 13:06 · edited
> Built into Slightly Parallel

---
name: keep-a-core
description: "Keep the program's cores for Slightly Parallel: #core-new makes a core from the operator's message (a short name, a type, the anchors you know), #core-note adds the message as a note with your one line, #core attaches the message and this chat's task, #core-off takes one out of view after the operator confirms; and the one-line auto note when work you finish changes a tracked core. Use when the operator types one of them or the hook's notice names tracked cores."
---

**Cores — the program's core elements, kept in view by the operator.** A
core is a noun about the program: chat capture, the ### suppressor, the
CSV + DuckDB store, the kanban. The operator names it; the product gathers
its story: notes, the tasks attached to it with their commits and files,
the commits that touched its anchors, the releases it went into. It is not
a feature tracker (no readiness, no dates), not a monitor (no alerts), not
a second board. The page is Architecture › cores.

- `#core-new <text>` → `core_new {name, type, reason?, anchors?, text, task_id?}`.
  `name`: short, at most 60 characters, the thing in the operator's words.
  `type`: one of capability · feature · surface · store · integration ·
  engine · workflow · experiment. `anchors`: the files or `file:symbol`
  paths you know it lives in from this chat (the server shows commits on
  them apart, as "touched nearby"). `text`: the operator's message as typed
  — the server keeps it as the core's founding note. Answer in one line:
  `cr_… · <name> · <type>`, with the anchors you set. The same name in view
  answers with the existing core: say so, add nothing.
- `#core-note <text>` → read `cores`, pick the core the text is about, then
  `core_note {id, text, comment}`: `text` the message as typed, `comment`
  your one line — what you did with it ("put on the release draft as a
  candidate"), or what it means. Answer: `added → <name> (cr_…)`. Two cores
  fit: ask first, with numbers, one line (`1 · <name>  2 · <name>  3 · a
  new core "<words>"`), and wait. None fits: offer a new core the same way.
  No cores yet: say so and offer to make one.
- `#core` alone in a message → `core_attach {id, turn, task_id?}`: the
  message, and this chat's task when it has one, attached to the core it
  is about. Pick by sense as above.
- `#core-off <words>` → name the core by sense, ask the operator to
  confirm with a number, then `core_off {id}`. The story and the links
  stay; the operator brings it back on its page.
- **Tracking.** The capture hook's notice on your first turn names the
  cores the operator tracks right now. When work you *finish* (a task
  reported done, a `#done`, a revert) changes one of them, add one line:
  `core_note {id, comment, kind: "auto", task_id}` — what is different now.
  Not intentions, not what you looked at, at most one note per task. With
  tracking off the server refuses an auto note: notes then come from the
  operator's `#core-note` only. Your notes wait for the operator's
  approval on the core's page; the operator's own are approved as written.

What you never do: change a core's name, type or tracking (the operator's,
on the page); write a note about work you have not finished; attach by a
word match — attach what the message or the task is about.

Check: the reply carries the core's id (`cr_…`) or the note's (`cn_…`), and
the core shows on Architecture › cores of the project; a `#core-note` shows
on the core's page with the operator's text above your comment.

Mistakes to avoid: making a second core for a thing that has one (the same
name answers with the existing core — say so); choosing a core by a word
match instead of by what the message is about; asking the operator for an
id (you pick by sense, the operator picks by number); an auto note on work
you have not finished, or more than one per task; a note that narrates
("looked at", "started") instead of saying what is different now.

## Version 2 · 2610-25 13:49 · edited
> Built into Slightly Parallel

---
name: keep-a-core
description: "Keep the program's cores for Slightly Parallel: #core-new makes a core from the operator's message (a short name, a type, the files you know), #core-note adds the message as a note with your one line, #core attaches the message and this chat's task, #core-off removes one from view after the operator confirms; and the one-line auto note when finished work changes a tracked core. Use when the operator types one of them or the hook's notice names tracked cores."
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

Check: the reply carries the core's id (`cr_…`) or the note's (`cn_…`), and
the core shows on Architecture › cores of the project; a `#core-note` shows
on the core's page with the operator's text above your comment.

Mistakes to avoid: making a second core for a thing that has one (the same
name answers with the existing core — say so); choosing a core by a word
match instead of by what the message is about; asking the operator for an
id (you choose the core, the operator confirms by number); an auto note on
work you have not finished, or more than one per task; a note that narrates
("looked at", "started") instead of saying what changed.
