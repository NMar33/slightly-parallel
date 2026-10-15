---
id: dc_c0ee19d8
created_date: 2608-02
created_time: 12:00
project: alpha-labs
agent_id: agent-genesis-2608-01
decision_text: "JWT with 15-min access + 7-day refresh"
source: auto
related_goal_id: g_a2
files_affected_n: 0
alternatives_n: 2
---

## L2 — Rationale

industry standard tradeoff

## L3 — Alternatives considered

- **Alt 1**: Session cookies — simpler but requires sticky sessions
- **Alt 2**: OAuth2 opaque tokens — server-side revocation lookup adds latency

## L4 — Raw context

See related_goal_id `g_a2` chat for the original discussion context. Line refs pending manual backfill.
