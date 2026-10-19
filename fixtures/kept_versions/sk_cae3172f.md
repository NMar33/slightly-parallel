---
id: sk_cae3172f
kind: skill
---

## Version 1 · 2609-21 01:48 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves. Use only when the operator types #task, with or without a hint."
---

**Agent task — `#task <hint>` → `write_entry {lens: "task"}`.** Only when
the user writes `#task`. You write the task the user would type themselves
if they had the time; you do it because you hold the context. The hint
says which thing; the conversation holds everything else.

1. Find it. Go back through the conversation to where this thing came up
   — a bug noticed, an idea raised, a step deferred, a thing left undone.
   Empty hint = the last such thing not yet done. Two things fit → ask
   which, one line, before writing. After a context compaction the exact
   words may be gone: say "from memory, not verbatim" rather than
   reconstruct them as quotes.
2. Pull out what belongs to it and only that: what the user wants, in the
   user's phrasing; what is already settled about it — constraints,
   rejected options, decisions taken; what it is attached to — URLs, ids,
   paths, the task in progress. Leave out what was done already, what was
   only mentioned in passing, and anything the user did not ask for.
3. Write the task, not the conversation: no quotes of who said what, no
   history of how it was reached — the state of it now: what is wrong or
   wanted, and where. `title`: the thing, in the user's words, ≤ 80
   chars. `description`: 2–6 plain lines from step 2, nothing added.
   `tags`: 1–3 of `ag_debt · ag_bug · ag_followup · ag_idea ·
   ag_decision`, the first is the main one. `status: "agent"` — the only
   status you may create with; the operator drags the
   card out of that column, which is the review. `lane` / `assignee` only
   if the user named one. No other field: priority, impact, effort,
   sprint, due date and the rest are the operator's; the server drops
   them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag>`. "Drop it" →
   `task_update {id, status: "done-archived"}` — the only status change
   you ever make, on a card you created.

```json
{"lens":"task","fields":{"title":"Architecture form without a scan",
  "status":"agent","tags":"ag_followup",
  "description":"rn the architecture form accepts an empty trigger_id, so an agent can write a form outside of #scan (the first one landed as 'without a scan' on the tab). It should be only with #scan — refuse a form without a scan id, drop the 'without a scan' bucket.\nbackend/backend/routers/architecture.py:architecture_form · frontend/src/features/project/ArchitectureTab.tsx:LooseCard"}}
```

The server refuses: a status other than `agent` from an agent, no tag or
a tag outside `ag_*`, more than three tags, a title missing or over 80
characters. Writing the same task twice answers with the existing one.

Check: the reply carries the task's id, and the card shows in the Agent
column of the project's board.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint or a due date;
any status other than `agent`.

## Version 2 · 2609-22 19:21 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves. Use only when the operator types #task, with or without a hint."
---

**Agent task — `#task <hint>` → `write_entry {lens: "task"}`.** Only when
the user writes `#task`. You write the task the user would type themselves
if they had the time; you do it because you hold the context. The hint
says which thing; the conversation holds everything else.

1. Find it. Go back through the conversation to where this thing came up
   — a bug noticed, an idea raised, a step deferred, a thing left undone.
   Empty hint = the last such thing not yet done. Two things fit → ask
   which, one line, before writing. After a context compaction the exact
   words may be gone: say "from memory, not verbatim" rather than
   reconstruct them as quotes.
2. Pull out what belongs to it and only that: what the user wants, in the
   user's phrasing; what is already settled about it — constraints,
   rejected options, decisions taken; what it is attached to — URLs, ids,
   paths, the task in progress. Leave out what was done already, what was
   only mentioned in passing, and anything the user did not ask for.
3. Write the task, not the conversation: no quotes of who said what, no
   history of how it was reached — the state of it now: what is wrong or
   wanted, and where. `title`: the thing, in the user's words, ≤ 80
   chars. `description`: 2–6 plain lines from step 2, nothing added.
   `tags`: 1–3 of `ag_debt · ag_bug · ag_followup · ag_idea ·
   ag_decision`, the first is the main one. `status: "agent"` — the only
   status you may create with; the operator drags the
   card out of that column, which is the review. `lane` / `assignee` only
   if the user named one. No other field: priority, impact, effort,
   sprint, due date and the rest are the operator's; the server drops
   them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag>`. "Drop it" →
   `task_update {id, status: "done-archived"}` — the only status change
   you ever make, on a card you created. `task_update` takes `title`,
   `description` and `today_on` as well; sprint, priority, due date and
   the operator's switches are refused by name.

```json
{"lens":"task","fields":{"title":"Architecture form without a scan",
  "status":"agent","tags":"ag_followup",
  "description":"rn the architecture form accepts an empty trigger_id, so an agent can write a form outside of #scan (the first one landed as 'without a scan' on the tab). It should be only with #scan — refuse a form without a scan id, drop the 'without a scan' bucket.\nbackend/backend/routers/architecture.py:architecture_form · frontend/src/features/project/ArchitectureTab.tsx:LooseCard"}}
```

The server refuses: a status other than `agent` from an agent, no tag or
a tag outside `ag_*`, more than three tags, a title missing or over 80
characters. Writing the same task twice answers with the existing one.

Check: the reply carries the task's id, and the card shows in the Agent
column of the project's board.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint or a due date;
any status other than `agent`.

## Version 3 · 2610-06 19:49 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves. Use only when the operator types #task, with or without a hint."
---

**Agent task — `#task <hint>` → `write_entry {lens: "task"}`.** Only when
the user writes `#task`. You write the task the user would type themselves
if they had the time; you do it because you hold the context. The hint
says which thing; the conversation holds everything else.

1. Find it. Go back through the conversation to where this thing came up
   — a bug noticed, an idea raised, a step deferred, a thing left undone.
   Empty hint = the last such thing not yet done. Two things fit → ask
   which, one line, before writing. After a context compaction the exact
   words may be gone: say "from memory, not verbatim" rather than
   reconstruct them as quotes.
2. Pull out what belongs to it and only that: what the user wants, in the
   user's phrasing; what is already settled about it — constraints,
   rejected options, decisions taken; what it is attached to — URLs, ids,
   paths, the task in progress. Leave out what was done already, what was
   only mentioned in passing, and anything the user did not ask for.
3. Write the task, not the conversation: no quotes of who said what, no
   history of how it was reached — the state of it now: what is wrong or
   wanted, and where. `title`: the thing, in the user's words, ≤ 80
   chars. `description`: 2–6 plain lines from step 2, nothing added.
   `tags`: 1–3 of `ag_debt · ag_bug · ag_followup · ag_idea ·
   ag_decision`, the first is the main one. `status: "agent"` — the only
   status you may create with; the operator drags the
   card out of that column, which is the review. `lane` / `assignee` only
   if the user named one. No other field: priority, impact, effort,
   sprint, due date and the rest are the operator's; the server drops
   them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag>`. "Drop it" →
   `task_update {id, status: "done-archived"}` — the only status change
   you ever make, on a card you created. `task_update` takes `title`,
   `description` and `today_on` as well; sprint, priority, due date and
   the operator's switches are refused by name.

```json
{"lens":"task","fields":{"title":"Architecture form without a scan",
  "status":"agent","tags":"ag_followup",
  "description":"rn the architecture form accepts an empty trigger_id, so an agent can write a form outside of #scan (the first one landed as 'without a scan' on the tab). It should be only with #scan — refuse a form without a scan id, drop the 'without a scan' bucket.\nbackend/backend/routers/architecture.py:architecture_form · frontend/src/features/project/ArchitectureTab.tsx:LooseCard"}}
```

The server refuses: a status other than `agent` from an agent, no tag or
a tag outside `ag_*`, more than three tags, a title missing or over 80
characters. Writing the same task twice answers with the existing one.

Check: the reply carries the task's id, and the card shows in the Agent
column of the project's board.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint or a due date;
any status other than `agent`.

## Version 4 · 2610-18 16:53 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing). Use only when the operator types one of them."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. You write the task the user would
type themselves if they had the time; you do it because you hold the
context. The two differ in when the work happens:

- `#task` — a task for later. The hint says which thing; the conversation
  holds everything else. The card lands in the `agent` column; the
  operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. The text after the tag is
  the task. The card lands in `doing`, in the lane for `#now` (Settings ›
  Tasks; `Now` unless changed), marked for today, with "started in the
  chat" in its history. Write it first, then do the work. `#done` closes
  it (the skill `finish-a-task`).

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now`: the text after the tag, as the operator wrote it.
   `#task`: go back through the conversation to where this thing came up
   — a bug noticed, an idea raised, a step deferred, a thing left undone.
   Empty hint = the last such thing not yet done. Two things fit → ask
   which, one line, before writing. After a context compaction the exact
   words may be gone: say "from memory, not verbatim" rather than
   reconstruct them as quotes.
2. Pull out what belongs to it and only that: what the user wants, in the
   user's phrasing; what is already settled about it — constraints,
   rejected options, decisions taken; what it is attached to — URLs, ids,
   paths, the task in progress. Leave out what was done already, what was
   only mentioned in passing, and anything the user did not ask for.
3. Write the task, not the conversation: no quotes of who said what, no
   history of how it was reached — the state of it now: what is wrong or
   wanted, and where. `title`: the thing, in the user's words, ≤ 80
   chars. `description`: 2–6 plain lines from step 2, nothing added.
   `tags`: 1–3 of `ag_debt · ag_bug · ag_followup · ag_idea ·
   ag_decision`, the first is the main one. `status`: `agent` for `#task`,
   `doing` for `#now`, or none — the server knows which the operator
   wrote and refuses the other. No other field: priority, impact, effort,
   sprint, due date, lane, assignee and the rest are the operator's; the
   server drops them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag> · <column> · <lane>`.
   "Drop it" → `task_update {id, status: "done-archived"}` — the only
   status change you ever make, on a card you created. `task_update` takes
   `title`, `description` and `today_on` as well; sprint, priority, due
   date and the operator's switches are refused by name.

```json
{"lens":"task","fields":{"title":"Architecture form without a scan",
  "status":"agent","tags":"ag_followup",
  "description":"rn the architecture form accepts an empty trigger_id, so an agent can write a form outside of #scan (the first one landed as 'without a scan' on the tab). It should be only with #scan — refuse a form without a scan id, drop the 'without a scan' bucket.\nbackend/backend/routers/architecture.py:architecture_form · frontend/src/features/project/ArchitectureTab.tsx:LooseCard"}}
```

The server refuses: a status other than the one the operator's command
asks for, no tag or a tag outside `ag_*`, more than three tags, a title
missing or over 80 characters, a lane the board does not have. Writing
the same task twice answers with the existing one.

Check: the reply carries the task's id, and the card shows on the project's
board: `#task` in the Agent column, `#now` in doing, in its lane.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; starting the
work before the `#now` card is written.
