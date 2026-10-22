---
id: fl_pdr_files01
created_date: 2608-10
created_time: '09:46'
project: pdr-framework-dev
agent_id: mira-sztern-lenses-2608-09
l1: "6 files · +412/−18 · Files lens: entity, view, chain endpoint, editorial page"
prev_file_id: fl_scan_close01
trigger_lens: scan
trigger_id: sn_pdr_files01
files_important_n: 4
files_ignored_n: 2
paths:
- path: backend/backend/entities.py
  action: modified
  lines_add: 38
  lines_del: 2
  importance: 4
  blast_radius: 8
  novelty: pattern-follow
  test_coverage: covered
  security_surface: false
  agent_confidence: 90
  tags: [registry]
  why: "Every lens is one registry entry; the file entity rides the same list/detail/create factory."
- path: backend/backend/routers/files_extra.py
  action: created
  lines_add: 140
  lines_del: 0
  importance: 5
  blast_radius: 6
  novelty: new
  test_coverage: covered
  security_surface: false
  agent_confidence: 85
  tags: [api]
  why: "The chain walk is the lens's reason to exist — without /diff a file entry is a scan with extra steps."
- path: backend/backend/db.py
  action: modified
  lines_add: 22
  lines_del: 4
  importance: 3
  blast_radius: 9
  novelty: pattern-follow
  test_coverage: covered
  security_surface: false
  agent_confidence: 80
  tags: [duckdb]
  why: "files_mutual view; touches the shared view builder every entity depends on."
- path: frontend/files.html
  action: created
  lines_add: 180
  lines_del: 0
  importance: 2
  blast_radius: 2
  novelty: pattern-follow
  test_coverage: untested
  security_surface: false
  agent_confidence: 70
  tags: [ui]
  why: "Editorial page copied from decisions.html — copy-paste strings were the bug found next turn."
- path: fixtures/file_details/260801-0900__alpha-labs__baseline.md
  action: created
  lines_add: 64
  lines_del: 0
  importance: 1
  blast_radius: 1
  novelty: new
  test_coverage: untested
  security_surface: false
  agent_confidence: 95
  tags: [fixture]
  why: "Seed entry; the chain has to start somewhere."
- path: fixtures/files.csv
  action: created
  lines_add: 6
  lines_del: 0
  importance: 1
  blast_radius: 1
  novelty: new
  test_coverage: untested
  security_surface: false
  agent_confidence: 95
  tags: [fixture]
  why: "Index for the seed entries."
---

## L2

Overall: the Files lens exists as an entity plus a chain endpoint. Blast radius sits in db.py (shared view builder) and entities.py (the registry every lens goes through); the editorial page is cosmetic and was copied, which is exactly where the next bugs appeared.

## L3

- backend/backend/routers/files_extra.py — files_diff(from, to): walks prev_file_id from `to` back to `from`, returns entries chronological; 404 when the chain never reaches `from`
- backend/backend/entities.py — file entity: id fl_, columns incl. prev_file_id/trigger_lens/trigger_id/files_important_n
- backend/backend/db.py — files_mutual view over files.csv with the same COALESCE/TRY_CAST pattern as scans

## L4

*(git diff — attached when the project path is registered)*
