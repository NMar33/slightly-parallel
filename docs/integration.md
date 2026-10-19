# Integrating a project

Five steps from clone to recorded chats. The first is in a terminal ([running.md](running.md)); the rest are on the **Setup** page in the browser:

1. **Run it** ([running.md](running.md)). The first start makes the data folder
   `~/.slightly-parallel` and plays the **example project** into it in about a
   minute: shopfront, a month of work on a small online store with the dates
   ending yesterday. Its chats show the commands the operator typed, and its
   scans, standups and decisions say which message they came from. Hide it
   from the sidebar; Settings › Example project brings it back.
2. **Pick a data folder** (optional) — Setup › Data folder: select another folder.
   It applies at once and is saved to `.env`.
3. **Integrate a project** — Setup › Integrate a project: the project code and the folder
   where its code is. Slightly Parallel writes a section into that project's
   `AGENTS.md` (and a line into `CLAUDE.md`), the capture hooks and the MCP
   server entry (`.mcp.json`). It shows the files before writing them, and
   marks a project whose section is out of date.
4. **Start an agent** in that project folder: Claude Code, Codex, OpenCode
   or Cursor. The agent reads the contract from the section, the hooks record
   its chat word for word (Cursor through its own hooks in
   `.cursor/hooks.json`), and it writes scans, standups and decisions
   through the MCP tools. Other tools that read `AGENTS.md` follow the
   contract without a recorded chat until an adapter exists
   ([logging.md](logging.md)). Every path in the section is absolute.
5. **Read the pages.** They update as the chat goes on.

## What Setup writes

There is one agent contract, [`SLIGHTLY-PARALLEL.md`](SLIGHTLY-PARALLEL.md)
in this folder. Projects point at it rather than copy it, so `git pull` here
updates the contract for every project. Setup writes a fenced
`<!-- slightly-parallel:begin … end -->` section into the project's `AGENTS.md` (the
cross-tool agent instructions standard, read natively by Codex, OpenCode,
Cursor, Gemini CLI, and others), the `@AGENTS.md` bridge line into
`CLAUDE.md` for Claude Code, the capture hooks into
`.claude/settings.local.json`, and the MCP server entry into `.mcp.json`
(with the Cursor hooks, also into `.cursor/mcp.json`, the file Cursor reads).
The same call without a browser:

```bash
curl -s -X POST http://127.0.0.1:8123/api/setup/integrate \
  -H 'Content-Type: application/json' \
  -d '{"project_code":"my-app","project_dir":"/abs/path/to/my-app"}'
```

Start the agent **in that folder**: hooks are set per folder. The first
turn prints `[slightly-parallel] project my-app · your agent_id is … · now …`; that
line shows the chat is being recorded. Git is optional in a project: with it,
scans list the commits and count the lines.

Every new chat in that folder, in any tool, reads the contract
from the section. The contract covers the commands (`#scan`, `#architecture`,
`#map`, `#task`, `#now`, `#decision`, `#standup`, `#evidence`, `#done`, `#help` and the kept tags),
when to write which entry, and what each entry holds. Procedures live in
built-in skills: `make-a-scan`, `keep-the-architecture-page`,
`map-the-program`, `update-the-architecture`, `daily-standup`,
`log-a-decision`, `write-a-task`, `task-evidence`, `make-an-artifact`,
`finish-a-task`, `undo-a-mistake`, `sp-help`.
Slightly Parallel installs them into `~/.claude/skills` and `~/.agents/skills`, once, for all projects.

Details: [`logging.md`](logging.md) for how chats are recorded,
[`api.md`](api.md) for the HTTP API and the MCP tools, interactive
API docs at `http://127.0.0.1:8123/docs`, and the in-app **Guide** page for
what each page is and what an entry holds.
