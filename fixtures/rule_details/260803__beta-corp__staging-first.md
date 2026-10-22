---
id: rl_b001cc03
created_date: 2608-03
project: beta-corp
agent_id: agent-explorer-2608-03
l1: Always test migrations on a staging replica before touching prod
kind: rule
importance: critical
status: active
---

## L2 — Why this rule

Near-miss: agent almost ran pgloader against prod directly without testing on staging first. Would have taken prod down for 8+ minutes and required manual recovery.

## L3 — Enforcement

- CI blocks any migration script commit that doesn't reference a staging validation run
- Migration playbook step 1: "Restore staging from prod snapshot"
- Migration playbook step 2: "Run migration on staging, verify row counts + sample queries"
- Only after both pass → prod window opens

## L4 — Raw context

See goal g_b1 discussion. Chat lines 145-201 for the near-miss timeline.
