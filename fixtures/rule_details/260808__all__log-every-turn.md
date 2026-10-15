---
id: rl__all2ff06
created_date: 2608-08
project: _all
agent_id: operator
l1: Log every turn (the capture hooks) — never batch-log at session close
kind: lesson
importance: critical
status: active
related_incident: missed-15-turns
---

## L2 — Why this lesson

Missed calling the capture hooks for ~15 turns during the v0.1 build. Backfilled with condensed single-summary log, but individual turns + auto-triggers (standup_due, dream_owed) were lost. Ack decline counters drifted.

## L3 — Enforcement going forward

- Every turn: rely on the capture hooks BEFORE substantive work
- Standup_due signal: honour immediately (don't skip)
- Chat.md gap detection: if turn counter jumps by >2 vs prior state, that's a bug — investigate
- No "I'll batch later" excuse — one turn = one log call, always

## L4 — Raw context

Session 2608-08: v0.1 build turns 311-334 backfilled retroactively. The operator called it out — I confirmed only 1 summary entry instead of ~15 real turns.
