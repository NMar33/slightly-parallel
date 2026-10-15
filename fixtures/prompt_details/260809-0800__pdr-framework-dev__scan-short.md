---
id: pm_mk_scan
title: SCAN checkpoint prompt (short version)
---

## L2

Write a SCAN entry for the period since the previous SCAN (find it in `/api/scans?agent_id={{agent_id}}&limit=1`). Structure:

**L1** (one sentence, CEO-scannable): what shipped OR what's the state right now.

**L2** (paragraph): expand L1 — what mattered, what's blocking, what surprised.

**L3** (bullets): concrete items — decisions logged, goals shipped, problems opened, files touched (reference `/api/files/heatmap?project={{project}}&from_date={{prev_scan_date}}`).

**L4** (raw): chat line refs for anyone auditing.

POST to `/api/scans` with all four layers. Also trigger a file-analysis entry via `/api/files` linking back to this SCAN (`trigger_lens=scan`, `trigger_id=<new_scan_id>`).
