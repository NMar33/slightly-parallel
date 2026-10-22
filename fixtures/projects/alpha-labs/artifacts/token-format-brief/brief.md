# Token format — what the SDK will see

One page for the two people who have to implement against it.

## The token

A JWT, signed RS256. Header `{alg: RS256, kid}`. Claims: `sub` (the API
key id), `scope` (space separated), `iat`, `exp` (15 minutes), `iss`
(`alpha-labs`). Nothing else — anything the client needs beyond this is a
second call, not a bigger token.

## Verifying it

1. Fetch `/v1/jwks` once and cache by `kid`.
2. Verify the signature, then `exp`, then `iss`.
3. Refuse `alg: none` and refuse HS256 outright, whatever the header says.

## What is not decided

- Rotation cadence. The endpoint serves two keys so rotation is possible;
  nobody has said how often.
- Refresh tokens. Out of scope for v1: 15 minutes and ask again.
