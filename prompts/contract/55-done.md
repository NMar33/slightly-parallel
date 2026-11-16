---
key: done
section: 4
title: Done in the chat
enabled: true
command: #done | MCP tool task_done: the server has moved the task; say what moved, then your task_report line; next tasks only when the work is unfinished without them (the skill finish-a-task)
brief: **Done** (`#done`). The operator closes a task from the chat: the server moves it to done and gives it its stretch of the chat. Call `task_done`, say what moved, then your one-line `task_report`. Offer next tasks (`task_done {proposals}`, then `next_tasks`) only when the work is unfinished without them. The skill `finish-a-task` holds the steps.
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
