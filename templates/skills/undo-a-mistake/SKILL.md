---
name: undo-a-mistake
description: "The operator typed #undo: archive the entries a tag made by mistake, only with their numbers and their #undo-yes. Use when the [slightly-parallel] #undo or #undo-yes notice appears."
---

`#undo` is the operator taking back entries nobody wanted. Archiving is
theirs: you list, they choose, you confirm, they say `#undo-yes`.

1. Call `undo_find`. Refused: there is no `#undo` in this chat — tell the
   operator in one line and stop.
2. Show the candidates as a numbered list, one line each:
   `3 · rule rl_7de70501 — "Rules for all agents …" · 16:20 · this chat`.
   Mark the ones that fit what the operator said (`← from the pasted
   announcement`). Ask: «Answer with the numbers to archive.»
3. Their numbers → the ids → `undo_propose {ids}`. Show its `confirm` text
   as it is, and say the answer: «Reply `#undo-yes` to archive them; any
   other reply cancels.»
4. On `#undo-yes`, call `undo_apply`. Say in one line what went to the
   archive and that each can be restored. Refused: say why, in one line;
   archive nothing.
5. «Bring back …»: `undo_restore {id}`.

{{part:undo}}
