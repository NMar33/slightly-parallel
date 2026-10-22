---
id: sp_a001alpha
name: Auth v1
started_date: 2608-01
ended_date: 2608-04
projects: alpha-labs
time_budget_h: 20
status: closed
confidence_pct: 80
---

## L2 — Theme + intent

Ship JWT-based auth (15-min access + 7-day refresh) alongside Redis rate limiter, cleanly integrated with existing v1 API scaffold. Sprint kept tight — 3 goals, one week window, 20h budget.

## L3 — Goals inside

- `g_a1` · Ship v1 API with OpenAPI docs · done · 80% pred → 100% actual
- `g_a2` · Auth flow with OAuth2 + refresh tokens · done · 75% pred → 90% actual
- `g_a3` · Rate limiting middleware · done · 90% pred → 100% actual

## L4 — Retro

**Shipped**: All 3 goals green. v1 API deployed staging.

**Slipped**: nothing.

**Calibration diff**: predicted 80% aggregate, hit 97%. Under-confident. Adjust future estimates ↑ 15% for known-stack goals.

**Rules learned**: rl_a002bb02 (confidence tends toward optimism only for unknown APIs, not known-stack).

**Next sprint focus**: SDK generator (harder — unfamiliar API surface).
