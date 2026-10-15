---
key: scan
section: 4
heading: ## 4. When and what to write
title: Checkpoint
enabled: true
command: #scan | Checkpoint: write a scan, then the file entry and the architecture form it triggers (section 4). The only way a scan is written — the user asks for it
brief: **Checkpoint** (`#scan`). Only when the user types `#scan` — never on your own. You may offer one after shipping or before a risky change. A scan is three entries: the scan, its file entry and its architecture form. It ends with the architecture page when the scan changed what the project is. Call `scan_material`: it returns this chat's commits since your last scan, the files they touched, what is not committed, the counters, and the instructions for all three. The skill `make-a-scan` holds the steps.
---

**Checkpoint — `write_entry {lens: "scan"}`** (`#scan`). Only when the
user types `#scan` — never on your own initiative. After shipping, before
a risky change or at the end of a chat, you may *offer* one; the user decides.

The team lead reads a scan to learn what the product can do now, what was
broken, and what is left. Write it as section 3 says. 300 words at most
for the whole scan.

The window is yours: this chat's commits since your last scan of the
project, and what this chat changed that is not committed. Another agent's
commits are not in it — they are that agent's scan. A scan is written from
the work, not from git: what was done but not committed is in the scan too,
said as not committed. Without a repository the material still lists the
files this chat's tool calls changed and the files changed in the folder
during its turns. Group the work into themes. Each theme gets one
delta, or one line under `proof`: "Not covered: …". Nothing is left out
silently.

- `summary` — one sentence, 30 words at most: the two or three largest
  themes, by what they change for a user or an agent. If something was
  broken or unsafe and is fixed, it belongs here.
- `why` — 2 sentences, 45 words at most: what was asked for or what the
  problem was, and whether the result matches. Do not repeat a delta.
- `deltas` — at most 7 items, the most important first, 35 words at most
  each. One item is one change: what a user or an agent met before, then
  what they meet now. Write a state only when the item is not finished:
  what is left, or what waits for the lead's choice. Put small fixes
  together in one last item.
- `proof` — at most 5 lines, 15 words at most each: the claim → what
  checks it, in words ("a new automated test", "opened the page by hand")
  → the result you saw, or "added, not run". Write only what you know.
  Then, when it applies: "Still works: …" for older chats and data,
  and "Not covered: …".

**After the three entries,** update the architecture page when the scan changed what the project
is, does or owes: `architecture_material`, then `architecture_page` (Architecture page, below).
A scan of small fixes skips it.

The counters go in the same call as numbers, not in the text: `files_n`,
`lines_add`, `lines_del`, `decisions_n`. The page shows them.

```json
{"lens":"scan","fields":{
  "summary":"Agents could not post scans since the MCP-only rule; the scan kind was missing from the write schema and is added.",
  "why":"The operator asked for every agent write to go through the MCP tools. The result matches, and the missing scan kind was found on the way.",
  "deltas":[
    "Agents write each kind of entry by its own field names, such as a decision's alternatives. Before, all kinds shared four numbered levels.",
    "A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's.",
    "Smaller fixes: the task window crashed when a file was missed; uncommitted changes were counted once per turn."],
  "proof":"Scans can be posted by name → a new automated test → checked.\nThe raw request is refused → tried by hand → checked.",
  "files_n":56,"lines_add":1056,"lines_del":556,"decisions_n":2}}
```
