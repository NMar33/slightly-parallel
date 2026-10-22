---
id: dc_a2bade34
created_date: 2608-01
created_time: 12:00
project: alpha-labs
agent_id: agent-genesis-2608-01
decision_text: "PostgreSQL over SQLite for prod"
source: explicit
related_goal_id: g_a1
files_affected_n: 0
alternatives_n: 2
---

## L2 — Rationale

horizontal scaling + JSONB queries

## L3 — Alternatives considered

- **Alt 1**: SQLite — zero-config but does not scale horizontally
- **Alt 2**: MongoDB — schemaless but no ACID for our write patterns

## L4 — Raw context

See related_goal_id `g_a1` chat for the original discussion context. Line refs pending manual backfill.
