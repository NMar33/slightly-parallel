---
id: sp_b001beta
name: MySQL→Postgres cutover
started_date: 2608-02
projects: beta-corp
time_budget_h: 40
status: active
confidence_pct: 55
---

## L2 — Theme + intent

Migrate legacy MySQL to Postgres with zero downtime, using pgloader + logical replication. Also scaffold Kafka analytics pipeline in parallel. Larger sprint (40h budget) — riskier moves, lower confidence.

## L3 — Goals inside

- `g_b1` · Migrate legacy MySQL to Postgres · active · 65% · 5d/7d
- `g_b2` · Zero-downtime cutover · active · 55% · 3d/2d (slipping)
- `g_b3` · Analytics event pipeline (Kafka) · active · 70% · 5d/10d

## L4 — Retro (pending — sprint active)

Cutover rehearsal in staging planned for 2608-09.
