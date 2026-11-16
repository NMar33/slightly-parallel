---
key: commands
section: 2
heading: ## 2. Commands
title: Commands
enabled: true
---

When the user types one of these, act as described. Commands start with
`#` and may stand anywhere in the message. One written with three hashes
(`###now-todo`) is the message's only command: the other tags in it are
silenced, and the notice names only that one.

<!-- commands -->

**Resolving `<id or text>`**: if it looks like an id (`sp_…`, `pb_…`), use it.
Otherwise read the lens (`search`, or `GET /api/<lens>?project=…`), match
the text against headlines, and confirm with the user when more than one
candidate fits. A task id may carry a turn — `tk_28b1b490.2` is the second
round of instruction on that task, and the text you were given is that
round alone. Strip the suffix to address the task; keep it when you name
the task in your entries, so the work can be tied back to the round that
asked for it. The earlier rounds are in the task's description. `ar_…`
names two things: an artifact and an architecture form. The notice that
gave you the id says which — an artifact id arrives with `#artifact`,
while an architecture form is addressed through its scan's `trigger_id`.

**Lifecycle updates** go through `update_entry {lens, id, changes}` with
only the fields to change (each lens's mutable fields are in
`sp://schema`; a field outside them is refused by name). The text of
an entry is changed by the same names it was written with (section 3),
every name but the first: `changes: {why: "…"}` on a decision rewrites its
why, while the `decision` line itself is fixed once written. Tasks are the
exception: their text is `description` (and rounds are `turns`), and they
are edited with `task_update`.
