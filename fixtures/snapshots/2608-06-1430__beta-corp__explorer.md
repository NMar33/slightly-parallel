---
id: sn_demo02
created_date: 2608-06
created_time: 14:30
project: beta-corp
agent_id: agent-explorer-2608-03
l1: Migration script tested in staging Kafka pipeline scaffolded cutover next week
files_n: 7
lines_add: 412
lines_del: 45
decisions_n: 3
scope: scripts/pgloader.conf
---

## L2

pgloader migration ran end-to-end in staging: 2.3M rows, 47 tables, 8 minutes wall clock. Schema mapping validated (MySQL TINYINT → PG SMALLINT, ENUM types preserved). Kafka scaffold up with 3 topics and Confluent schema registry. Cutover plan drafted — read replica ready.

## L3

- Chose pgloader over custom ETL — handles schema mapping automatically
- Kafka over RabbitMQ — retention + replay + analytics tools
- Logical replication for cutover — zero-downtime + rollback safe
- Staging tests: all queries return same result set as MySQL production

## L4

Chat lines 89-156 for migration approach evaluation; lines 234-289 for Kafka schema registry setup.
