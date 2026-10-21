# The fresh-user test

Slightly Parallel from `git clone` to an agent at work, checked at every step. It
answers one question: can someone who found the repository install it,
set it up, and have an agent's work appear on the pages.

```bash
python3 scripts/fresh_user/run.py                  # everything; Claude Code on sonnet
python3 scripts/fresh_user/run.py --no-agent       # the stages that cost nothing (~6 min)
python3 scripts/fresh_user/run.py --scenario core  # 8 messages instead of 21
python3 scripts/fresh_user/run.py --agent-runs 3   # the chat three times: how steady is it
python3 scripts/fresh_user/run.py --tools claude-code,codex,opencode
python3 scripts/fresh_user/run.py --model haiku --keep
scripts/fresh_user/docker.sh                       # --no-agent on a clean machine, in a container
```

It needs what the product needs (Python 3.11+, Node, git), tmux for the
terminal stage, and Playwright in this repository for the browser stages:
`cd frontend && npm install && npx playwright install chromium`.

## What it does

Everything happens in one temporary folder, on a free port:

| in the folder | what it is |
|---|---|
| `home/` | a home folder that has never seen Slightly Parallel |
| `slightly-parallel/` | a clone of this repository's **last commit** |
| `data/` | the empty data folder Setup is pointed at |
| `sample/`, `notes/` | the user's projects: small git repositories |

| stage | what it checks |
|---|---|
| **install** | `git clone`, then `./run.sh --prod`: the environment and the UI are built, the server answers, healthy, on the shipped demo data. No committed file names a folder of the machine it was committed on. |
| **readme** | the README against the clone: every file it links, script it tells you to run, launcher command, npm script, skill and setting it names exists; the prerequisites come before the first command. |
| **pages** | every route of the app opens without a crash. |
| **setup** | the Setup page in a browser: the data folder, then the project. Then the files Setup wrote are read: `.env`, `AGENTS.md`, `CLAUDE.md`, the hooks, `.mcp.json`, the built-in skills in the home folder. Installing and setting up change no file of the repository. A second project is integrated through the API. |
| **wiring** | no agent: the hook is run with a message and a reply and the chat appears; the MCP server is started from `.mcp.json`, lists its tools and writes a decision; a write that skips MCP is refused. |
| **agent** | a real agent, headless, in `sample/`. After each message the result is read through the API; at the end a browser looks for the work on the pages. |
| **parallel** | agents at the same time: one in each of two projects, then two in one folder. |
| **terminal** | Slightly Parallel's own terminal: a shell runs a command; Resume opens in the folder the chat started in, with the chat's own tool and session; Start on a task carries the task. The commands are typed and not run, so nothing is spent. |
| **failures** | what a new user can get wrong or lack, each ending in words that say what to do: a port in use, no Node, no tmux, a project folder that does not exist / is relative / is a file, a bad project code, a data folder that is missing or read-only. And names with spaces and non-Latin letters, from the data folder to a written entry. |
| **disconnect** | Setup's Disconnect in a browser: the project's folder is as it was before Setup, and its data is kept. |
| **restart** | stop, start again: the chosen data folder, the projects and the agents are all there. |
| **background** | `sp up`, `status`, `down`: it starts, a second `up` refuses, `down` leaves nothing on the port. |
| **volume** | a month of work on three projects (the demo builder), one chat of 1,500 turns and 400 more tasks: the server starts, a write does not slow down as the data grows, the main reads answer within 2 s, every page opens, and the heavy pages show their content within 6 s. |
| **upgrade** | an earlier commit is installed, set up and used; then `git pull` and a restart: the data folder, the project, the chat and the task are still there, the old project's hook still captures, every page opens. `--upgrade-from <commit>` names the start (default: the newest `v*` tag, else 5 commits back). |
| **dev** | `./run.sh` with no flag, on its own ports: the hot-reload UI answers and shows this server's data. |

Pictures of the pages are saved at three moments (first start, after
Setup, after the agent) for a person to look at.

### The agent's chat

`--scenario core`: a plain request, `#task`, `#decision`, `#rule`, the
work, `#scan`, `#done`.

`--scenario full` (the default) first puts a chat on yesterday's date, so
today's first message owes a standup. Then: hello (the agent asks about
the standup), the answer, and the core steps with `#vision`, `#problem`,
`#evidence`, `#important`, `#architecture`, `#map` (and the answer
"now"), `#artifact`, `#skill`, `#problem solved` and `#help` between them.

The first stages are deterministic. The agent stages are not: they cost
tokens, take minutes, and an agent may word or order things its own way.
Their checks are about structure — an entry exists, on the right project,
by the right agent — and the ones that depend on the agent's own choices
are **soft**: reported, not failing. `--agent-runs N` repeats the chat in
new projects and lists the checks that did not hold every time.

## What it touches

Nothing of yours, with one exception. An agent must be logged in, and the
temporary home is empty. The runner gives it a login from an environment
variable if one is set (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`,
`OPENAI_API_KEY`); otherwise it **copies the tool's login file** (for
Claude Code, `~/.claude/.credentials.json`) into the temporary home, and
deletes the copy at the end, also with `--keep`. On macOS Claude Code
keeps its login in the keychain, so set `CLAUDE_CODE_OAUTH_TOKEN` (from
`claude setup-token`) there.

## The tools

| tool | state |
|---|---|
| Claude Code | run and checked |
| Codex | written from its documented commands (`codex exec`, `codex exec resume --last`); not run by the author. |
| OpenCode | written from its documented commands (`opencode run`, `--continue`); not run by the author. |

A tool that is not installed is skipped. The first run with Codex or
OpenCode is also the test of its adapter in `agents.py`.

## The clean machine

`docker.sh` runs `--no-agent` in Playwright's container image (Ubuntu
24.04 with Node and Python). The repository is mounted read-only and
cloned inside; `git`, `python3-venv` and `tmux` are installed on top.
Its report and pictures land in `.sp/fresh-user-docker/`.

Before that it starts Slightly Parallel on two machines that lack something — one
with no `venv` module, one with Python 3.9 — and checks that each start
ends in one line that says what is missing.

## What is not tested

- Windows (`sp.cmd`): the runner uses the shell scripts.
- Cloning from a remote URL: the clone is of this folder's last commit.
- The map helper of the standup (answer 1); `#map` itself is tested.
- Two chats in one folder on Windows: they are told apart by their
  processes, which is read on Linux and macOS only.
- What an interactive agent shows in the terminal: Resume and Start are
  checked up to the command that would run.

## Reading the result

The run prints each check as it goes and ends with a table by stage. The
same is written to `.sp/fresh-user/report.json`, and the pictures to
`.sp/fresh-user/screens/`. With `--keep` the folder stays:
`server.log`, the Playwright logs and each agent turn
(`calc-claude-code-turn-01.txt` …) are in it.
