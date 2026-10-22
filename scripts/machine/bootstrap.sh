#!/usr/bin/env bash
# Slightly Parallel on a blank Linux or macOS machine (a virtual machine is
# the intended place): installs what it needs, asks you to log in to the
# three agents, then runs scripts/machine/run.py and leaves one archive to send.
#
#   curl -fsSL https://raw.githubusercontent.com/NMar33/slightly-parallel/main/scripts/machine/bootstrap.sh | bash
#
# Installs, for this user: uv and Python 3.14 (~/.local/bin), Node 22 (nvm),
# Claude Code, Codex and OpenCode (npm -g); with the system's package manager:
# git, tmux, curl (Linux asks for sudo; macOS uses Homebrew, installing it
# when missing). What is there already is left as it is.
set -euo pipefail

REPO_URL="${SP_REPO_URL:-https://github.com/NMar33/slightly-parallel.git}"
DEST="${SP_DEST:-$HOME/slightly-parallel}"
# SP_LOCAL=1: run from the repository this script sits in (a CI checkout),
# no clone. CI or SP_NONINTERACTIVE: no login prompts — the keys come from
# ANTHROPIC_API_KEY and OPENAI_API_KEY.
if [[ -n ${SP_LOCAL:-} ]]; then DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; fi
QUIET="${SP_NONINTERACTIVE:-${CI:-}}"
say() { printf '\n\033[1m[sp] %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- system
if [[ $(uname) == Darwin ]]; then
  if ! command -v brew >/dev/null; then
    say "Homebrew is missing: installing it (it asks for your password)"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
  fi
  brew list git >/dev/null 2>&1 || brew install git
  brew list tmux >/dev/null 2>&1 || brew install tmux
else
  say "git, tmux and curl (sudo)"
  if command -v apt-get >/dev/null; then sudo apt-get update -qq && sudo apt-get install -y -qq git tmux curl ca-certificates
  elif command -v dnf >/dev/null; then sudo dnf install -y -q git tmux curl
  elif command -v pacman >/dev/null; then sudo pacman -S --noconfirm --needed git tmux curl
  else echo "[sp] install git, tmux and curl with your package manager, then run this again" >&2; exit 1; fi
fi

# ---------------------------------------------------------------- Python 3.14
if ! command -v uv >/dev/null; then
  say "uv (it installs Python)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
say "Python 3.14"
uv python install 3.14
PY="$(uv python find 3.14)"
mkdir -p "$HOME/.local/bin" && ln -sf "$PY" "$HOME/.local/bin/python3.14"

# ---------------------------------------------------------------- Node
export NVM_DIR="$HOME/.nvm"
if [[ ! -s $NVM_DIR/nvm.sh ]]; then
  say "nvm (it installs Node)"
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
fi
# shellcheck disable=SC1091
. "$NVM_DIR/nvm.sh"
say "Node 22"
nvm install 22 >/dev/null && nvm use 22 >/dev/null

# ---------------------------------------------------------------- the agents
say "Claude Code, Codex and OpenCode"
npm install -g --silent @anthropic-ai/claude-code @openai/codex opencode-ai

if [[ -n $QUIET ]]; then
  say "No login prompts: the keys come from the environment"
  if [[ -n ${OPENAI_API_KEY:-} && ! -f $HOME/.codex/auth.json ]]; then printenv OPENAI_API_KEY | codex login --with-api-key || true; fi
else
say "Log in to each agent now — the only step that needs you"
if [[ ! -f $HOME/.claude/.credentials.json ]]; then
  echo "Claude Code opens: log in (/login if it asks), then leave with /exit."
  claude </dev/tty || true
fi
if [[ ! -f $HOME/.codex/auth.json ]]; then
  echo "Codex: log in."
  codex login </dev/tty || true
fi
if [[ ! -f $HOME/.local/share/opencode/auth.json ]]; then
  echo "OpenCode: pick Anthropic and log in (the run uses OpenCode on Claude Haiku)."
  opencode auth login </dev/tty || true
fi
fi

# ---------------------------------------------------------------- the run
if [[ -n ${SP_LOCAL:-} ]]; then :
elif [[ -d $DEST/.git ]]; then git -C "$DEST" pull --ff-only --quiet; else git clone --quiet "$REPO_URL" "$DEST"; fi
git -C "$DEST" config user.email >/dev/null || git config --global user.email "machine-test@example.com"
git -C "$DEST" config user.name >/dev/null || git config --global user.name "Machine Test"
say "Running everything (about an hour). Leave it be."
cd "$DEST"
"$HOME/.local/bin/python3.14" scripts/machine/run.py "$@"
