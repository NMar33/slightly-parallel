---
key: task
section: 4
title: Agent task
enabled: true
command: #task <hint> | Write the task the user is pointing at, from the conversation, into the `agent` column, for later; `#task {lane} …` names the board lane (section 4)
command: #now <text> | Title the task this chat starts on; the server keeps the operator's message as its text, in `doing`, in the lane for #now or the one in braces; then do the work; `#done` closes it (section 4)
command: #now-todo <text> | Title the operator's message; the server files it, as written, in To do (also `-next`, `-backlog`, `-review`, `-parked`, `-done`, `-doing`); not started in this chat (section 4)
command: #think <tk_… or with #now / #task> | Nothing to write — the server marks the task as the operator's to think through: never start, move or finish it; comment, note and ask instead (section 4)
command: #think-off <tk_…> | Nothing to write — the server removes the think mark; with no task named, ask which
brief: **Agent task** (`#task <hint>`, `#now <text>`, `#now-todo <text>`). Only when the user writes one of them, with `write_entry {lens: "task"}`. `#task`: you write the task from the conversation, title and text, into the `agent` column for later. `#now`: the task this chat starts on, in `doing`; `#now-todo` (`-next`, `-backlog`, `-review`, `-parked`, `-done`) files it in that column, not started. A `#now` task's text is the operator's message as written, kept by the server: you send the title and tags only; a note of yours goes after it with `task_update {id, comment}`. `task_update` changes the title, text and day only of a task you created; on the operator's or another agent's, add a comment. `{lane}` after the tag names the board lane; the server sets it. `#think` marks a task as the operator's to think through: never start, move or finish it; comment and ask instead. Every commit you make for a task ends with `Task: tk_…` and `Agent: <your agent_id>`; a commit without it is linked with `task_commits`. The skill `write-a-task` holds the steps.
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
