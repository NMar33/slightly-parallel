---
id: sk_2a1cf6d2
kind: skill
---

## Version 1 · 2609-25 23:56 · edited
> Built into Slightly Parallel

---
name: finish-a-task
description: "The operator typed #done: the server has moved the task to done and given it its stretch of the chat. Say what moved, then add your one-line report and any evidence. Use when the [slightly-parallel] #done notice appears."
---

`#done` is the operator's verdict. The server has already applied it: you
never change a task's status. Your part is the account.

1. Call `task_done`. It answers `tasks` (each: `id`, `title`, `result`,
   `stretch` with `start`, `end`, `turns`, `minutes`) or `unnamed`.
   - `unnamed`: no task was named in this chat since the last `#done`.
     Ask the operator which task is done; they answer `#done tk_…`. Stop.
   - `result: already` or `archived`: say so in one line; nothing moved.
2. Say in one line what moved: `tk_… "title" moved to done — turns
   12–31, 1h 20m.`
3. For each moved task, `task_report {id, summary}`: one line, what
   shipped, as a fact about the product. It moves nothing on a done task;
   it is the note on the card.
4. When `evidence` is true for a task, the report's answer carries the
   operator's instructions: follow them (the skill `task-evidence`).
5. If choices were made in the stretch that are not logged yet, offer
   `#decision` in one line. Then go on with the operator's next request.

**`#done`** is the operator closing a task where the work happened. The
task is the one the message names (`#done tk_…`; several ids close
several), else the last task named in this chat since the previous
`#done`. The server moves it to *done* as the operator's move — you never
change a status — and gives the task its stretch of the chat: every
message from after the previous `#done` (or after another task was named,
or the chat's start) up to and including the `#done` message. Its files,
commits, messages and time are counted over that stretch.

On the `[slightly-parallel] #done` notice call `task_done`. It answers what moved,
each task with its stretch, and `next`:

1. Say in one line what moved, with the stretch (`tk_… moved to done —
   turns 12–31, 1h 20m`). If it answers `unnamed`, ask the operator which
   task; they answer `#done tk_…`.
2. `task_report {id, summary}` for each task: one line, what shipped. On a
   done task it moves nothing — it is your account on the card.
3. Where the task has `evidence: true`, the report's answer carries the
   operator's instructions: follow them with `task_evidence`.

A task the operator moves back out of done stays where they put it: the
old `#done` is not applied again.

## Version 2 · 2610-06 20:00 · edited
> Built into Slightly Parallel

---
name: finish-a-task
description: "The operator typed #done: the server has moved the task to done and given it its stretch of the chat. Say what moved, then add your one-line report and any evidence. Use when the [slightly-parallel] #done notice appears."
---

`#done` is the operator's verdict. The server has already applied it: you
never change a task's status. Your part is the account.

1. Call `task_done`. It answers `tasks` (each: `id`, `title`, `result`,
   `stretch` with `start`, `end`, `turns`, `minutes`) or `unnamed`.
   - `unnamed`: no task was named in this chat since the last `#done`.
     Ask the operator which task is done; they answer `#done tk_…`. Stop.
   - `result: already` or `archived`: say so in one line; nothing moved.
2. Say in one line what moved: `tk_… "title" moved to done — turns
   12–31, 1h 20m.`
3. For each moved task, `task_report {id, summary}`: one line, what
   shipped, as a fact about the product. It moves nothing on a done task;
   it is the note on the card.
4. When `evidence` is true for a task, the report's answer carries the
   operator's instructions: follow them (the skill `task-evidence`).
5. If choices were made in the stretch that are not logged yet, offer
   `#decision` in one line. Then go on with the operator's next request.

**`#done`** is the operator closing a task where the work happened. The
task is the one the message names (`#done tk_…`; several ids close
several), else the last task named in this chat since the previous
`#done`. The server moves it to *done* as the operator's move — you never
change a status — and gives the task its stretch of the chat: every
message from after the previous `#done` (or after another task was named,
or the chat's start) up to and including the `#done` message. Its files,
commits, messages and time are counted over that stretch.

On the `[slightly-parallel] #done` notice call `task_done`. It answers what moved,
each task with its stretch, and `next`:

1. Say in one line what moved, with the stretch (`tk_… moved to done —
   turns 12–31, 1h 20m`). If it answers `unnamed`, ask the operator which
   task; they answer `#done tk_…`.
2. `task_report {id, summary}` for each task: one line, what shipped. On a
   done task it moves nothing — it is your account on the card.
3. Where the task has `evidence: true`, the report's answer carries the
   operator's instructions: follow them with `task_evidence`.

A task the operator moves back out of done stays where they put it: the
old `#done` is not applied again.

## Version 3 · 2611-11 21:37 · edited
> Built into Slightly Parallel

---
name: finish-a-task
description: "The operator typed #done: the server has moved the task to done and given it its stretch of the chat. Say what moved, then add your one-line report and any evidence. Use when the [slightly-parallel] #done notice appears."
---

`#done` is the operator's verdict. The server has already applied it: you
never change a task's status. Your part is the account.

1. Call `task_done`. It answers `tasks` (each: `id`, `title`, `result`,
   `stretch` with `start`, `end`, `turns`, `minutes`) or `unnamed`.
   - `unnamed`: no task was named in this chat since the last `#done`.
     Ask the operator which task is done; they answer `#done tk_…`. Stop.
   - `result: already` or `archived`: say so in one line; nothing moved.
2. Say in one line what moved: `tk_… "title" moved to done — turns
   12–31, 1h 20m.`
3. For each moved task, `task_report {id, summary}`: one line, what
   shipped, as a fact about the product. It moves nothing on a done task;
   it is the note on the card.
4. When `evidence` is true for a task, the report's answer carries the
   operator's instructions: follow them (the skill `task-evidence`).
5. If choices were made in the stretch that are not logged yet, offer
   `#decision` in one line.
6. Next tasks, only when a step follows without which the task does not
   do what it was for (section 4's examples): call `task_done
   {proposals}` (at most three `{title, line}`), drop one whose `similar`
   task is the same thing (call again with the rest), and end the reply
   with the answer's `show` line as it is. More than three: say the task
   is not finished instead. None: offer nothing. When the operator
   answers, `next_tasks {numbers}` with the numbers they wrote. Then go
   on with the operator's next request.

**`#done`** is the operator closing a task where the work happened. The
task is the one the message names (`#done tk_…`; several ids close
several), else the last task named in this chat since the previous
`#done`. The server moves it to *done* as the operator's move — you never
change a status — and gives the task its stretch of the chat: every
message from after the previous `#done` (or after another task was named,
or the chat's start) up to and including the `#done` message. Its files,
commits, messages and time are counted over that stretch.

On the `[slightly-parallel] #done` notice call `task_done`. It answers what moved,
each task with its stretch, and `next`:

1. Say in one line what moved, with the stretch (`tk_… moved to done —
   turns 12–31, 1h 20m`). If it answers `unnamed`, ask the operator which
   task; they answer `#done tk_…`.
2. `task_report {id, summary}` for each task: one line, what shipped. On a
   done task it moves nothing — it is your account on the card.
3. Where the task has `evidence: true`, the report's answer carries the
   operator's instructions: follow them with `task_evidence`.

4. **Next tasks — only when the work is unfinished without them.** After
   the report, offer next tasks if a step follows from this task so that
   without it the task does not do what it was for. At most three. More
   than three such steps means the task is not finished: say so in one
   line instead (the operator decides whether it goes back), and offer
   nothing. No such step: offer nothing, which is the normal case.
   - yes: the task was to put the site live; it is deployed, but `www`
     has no DNS record → "Set up the www DNS record".
   - yes: the task asked for Linux and Windows; the fix ran on Linux
     only → "Check the path fix on Windows".
   - no: "Add caching to the endpoint" — an improvement, not a missing
     part.
   - no: "Write docs for the new endpoint" when the task did not ask for
     docs; nor a retelling of what was done, nor "worth thinking about".

   Call `task_done` again with `proposals`: `[{title, line}]`, the title
   as a task title, the line what is left and why it follows. The server
   compares each with the project's open tasks (you never read the board
   for it) and answers `similar` for each and `show`: the line to give
   the operator, as it is, as the last line of your reply (`Make these
   tasks? 1) … 2) …`). A proposal whose similar task is the same thing:
   send the rest again without it, and name that task instead. The
   operator answers with numbers or skips; then call `next_tasks
   {numbers}` with the numbers they wrote (`[]` for none). The server
   checks them against their message and makes the chosen ones in the
   `agent` column. Never write them with `write_entry`.

A task the operator moves back out of done stays where they put it: the
old `#done` is not applied again.

## Version 4 · 2611-11 21:55 · edited
> Built into Slightly Parallel

---
name: finish-a-task
description: "The operator typed #done: the server has moved the task to done and given it its stretch of the chat. Say what moved, then add your one-line report and any evidence. Use when the [slightly-parallel] #done notice appears."
---

`#done` is the operator's verdict. The server has already applied it: you
never change a task's status. Your part is the account.

1. Call `task_done`. It answers `tasks` (each: `id`, `title`, `result`,
   `stretch` with `start`, `end`, `turns`, `minutes`) or `unnamed`.
   - `unnamed`: no task was named in this chat since the last `#done`.
     Ask the operator which task is done; they answer `#done tk_…`. Stop.
   - `result: already` or `archived`: say so in one line; nothing moved.
2. Say in one line what moved: `tk_… "title" moved to done — turns
   12–31, 1h 20m.`
3. For each moved task, `task_report {id, summary}`: one line, what
   shipped, as a fact about the product. It moves nothing on a done task;
   it is the note on the card.
4. When `evidence` is true for a task, the report's answer carries the
   operator's instructions: follow them (the skill `task-evidence`).
5. When the answer names a task's topic (an entry point), add one
   message of where it stopped: `entrypoint_stop {id, task_id, text}`,
   one or two plain sentences — what is done, what is not, what waits for
   whom. One per topic, even when two of its tasks closed. A task with no
   topic: if its work belongs to an entry point of this project, set it
   with `task_topic` first. A way in only when you made one or its way to
   open changed (`entrypoint_way`, a shot while it is up); a new entry
   point only by section 4's rule (`entrypoint_offer` first).
6. If choices were made in the stretch that are not logged yet, offer
   `#decision` in one line.
7. Next tasks, only when a step follows without which the task does not
   do what it was for (section 4's examples): call `task_done
   {proposals}` (at most three `{title, line}`), drop one whose `similar`
   task is the same thing (call again with the rest), and end the reply
   with the answer's `show` line as it is. More than three: say the task
   is not finished instead. None: offer nothing. When the operator
   answers, `next_tasks {numbers}` with the numbers they wrote. Then go
   on with the operator's next request.

**`#done`** is the operator closing a task where the work happened. The
task is the one the message names (`#done tk_…`; several ids close
several), else the last task named in this chat since the previous
`#done`. The server moves it to *done* as the operator's move — you never
change a status — and gives the task its stretch of the chat: every
message from after the previous `#done` (or after another task was named,
or the chat's start) up to and including the `#done` message. Its files,
commits, messages and time are counted over that stretch.

On the `[slightly-parallel] #done` notice call `task_done`. It answers what moved,
each task with its stretch, and `next`:

1. Say in one line what moved, with the stretch (`tk_… moved to done —
   turns 12–31, 1h 20m`). If it answers `unnamed`, ask the operator which
   task; they answer `#done tk_…`.
2. `task_report {id, summary}` for each task: one line, what shipped. On a
   done task it moves nothing — it is your account on the card.
3. Where the task has `evidence: true`, the report's answer carries the
   operator's instructions: follow them with `task_evidence`.

4. **Next tasks — only when the work is unfinished without them.** After
   the report, offer next tasks if a step follows from this task so that
   without it the task does not do what it was for. At most three. More
   than three such steps means the task is not finished: say so in one
   line instead (the operator decides whether it goes back), and offer
   nothing. No such step: offer nothing, which is the normal case.
   - yes: the task was to put the site live; it is deployed, but `www`
     has no DNS record → "Set up the www DNS record".
   - yes: the task asked for Linux and Windows; the fix ran on Linux
     only → "Check the path fix on Windows".
   - no: "Add caching to the endpoint" — an improvement, not a missing
     part.
   - no: "Write docs for the new endpoint" when the task did not ask for
     docs; nor a retelling of what was done, nor "worth thinking about".

   Call `task_done` again with `proposals`: `[{title, line}]`, the title
   as a task title, the line what is left and why it follows. The server
   compares each with the project's open tasks (you never read the board
   for it) and answers `similar` for each and `show`: the line to give
   the operator, as it is, as the last line of your reply (`Make these
   tasks? 1) … 2) …`). A proposal whose similar task is the same thing:
   send the rest again without it, and name that task instead. The
   operator answers with numbers or skips; then call `next_tasks
   {numbers}` with the numbers they wrote (`[]` for none). The server
   checks them against their message and makes the chosen ones in the
   `agent` column. Never write them with `write_entry`.

A task the operator moves back out of done stays where they put it: the
old `#done` is not applied again.
