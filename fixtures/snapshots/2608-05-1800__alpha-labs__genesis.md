---
id: sn_demo01
created_date: 2608-05
created_time: 18:00
project: alpha-labs
agent_id: agent-genesis-2608-01
l1: v1 API shipped GREEN — auth + rate limit landed, SDK generator next
files_n: 14
lines_add: 892
lines_del: 134
decisions_n: 4
scope: app/
---

## L2

v1 API delivered end-to-end: 47 endpoints with OpenAPI docs, JWT auth (15-min access + 7-day refresh), Redis-backed rate limiter (100 req/min per user). 42 unit tests + 12 integration tests all green. Deployed to staging, Postgres migrations clean.

## L3

- Chose FastAPI over Flask — async + auto-OpenAPI won
- JWT rotation with 15/7 window — industry standard, refresh flow tested
- Redis for rate-limit counters — atomic INCR cheaper than Postgres
- pgloader migration handled edge cases: TIMESTAMP vs TIMESTAMPTZ, enum types

## L4

Chat lines 234-341 for auth flow discussion; lines 512-598 for rate limiter design tradeoffs.
