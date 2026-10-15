---
id: fl_auth001
created_date: 2608-02
project: alpha-labs
agent_id: agent-genesis-2608-01
l1: 5 files · +342/−78 · Auth flow refactored — JWT + refresh rotation now atomic
prev_file_id: fl_baseline01
trigger_lens: decision
trigger_id: dc_c0ee19d8
files_important_n: 5
files_ignored_n: 3
paths:
- path: app/auth/jwt.py
  action: created
  lines_add: 98
  lines_del: 0
  importance: 5
  blast_radius: 9
  novelty: new
  test_coverage: covered
  security_surface: true
  agent_confidence: 85
  tags:
  - security
  why: JWT primitives — every authenticated request decodes tokens here.
- path: app/auth/rotation.py
  action: created
  lines_add: 67
  lines_del: 0
  importance: 5
  blast_radius: 8
  novelty: new
  test_coverage: covered
  security_surface: true
  agent_confidence: 75
  tags:
  - security
  why: Atomic refresh — the reason for the sprint. Race would corrupt sessions.
- path: app/api/v1/auth.py
  action: created
  lines_add: 54
  lines_del: 0
  importance: 4
  blast_radius: 7
  novelty: new
  test_coverage: covered
  security_surface: true
  agent_confidence: 85
  tags:
  - api-endpoint
  why: Login/refresh/logout endpoints — public surface for auth.
- path: tests/auth/test_rotation.py
  action: created
  lines_add: 156
  lines_del: 0
  importance: 4
  blast_radius: 3
  novelty: new
  test_coverage: covered
  security_surface: true
  agent_confidence: 90
  tags:
  - test
  why: Concurrent-rotation race test — the invariant guardrail.
- path: migrations/003_refresh_tokens.sql
  action: created
  lines_add: 34
  lines_del: 0
  importance: 4
  blast_radius: 7
  novelty: new
  test_coverage: partial
  security_surface: true
  agent_confidence: 90
  tags:
  - migration
  - breaking
  why: Refresh tokens table with revoked_at — hard to rollback once shipped.
- path: app/main.py
  action: modified
  lines_add: 4
  lines_del: 8
  importance: 5
  blast_radius: 10
  novelty: new
  test_coverage: covered
  security_surface: false
  agent_confidence: 90
  tags: []
  why: Application entry — every request flows through this factory.
- path: app/deps.py
  action: modified
  lines_add: 3
  lines_del: 12
  importance: 4
  blast_radius: 8
  novelty: new
  test_coverage: covered
  security_surface: false
  agent_confidence: 85
  tags: []
  why: Dependency wiring — any handler using Depends() touches this.
---

## L2

**Overall**: JWT auth landed with atomic refresh token rotation. Previous naive implementation had race window where two concurrent refreshes could both succeed and leave orphaned tokens. Fixed by wrapping rotation in single DB transaction using `SELECT FOR UPDATE`.

**Per-file narrative**:
- `app/auth/jwt.py` — new file, all JWT primitives (encode, decode, verify signature).
- `app/auth/rotation.py` — the atomic-swap logic, uses row-level lock to eliminate race.
- `app/api/v1/auth.py` — endpoints exposing login/refresh/logout to clients.
- `tests/auth/test_rotation.py` — 12 tests including deliberate concurrent-rotation scenario that used to fail.
- `migrations/003_refresh_tokens.sql` — schema addition for `refresh_tokens` table with revoked_at column.

## L3

**`app/auth/jwt.py`** — new file (98 lines). Defines `encode_access_token(user_id, expires_in_minutes=15)`, `encode_refresh_token(user_id, expires_in_days=7)`, `decode_token(raw) -> Claims | None`. Uses `python-jose` under the hood with HS256 (algo pinned). Adds `TokenClaims` Pydantic model. Why HS256 not RS256: no key-distribution needed for single-service auth; can upgrade later.

**`app/auth/rotation.py`** — new file (67 lines). Core function `rotate_refresh_token(session, old_refresh_token) -> tuple[str, str] | None`. Inside a single transaction: `SELECT ... FOR UPDATE` on refresh_tokens row → mark old row as `revoked_at=now()` → INSERT new row → return (new_access, new_refresh). Why FOR UPDATE not optimistic: refresh calls are rare enough that lock contention doesn't hurt, and race elimination guarantees stronger than retry-on-conflict.

**`app/api/v1/auth.py`** — new file (54 lines) + updates. Endpoints: `POST /login` (email + password → access + refresh), `POST /refresh` (refresh → new pair, calls rotation.py), `POST /logout` (revokes current refresh). Why POST not PUT for refresh: not idempotent (rotation consumes old token).

**`tests/auth/test_rotation.py`** — new file (156 lines). Notable tests: `test_concurrent_refresh_only_one_wins` uses `asyncio.gather` to fire two refreshes with same token → asserts exactly one succeeds and other gets 401. Why this test matters: the whole reason for the SELECT FOR UPDATE.

**`migrations/003_refresh_tokens.sql`** — new file (34 lines). Creates `refresh_tokens(id, user_id FK, token_hash UNIQUE, issued_at, expires_at, revoked_at NULL)`. Index on (user_id, revoked_at). Why hash not raw: even if DB dumped, tokens are useless.

## L4

*(parked — auto-populated from git branch diff in future iteration)*
