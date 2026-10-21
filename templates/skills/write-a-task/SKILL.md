---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing), #now-todo and the like for the operator's message filed in a column; a #now task's text is the operator's message, the agent writes the title. Use only when the operator types one of them."
---

{{part:task}}

Check: the reply carries the task's id, and the card shows on the project's
board: `#task` in the Agent column, `#now` in doing, `#now-todo` in To do,
in its lane; a `#now` card's text is the operator's message.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; a description
on a `#now` card; starting the work before the `#now` card is written, or
starting it at all on `#now-todo`.
