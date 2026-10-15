![Slightly Parallel](brand/kit/files/readme-banner.svg)

# Slightly Parallel

**A dashboard for coding agents. Open source, MIT; runs on your own computer.**

You work with coding agents in several repositories, maybe in several tools at once: Claude Code in one, Codex or Cursor in another. Each chat ends and its content is gone; nothing connects one project to the next.

Slightly Parallel records every one of those chats into one record and shows all your projects on one page. You write rules for the agents, visions of where a project is going, and skills, which are procedures an agent follows; what you wrote in one project can be installed into any other, so a new chat there starts with the same knowledge. For managing a project there is a Kanban board, with sprints, milestones, a calendar and your own hours; a task on the board can be handed to an agent, and its report comes back to the card.

▶ [Slightly Parallel in a minute](https://youtu.be/NmtQgkg-D-E) (0:58) · [How Slightly Parallel works](https://youtu.be/eZ0_f1sKaLE), every page in 6:42

## How you use it

You start an agent in a project folder, as you do now. A hook records the chat as it goes, and the chat appears on the Chats page with the agent's name and the files it touched.

Inside the chat you type commands. `#task fix the login timeout` puts a task on the board. `#decision` logs the choice you just made, with the reasons and what was turned down. `#scan` writes a checkpoint: what this chat changed since the last one, with the files and the architecture form. `#rule`, `#vision`, `#problem` and `#skill` keep the message on the page of that name; the agent writes what it means. The agent does the writing; you read the pages.

A task on the board can be given to an agent: the task opens in a terminal inside the app, the agent works, and its report comes back to the card with the evidence. You move the task to done; the agent cannot.

The next day, the first agent that works on a project writes yesterday's standup: what moved, what went wrong, what waits for your answer. The Overview page shows the same across all projects: what changed since your last visit and what needs a decision.

## Install

You need Python 3.11+, Node 20+ and git.

```bash
git clone https://github.com/nmar33/slightly-parallel.git
cd slightly-parallel
./run.sh --prod       # http://127.0.0.1:8123
```

The first start builds the UI and takes a minute or two. It makes the data folder `~/.slightly-parallel` and fills it with an example project, a month of work on a small online store, so every page has something on it. Both films are shot on it. Hide it from the sidebar when you no longer need it.

Then, on the **Setup** page in the app:

1. **Integrate a project**: its code and the folder where its code is. Setup writes a section into the project's `AGENTS.md` (and a line into `CLAUDE.md`), the capture hooks and the MCP server entry. It shows the files before writing them.
2. **Start an agent in that folder**: Claude Code, Codex, OpenCode or Cursor. The first answer prints `[slightly-parallel] project … · your agent_id is …`; from then on the chat is recorded.

On Windows: `sp run --prod`. To keep it running in the background: `./sp.sh up`, `status`, `logs`, `down` ([docs/running.md](docs/running.md)).

## The pages

- **Overview and Project** — all projects on one page; one page per project with its agents, board, sprints, calendar, decisions, chats, files, architecture and timer.
- **Chats, Scans, Standups, Decisions** — the record: every chat word for word, the checkpoints, one standup per project per day, the decisions with their weight.
- **Kanban, Sprints, Calendar, Timer** — the plan: the board with its history and evidence, sprints and milestones, the dates, your own hours.
- **Visions, Rules, Problems, Skills, Prompts, Artifacts** — the project's memory: what you kept from the chats, installable into other projects; your saved prompts; folders an agent wrote.
- **Architecture, Files, Search, Agents** — what the project is, as claims with their evidence; which files change and how often; search over everything; each agent with its chats and tasks.
- **Health, Monitor, Backups, Settings** — the server's state and log; CPU, memory, disk and network; copies of the data folder; language (English, Russian), appearance, the terminal switch.

## What it needs and where the data is

- One person, one computer. The server listens on `127.0.0.1` and has no login; the network is off unless you turn it on ([docs/configuration.md](docs/configuration.md)).
- The data is plain files in the folder you chose: one CSV per kind of entry, one Markdown file per entry, the chats as `chat.md`. No database server. Back it up by copying the folder, or let Backups do it.
- Agents write only through the MCP server (`write_entry`); the server refuses an agent's write that comes any other way. The contract they follow is [`SLIGHTLY-PARALLEL.md`](SLIGHTLY-PARALLEL.md).

## More

- [docs/integration.md](docs/integration.md) — what Setup writes into a project, the contract, the commands, the built-in skills, the same call without a browser.
- [docs/configuration.md](docs/configuration.md) — `.env`, the ports, the network and the terminal; what the security model is and is not.
- [docs/running.md](docs/running.md) — the launcher: `sp.sh up`, `status`, `logs`, `restart`, `down`; Windows.
- [docs/development.md](docs/development.md) — tests, the lock file, the fresh-user test.
- [docs/api.md](docs/api.md), [docs/logging.md](docs/logging.md) — the HTTP API and MCP tools; how chats are recorded.
- [AGENT-README.md](AGENT-README.md) — for an agent working on Slightly Parallel's own code.

## License

MIT — see [LICENSE](LICENSE).
