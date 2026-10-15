---
id: fl_baseline01
created_date: 2608-01
project: alpha-labs
agent_id: agent-genesis-2608-01
l1: 8 files · +820/−0 · FastAPI scaffold + Postgres migrations baseline landed
trigger_lens: scan
trigger_id: sn_baseline
files_important_n: 8
files_ignored_n: 2
paths:
- path: app/main.py
  action: created
  lines_add: 47
  lines_del: 0
  importance: 5
  blast_radius: 10
  novelty: new
  test_coverage: covered
  security_surface: false
  agent_confidence: 90
  tags: []
  why: Application entry — every request flows through this factory.
- path: app/deps.py
  action: created
  lines_add: 34
  lines_del: 0
  importance: 4
  blast_radius: 8
  novelty: new
  test_coverage: covered
  security_surface: false
  agent_confidence: 85
  tags: []
  why: Dependency wiring — any handler using Depends() touches this.
- path: app/api/v1/__init__.py
  action: created
  lines_add: 12
  lines_del: 0
  importance: 2
  blast_radius: 5
  novelty: new
  test_coverage: partial
  security_surface: false
  agent_confidence: 95
  tags:
  - api-endpoint
  why: Router mount point — thin wrapper.
- path: migrations/001_baseline.sql
  action: created
  lines_add: 89
  lines_del: 0
  importance: 5
  blast_radius: 10
  novelty: new
  test_coverage: partial
  security_surface: false
  agent_confidence: 90
  tags:
  - migration
  - breaking
  why: Foundational schema — locks downstream model shape.
- path: migrations/002_indexes.sql
  action: created
  lines_add: 23
  lines_del: 0
  importance: 3
  blast_radius: 6
  novelty: new
  test_coverage: partial
  security_surface: false
  agent_confidence: 85
  tags:
  - migration
  why: Critical query performance indexes.
- path: tests/conftest.py
  action: created
  lines_add: 58
  lines_del: 0
  importance: 3
  blast_radius: 8
  novelty: new
  test_coverage: covered
  security_surface: false
  agent_confidence: 90
  tags:
  - test
  why: Test fixtures — enables every future test to be fast + isolated.
- path: pyproject.toml
  action: created
  lines_add: 76
  lines_del: 0
  importance: 2
  blast_radius: 3
  novelty: new
  test_coverage: partial
  security_surface: false
  agent_confidence: 95
  tags:
  - infra
  why: Dependency pins — prevents silent transitive breakage.
- path: .github/workflows/ci.yml
  action: created
  lines_add: 34
  lines_del: 0
  importance: 3
  blast_radius: 4
  novelty: new
  test_coverage: partial
  security_surface: false
  agent_confidence: 80
  tags:
  - infra
  why: CI catches regressions before merge.
---

## L2

**Overall**: Initial project scaffold. FastAPI application entry, dependency wiring, Postgres migration baseline schema (users + sessions + api_keys), pytest harness + CI. Everything ready for feature work.

**Per-file narrative**:
- `app/main.py` — FastAPI entrypoint. Wires CORS, lifespan hooks for DB connection pooling, health endpoint.
- `app/deps.py` — dependency-injection setup. Central place where auth / DB / config injected across handlers.
- `app/api/v1/__init__.py` — v1 router mount point. Future endpoints branch from here.
- `migrations/001_baseline.sql` — foundational schema. Locks down user identity + session shape early so downstream work doesn't fight the model.
- `migrations/002_indexes.sql` — critical indexes for auth queries. Adding these later would require prod downtime.
- `tests/conftest.py` — pytest fixtures: db_session, client. Enables every future test to write cleanly.
- `pyproject.toml` — pinned deps (FastAPI 0.115, sqlalchemy 2.0, alembic).
- `.github/workflows/ci.yml` — GitHub Actions lint+test on push. Catches breakage before it reaches main.

## L3

**`app/main.py`** — new file (47 lines). Defines `create_app()` factory returning FastAPI instance. Adds middleware: `CORSMiddleware` (permissive for dev), custom `lifespan` async context manager that opens/closes DB pool. Registers `/health` endpoint returning `{status: 'ok', version: settings.VERSION}`. Why: factory pattern lets tests inject config without mutating module globals.

**`app/deps.py`** — new file (34 lines). Declares `get_db()` async generator using `sqlalchemy.ext.asyncio`, `get_settings()` cached via `lru_cache`, `get_current_user()` stub (returns None until auth lands). Why: FastAPI's `Depends()` semantics require these as callables — centralized here so router files stay thin.

**`app/api/v1/__init__.py`** — new file (12 lines). Creates `APIRouter(prefix='/api/v1')`, exposes as `router`. Why: prefix at router level (not per-endpoint) simplifies later versioning (`/api/v2` becomes copy+bump).

**`migrations/001_baseline.sql`** — new file (89 lines). Creates 3 tables: `users(id, email UNIQUE, created_at)`, `sessions(id, user_id FK, refresh_token_hash, expires_at, revoked_at NULL)`, `api_keys(id, user_id FK, key_hash UNIQUE, created_at, revoked_at NULL)`. Why: `refresh_token_hash` column added preemptively — auth flow next sprint doesn't need migration.

**`migrations/002_indexes.sql`** — new file (23 lines). B-tree indexes on `users.email`, `sessions.user_id`, `sessions.expires_at WHERE revoked_at IS NULL`, `api_keys.key_hash`. Why: query planner needs these for sub-100ms auth lookups on real data.

**`tests/conftest.py`** — new file (58 lines). Defines `db_session` (transactional rollback fixture), `client` (httpx AsyncClient tied to app), `settings_override` (env-var patch context manager). Why: enables integration tests to be fast (transaction rollback) + isolated (fresh settings per test).

**`pyproject.toml`** — new file (76 lines). Project metadata + explicit version pins. Why: pinned versions prevent silent breakage on transitive upgrades.

**`.github/workflows/ci.yml`** — new file (34 lines). Triggers on push to main + PRs. Runs ruff (lint), mypy (types), pytest (tests) in parallel jobs. Why: parallel execution keeps CI < 3min.

## L4

*(parked — auto-populated from git branch diff in future iteration)*
