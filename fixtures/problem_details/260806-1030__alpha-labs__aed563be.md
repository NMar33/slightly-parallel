---
id: pb_aed563be
created_date: 2608-06
created_time: 10:30
project: alpha-labs
agent_id: agent-genesis-2608-01
l1: "TS SDK types leak internal enum variants — public API surface pollution."
severity: nit
status: resolved
related_goal_id: g_a4
resolved_date: 2608-08
---

## L2 — Problem context

openapi-generator emitted every discriminator variant into the public types file, including internal-only ones prefixed `_`. TS users saw unfamiliar enum values in autocomplete.

## L3 — Attempts / workarounds

- Add a filter step in the SDK build to drop `_`-prefixed variants
- Verify against generated .d.ts file

## L4 — Resolution / raw discussion

Fixed by post-processing the emitted types. Kept the fix in the build script rather than forking the generator config.
