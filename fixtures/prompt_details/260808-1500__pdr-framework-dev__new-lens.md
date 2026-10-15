---
id: pm_mk_lens
title: New lens scaffold prompt
---

## L2

I want to add a new lens called `{{lens_name}}` to Slightly Parallel. Please:

1. Add entry to `_ENTITY_CONFIG` in `backend/backend/server.py` with `id_prefix`, `csv_cols`, `detail_dir`, `view`, `response_key`.
2. Add its mutual view to the tuple in `backend/backend/db.py` rebuild loop.
3. Register 3 endpoints (GET list, GET /{id}, POST) reusing `_generic_create` + `_read_detail_md`.
4. Create seed data — 3-4 realistic entries plus MD detail files.
5. Copy `frontend/public/decisions.html` to `frontend/public/{{lens_name}}.html`, sed-swap decisions strings to new lens semantics.
6. Add sidebar entry in `frontend/src/App.tsx` with a lucide icon.
7. Update `frontend/public/lenses.html` — add lens card front + back face with L1-L4 layer descriptions, bump lenses count.
8. Rebuild frontend + restart backend + screenshot.

Layer semantics I want:
- L1: {{L1 description}}
- L2: {{L2 description}}
- L3: {{L3 description}}
- L4: {{L4 description}}
