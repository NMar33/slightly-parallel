---
key: entrypoint
section: 4
title: Entry point
enabled: true
command: #entrypoint | Nothing to write — the server keeps the message as an entry point; write its text (Kept messages, section 4): What, Where, How, State, Next
---

**Entry point — `#entrypoint`.** The way into a topic, for whoever comes
back to it after a while — the operator in a month, or an agent in a new
chat. One entry point per topic ("the install film", "the launch"), kept by
the server from the operator's message; you write its text through
`interpret {lens: "entrypoint", id, text, note}`.

The text has five sections, as Markdown headings, 400 words at most
(Where is the long one: every path and link the topic needs):

- **What** — what the topic is and what for, one or two sentences.
- **Where** — the files, folders, artifacts and links the topic lives in,
  one per line, exact paths.
- **How** — how to run or repeat it: the commands, the pages, the skill to
  use.
- **State** — where the work stopped, as of this version.
- **Next** — what comes next, by items.

Write it from this chat: the paths and commands that were used, the state
as the last messages leave it. Nothing that was not done or decided. A
second `#entrypoint` on the same topic is a new version of the same
record: replace State and Next, add to Where and How, keep the rest.
`topic` is the title, four words or so.

When the operator opens a topic that has an entry point, read it first
(the Entry points page, or `GET /api/entrypoints?project=…`): it says
where things are and where the work stopped.
