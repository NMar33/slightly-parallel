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

{{part:done}}
