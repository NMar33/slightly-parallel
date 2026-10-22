---
id: pm_bc_migplan
title: Migration risk assessment prompt
---

## L2

Given this migration script and target schema, assess:

1. **Data loss risk** — Any columns being dropped OR types being narrowed? What existing rows would violate the new constraints?

2. **Downtime risk** — What operations require table locks? Estimated duration on a table of {{row_count}} rows on production hardware.

3. **Rollback path** — Is this reversible via simple `alembic downgrade`? Or does it require manual data recovery? Write the exact rollback SQL.

4. **Silent-failure classes** — Would pgloader/tools log WARNING but exit 0 on any expected edge case? What post-migration diff catches this?

Output as a checklist the operator can sign off on before enabling the migration window.
