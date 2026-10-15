---
id: nt_mk_ports
title: Port assignments and env vars cheatsheet
---

## L2

**Ports**:
- 8123 — old MVP (killed)
- 8124 — Slightly Parallel backend (current)
- 5173 — Vite dev server

**Env vars**:
- `SCAN_DATA_ROOT` — data root path (recommended)
- `DATA_ROOT` — legacy alias
- fallback → repo-relative `./fixtures/`

**Start command**:
```bash
cd slightly-parallel/backend
PORT=8124 SCAN_DATA_ROOT="$SP_REPO/fixtures" ./.venv/bin/python -m backend.server
```
