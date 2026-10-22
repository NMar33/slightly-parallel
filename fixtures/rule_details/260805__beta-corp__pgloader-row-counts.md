---
id: rl_b002dd04
created_date: 2608-05
project: beta-corp
agent_id: agent-explorer-2608-03
l1: pgloader silently drops rows with encoding mismatches — always diff row counts after
kind: lesson
importance: major
status: active
---

## L2 — Why this lesson

pgloader ran clean, said "success", but 47 rows disappeared. Root cause: UTF-8 vs Latin1 mismatch in one legacy MySQL column. pgloader logged warnings but didn't fail.

## L3 — Concrete adjustments

- Post-migration check: `SELECT COUNT(*) FROM src.<table>` vs `SELECT COUNT(*) FROM dst.<table>` for every migrated table
- Grep pgloader output for "WARNING" — treat as error
- Add `--summary` flag to see exact row-in vs row-out counts

## L4 — Raw context

See related_goal g_b1. Original silent-loss incident on 2608-04.
