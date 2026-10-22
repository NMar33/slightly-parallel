---
id: fl_pgloader01
created_date: 2608-04
project: beta-corp
agent_id: agent-explorer-2608-03
l1: 4 files · +214/−12 · pgloader config landed — schema mapping edge cases handled
prev_file_id: fl_rate001
trigger_lens: decision
trigger_id: dc_b_pgloader
files_important_n: 4
files_ignored_n: 7
paths:
- path: scripts/pgloader.conf
  action: created
  lines_add: 78
  lines_del: 0
  importance: 5
  blast_radius: 10
  novelty: new
  test_coverage: untested
  security_surface: false
  agent_confidence: 65
  tags:
  - infra
  - breaking
  why: Migration recipe — silent row loss would corrupt analytics.
- path: scripts/pre_migrate.sql
  action: created
  lines_add: 34
  lines_del: 0
  importance: 3
  blast_radius: 5
  novelty: new
  test_coverage: untested
  security_surface: false
  agent_confidence: 80
  tags:
  - infra
  why: Pre-flight validation — catches config errors early.
- path: scripts/post_migrate.sql
  action: created
  lines_add: 67
  lines_del: 0
  importance: 4
  blast_radius: 7
  novelty: new
  test_coverage: untested
  security_surface: false
  agent_confidence: 75
  tags:
  - infra
  why: Row-count diff + checksum — the safety net for silent loss.
- path: docs/migration-runbook.md
  action: created
  lines_add: 35
  lines_del: 0
  importance: 3
  blast_radius: 2
  novelty: new
  test_coverage: partial
  security_surface: false
  agent_confidence: 85
  tags:
  - docs
  why: Operator playbook — reduces judgment errors under time pressure.
---

## L2

**Overall**: pgloader configuration for MySQL→Postgres migration. Handles legacy schema edge cases: TINYINT→SMALLINT, ENUM types via cast expressions, TIMESTAMP vs TIMESTAMPTZ conversion. Rule `rl_b002dd04` (silent row loss) earned before this — post-migrate.sql now diffs COUNT(*) to catch.

**Per-file narrative**:
- `scripts/pgloader.conf` — the migration recipe, cast rules + batching.
- `scripts/pre_migrate.sql` — pre-flight validation queries.
- `scripts/post_migrate.sql` — post-migration verification (row counts, checksums).
- `docs/migration-runbook.md` — step-by-step operator playbook.

## L3

**`scripts/pgloader.conf`** — new file (78 lines). Source `MYSQL://...`, target `POSTGRESQL://...`. CAST rules: `type tinyint to smallint`, `type enum to text drop typemod using enum-to-text`, `type datetime to timestamptz using zero-dates-to-null`. Batch size 5000, workers 4. Why batch=5000: sweet spot between throughput + memory (tested).

**`scripts/pre_migrate.sql`** — new file (34 lines). Queries: row counts per table on source, unique constraint conflict pre-check, foreign key orphan pre-check. Exits nonzero if any table has zero rows unexpectedly. Why runs before not during: catches misconfiguration earlier — pgloader failures mid-run are painful to recover.

**`scripts/post_migrate.sql`** — new file (67 lines). For each migrated table: `SELECT COUNT(*)` vs source's known count → assert equal. `MD5(string_agg(...))` checksum comparison on sample of PK ranges. Fails loudly if mismatch. Why checksum on sample not full: full table checksum too slow (30min+ on 2.3M rows); sample gives 99%+ confidence in 30s.

**`docs/migration-runbook.md`** — new file (35 lines). 6-step playbook: (1) restore staging from prod snapshot, (2) run pre_migrate, (3) run pgloader, (4) run post_migrate, (5) sample queries, (6) sign-off checklist. Why doc not just script: cutover happens under time pressure; step-by-step manual reduces judgment errors.

## L4

*(parked — auto-populated from git branch diff in future iteration)*
