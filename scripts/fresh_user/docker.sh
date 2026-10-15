#!/usr/bin/env bash
# The fresh-user test on a clean machine: a container that has a browser,
# Node and Python and nothing of Slightly Parallel. The repository is mounted
# read-only; inside, it is cloned, and the test runs every stage that needs
# no agent login.
#
#   scripts/fresh_user/docker.sh            # the stages that cost nothing
#   scripts/fresh_user/docker.sh --stages install,pages,setup,wiring
#
# The image is Playwright's own for the version this repository uses, on
# Ubuntu 24.04. What is installed on top is what the README asks a user to
# have: git and Python's venv module (plus tmux, for the terminal stage).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(node -e "console.log(require('$REPO/frontend/node_modules/@playwright/test/package.json').version)")"
IMAGE="mcr.microsoft.com/playwright:v${VERSION}-noble"
ARGS="${*:---no-agent}"
mkdir -p "$REPO/.sp/fresh-user-docker"

# Two machines that lack something: the first start must say what, in one line.
lacking() {  # image, the words the launcher must say
  local out
  out="$(docker run --rm -v "$REPO":/src:ro "$1" bash -c 'mkdir -p /m/backend /m/frontend && cp /src/sp.py /src/run.sh /m/ && cd /m && ./run.sh --prod' 2>&1 || true)"
  if grep -q "$2" <<<"$out" && ! grep -q Traceback <<<"$out"; then echo "  [ok  ] $3"; else echo "  [FAIL] $3 — $(tail -2 <<<"$out")"; FAILED=1; fi
}
FAILED=0
echo "machines that lack something"
lacking "$IMAGE" "sudo apt install python3-venv" "no venv module: the start says which package to install"
lacking "python:3.9-slim" "Python 3.11+ is needed" "Python 3.9: the start says which Python it needs"
[ "$FAILED" = 0 ] || exit 1
echo
docker run --rm --ipc=host \
  -v "$REPO":/src:ro \
  -v "$REPO/.sp/fresh-user-docker":/out \
  "$IMAGE" bash -c '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null && apt-get install -y -qq git python3-venv tmux >/dev/null
    echo "machine: $(. /etc/os-release; echo "$PRETTY_NAME") · python $(python3 -V | cut -d" " -f2) · node $(node -v) · git $(git --version | cut -d" " -f3)"
    chown pwuser /out
    su pwuser -c "
      set -euo pipefail
      git config --global --add safe.directory \"*\"
      git clone -q /src \$HOME/src
      cd \$HOME/src/frontend && npm ci --no-audit --no-fund >/dev/null 2>&1
      cd \$HOME/src && code=0; python3 scripts/fresh_user/run.py '"$ARGS"' || code=\$?
      cp -r .sp/fresh-user/. /out/ 2>/dev/null || true
      exit \$code
    "
  '
