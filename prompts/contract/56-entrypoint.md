---
key: entrypoint
section: 4
title: Entry point
enabled: true
command: #entrypoint | Nothing to write — the server keeps the message as an entry point; write its record (Kept messages, section 4): What, Where, How, State, Next
---

**Entry point — `#entrypoint`.** The outside of a project: a topic the
operator opens and comes back to ("the films and the launch", "the site's
texts"), for the operator in a month and for the agent they hand it to. One
entry point per topic; what is opened lives inside it. Cores are the inside
of the program; entry points are the outside.

An entry point holds:

- **its name** — the operator's words, four words or so;
- **ways in** — what the operator opens to look at the work: a page, a
  site, an app, a file, a folder, a script, an artifact; each with where it
  opens (URL or path), the command that starts it, its folder and port.
  Slightly Parallel checks the port when the page opens and shows the
  command of a way that is down; it starts nothing itself;
- **where it stopped** — a feed of short messages, the operator's and the
  agents'; the last five count;
- **shots** — screenshots, a series per way in, each with the chat it was
  taken in;
- **the record** — What, Where, How, State, Next, in versions;
- **what is next** — not written anywhere: it is the topic's open tasks
  (a task carries its topic).

**After `#entrypoint`** (the notice names the id): write the record
through `interpret {lens: "entrypoint", id, text, note}` — five sections
as Markdown headings, 400 words at most: **What** (one or two sentences),
**Where** (every file, folder and link, one per line, exact paths),
**How** (the commands, the pages, the skill), **State** (where the work
stopped), **Next** (by items). Write it from this chat; nothing that was
not done or decided. Set its `topic` with `update_entry` from the
operator's words. Then add each way in the chat used with
`entrypoint_way`. Only the chat where the operator kept it writes the
record.

**Everywhere else you write three things, never free text into the topic:**

- `entrypoint_stop {id, text, task_id?}` — one message of where it
  stopped, one or two plain sentences: what is done, what is not, what
  waits for whom. At `#done` the answer names the task's topic and asks
  for it: one per topic.
- `entrypoint_way {id, way}` — a way in you made, or one whose way to open
  changed (port, command, folder). A way the operator wrote is theirs.
- `entrypoint_shot {id, way_id, path, caption}` — a screenshot of a way in
  you made or changed, taken while it is up.

A task's topic: `task_topic {id, topic}` when its work belongs to an
entry point of this project. The topics: the MCP tool `entrypoints`.

**Offering a new entry point.** Only when something new to open appeared
(a page, a server, a site, a dashboard, an artifact with a link) or a way
to open one changed — never for a one-off result. Call `entrypoint_offer
{name, why}` first: it answers the topics like it. A match: add the way in
there and say so in one line. None: show the operator its line; they keep
it with `#entrypoint`. Inside an existing topic, only a stop message.

When the operator brings up a topic that has an entry point, read it
first (`entrypoints`; the briefing is on the Entry points page, "Copy to
agent"): it says where things are and where the work stopped.
