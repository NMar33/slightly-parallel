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
# SP_LOCAL=1: run from the repository this script sits in (a CI checkout), no
# clone. CI or SP_NONINTERACTIVE: no login prompts; the keys come from
# ANTHROPIC_API_KEY and OPENAI_API_KEY.
$Local = [bool]$env:SP_LOCAL
if ($Local) { $Dest = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$Quiet = [bool]($env:SP_NONINTERACTIVE -or $env:CI)
function Say($text) { Write-Host "`n[sp] $text" -ForegroundColor Cyan }
# What an install added to the system and user PATH, kept with what this
# session already had (a runner's tool folders are in neither).
function Refresh-Path {
  $all = @($env:Path -split ";") + @([Environment]::GetEnvironmentVariable("Path", "Machine") -split ";") +
         @([Environment]::GetEnvironmentVariable("Path", "User") -split ";")
  $env:Path = (($all | Where-Object { $_ }) | Select-Object -Unique) -join ";"
}
# A native command's failure stops the script: ErrorActionPreference does not
# turn a non-zero exit into an error. The npm-installed tools are called by
# their .cmd: their .ps1 may be refused by the execution policy.
function Must($what) {
  if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

# What is already there is left as it is; the rest comes from winget.
$need = @()
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { $need += "Git.Git" }
# Asked through cmd: in Windows PowerShell a native command's stderr under
# ErrorActionPreference Stop is an error of its own.
cmd /c "py -3.14 -c ""import sys"" >nul 2>nul"; if ($LASTEXITCODE -ne 0) { $need += "Python.Python.3.14" }
$nodeMajor = 0
if (Get-Command node -ErrorAction SilentlyContinue) { $nodeMajor = [int]((node --version) -replace '^v(\d+).*', '$1') }
if ($nodeMajor -lt 20) { $need += "OpenJS.NodeJS.LTS" }
if ($need.Count -and -not (Get-Command winget -ErrorAction SilentlyContinue)) {
  throw "winget is missing (needed for: $($need -join ', ')): install 'App Installer' from the Microsoft Store, then run this again"
}
foreach ($id in $need) {
  Say "winget: $id"
  winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements | Out-Host
  # 0, or "already installed" (-1978335189): both leave it there.
  if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { throw "winget install $id failed (exit code $LASTEXITCODE)" }
}
Refresh-Path
cmd /c "py -3.14 -c ""import sys"" >nul 2>nul"; Must "Python 3.14 (py -3.14)"
git --version | Out-Null; Must "git"
npm.cmd --version | Out-Null; Must "npm"

Say "Claude Code, Codex and OpenCode"
npm.cmd install -g --silent @anthropic-ai/claude-code @openai/codex opencode-ai | Out-Host; Must "npm install of the agents"
Refresh-Path

if ($Quiet) {
  Say "No login prompts: the keys come from the environment"
  if ($env:OPENAI_API_KEY -and -not (Test-Path (Join-Path $HOME ".codex\auth.json"))) { $env:OPENAI_API_KEY | codex.cmd login --with-api-key; Must "codex login" }
} else {
Say "Log in to each agent now - the only step that needs you"
if (-not (Test-Path (Join-Path $HOME ".claude\.credentials.json"))) {
  Write-Host "Claude Code opens: log in (/login if it asks), then leave with /exit."
  claude.cmd
}
if (-not (Test-Path (Join-Path $HOME ".codex\auth.json"))) {
  Write-Host "Codex: log in."
  codex.cmd login
}
if (-not (Test-Path (Join-Path $HOME ".local\share\opencode\auth.json"))) {
  Write-Host "OpenCode: pick Anthropic and log in (the run uses OpenCode on Claude Haiku)."
  opencode.cmd auth login
}
}

if ($Local) { }
elseif (Test-Path (Join-Path $Dest ".git")) { git -C $Dest pull --ff-only --quiet; Must "git pull" } else { git clone --quiet $RepoUrl $Dest; Must "git clone" }
if (-not (git config --global user.email)) { git config --global user.email "machine-test@example.com" }
if (-not (git config --global user.name)) { git config --global user.name "Machine Test" }

Say "Running everything (about an hour). Leave it be."
Set-Location $Dest
py -3.14 scripts\machine\run.py @args
exit $LASTEXITCODE
