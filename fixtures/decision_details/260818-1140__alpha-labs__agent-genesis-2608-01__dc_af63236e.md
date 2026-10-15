---
id: dc_af63236e
created_date: 2608-18
created_time: '11:40'
project: alpha-labs
agent_id: agent-genesis-2608-01
weight: major
source: explicit
l1: Tokens are signed with RS256, not HS256
decision_text: Tokens are signed with RS256, not HS256
md_ref: decision_details/260818-1140__alpha-labs__agent-genesis-2608-01__dc_af63236e.md
---

## L2
The SDK ships to customers, so the verifying key travels with it. A shared secret in a customer's binary is a breach waiting for a decompiler. Undo it only if key rotation turns out to cost more than a week a quarter, or if a customer cannot reach `/v1/jwks` from their build.

## L3
- HS256 with a shared secret — rejected: the secret would ship in the SDK.
- Opaque tokens with an introspection call — rejected: one extra round trip on every request, and the SDK works offline in CI.

## L4
operator: 'the SDK is going to customers, assume it is read'
