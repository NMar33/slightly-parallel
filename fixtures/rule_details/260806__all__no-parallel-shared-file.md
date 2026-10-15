---
id: rl__all1ee05
created_date: 2608-06
project: _all
agent_id: operator
l1: No parallel subagents that share a mutable file — sequential only
kind: rule
importance: critical
status: active
related_incident: server-py-endpoints-dropped
---

## L2 — Why this rule

Ran 3 parallel subagents editing server.py + App.tsx simultaneously. Result: last-writer-wins overwrote endpoints and sidebar entries added by earlier agents. Lost ~2 hours reconstructing dropped code.

## L3 — Correct patterns

- **Sequential**: agent 1 finishes server.py edit → agent 2 starts next edit
- **Isolated**: each agent works in its own file/module
- **Merge stage**: parallel agents produce diffs → dedicated merger applies them one at a time
- **Never**: multiple agents editing same file simultaneously with overlapping regions

## L4 — Raw context

Incident 2608-08: react-drill-parity workflow. Reconstruction took 3 turns + 2 workflow runs.
