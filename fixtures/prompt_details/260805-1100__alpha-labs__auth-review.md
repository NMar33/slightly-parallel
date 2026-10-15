---
id: pm_al_review
title: Auth flow code review prompt
---

## L2

Review this auth flow diff. Focus specifically on:

1. **Token rotation atomicity** — Is the refresh path a single DB transaction? Does it survive concurrent invocation with the same refresh token? Point to the specific line where race protection lives.

2. **Secret handling** — Are any tokens logged? Any tokens passed in URL parameters? Any long-lived credentials in-memory without explicit revocation path?

3. **Error responses** — Do 401 responses differentiate between "no token" vs "expired token" vs "revoked token"? Should they, or is uniform failure better for security posture?

4. **Test coverage gaps** — What class of concurrent-refresh scenarios are not covered? Any race conditions I might have missed?

Reply with line-referenced findings, ranked by severity.
