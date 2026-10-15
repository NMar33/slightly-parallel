---
key: problem
section: 4
title: Problem
enabled: true
command: #problem <text> | Nothing to write — the server keeps the message as a problem; write its interpretation (Kept messages, section 4)
command: #problem solved <id or text> | Update it: `status:"resolved"`, `resolved_date`
---

**Problem — `#problem`, or `write_entry {lens: "problem"}`.** The user's
`#problem` is kept by the server (see *Kept messages*). When you are
blocked yourself, write one the moment it happens — before workarounds
bury it. `problem`: what is blocked, in one line. `impact`: what it
affects, and who or what owns the fix. `attempts`: one item per attempt:
`"<tried> — <result>"`. `excerpt`: the error or the log. Resolve with
`#problem solved` → `update_entry {lens: "problem", id, changes: {status:
"resolved", resolved_date}}`.
