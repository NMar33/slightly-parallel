---
key: vision
section: 4
title: Vision
enabled: true
command: #vision | Nothing to write — the server keeps the message as a vision; write its interpretation (Kept messages, section 4)
command: #prompt | Nothing to write — the server keeps the message in the operator's prompt library
command: #important | Nothing to write — the server stars the message, its agent and the tasks it names; `#important-agent`, `-task` or `-message` stars one of them
---

**Vision — `#vision`.** A directional idea, kept by the server in the
user's own words.

**Kept messages — `#vision`, `#rule`, `#problem`.** The tagged message is
the entry: the server takes it from the chat log verbatim. Do not write an
entry for it. A message that is only the tag keeps nothing: no id is
minted and no notice appears — ask the user what to keep. The hook names the id —
`[slightly-parallel] #vision — the server keeps this message as vs_…` — and your part
is the interpretation, written in the same turn:
`interpret {lens: "vision" | "rule" | "problem", id, text}` (`text` is
markdown; `note` is one optional line on what changed).

The interpretation is the message read with the conversation around it:
what the user means, in plain words, with what the context settles —
constraints, rejected options, what it replaces. A vision: the direction
and what it would change. A rule: the rule, imperative, and the incident
behind it. A problem: what is blocked and what was tried. Keep the user's
words where they are exact; add nothing that was not said. Each write is a
version; the operator edits from there. On the page, the message is "Your
words" and the interpretation sits beside it.

`#prompt` is kept the same way, into the operator's prompt library. It
asks nothing of you: answer the message as usual.

`#important` is kept the same way, as a star: the server marks the message,
the agent of the chat and every task the message names; `#important-agent`,
`#important-task` (the named task, else the last task named in this chat)
and `#important-message` mark one of them. There is nothing to write.
