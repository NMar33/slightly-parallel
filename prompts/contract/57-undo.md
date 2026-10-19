---
key: undo
section: 4
title: Undo a mistake
enabled: true
command: #undo <what was the mistake> | MCP tool undo_find, list the candidates by number, then undo_propose with the operator's numbers and show its confirm text (the skill undo-a-mistake)
command: #undo-yes | The operator confirmed: MCP tool undo_apply. The server archives only on this reply right after your proposal
brief: **Undo** (`#undo`). The operator archives entries made by mistake. List the candidates from `undo_find` by number; send their numbers' ids to `undo_propose` and show its confirm text; on `#undo-yes`, call `undo_apply`. Never archive without both. The skill `undo-a-mistake` holds the steps.
---

**Undo a mistake — `#undo`.** A tag typed or pasted by accident makes an
entry nobody wanted: a pasted announcement that mentions #vision and #rule
keeps a vision and a rule. `#undo <what was the mistake>` archives such
entries. Archiving hides an entry from its page's list and from the
agents' files; nothing is deleted, and each entry can be restored.

It is the operator's act, confirmed twice, and the server checks both
against the captured chat:

1. On the `[slightly-parallel] #undo` notice call `undo_find`. It answers
   the operator's words and the candidates, numbered: this chat's entries
   first, then the project's recent ones. Show them as a numbered list —
   number, kind and id, title, when, from this chat or not — and mark the
   ones that fit what the operator said. Ask them to answer with the
   numbers.
2. Send the chosen ids to `undo_propose {ids}`. It answers `confirm`: what
   goes to the archive, a warning, and the reply that confirms. Show it as
   it is. Say plainly that the answer is `#undo-yes`.
3. On `#undo-yes` call `undo_apply`. The server archives only when the
   operator's next message after the proposal carries `#undo-yes`. Any
   other answer cancels the request; a changed choice is a new
   `undo_propose`, confirmed again.

Without an `#undo` request in the chat, `undo_find` and `undo_propose` are
refused; without `#undo-yes`, `undo_apply` is refused. Never archive on
your own initiative, and never route around a refusal. `undo_restore {id}`
brings one entry back, with the status it had.
