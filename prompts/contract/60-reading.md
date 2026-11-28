---
key: reading
section: 5
heading: ## 5. Reading
title: Reading
enabled: true
---

Project reads through MCP and HTTP `GET` are open to any existing project.
A project-scoped MCP reader defaults to the chat's home project.
The scan, map and architecture material tools prepare a write and require
membership in the target project.

- `tasks {project?, status?}` — the board; `search {q}` — tasks,
  decisions and agents by text; `project {project}` — one project's bundle;
  `deck` — every running sprint block; `doctor` — the data-integrity report.
- `sp://rules` — the active rules of the chat's home project; `sp://schema` — every lens,
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
