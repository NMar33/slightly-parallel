---
key: done
section: 4
title: Done in the chat
enabled: true
command: #done | MCP tool task_done: the server has moved the task; say what moved, then your task_report line (the skill finish-a-task)
brief: **Done** (`#done`). The operator closes a task from the chat: the server moves it to done and gives it its stretch of the chat. Call `task_done`, say what moved, then your one-line `task_report`. The skill `finish-a-task` holds the steps.
---

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
