---
key: message-marks
section: 4
title: Pin, carry, fork later
enabled: true
command: #pin | Nothing to write — the server pins the message for the operator to come back to; when told to go back to a pin, read it with `pins`
command: #carry | Nothing to write — after a context compaction the hook gives this message and your reply to it back to you whole
command: #carry-brief | `carry_brief {message, text}` now: a short brief of the message with the context needed to understand it; after a compaction the brief is given back instead
command: #fork-later | Nothing to write — the server lists the message as work another agent could take later, with the command that starts it
---

**Marks on one message — `#pin`, `#carry`, `#carry-brief`, `#fork-later`.**
Like `#important`, the tag is the whole act: the server marks the message
it is in from the chat log, and the operator can set or remove each one by
hand on the chat page. A message is `<agent_id>#<turn>`; the agent's reply
in that turn is `<agent_id>#<turn>/reply`.

- `#pin` — the operator will come back to this message. When they say "go
  back to the pin" (or name one), read it with `pins` (this chat's pins
  with each message whole; `scope: "project"` for the whole project).
- `#carry` — the message survives a context compaction: right after one,
  the capture hook gives it back to you whole, with your reply to it (the
  first 4,000 characters). Nothing to write.
- `#carry-brief` — the message survives as a brief you write now:
  `carry_brief {message, text}` (`message` as the notice names it; without
  it, this chat's turn by `turn`). The brief is what the message says and
  the context needed to understand it after the chat is compacted: who
  asked, what for, what was decided — a few sentences, at most 4,000
  characters. When the operator marks a message this way by hand, the next
  notice names it: write its brief then.
- `#fork-later` — work another agent could take later, in parallel. Go on
  with the message as usual; the operator starts the fork from the list.

After a compaction the hook's notice `[slightly-parallel] carried — …` holds
the carried messages, whole ones first, then briefs, newest first, within
30,000 characters. What does not fit is named in it: `pins {kind: "carry"}`
gives every carried message whole. Read them as part of what you know about
the chat.
