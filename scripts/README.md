# Scripts

Tools that ship with Slightly Parallel. The Python ones use only the standard
library (3.11+), except `demo/` and `check_api_doc.py`, which need the
backend's environment. Each can be run again with the same result.

## `hooks/` — recording the chats

The capture core and one adapter per tool, all installed from the Setup
page. `capture.py` writes every chat turn; `claude-code-capture.py`,
`slightly-parallel-opencode.js` and `codex-capture.py` pass each tool's
events to it; `capture-cli.py` is the command-line entry for other adapters. Details:
[`docs/logging.md`](../docs/logging.md).

## `doctor.py` — environment and data health check

Read-only checks of the data root (`SP_DATA_ROOT`, `SCAN_DATA_ROOT` or
`DATA_ROOT`, else the repo's `fixtures/`) and the build environment. Prints an
OK/WARN/ERROR report. The server has a newer check at `GET /api/doctor` (also on
the Internals page); this one also checks the machine.

```bash
python3 scripts/doctor.py
python3 scripts/doctor.py --root /path/to/data --json
```

## `demo/` — the example project and the demo dataset

A month of work played on a fake clock, through the product's own code.
`build_example.py` plays one project, shopfront, into a data root with the
dates ending yesterday: the example project a new install starts with, and
what the tour walks and photographs (the server runs it; `backend/backend/example.py`).
`build_demo.py` plays three projects into a folder you name, for screenshots.
Details: [`demo/README.md`](demo/README.md).

## `backup.py` — the archives behind `/api/backup*`

Makes, rotates, checks and restores `.tar.gz` archives of a data root.
The Backups page uses it through the API; it also runs on its own.
`SP_BACKUP_ROOT` says where the archives go (default: a sibling of
the data root).

## `check_api_doc.py` — is `docs/api.md` still true?

Compares every route the server publishes against the paths the API
reference names, both ways. Prints the line that goes at the bottom of
`docs/api.md`. Exit 1 when something is missing or stale.

```bash
backend/.venv/bin/python scripts/check_api_doc.py
```

## `bench_rebuild.py` — DuckDB rebuild timings

Measures how long rebuilding the tables takes for a data root. Its published
numbers date from the August 2026 data model; re-measure before quoting
them.

## `check-no-raw-hex.sh` — the colour guard

Fails when a raw hex colour appears outside `tokens.css`. It runs only by hand.
