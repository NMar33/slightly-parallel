---
id: sn_pdr_files02
created_date: 2608-10
created_time: '12:50'
project: pdr-framework-dev
agent_id: mira-sztern-lenses-2608-09
l1: "Heatmap: paths frontmatter on every file entry, /api/files/heatmap path × date, CSS-grid density strip in the project tab"
files_n: 4
lines_add: 231
lines_del: 9
decisions_n: 0
scope: backend/routers/files_extra, frontend FilesTab
---

## L2

The heatmap forced structure the lens did not have: per-path records replaced prose lists in every seed entry.

## L3

- backend/backend/routers/files_extra.py +96 — heatmap aggregation, semantic score
- fixtures/file_details/* — 44 path records added across 5 entries
- frontend/src/features/project/FilesTab.tsx +118 — CSS grid heatmap, 14px cells

## L4

pytest: 121 passed. Heatmap for alpha-labs: 12 files × 3 dates.
