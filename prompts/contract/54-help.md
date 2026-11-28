---
key: help
section: 4
title: Help
enabled: true
command: #help | Answer the operator with the list of commands and what each does for them (the skill sp-help holds it)
command: #mute | No command in the message runs, `###` ones too: every tag in it is plain text. Do nothing for its tags
brief: **Help** (`#help`). Answer the operator with the list of commands, what each does for them and where they see the result. The skill `sp-help` holds the list; give it as it is, in the operator's language, and add nothing that is not in it.
---

**Slightly Parallel commands.** Type one anywhere in a message. The agent does the
rest; you see the result on the page named.

**Record the work**

| Command | What it does | Where you see it |
|---|---|---|
| `#scan` | Saves a checkpoint: what changed in the project since the last scan, with its files and the architecture form. | Scans |
| `#architecture` | Brings the architecture up to date: the form for the last scan, the page and the map of the program — each only when it is out of date. | Architecture |
| `#page` | Writes the next version of the architecture page: what the project is, does and is made of, and what is owed. | Architecture |
| `#map` | Maps the program: every part as a row and what connects to what. Asks you first, then a helper agent maps. | Architecture · switch "map" |
| `#decision` | Logs the decision just made, with why and what was turned down. | Decisions |
| `#standup` | Writes yesterday's standup from every chat of that day. | Standups |

**Tasks**

| Command | What it does | Where you see it |
|---|---|---|
| `#task <hint>` | Writes the task you are pointing at onto the board, in the agent column, for later. `#task {ui} …` names the lane. | Kanban |
| `#now <text>` | Your message becomes the task this chat starts on, as you wrote it (the agent adds a title): into doing, in the lane for #now (Settings › Tasks) or the one in braces, `#now {ui} …`; then the agent works on it. `#done` closes it. | Kanban |
| `#now-todo <text>` | Your message, as you wrote it, filed in To do and not started; `-next`, `-backlog`, `-review`, `-parked`, `-done` file it in those columns. | Kanban |
| `#think` | Marks a task as yours to think through: agents never start, move or finish it, they only gather context, comment and ask. With `#now-todo` (or `#now`, `#task`) the new task gets the mark; `#think tk_…` marks those tasks. Remove it with the × on the badge. | Kanban · the task's window |
| `#think-off <tk_…>` | Removes the think mark from those tasks. | Kanban · the task's window |
| `#evidence` | Attaches the proof for the task: what it touched and what it did, the way you asked for it. | The task's window |
| `#done` | Closes the tasks named next to the tag. A bare tag uses the last local task named in this chat since the previous tag. The notice lists doubtful IDs and gives a command to confirm them. | Kanban · the task's window |

**Keep a message**

| Command | What it does | Where you see it |
|---|---|---|
| `#vision` | Keeps the message as a vision; the agent writes what it means. | Visions |
| `#rule <text>` | Keeps the message as a rule for agents; the agent writes what it means. | Rules |
| `#problem <text>` | Keeps the message as a problem; the agent writes what it means. | Problems |
| `#problem solved <id or text>` | Marks that problem solved. | Problems |
| `#publish <text>` | Makes a card of what shipped, worth telling: your text as is, or "about X" for the agent to write it. The agent adds the context and attaches tasks, commits, files, screenshots and links. `#publish pu_… <more>` adds to that card. | Publish |
| `#entrypoint <topic>` | The agent shows the topics it may mean, numbered, with a new one last; you answer with a number (and a name for a new one). Then the agent writes what it is, where it lives, how to run it, where the work stopped and what is next; for a topic that exists, a new version of its record. Any chat of the project; the words may be a name, a description or nothing. | Entry points |
| `#prompt` | Keeps the message in your prompt library, to send again. | Prompts |
| `#skill` | Turns what was done in this chat into a skill agents can use. | Skills |
| `#artifact <what>` | Makes an artifact: a dataset, a document, a page or an app, kept as a folder. | Artifacts |

**Cores — the program's core elements you keep in view**

| Command | What it does | Where you see it |
|---|---|---|
| `#core-new <text>` | Keeps a core element of the program in view: a capability, a feature, a store, a part of the interface. The agent sets its name, type and files; your message is its first note. | Architecture · switch "cores" |
| `#core-note <text>` | Adds your message as a note on the matching core, with one line from the agent. If two cores match, the agent asks you to choose by number. | The core's page |
| `#core` | Attaches this message, and the task this chat works on, to the matching core. | The core's page |
| `#core-off <words>` | Removes a core from view after you confirm by number. Its notes and links are kept; restore it on its page. | Architecture · switch "cores" |

**Usage — tokens and plan limits**

| Command | What it does | Where you see it |
|---|---|---|
| `#usage` | Shows this chat's tokens, the plan limits of Claude Code and Codex, and the project's day against your usual one. The hook answers; the agent adds nothing. | The terminal · Usage |
| `#usage-on` | Shows the tokens after each reply in this chat: → new ↑ output ↓ (cache). Tokens are recorded in any case. | The terminal · the chat viewer |
| `#usage-off` | Hides the tokens after each reply in this chat. They are still recorded. | The terminal |
| `#usage-warnings-on` | Shows the usage warnings under the replies of this chat again: a chat about to be compacted, a long chat, a reply that read the whole chat again after a break, a chat that used more than 25% of the 5-hour limit. Claude Code only. | The terminal |
| `#usage-warnings-off` | Turns the usage warnings off in this chat. Tokens are still recorded. Claude Code only. | The terminal |
| `#ping <agent id, optional off>` | Enables keep-alive for a named chat. Add `off` to disable it. | The terminal · Settings for interval and quiet hours |
| `#usage-price` | Updates the API prices the Usage page counts dollars with: a helper agent reads the providers' pricing pages. The days before keep their prices. | Usage |

**Mark**

Each of these marks also has a button on every message of the chat page.

| Command | What it does | Where you see it |
|---|---|---|
| `#important` | Stars the message, this chat's agent and the task the message names. | Important |
| `#important-agent` · `-task` · `-message` | Stars only one of them. `-task` with no id takes the last task named in the chat. | Important |
| `#pin` | Pins the message, to come back to it. Tell the agent "go back to the pin" and it reads it again. | Pins · the chat's pins |
| `#carry` | The message survives a context compaction: right after one, the agent is given it back whole, with its reply. | Pins › Carried |
| `#carry-brief` | The message survives a compaction as a brief the agent writes now; the brief is given back instead of the message. | Pins › Carried |
| `#fork-later` | Keeps the message as work another agent could take later, with the command that starts it from this chat. | Pins › Fork later |

**Undo a mistake**

| Command | What it does | Where you see it |
|---|---|---|
| `#undo <what was the mistake>` | Archives entries a tag made by mistake. The agent lists the candidates by number; you answer with the numbers, then confirm with `#undo-yes`. Nothing is deleted, and each entry can be restored. | The entry's page; ask the agent to restore one |
| `#undo-yes` | Confirms the archive the agent proposed, right after its proposal. Without it nothing is archived; any other reply cancels. | — |

**Ask**

| Command | What it does |
|---|---|
| `#help` | Shows this list. |
| `#mute` | Turns off every command in the message, `###` ones too: you can write about `#now` or paste a log without anything running. |
| `#sp <what worries you>` | Checks whether Slightly Parallel works for this chat and folder: messages recorded, MCP, hooks, skills, data, backups, the server's memory. Says what works and what is a concern; with text, looks into that. Changes nothing without your yes. |

`#mute` anywhere in a message turns all its commands off.

A tag written with three hashes is the message's only command:
`###now-todo` files the message and every other tag in it — in a pasted
reply, a log — does nothing.

A task id (`tk_…`) in a message is noticed on its own: the task shows the
chat under its history.
