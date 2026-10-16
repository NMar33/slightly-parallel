---
name: write-a-task
description: "Write a task onto the Slightly Parallel board from the conversation, the way the operator would type it themselves: #task for later (the agent column), #now for the task this chat starts on (doing). Use only when the operator types one of them."
---

{{part:task}}

Check: the reply carries the task's id, and the card shows on the project's
board: `#task` in the Agent column, `#now` in doing, in its lane.

Mistakes to avoid: writing a task nobody asked for; retelling the
conversation in the description; setting priority, sprint, a due date or a
lane; `agent` for a `#now` card or `doing` for a `#task` one; starting the
work before the `#now` card is written.
