---
key: help
section: 4
title: Help
enabled: true
command: #help | Answer the operator with the list of commands and what each does for them (the skill sp-help holds it)
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
| `#task <hint>` | Writes the task you are pointing at onto the board, in the agent column. | Kanban |
| `#evidence` | Attaches the proof for the task: what it touched and what it did, the way you asked for it. | The task's window |
| `#done` | Moves the task to done: the one named, else the last task named since the previous `#done`. Its messages up to here count as its work. | Kanban · the task's window |

**Keep a message**

| Command | What it does | Where you see it |
|---|---|---|
| `#vision` | Keeps the message as a vision; the agent writes what it means. | Visions |
| `#rule <text>` | Keeps the message as a rule for agents; the agent writes what it means. | Rules |
| `#problem <text>` | Keeps the message as a problem; the agent writes what it means. | Problems |
| `#problem solved <id or text>` | Marks that problem solved. | Problems |
| `#prompt` | Keeps the message in your prompt library, to send again. | Prompts |
| `#skill` | Turns what was done in this chat into a skill agents can use. | Skills |
| `#artifact <what>` | Makes an artifact: a dataset, a document, a page or an app, kept as a folder. | Artifacts |

**Mark**

| Command | What it does | Where you see it |
|---|---|---|
| `#important` | Stars the message, this chat's agent and the task the message names. | Important |
| `#important-agent` · `-task` · `-message` | Stars only one of them. `-task` with no id takes the last task named in the chat. | Important |

**Ask**

| Command | What it does |
|---|---|
| `#help` | Shows this list. |

A task id (`tk_…`) in a message is noticed on its own: the task shows the
chat under its history.
