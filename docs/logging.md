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
  | Claude Code | `.claude/settings.local.json` hooks: `UserPromptSubmit` + `Stop`, and `SessionEnd` + `StopFailure`, which only record the tokens read so far (no turn closes); the `statusLine` beside them reads the plan limits. A reply after the tool woke the agent itself (a helper's report, a background task's notice: no prompt event comes for those) goes on the operator's last turn, after the answer already there | both sides, verbatim, live signals |
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
  a command (`#scan`, `#task`, `#now`, `#evidence`, `#done`, …) with the skill and
  the first tool.

Thresholds live in Settings (the Agent signals and Chats groups) and persist
in `settings.json` at the data root, which the capture core reads directly.

## Helper chats

A run another program started is recorded as a chat of its own and marked a
helper in its `meta.json`: a `codex exec`, a Codex subagent, a `claude -p`,
an `opencode run`. No command in its messages acts (no `#task`, `#now`,
`#done`, `#entrypoint`, `#usage`, …, no kept entry, no notice that asks for
work); the messages are kept whole. The operator's own chats are unchanged:
a tag anywhere in the message acts, pasted text included.

```json
{"helper": true, "helper_kind": "codex-exec", "helper_of": "cc-ca77654e", "helper_of_by": "env"}
```

- `helper_kind` — `codex-exec` (the session file's first line: `source:
  "exec"`, `originator: "codex_exec"`), `codex-subagent` (`source:
  {"subagent": …}`), `claude-print` (Claude Code's `entrypoint` `sdk-cli`,
  read from the hook's `CLAUDE_CODE_ENTRYPOINT`, else the transcript),
  `opencode-run` (the plugin runs inside `opencode run`).
- `helper_of` — the chat that started it, "" when not known. Codex's
  subagents name their parent thread in the first line (`helper_of_by:
  "session"`). Any other helper inherits its parent's environment, which
  neither tool filters for its hooks (`helper_of_by: "env"`): Claude Code
  sets `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID` for what it starts, Codex
  sets `CODEX_THREAD_ID` for its shell commands. A `claude -p` replaces
  `CLAUDE_CODE_SESSION_ID` with its own; its parent is the chat whose Claude
  Code process (the breadcrumb's `tool_pid`, checked against the process's
  start time, `tool_started`) is among the hook's ancestors. Two candidates:
  the one started last; a candidate whose time is not known beside another:
  none. Chats recorded before the hooks marked helpers are marked once at
  the server's start from the tools' own logs (`helper_backfill` in
  `meta.json`; [`helperbackfill.py`](../backend/backend/helperbackfill.py)),
  where `helper_of_by: "time"` is a parent found by folder and time.
- `CLAUDE_EFFORT` in a hook's environment is the parent Claude Code's when
  the hook runs under Codex or OpenCode; the effort is read from the logs
  (below), never from it.

## The reasoning effort of each reply

Each line of a chat's `usage.jsonl` carries `effort`: the reasoning effort
the reply ran with, "" when the tool's log does not say. One of `none`,
`minimal`, `low`, `medium`, `high`, `xhigh`, `max`; any other word is "".

| Tool | Where it is read | Changes within a chat |
|---|---|---|
| Claude Code | `effort` on each assistant record of the transcript (a model without effort levels writes none) | yes: `/effort` (and a model switch) applies from the next reply; checked with Claude Code 2.1.322 (`high` → `/effort low` → `low` → `/effort max` → `max`) |
| Codex | `effort` of the session file's `turn_context` in force (else its `collaboration_mode.settings.reasoning_effort`) | per turn: `-c model_reasoning_effort=…`, the picker in the TUI |
| OpenCode | the assistant message's `variant` (else its prompt's `model.variant`), passed by the plugin | per message: `--variant high`, the picker |

The hook's `CLAUDE_EFFORT` is not read: Claude Code sets it at the `Stop`
event to the effort in force, but at `UserPromptSubmit` it read `medium`
whatever the level, and a hook under Codex or OpenCode sees its parent
Claude Code's. Claude Code's `facts.jsonl` line carries the turn's
`effort` too: the last reply's of the main agent. Lines written before
2026-11-11 have none. The Usage page splits each model's tokens by effort
under the model's name in the by-model table, only when a reply named one.

## Facts for analysis

For Claude Code, the `Stop` hook adds one line per turn to `facts.jsonl` in the
chat's folder, beside `chat.md`: what the chat's context grew by since the last
`Stop`, so a month of them shows where the tokens go.

```json
{"turn": 12, "at": "2026-11-10T15:31:40",
 "appended": {"operator": 210, "notices": 1840, "agent_text": 960, "agent_tool_calls": 3100,
              "thinking": 0, "result_Read": 41200, "result_Bash": 5300, "result_MCP": 800, "images": 1},
 "tools": {"Read": 6, "Bash": 3, "mcp__slightly-parallel__tasks": 1},
 "warnings": ["context"], "effort": "high"}
```

- `appended` — characters by kind; a kind with nothing is left out.
  `operator` is what the person typed; `notices` what the tool added for the
  model (system reminders, a prompt hook's output, a helper's report, a
  compaction summary); `agent_text`, `agent_tool_calls` (each call's input as
  JSON) and `thinking` are the agent's (Claude Code often keeps thinking empty
  in its log, so it is mostly 0); `result_<tool>` are tool results, by the tool
  that asked: `Read`, `Bash`, `Grep`, `Glob`, `Edit`, `Write`, `Agent`,
  `WebFetch`, `WebSearch`, `MCP` (every `mcp__*` tool) and `other`. `images`
  is a count, not characters.
- `tools` — the tool calls by their full name.
- `warnings` — the usage warnings shown under the reply (`compact`,
  `context`, `rebuild`, `window`; [`usagewarn.py`](../backend/backend/usagewarn.py)).
- `effort` — the reasoning effort of the turn's last reply of the main
  agent, "" when the transcript does not say (see above).

The hook counts while it reads the transcript from where the previous `Stop`
stopped, so the transcript is never read whole. A `Stop` that adds nothing
writes no line. The file is never pruned: a line is about 300 bytes, a few
hundred kilobytes for a long chat.

## Usage files at the data root

Besides each chat's `usage.jsonl`, the server and the hooks keep these in
`<data root>/.usage/`:

- `units.json` — what one dollar at API prices takes of Claude Code's
  5-hour limit, per model, as the Usage page measured it over the last 30
  days ([`usageanalysis.py`](../backend/backend/usageanalysis.py)):

  ```json
  {"at": "2026-11-10T15:31:40", "days": 30,
   "models": {"claude-opus-5-5": 0.62, "claude-fable-5-1": 2.4}, "fallback": 0.7}
  ```

  `fallback` is the rate of every window, for a model with none of its own
  (null when nothing was measured). The server writes it each time it builds
  the page's analysis, only when it changed, through a temp file it deletes
  on a failure; Claude Code's `Stop` hook reads it for the percent in its
  warnings. Without it the warnings name tokens only.
- `insights.json` — the Usage page's feed of insights
  ([`usageinsights.py`](../backend/backend/usageinsights.py)):

  ```json
  {"day": "2026-11-10",
   "items": [{"id": "in_1a2b3c4d", "at": "2026-11-10T09:00:00", "kind": "resume", "key": "",
              "params": {"each": 3.9, "n": 16, "total": 63, "ctx": 450000},
              "pinned": false, "hidden_at": ""}]}
  ```

  `day` is the day the last messages were written; a message keeps the
  numbers it was written with, the page holds the words. Hidden messages
  stay in the file with `hidden_at`. The server writes it under a file lock
  through a temp file; a file it cannot read is never written over (the
  feed shows nothing until it is fixed or removed). It is never pruned.
- `api-prices.jsonl` (the price updates, appended), `limits.jsonl` (the plan
  limits' readings), `codex-poll.json` and `codex-account.json` (the
  background reading of Codex's limits) and `sessions/` (each open Claude
  Code chat's status line) are described with their routes in
  [api.md](api.md).

## Guarantees

- **The tool keeps working** — every adapter catches every error. When
  Slightly Parallel is down, the coding session goes on and the turn is missing.
- **Installs can be repeated** — Setup shows the files before writing, merges
  into existing files, and Disconnect removes what it installed.
- **One writer** — every adapter writes through the capture core, so a chat
  looks the same whichever tool it came from.
