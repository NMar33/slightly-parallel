---
key: note
section: 4
title: Note
enabled: true
brief: **Note** (no command; your own call). A text the operator will read again or keep — context to come back to, a text to paste elsewhere, a review with pictures, a plan for helpers, a helper's report, steps only the operator can do — goes into a note with `note_write {text, kind, task_id?, entrypoint_id?}`, not into a long chat reply or a markdown file. The reply then says one line and the note's id. The skill `write-a-note` holds the blocks and the steps. Read `notes {id}` after the operator reviews the note. It returns their ticks, answers and comments.
---

**Note — no command; write one on your own.** A text the operator will
read again or keep goes into a note, not into a long chat reply and not
into a markdown file in the scratchpad or the repository: context to come
back to, a text to paste somewhere, a review with screenshots, a plan for
helper agents, a helper's report, a checklist of steps only the operator
can do. Notes show on the Notes page and in the task's window. A short
answer stays in the chat.

1. Write it with `note_write {text, kind, task_id?, entrypoint_id?}`.
   `text` is markdown whose first line is `# Title`; each `## ` heading is
   a section. `kind` is one of `context` (what to know when coming back),
   `paste` (a text for another chat or place), `review` (pictures and the
   choice they ask for), `plan` (a spec for helpers), `report` (what a
   helper found and did), `actions` (what only the operator can do). Give
   the task the note is for, and its entry point when there is one.
2. Use the blocks where they fit, and only there:
   - ```` ```copy Title ```` … ```` ``` ```` — a text to paste, with a copy button;
   - `- [ ] step` — a step the operator ticks; the ticks are kept;
   - ```` ```choice Question ```` with lines `1. option` — the operator picks one;
   - ```` ```gallery ```` with lines `![caption](file.png)` and the files in
     `images: [{path, caption}]` — pictures with captions;
   - `:::fold Title` … `:::` — a section folded until opened;
   - ```` ```mermaid ```` — a diagram (`flowchart LR`, `A[x] --> B[y]`);
   - task, entry point, decision and note ids (`tk_…`, `ep_…`, `dc_…`, `nt_…`) show as live chips.
3. In the chat, say in one line what the note is for and give its id.
4. To change it, write its next version: `note_write {id, base, text, kind}`
   with `base` the version you read (`notes {id}` reads it). Any chat of
   the project may. A newer note that takes an older one's place says so
   with `replaces`. `note_image {id, path, caption}` adds a picture and
   answers the line to put in the next version.
5. Read the operator's ticks, answers and comments with `notes {id}`.
   Item comments carry the original label, section and note version even
   when the item changes or disappears.
