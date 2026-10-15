---
key: entry
section: 3
heading: ## 3. What an entry holds
title: What an entry holds
enabled: true
---

Every entry is one call: `write_entry {lens, fields}`. `fields` holds the
whole entry by name: what the entry says, and the columns of its lens.
The page of each lens decides what an entry holds, so the names differ by
lens:

| lens | the line | the text | the list (one item each) | the long part |
|---|---|---|---|---|
| `scan` | `summary` | `why` | `deltas` | `proof` |
| `file` | `summary` | `narrative` | `per_file` | `diff` |
| `decision` | `decision` | `why` | `alternatives` | `excerpt` |
| `problem` | `problem` | `impact` | `attempts` | `excerpt` |
| `standup` | `summary` | `deviation` | `movement` | `detail` |
| `task` | `title` | `description` | | |
| `sprint` | `headline` | `retro` | `points` | `detail` |
| any other | `headline` | `summary` | `points` | `detail` |

Section 4 says what goes in each, per lens. `sp://schema` lists every
lens with its names and columns. A name the lens does not have is refused,
and the refusal lists the names it has. Do not send project, agent id,
date or time: the tool stamps them.

Two rules hold everywhere. The first field is one sentence: what happened,
or what it is. A field you cannot fill is left out: the wrong kind of
content is worse than an empty field. The answer may carry a `warnings`
list when an entry falls short. Fix it with `update_entry {lens, id,
changes}` — every name but the first — and write a new entry only when the
first line itself is wrong. The same entry written twice is one entry.

**Born from a discussion** (decisions, and any entry you write because of
an exchange; tagged visions, rules and problems are kept by the server
instead, section 4): the long part holds the chat excerpt as it was said.
The list holds the exchange, one item per point ("user: …", "agent: …").
The text holds the takeaway. The reader goes from the one line to what
was said.

Dates use `YYMM-DD` (`2608-12` = 2026-08-12). Times are `HH:MM`. The tool
stamps both.
