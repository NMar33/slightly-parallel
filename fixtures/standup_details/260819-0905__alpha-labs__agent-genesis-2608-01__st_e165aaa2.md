---
id: st_e165aaa2
created_date: 2608-19
created_time: 09:05
project: alpha-labs
agent_id: agent-genesis-2608-01
for_date: 2608-18
goals_open_n: 2
goals_closed_n: 1
blockers_n: 1
hours_today: 4.5
l1: Token signing settled on RS256; the rate limiter is the one thing still open.
md_ref: standup_details/260819-0905__alpha-labs__agent-genesis-2608-01__st_e165aaa2.md
---

## L2
- The limiter was called done on 2608-17; it counts in memory only, so two API processes each allow the whole quota.

## L3
- `POST /v1/token` issues a 15-minute token a customer's SDK can verify.
- The token format brief is written and names its open questions.
- Per-key rate limiting counts correctly on one process.

## L4
Yesterday's two sessions were agent-genesis on auth. The operator asked once for the SDK generator choice and did not get an answer, so it carries over.
