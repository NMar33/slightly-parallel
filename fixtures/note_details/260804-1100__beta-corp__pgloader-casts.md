---
id: nt_bc_pgloader
title: pgloader cast rules that actually worked
---

## L2

Legacy MySQL edge cases in our production data:

- `type tinyint to smallint` — MySQL TINYINT(1) treats as bool but our data has values 0-127
- `type enum to text drop typemod using enum-to-text` — Postgres enums are inflexible; text + CHECK constraint is easier to evolve
- `type datetime to timestamptz using zero-dates-to-null` — MySQL has '0000-00-00' zero-dates; Postgres won't accept these

Full config lives in `scripts/pgloader.conf`.
