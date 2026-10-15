# Chat log — cc-cutover01
*Started 2026-08-11T09:31:02. Verbatim captured turns.*

---

## Turn 1 · 2026-08-11T09:31:02
**User**: 1. tk_bc_pgloader_fix · Fix pgloader silent-loss detection in post-migrate script
Compare source and target row counts per table after the load; fail loudly, print the delta.

2. tk_bc_checksum · Sample-checksum validation harness for post-migrate
Sample 1% of rows per table, md5 both sides, report mismatches.
**Agent**: Taking both. Starting with tk_bc_pgloader_fix — the post-migrate script swallows pgloader's exit code, so a partial load looks green. Adding a per-table count diff and a non-zero exit. Then tk_bc_checksum on top of the same table list.

## Turn 2 · 2026-08-11T10:48:40
**User**: status?
**Agent**: tk_bc_pgloader_fix: done — counts diffed per table, delta printed, exit 2 on any loss; 3 tests. tk_bc_checksum: harness samples 1% with a fixed seed, md5 per row, mismatches listed with primary keys; running it against staging now.

## Turn 3 · 2026-08-11T12:05:11
**User**: ok, and tk_bc_kafka_alert · Add Kafka consumer lag Prometheus alert
lag > 5000 for 5m pages the on-call
**Agent**: tk_bc_kafka_alert added: rule on kafka_consumergroup_lag, for: 5m, severity page; wired into the cutover alert group. Both harness runs on staging came back clean.
