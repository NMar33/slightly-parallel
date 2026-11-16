---
key: entrypoint
section: 4
title: Entry point
enabled: true
command: #entrypoint | Nothing is made until the operator chooses the topic: entrypoint_ask {id, name}, show its line; on their answer entrypoint_answer {number, name?}; then write the record (What, Where, How, State, Next), the ways in, one stop, shots of the ways that are up, the tasks' topic
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

**After `#entrypoint`** (the notice names the id) nothing is made until
the operator chooses the topic: they do not remember topic names, and may
type the command with a name, a description or nothing, in any chat of the
project.

1. `entrypoint_ask {id, name}` at once, `name` your proposal for a new
   topic, four words or so, from their words or this chat. The server finds
   the topics of this project the command may mean — by the message's
   words, by what this chat already wrote on (stops, ways in, versions), by
   the topics of the tasks named in this chat — at most three, and always
   a last line for a new topic. It answers `show`: give it as it is, as the
   last line of your reply (`Is this one of the topics? 1) Site and SEO —
   last stop 5 Nov: deploy, the text console 2) A new topic: «…»`); with no
   candidate it is one line, `A new topic: «…»?`. Write nothing else for the
   topic yet. The exact name of one named topic skips the question: the
   answer says a new version of it was opened; say so in one line.
2. The operator answers in their next message: a number; the new topic's
   number and a name (`2 Консоль текстов`); `yes` when there is one line.
   Call `entrypoint_answer {number, name?}`: the number they chose (0 when
   none), the name only when they wrote one, as they wrote it. The server
   checks both against their message. A command or a question in it
   chooses nothing: answer the question and call `entrypoint_ask` again.
3. An existing topic chosen opens a new version of its record, and you, in
   this chat, write it (an unnamed topic takes the name given); the new
   topic's line makes the topic then, with its name. The answer gives the
   topic's id, the record as it is and `next`, the line of what to write.

Then write the record through `interpret {lens: "entrypoint", id, text,
note}` — five sections as Markdown headings, no word limit: **What**
(one or two sentences), **Where** (every file, folder and link, one per
line, exact paths), **How** (the commands, the pages, the skill),
**State** (where the work stopped), **Next** (by items). A new version
starts from the record as it is: Where and How are added to (every line
kept, this chat's added), State is replaced, What and Next are kept
unless this chat changed them. Write from this chat; nothing that was not
done or decided.

Then, in this order (the answer's `next` names them for the topic):

1. each way in this chat used or made: `entrypoint_way` (where it opens,
   the command that starts it, its folder and port);
2. one message of where the work stopped: `entrypoint_stop`;
3. a screenshot of each way in that is up now (the port check:
   `GET /api/entrypoints/{id}/ports`, or open it): `entrypoint_shot`;
4. the topic of each task of this topic named in this chat:
   `task_topic {id, topic}` — the card's tasks, what is next, come from it.

Then say in one line what was written.

The record is written only right after the operator's `#entrypoint` in
your chat and their choice, never on your own: the chat that chose the
topic last writes it, every version is kept with the chat that wrote it,
and a topic of another project is refused.

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
