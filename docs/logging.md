# How chats are recorded

Slightly Parallel records the chat of every integrated agent word for word:
each user message and each final answer. Sessions, hours, heatmaps and quiet
projects are computed from their timestamps. Hooks in each tool do the writing,
so the model spends no tokens on it and cannot skip it.

## Architecture

```
tool event ──► adapter (scripts/hooks/…) ──► capture core ──► chat.md
                                                            meta.json
```

- **Capture core** — [`scripts/hooks/capture.py`](../scripts/hooks/capture.py),
  stdlib-only. Two-phase (`open_turn` on the user message, `complete_turn`
  on the answer) or one-shot (`full_turn`). Writes multiline verbatim turns:

  ```markdown
  ## Turn 12 · 2026-08-14T10:15:03
  **User**: the literal message…
  **Agent**: the literal final answer…
  ```

- **Adapters** — one small script per tool, all installed from the Setup page:

  | Tool | Mechanism | Fidelity |
  |---|---|---|
  | Claude Code | `.claude/settings.local.json` hooks: `UserPromptSubmit` + `Stop` | both sides, verbatim, live signals |
  | OpenCode | `.opencode/plugin/slightly-parallel.js` (installed from `scripts/hooks/slightly-parallel-opencode.js`) — the `chat.message` hook for the prompt, `session.idle` + a messages fetch for the reply | both sides, verbatim |
  | Codex CLI | `.codex/hooks.json` per project (`UserPromptSubmit` + `Stop`, the same script as Claude Code with `--tool codex`); or the legacy global `notify` in `~/.codex/config.toml`, project resolved from the event's cwd via `integrations.csv` | both sides, verbatim |
  | Cursor | `.cursor/hooks.json` per project (schema version 1; [Cursor's hooks](https://cursor.com/docs/agent/hooks)): `beforeSubmitPrompt` (the `prompt`) + `afterAgentResponse` (the `text`) + `stop` (closes a turn whose reply never came), all three running `scripts/hooks/cursor-capture.py`, which answers the JSON Cursor reads and never blocks a prompt; the agent is keyed by `conversation_id`, and a user-level install resolves the project from `workspace_roots` via `integrations.csv`; the MCP server entry goes into `.cursor/mcp.json` beside it | both sides, verbatim |

  Another tool can be recorded with an adapter of about 50 lines that calls
  [`scripts/hooks/capture-cli.py`](../scripts/hooks/capture-cli.py).

## Operator signals

The hook also adds `[slightly-parallel]` notices to the agent's context. Tools
that take hook output as context (Claude Code's `UserPromptSubmit`) get them at
once:

- **identity** — the first turn: `[slightly-parallel] project … · your agent_id is …`.
  It shows the chat is being recorded.
- **standup due** — the first turn of a new day when yesterday has no standup:
  the agent asks the operator to write it now or later.
- **decision hint** — a message contains a decision phrase: the agent offers
  to log the decision.
- **contract refresh** — every 25 turns by default (Settings › Agent signals,
  `agent.contract_refresh_turns`) the agent re-reads `SLIGHTLY-PARALLEL.md`
  and the rules in the project's AGENTS.md.
- **files / architecture due** — the latest scan has no file entry or
  architecture form: the agent is reminded once.
- **kept messages and commands** — a tag (`#vision`, `#rule`, `#problem`,
  `#skill`, `#artifact`) arrives with the kept entry's id to interpret;
  a command (`#scan`, `#task`, `#evidence`, `#done`, …) with the skill and
  the first tool.

Thresholds live in Settings (the Agent signals and Chats groups) and persist
in `settings.json` at the data root, which the capture core reads directly.

## Guarantees

- **The tool keeps working** — every adapter catches every error. When
  Slightly Parallel is down, the coding session goes on and the turn is missing.
- **Installs can be repeated** — Setup shows the files before writing, merges
  into existing files, and Disconnect removes what it installed.
- **One writer** — every adapter writes through the capture core, so a chat
  looks the same whichever tool it came from.
