---
id: rl_a002bb02
created_date: 2608-04
project: alpha-labs
agent_id: agent-genesis-2608-01
l1: Confidence percentages tend toward optimism — halve first estimate for anything involving unknown APIs
kind: lesson
importance: minor
status: active
---

## L2 — Why this lesson

SDK generator research was estimated at 5 days, 60% confidence. Actual: 9 days. Pattern repeats — anytime the goal touches an unfamiliar API, initial estimate is 40-60% under.

## L3 — Concrete adjustments

- Known-stack goals: keep estimate + confidence as-is
- Unknown-API goals: multiply time_est × 2, subtract 20% from confidence
- Novel research goals: multiply time_est × 3, confidence ≤ 40%

## L4 — Raw context

Calibration data from Goal g_a4 retro. See goal L4 for full retrospective.
