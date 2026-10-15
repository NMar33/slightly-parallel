---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves. Use only when the operator types #task, with or without a hint."
---

{{part:task}}

Check: the reply carries the task's id, and the card shows in the Agent
column of the project's board.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint or a due date;
any status other than `agent`.
