---
key: done
section: 4
title: Done in the chat
enabled: true
command: #done | MCP tool task_done: say what moved and show doubtful IDs with their confirmation line, then your task_report line; next tasks only when the work is unfinished without them (the skill finish-a-task)
brief: **Done** (`#done`). The operator closes a task from the chat: the server moves it to done and gives it its stretch of the chat. Call `task_done`, say what moved, and pass on any doubtful IDs with their confirmation line. Add your one-line `task_report` to each task that moved. Offer next tasks (`task_done {proposals}`, then `next_tasks`) only when the work is unfinished without them. The skill `finish-a-task` holds the steps.
---

**`#done`** is the operator closing a task where the work happened. The
server closes each ID in the list immediately following the tag. The list
ends at the first intervening word other than `and` or `и`. IDs immediately
before the tag also count when only punctuation follows them. A bare tag
closes the last local task the operator named since the previous tag.
A paste in an operator message can still trigger the tag. Incidental IDs
and earlier mentions in operator messages go into the list for confirmation
while those tasks are open. Agent replies and incoming agent messages
do not supply candidates. Foreign examples can accompany the chat's
existing local task, which remains the only eligible fallback.

The server records the operator's move on each task it closes
and gives the task its stretch of the chat: every
message from after the previous `#done` (or after another task was named,
or the chat's start) up to and including the `#done` message. Its files,
commits, messages and time are counted over that stretch.

On the `[slightly-parallel] #done` notice call `task_done`. It answers what moved,
each task with its stretch, and `next`:

1. Say what moved, with its stretch. If `doubt` is present, show each
   ID and its reason, and give the `confirmation` line for the operator to
   copy and send. A plain yes has no effect. With `unnamed` and an empty
   doubt list, ask which task. The operator answers with `#done tk_…`.
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
