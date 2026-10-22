# Slightly Parallel on a real machine

One command on a blank machine: it installs what Slightly Parallel and the
agents need, asks you to log in to Claude Code, Codex and OpenCode, then
does what a new user does and checks every step. At the end there is one
archive to send back for review.

Use a virtual machine. The run installs tools for its user, turns start at
login and the desktop shortcut on and off, and writes a data folder in the
home folder: on your own computer that is clutter at best.

## The machine

| System | A blank one |
|---|---|
| Windows 11 | the free evaluation image (Microsoft's "Windows 11 Enterprise evaluation"), in VirtualBox, Hyper-V or VMware; 4 CPUs, 8 GB, 60 GB |
| Ubuntu 24.04 | the desktop image, in VirtualBox or virt-manager |
| macOS | on a Mac only: UTM with a macOS image |

## The command

Linux and macOS, in a terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/NMar33/slightly-parallel/main/scripts/machine/bootstrap.sh | bash
```

Windows, in PowerShell:

```powershell
irm https://raw.githubusercontent.com/NMar33/slightly-parallel/main/scripts/machine/bootstrap.ps1 | iex
```

You do one thing: log in when each agent opens (Claude Code: `/login`, then
`/exit`; Codex and OpenCode ask in the terminal). Then it runs for about an
hour. On a machine that already has the tools, `python scripts/machine/run.py`
from the repository folder does the run alone.

## What it checks

1. The fresh-user test (`scripts/fresh_user`) with all three agents: from a
   clone to Setup, the hooks, MCP, and a real agent building a small notes
   page with `#now`, then `#task`, the tests, `#scan`, `#sp` and `#done`.
2. This machine's own start: `sp up`, the monitor reading this machine, the
   top bar, `#sp` and the report, `sp down`, `sp check` with the server down,
   start at login and the shortcut for real.

## What comes out

`sp-machine-<computer>-<date>.zip` beside the repository folder:

- `run/steps.json` — every step, passed or not, with its log;
- `run/versions.json` — the system and every tool's version;
- `fresh-user/report.json`, `fresh-user/screens/` — every check, the pages as they looked;
- `built/` — the page the agents made;
- `report/` — `sp.py report` from this machine.

No login is in it: the agents' logins are copied into the test's own folder
and removed with it, and files named like a login are left out.
