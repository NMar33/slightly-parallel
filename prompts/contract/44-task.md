---
key: task
section: 4
title: Agent task
enabled: true
command: #task <hint> | Write the task the user is pointing at, from the conversation, into the `agent` column (section 4)
brief: **Agent task** (`#task <hint>`). Only when the user writes `#task`: write the task the user is pointing at, from the conversation, with `write_entry {lens: "task"}` and `status: "agent"`. The skill `write-a-task` holds the steps.
---

**Agent task — `#task <hint>` → `write_entry {lens: "task"}`.** Only when
the user writes `#task`. You write the task the user would type themselves
if they had the time; you do it because you hold the context. The hint
says which thing; the conversation holds everything else.

1. Find it. Go back through the conversation to where this thing came up
   — a bug noticed, an idea raised, a step deferred, a thing left undone.
   Empty hint = the last such thing not yet done. Two things fit → ask
   which, one line, before writing. After a context compaction the exact
   words may be gone: say "from memory, not verbatim" rather than
   reconstruct them as quotes.
2. Pull out what belongs to it and only that: what the user wants, in the
   user's phrasing; what is already settled about it — constraints,
   rejected options, decisions taken; what it is attached to — URLs, ids,
   paths, the task in progress. Leave out what was done already, what was
   only mentioned in passing, and anything the user did not ask for.
3. Write the task, not the conversation: no quotes of who said what, no
   history of how it was reached — the state of it now: what is wrong or
   wanted, and where. `title`: the thing, in the user's words, ≤ 80
   chars. `description`: 2–6 plain lines from step 2, nothing added.
   `tags`: 1–3 of `ag_debt · ag_bug · ag_followup · ag_idea ·
   ag_decision`, the first is the main one. `status: "agent"` — the only
   status you may create with; the operator drags the
   card out of that column, which is the review. `lane` / `assignee` only
   if the user named one. No other field: priority, impact, effort,
   sprint, due date and the rest are the operator's; the server drops
   them and names them back as `ignored`.
4. Reply with one line: `tk_… · <title> · <tag>`. "Drop it" →
   `task_update {id, status: "done-archived"}` — the only status change
   you ever make, on a card you created. `task_update` takes `title`,
   `description` and `today_on` as well; sprint, priority, due date and
   the operator's switches are refused by name.

```json
{"lens":"task","fields":{"title":"Architecture form without a scan",
  "status":"agent","tags":"ag_followup",
  "description":"rn the architecture form accepts an empty trigger_id, so an agent can write a form outside of #scan (the first one landed as 'without a scan' on the tab). It should be only with #scan — refuse a form without a scan id, drop the 'without a scan' bucket.\nbackend/backend/routers/architecture.py:architecture_form · frontend/src/features/project/ArchitectureTab.tsx:LooseCard"}}
```

The server refuses: a status other than `agent` from an agent, no tag or
a tag outside `ag_*`, more than three tags, a title missing or over 80
characters. Writing the same task twice answers with the existing one.
