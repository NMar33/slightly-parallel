# Development

Each block starts in the repository folder.

```bash
# Backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The backend has two layers. `backend/backend/routers/` answer HTTP: they
read the request, call the libraries and shape the answer. Every other
module in `backend/backend` is a library: it does the work and never imports
a router (`tests/test_layers.py` fails the run when one does). A router's
helper that a library needs moves into a library, and the router imports it
back under its old name.

`backend/requirements.txt` holds the ranges, `backend/requirements.lock` the
exact versions the tests ran on; `sp.py` installs from the lock, once,
and again when the file changes. To refresh the lock — after a change to
`requirements.txt`, or to take newer releases — resolve it in a fresh
environment, run the tests on exactly that, and keep the result:

```bash
# Backend — refresh requirements.lock
cd backend && python3 -m venv /tmp/sp-lock
/tmp/sp-lock/bin/pip install -r requirements.txt
{ grep '^#' requirements.lock
  /tmp/sp-lock/bin/pip freeze --exclude pip --exclude setuptools --exclude wheel \
    | sed 's/^\(uvloop==.*\)$/\1 ; sys_platform != "win32"/'; } > requirements.lock.new
mv requirements.lock.new requirements.lock
/tmp/sp-lock/bin/pip install pytest httpx pyflakes pytest-xdist
/tmp/sp-lock/bin/python -m pytest
```

`pyproject.toml` lists the same ranges as `requirements.txt`: change both.

```bash
# Frontend — unit tests, typecheck, build
cd frontend && npm install
npm test && npm run typecheck && npm run build

# In the browser, on a copy of the test data. It starts its own server from
# backend/.venv and serves the build above. Once: npx playwright install chromium
npm run e2e
```

```bash
# From `git clone` to a working setup, as a new user meets it; with an
# agent login it also talks to a real agent ([scripts/fresh_user/README.md](../scripts/fresh_user/README.md))
python3 scripts/fresh_user/run.py --no-agent
```
