---
key: task
section: 4
title: Agent task
enabled: true
command: #task <hint> | Write the task the user is pointing at, from the conversation, into the `agent` column, for later; `#task {lane} …` names the board lane (section 4)
command: #now <text> | Title the task this chat starts on; the server keeps the operator's message as its text, in `doing`, in the lane for #now or the one in braces; then do the work; `#done` closes it (section 4)
command: #now-todo <text> | Title the operator's message; the server files it, as written, in To do (also `-next`, `-backlog`, `-review`, `-parked`, `-done`, `-doing`); not started in this chat (section 4)
brief: **Agent task** (`#task <hint>`, `#now <text>`, `#now-todo <text>`). Only when the user writes one of them, with `write_entry {lens: "task"}`. `#task`: you write the task from the conversation, title and text, into the `agent` column for later. `#now`: the task this chat starts on, in `doing`; `#now-todo` (`-next`, `-backlog`, `-review`, `-parked`, `-done`) files it in that column, not started. A `#now` task's text is the operator's message as written, kept by the server: you send the title and tags only. `{lane}` after the tag names the board lane; the server sets it. The skill `write-a-task` holds the steps.
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
