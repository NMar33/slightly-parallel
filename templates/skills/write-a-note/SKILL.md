---
name: write-a-note
description: "Write a note for the operator on the Notes page instead of a long chat reply or a markdown file: context to come back to, a text to paste, a review with pictures, a plan for helpers, a report, the steps only the operator can do. Use when what you are about to write is something the operator will read again or keep."
---

{{part:note}}

Check: the answer of `note_write` carries the note's id and version; the
note shows on the Notes page (`/notes?note=<id>`) and, when it names a
task, in that task's window; the reply in the chat is one line with the id.

Mistakes to avoid: a note for a short answer that belongs in the chat;
pasting the note's text into the chat as well; a markdown file in the
scratchpad or the repository for the same text; a checklist for steps you
can do yourself; a choice the operator has already answered in the chat;
a new note where the next version of the existing one was meant; leaving
`task_id` out when the note is for a task.
