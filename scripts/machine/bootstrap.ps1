# Slightly Parallel on a blank Windows machine (a virtual machine is the
# intended place): installs what it needs, asks you to log in to the three
# agents, then runs scripts\machine\run.py and leaves one archive to send.
#
#   irm https://raw.githubusercontent.com/NMar33/slightly-parallel/main/scripts/machine/bootstrap.ps1 | iex
#
# Installs with winget, for this user where it can: Git, Python 3.14 (with
# the py launcher), Node.js LTS; then Claude Code, Codex and OpenCode with
# npm -g. What is there already is left as it is.
$ErrorActionPreference = "Stop"
$RepoUrl = if ($env:SP_REPO_URL) { $env:SP_REPO_URL } else { "https://github.com/NMar33/slightly-parallel.git" }
$Dest = if ($env:SP_DEST) { $env:SP_DEST } else { Join-Path $HOME "slightly-parallel" }
function Say($text) { Write-Host "`n[sp] $text" -ForegroundColor Cyan }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  throw "winget is missing: install 'App Installer' from the Microsoft Store, then run this again"
}
foreach ($id in @("Git.Git", "Python.Python.3.14", "OpenJS.NodeJS.LTS")) {
  Say "winget: $id"
  winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements | Out-Host
}
Refresh-Path

Say "Claude Code, Codex and OpenCode"
npm install -g --silent @anthropic-ai/claude-code @openai/codex opencode-ai | Out-Host
Refresh-Path

Say "Log in to each agent now - the only step that needs you"
if (-not (Test-Path (Join-Path $HOME ".claude\.credentials.json"))) {
  Write-Host "Claude Code opens: log in (/login if it asks), then leave with /exit."
  claude
}
if (-not (Test-Path (Join-Path $HOME ".codex\auth.json"))) {
  Write-Host "Codex: log in."
  codex login
}
if (-not (Test-Path (Join-Path $HOME ".local\share\opencode\auth.json"))) {
  Write-Host "OpenCode: pick Anthropic (or OpenAI) and log in."
  opencode auth login
}

if (Test-Path (Join-Path $Dest ".git")) { git -C $Dest pull --ff-only --quiet } else { git clone --quiet $RepoUrl $Dest }
if (-not (git config --global user.email)) { git config --global user.email "machine-test@example.com" }
if (-not (git config --global user.name)) { git config --global user.name "Machine Test" }

Say "Running everything (about an hour). Leave it be."
Set-Location $Dest
py -3.14 scripts\machine\run.py @args
