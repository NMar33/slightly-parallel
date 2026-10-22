---
id: fl_pdr_files02
created_date: 2608-10
created_time: '12:51'
project: pdr-framework-dev
agent_id: mira-sztern-lenses-2608-09
l1: "4 files · +231/−9 · heatmap: paths frontmatter, aggregation endpoint, grid in the project tab"
prev_file_id: fl_pdr_files01
trigger_lens: scan
trigger_id: sn_pdr_files02
files_important_n: 3
files_ignored_n: 1
paths:
- path: backend/backend/routers/files_extra.py
  action: modified
  lines_add: 96
  lines_del: 3
  importance: 5
  blast_radius: 7
  novelty: pattern-break
  test_coverage: covered
  security_surface: false
  agent_confidence: 85
  tags: [api, hot-path]
  why: "Reads every file entry's frontmatter on each call — the first endpoint that parses YAML at request time; the etag is what keeps it cheap."
- path: frontend/src/features/project/FilesTab.tsx
  action: created
  lines_add: 118
  lines_del: 0
  importance: 3
  blast_radius: 3
  novelty: new
  test_coverage: partial
  security_surface: false
  agent_confidence: 80
  tags: [ui]
  why: "CSS-grid density strip; quantile buckets so a 3-line edit and a 3400-line commit both show."
- path: fixtures/file_details/260803-1130__alpha-labs__rate-limit.md
  action: modified
  lines_add: 17
  lines_del: 6
  importance: 2
  blast_radius: 1
  novelty: pattern-follow
  test_coverage: untested
  security_surface: false
  agent_confidence: 95
  tags: [fixture]
  why: "paths: block added — the heatmap has nothing to plot without it."
- path: docs/api.md
  action: modified
  lines_add: 8
  lines_del: 0
  importance: 1
  blast_radius: 1
  novelty: pattern-follow
  test_coverage: untested
  security_surface: false
  agent_confidence: 95
  tags: [docs]
  why: "Endpoint documented."
---

## L2

Overall: the heatmap turned the lens from prose into structure — per-path records with importance, blast radius and coverage. The risk is request-time YAML parsing in files_extra.py; acceptable while entries number in the hundreds.

## L3

- backend/backend/routers/files_extra.py — files_heatmap(): matrix keyed path||date, semantic_score composite (importance×5 + blast×2 + security 15 + coverage 0/8/15 + (100−confidence)×0.15 + novelty 3/6/10)
- frontend/src/features/project/FilesTab.tsx — weightOf(cell) by mode (lines | importance), rank-based quantile buckets at 22/40/60/80/100%

## L4

*(git diff — attached when the project path is registered)*
