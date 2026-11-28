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

## Version 5 · 2610-20 14:36 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`).
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`.

## Version 6 · 2610-25 13:06 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`.

## Version 7 · 2610-26 00:51 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

**Commits.** Every commit you make for a task says so: end its message
with a blank line, then `Task: tk_…` (one line per task it serves) and
`Agent: <your agent_id>` (the identity notice gives it):

```
Hook: append a cut-off line on its own line

Task: tk_54406e4e
Agent: cc-25eaa814
```

That line is how the task's commits, files and time are counted, and with
two agents in one repository it is the only exact way. A commit for no
task has no `Task:` line. When a commit went out without it, link it with
`task_commits {id, shas}` (the commits notice names them on your next
turn): never amend or rewrite a commit for it.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`.

## Version 8 · 2611-05 12:28 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

**Commits.** Every commit you make for a task says so: end its message
with a blank line, then `Task: tk_…` (one line per task it serves) and
`Agent: <your agent_id>` (the identity notice gives it):

```
Hook: append a cut-off line on its own line

Task: tk_54406e4e
Agent: cc-25eaa814
```

That line is how the task's commits, files and time are counted, and with
two agents in one repository it is the only exact way. A commit for no
task has no `Task:` line. When a commit went out without it, link it with
`task_commits {id, shas}` (the commits notice names them on your next
turn): never amend or rewrite a commit for it.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags. Once that card is on
   the board, what you write next while working (a bug found, a thing
   left undone) is an ordinary task: `status: "agent"`, as with `#task`.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`.

## Version 9 · 2611-18 19:51 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them, or when the #task-title notice names a task the operator made from a message of this chat."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

**A task made from a message — the notice `#task-title`.** The operator
can make a task from one message of this chat (the terminal's message
menu); the server titles it from the message's first line for now. On
your next turn the notice names it once: give it a title with
`task_update {id, title}` — what it is about, in the operator's
language, ≤ 80 chars — and go on with the turn. Only the title, and only
once; a second title, or one after the operator renamed it, is refused.

**Commits.** Every commit you make for a task says so: end its message
with a blank line, then `Task: tk_…` (one line per task it serves) and
`Agent: <your agent_id>` (the identity notice gives it):

```
Hook: append a cut-off line on its own line

Task: tk_54406e4e
Agent: cc-25eaa814
```

That line is how the task's commits, files and time are counted, and with
two agents in one repository it is the only exact way. A commit for no
task has no `Task:` line. When a commit went out without it, link it with
`task_commits {id, shas}` (the commits notice names them on your next
turn): never amend or rewrite a commit for it.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags. Once that card is on
   the board, what you write next while working (a bug found, a thing
   left undone) is an ordinary task: `status: "agent"`, as with `#task`.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`; on `#task-title`, changing anything but
the title, or titling it twice.

## Version 10 · 2611-18 20:14 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them, or when the #task-title notice names a task the operator made from a message of this chat."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

**A task made from a message — the notice `#task-title`.** The operator
can make a task from one message of this chat (the terminal's message
menu); the server titles it from the message's first line for now. On
your next turn the notice names it once: give it a title with
`task_update {id, title}` — what it is about, in the operator's
language, ≤ 80 chars — and go on with the turn. Only the title, and only
once; a second title, or one after the operator renamed it, is refused.

**Commits.** Every commit you make for a task says so: end its message
with a blank line, then `Task: tk_…` (one line per task it serves) and
`Agent: <your agent_id>` (the identity notice gives it):

```
Hook: append a cut-off line on its own line

Task: tk_54406e4e
Agent: cc-25eaa814
```

That line is how the task's commits, files and time are counted, and with
two agents in one repository it is the only exact way. A commit for no
task has no `Task:` line. When a commit went out without it, link it with
`task_commits {id, shas}` (the commits notice names them on your next
turn): never amend or rewrite a commit for it.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags. Once that card is on
   the board, what you write next while working (a bug found, a thing
   left undone) is an ordinary task: `status: "agent"`, as with `#task`.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
   sprint, due date, lane, assignee and the rest are the operator's; the
   server drops them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag> · <column> · <lane>`.
   "Drop it" → `task_update {id, status: "done-archived"}` — the only
   status change you ever make, on a card you created. `task_update` takes
   `title`, `description` and `today_on` as well, on a card you created
   only (a `#now` card you wrote or the server wrote for your chat counts;
   its text stays the operator's). On the operator's card or another
   agent's they are refused: add a `comment` instead, open on any task.
   Sprint, priority, due date and the operator's switches are refused by
   name.

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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`; on `#task-title`, changing anything but
the title, or titling it twice; changing the title, text or day of a card
you did not create.

## Version 11 · 2611-26 12:21 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them, or when the #task-title notice names a task the operator made from a message of this chat."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

**A task to think through — `#think`, `#think-off`.** A task marked
«think» is one the operator thinks through himself. `#think` beside
`#now`, `#now-todo` or `#task` marks the card that message makes (write
it as usual; the server sets the mark); `#think tk_…` marks those tasks;
`#think-off tk_…` removes the mark. With no task named, ask which, in one
line. While the mark is on, the server refuses your status, lane and
assignee changes, your `task_report` and an archive of the task, with a
reason that names the mark. You may still read it, comment
(`task_update {id, comment}`), add notes, evidence and links, gather
context, propose options and ask the operator. Only the operator removes
the mark: the badge's × on the board or in the task window, or
`#think-off`. The operator's own `#done` still closes it.

**A task made from a message — the notice `#task-title`.** The operator
can make a task from one message of this chat (the terminal's message
menu); the server titles it from the message's first line for now. On
your next turn the notice names it once: give it a title with
`task_update {id, title}` — what it is about, in the operator's
language, ≤ 80 chars — and go on with the turn. Only the title, and only
once; a second title, or one after the operator renamed it, is refused.

**Commits.** Every commit you make for a task says so: end its message
with a blank line, then `Task: tk_…` (one line per task it serves) and
`Agent: <your agent_id>` (the identity notice gives it):

```
Hook: append a cut-off line on its own line

Task: tk_54406e4e
Agent: cc-25eaa814
```

That line is how the task's commits, files and time are counted, and with
two agents in one repository it is the only exact way. A commit for no
task has no `Task:` line. When a commit went out without it, link it with
`task_commits {id, shas}` (the commits notice names them on your next
turn): never amend or rewrite a commit for it.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags. Once that card is on
   the board, what you write next while working (a bug found, a thing
   left undone) is an ordinary task: `status: "agent"`, as with `#task`.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
   sprint, due date, lane, assignee and the rest are the operator's; the
   server drops them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag> · <column> · <lane>`.
   "Drop it" → `task_update {id, status: "done-archived"}` — the only
   status change you ever make, on a card you created. `task_update` takes
   `title`, `description` and `today_on` as well, on a card you created
   only (a `#now` card you wrote or the server wrote for your chat counts;
   its text stays the operator's). On the operator's card or another
   agent's they are refused: add a `comment` instead, open on any task.
   Sprint, priority, due date and the operator's switches are refused by
   name.

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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`; on `#task-title`, changing anything but
the title, or titling it twice; changing the title, text or day of a card
you did not create.

## Version 12 · 2611-26 17:44 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them, or when the #task-title notice names a task the operator made from a message of this chat."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

**A task to think through — `#think`, `#think-off`.** A task marked
«think» is one the operator thinks through himself. `#think` beside
`#now`, `#now-todo` or `#task` marks the card that message makes (write
it as usual; the server sets the mark); `#think tk_…` marks the ids
written right beside the tag, never others in the message;
`#think-off tk_…` removes the mark. With no task named, ask which, in one
line. While the mark is on, the server refuses your status, lane and
assignee changes, your `task_report` and an archive of the task, with a
reason that names the mark. You may still read it, comment
(`task_update {id, comment}`), add notes, evidence and links, gather
context, propose options and ask the operator. Only the operator removes
the mark: the badge's × on the board or in the task window, or
`#think-off`. The operator's own `#done` closes it and clears the mark;
your `task_report` after it goes through.

**A task made from a message — the notice `#task-title`.** The operator
can make a task from one message of this chat (the terminal's message
menu); the server titles it from the message's first line for now. On
your next turn the notice names it once: give it a title with
`task_update {id, title}` — what it is about, in the operator's
language, ≤ 80 chars — and go on with the turn. Only the title, and only
once; a second title, or one after the operator renamed it, is refused.

**Commits.** Every commit you make for a task says so: end its message
with a blank line, then `Task: tk_…` (one line per task it serves) and
`Agent: <your agent_id>` (the identity notice gives it):

```
Hook: append a cut-off line on its own line

Task: tk_54406e4e
Agent: cc-25eaa814
```

That line is how the task's commits, files and time are counted, and with
two agents in one repository it is the only exact way. A commit for no
task has no `Task:` line. When a commit went out without it, link it with
`task_commits {id, shas}` (the commits notice names them on your next
turn): never amend or rewrite a commit for it.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags. Once that card is on
   the board, what you write next while working (a bug found, a thing
   left undone) is an ordinary task: `status: "agent"`, as with `#task`.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
   sprint, due date, lane, assignee and the rest are the operator's; the
   server drops them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag> · <column> · <lane>`.
   "Drop it" → `task_update {id, status: "done-archived"}` — the only
   status change you ever make, on a card you created. `task_update` takes
   `title`, `description` and `today_on` as well, on a card you created
   only (a `#now` card you wrote or the server wrote for your chat counts;
   its text stays the operator's). On the operator's card or another
   agent's they are refused: add a `comment` instead, open on any task.
   Sprint, priority, due date and the operator's switches are refused by
   name.

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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`; on `#task-title`, changing anything but
the title, or titling it twice; changing the title, text or day of a card
you did not create.

## Version 13 · 2611-26 18:04 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them, or when the #task-title notice names a task the operator made from a message of this chat."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

**A task to think through — `#think`, `#think-off`.** A task marked
«think» is one the operator thinks through himself. `#think` beside
`#now`, `#now-todo` or `#task` marks the card that message makes (write
it as usual; the server sets the mark); `#think tk_…` marks the ids
written right beside the tag, never others in the message;
`#think-off tk_…` removes the mark. With no task named, ask which, in one
line. While the mark is on, the server refuses your status, lane and
assignee changes, your `task_report`, an archive of the task and a move
to another project, with a reason that names the mark. You may still read it, comment
(`task_update {id, comment}`), add notes, evidence and links, gather
context, propose options and ask the operator. Only the operator removes
the mark: the badge's × on the board or in the task window, or
`#think-off`. The operator's own `#done` closes it and clears the mark;
your `task_report` after it goes through.

**A task made from a message — the notice `#task-title`.** The operator
can make a task from one message of this chat (the terminal's message
menu); the server titles it from the message's first line for now. On
your next turn the notice names it once: give it a title with
`task_update {id, title}` — what it is about, in the operator's
language, ≤ 80 chars — and go on with the turn. Only the title, and only
once; a second title, or one after the operator renamed it, is refused.

**Commits.** Every commit you make for a task says so: end its message
with a blank line, then `Task: tk_…` (one line per task it serves) and
`Agent: <your agent_id>` (the identity notice gives it):

```
Hook: append a cut-off line on its own line

Task: tk_54406e4e
Agent: cc-25eaa814
```

That line is how the task's commits, files and time are counted, and with
two agents in one repository it is the only exact way. A commit for no
task has no `Task:` line. When a commit went out without it, link it with
`task_commits {id, shas}` (the commits notice names them on your next
turn): never amend or rewrite a commit for it.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane; you never send `lane` or
`assignee` (the server drops them). A lane the board does not have is
refused with the board's lanes: ask the operator which, in one line, and
write when they answer. The notice from the capture hook says this before
you start.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags. Once that card is on
   the board, what you write next while working (a bug found, a thing
   left undone) is an ordinary task: `status: "agent"`, as with `#task`.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. No other field: priority, impact, effort,
   sprint, due date, lane, assignee and the rest are the operator's; the
   server drops them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag> · <column> · <lane>`.
   "Drop it" → `task_update {id, status: "done-archived"}` — the only
   status change you ever make, on a card you created. `task_update` takes
   `title`, `description` and `today_on` as well, on a card you created
   only (a `#now` card you wrote or the server wrote for your chat counts;
   its text stays the operator's). On the operator's card or another
   agent's they are refused: add a `comment` instead, open on any task.
   Sprint, priority, due date and the operator's switches are refused by
   name.

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
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`; on `#task-title`, changing anything but
the title, or titling it twice; changing the title, text or day of a card
you did not create.

## Version 14 · 2611-28 01:20 · edited
> Built into Slightly Parallel

---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them, or when the #task-title notice names a task the operator made from a message of this chat."
---

**Agent task — `#task <hint>` / `#now <text>` → `write_entry {lens: "task"}`.**
Only when the user writes one of them. They differ in who writes the text
and when the work happens:

- `#task` — a task for later, written by you: you hold the context the
  operator would otherwise have to type. The hint says which thing; the
  conversation holds everything else. The card lands in the `agent`
  column; the operator drags it out, which is the review.
- `#now` — the task this chat starts on, now. Its text is the operator's
  message, exactly as written: the server takes it from the captured chat.
  You send the `title` and `tags` only; a `description` is refused. The
  card lands in `doing`, in the lane for `#now` (Settings › Tasks; `Now`
  unless changed), marked for today, with "started in the chat" in its
  history. Write it first, then do the work. `#done` closes it (the skill
  `finish-a-task`). A turn that ends with no card gets one from the server,
  titled with the operator's own words; a later write is refused and names
  that card: retitle it with `task_update {id, title}`. A note of yours
  goes after the operator's text with `task_update {id, comment}` (each
  call adds one, under `--- comment from agent:`); the card's own text is
  the operator's and is not rewritten.
- `#now-todo` — the same card, filed in To do instead, and not started:
  write it, say so in one line, and go on with what the chat was doing.
  `#now-next`, `#now-backlog`, `#now-review`, `#now-parked` and
  `#now-done` file it in those columns; `#now-doing` is `#now`.

**A task to think through — `#think`, `#think-off`.** A task marked
«think» is one the operator thinks through himself. `#think` beside
`#now`, `#now-todo` or `#task` marks the card that message makes (write
it as usual; the server sets the mark); `#think tk_…` marks the ids
written right beside the tag, never others in the message;
`#think-off tk_…` removes the mark. With no task named, ask which, in one
line. While the mark is on, the server refuses your status, lane and
assignee changes, your `task_report`, an archive of the task and a move
to another project, with a reason that names the mark. You may still read it, comment
(`task_update {id, comment}`), add notes, evidence and links, gather
context, propose options and ask the operator. Only the operator removes
the mark: the badge's × on the board or in the task window, or
`#think-off`. The operator's own `#done` closes it and clears the mark;
your `task_report` after it goes through.

**A task made from a message — the notice `#task-title`.** The operator
can make a task from one message of this chat (the terminal's message
menu); the server titles it from the message's first line for now. On
your next turn the notice names it once: give it a title with
`task_update {id, title}` — what it is about, in the operator's
language, ≤ 80 chars — and go on with the turn. Only the title, and only
once; a second title, or one after the operator renamed it, is refused.

**Commits.** Every commit you make for a task says so: end its message
with a blank line, then `Task: tk_…` (one line per task it serves) and
`Agent: <your agent_id>` (the identity notice gives it):

```
Hook: append a cut-off line on its own line

Task: tk_54406e4e
Agent: cc-25eaa814
```

That line is how the task's commits, files and time are counted, and with
two agents in one repository it is the only exact way. A commit for no
task has no `Task:` line. When a commit went out without it, link it with
`task_commits {id, shas}` (the commits notice names them on your next
turn): never amend or rewrite a commit for it.

`{lane}` right after either tag names the board lane: `#now {ui} fix the
login timeout`, `#task {Kanban Board} the cards do not sort`. The server
reads it from the message and sets the lane. If the spelling is close to
an existing lane, write the card at once. Its chip lets the operator
create the named lane or pick a suggestion. An exact agent lane named
by the operator moves onto the board with its cards. A new name opens a
board lane. An agent filing its own card can send `lane` to use an
existing lane or create one in the collapsed Agents group. A close
spelling in an agent's write is refused with the matching names.

1. Find it. `#now` (any column): the operator's message is the task; you
   only title it — skip to step 3, title and tags. Once that card is on
   the board, what you write next while working (a bug found, a thing
   left undone) is an ordinary task: `status: "agent"`, as with `#task`.
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
   `doing` for `#now`, the named column for `#now-todo` and the rest, or
   none — the server knows which the operator wrote and refuses another.
   For any `#now` there is no `description`: the server writes the
   operator's message in. For an agent's own card, `lane` can select an
   existing lane or start one in Agents when the operator did not name a
   lane. Priority, impact, effort, sprint, due date and other planning
   fields are the operator's; the server names dropped fields as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag> · <column> · <lane>`.
   "Drop it" → `task_update {id, status: "done-archived"}` — the only
   status change you ever make, on a card you created. `task_update` takes
   `title`, `description` and `today_on` as well, on a card you created
   only (a `#now` card you wrote or the server wrote for your chat counts;
   its text stays the operator's). On the operator's card or another
   agent's they are refused: add a `comment` instead, open on any task.
   Sprint, priority, due date and the operator's switches are refused by
   name.

```json
{"lens":"task","fields":{"title":"Architecture form without a scan",
  "status":"agent","tags":"ag_followup",
  "description":"rn the architecture form accepts an empty trigger_id, so an agent can write a form outside of #scan (the first one landed as 'without a scan' on the tab). It should be only with #scan — refuse a form without a scan id, drop the 'without a scan' bucket.\nbackend/backend/routers/architecture.py:architecture_form · frontend/src/features/project/ArchitectureTab.tsx:LooseCard"}}
```

The server refuses: a status other than the one the operator's command
asks for, no tag or a tag outside `ag_*`, more than three tags, a title
missing or over 80 characters, and an agent's lane name close to an
existing one. Writing the same task twice answers with the existing one.

Check: the reply carries the task's id, and the card shows on the project's
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint or a due date;
sending a lane for the operator's #now card; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`; on `#task-title`, changing anything but
the title, or titling it twice; changing the title, text or day of a card
you did not create.
