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
