---
id: rl_a001aa01
created_date: 2608-02
project: alpha-labs
agent_id: agent-genesis-2608-01
l1: Never mock the database in integration tests — use a real Postgres container
kind: rule
importance: major
status: active
related_incident: mock-vs-prod-migration-fail
related_goal_id: g_a1
---

## L2 — Why this rule

Mocked tests passed but production migration failed silently because the mock didn't enforce the same NOT NULL / foreign key constraints as real Postgres. The team lost 4 hours to a bug that would have been caught in seconds by a real DB.

## L3 — Examples

- **Bad**: `mock_db.query.return_value = [{"id": 1}]` — passes but hides real constraint violations
- **Good**: `docker run postgres:16` + real migration + real seed data
- **Compromise**: `testcontainers-python` for automated real-Postgres fixtures

## L4 — Raw context

See goal g_a1 chat lines 234-289. Original discussion + post-mortem.
