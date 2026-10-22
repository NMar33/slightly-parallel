---
key: reading
section: 5
heading: ## 5. Reading
title: Reading
enabled: true
---

Reading is open: the MCP readers and the HTTP `GET` routes both answer.

- `tasks {project?, status?}` — the board; `search {q}` — tasks,
  decisions and agents by text; `project {code}` — one project's bundle;
  `deck` — every running sprint block; `doctor` — the data-integrity report.
- `sp://rules` — the active rules; `sp://schema` — every lens,
  its fields and what is mutable; `sp://contract` — this file.
- `GET /api/<entity>?project=<PROJECT>` — any ledger, filterable.
- `GET /api/<entity>/{id}` — one entry with its text and fields.
- `GET /api/sessions?project=<PROJECT>` — the chats, read from the turns (read-only).
- `GET /api/agents/<agent_id>/profile` — everything under one agent id:
  chats, scans, entries, the tasks its turns named, links, group
  (read-only; yours is under your own id).
- `GET /api/snapshot` — the cross-project overview.

Full reference: `docs/api.md` in the Slightly Parallel repo, or `/docs` on the server.
The dashboard's Guide page describes every page as it is.
