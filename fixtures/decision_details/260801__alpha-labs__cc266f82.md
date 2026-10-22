---
id: dc_cc266f82
created_date: 2608-01
created_time: 12:00
project: alpha-labs
agent_id: agent-genesis-2608-01
decision_text: "Chose FastAPI over Flask"
source: explicit
related_goal_id: g_a1
files_affected_n: 0
alternatives_n: 2
---

## L2 — Rationale

async support + auto OpenAPI + type hints

## L3 — Alternatives considered

- **Alt 1**: Flask — mature ecosystem but sync-only; blocks the async workload
- **Alt 2**: Starlette — thinner layer but no built-in OpenAPI generation

## L4 — Raw context

See related_goal_id `g_a1` chat for the original discussion context. Line refs pending manual backfill.
